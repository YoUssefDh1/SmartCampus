-- =====================================================================
-- 002 - Catalogue : statut de publication, periode de validite, modalites de paiement
--       (Membre 3 - SA-20 / SA-21)
--
-- Regle metier : un candidat ou l'agent IA ne voit QUE les informations
--   * publiees        (status = 'published')
--   * valides ce jour (valid_from <= aujourd'hui <= valid_until ; NULL = borne ouverte)
--   * d'une formation active (program.is_active)
-- Cette regle est definie UNE seule fois : fonction catalog_is_official() + vues v_official_*.
-- L'API publique et l'agent IA lisent les vues, jamais les tables directement.
--
-- Workflow : draft -> published -> archived (archived -> draft pour restaurer).
-- Les periodes de validite sont des DATES (un tarif est valable "du 1er septembre au 31 aout").
-- Pas de BEGIN/COMMIT : app.db.migrate execute ce fichier dans une transaction.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 0. Recherche insensible aux accents ("genie" trouve "Génie") - extension contrib standard
-- ---------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE FUNCTION catalog_search_text(text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT lower(public.unaccent('public.unaccent'::regdictionary, coalesce($1, '')))
$$;

-- ---------------------------------------------------------------------
-- 1. Fonction unique de visibilite
-- ---------------------------------------------------------------------
CREATE FUNCTION catalog_is_official(p_status text, p_valid_from date, p_valid_until date,
                                    p_on date DEFAULT current_date)
RETURNS boolean LANGUAGE sql IMMUTABLE AS $$
  SELECT p_status = 'published'
     AND (p_valid_from  IS NULL OR p_valid_from  <= p_on)
     AND (p_valid_until IS NULL OR p_valid_until >= p_on)
$$;

-- ---------------------------------------------------------------------
-- 2. Frais de scolarite : publication + validite
-- ---------------------------------------------------------------------
ALTER TABLE tuition_fee
  ADD COLUMN status          text NOT NULL DEFAULT 'draft'
                             CHECK (status IN ('draft','published','archived')),
  ADD COLUMN valid_from      date,
  ADD COLUMN valid_until     date,
  ADD COLUMN published_at    timestamptz,
  ADD COLUMN published_by_id uuid REFERENCES app_user(id) ON DELETE SET NULL,
  ADD CONSTRAINT tuition_fee_validity_check
      CHECK (valid_until IS NULL OR valid_from IS NULL OR valid_until >= valid_from),
  ADD CONSTRAINT tuition_fee_published_check
      CHECK (status <> 'published' OR published_at IS NOT NULL);

-- Un tarif archive ne bloque plus la cle : on peut archiver l'ancien et en creer un nouveau.
DROP INDEX tuition_fee_key;
CREATE UNIQUE INDEX tuition_fee_key ON tuition_fee
  (program_id, academic_year, fee_type, coalesce(study_year, 0))
  WHERE status <> 'archived';
CREATE INDEX tuition_fee_program_status_idx ON tuition_fee (program_id, status);

-- ---------------------------------------------------------------------
-- 3. Conditions d'admission : publication + validite
-- ---------------------------------------------------------------------
ALTER TABLE admission_requirement
  ADD COLUMN status          text NOT NULL DEFAULT 'draft'
                             CHECK (status IN ('draft','published','archived')),
  ADD COLUMN valid_from      date,
  ADD COLUMN valid_until     date,
  ADD COLUMN published_at    timestamptz,
  ADD COLUMN published_by_id uuid REFERENCES app_user(id) ON DELETE SET NULL,
  ADD CONSTRAINT admission_requirement_validity_check
      CHECK (valid_until IS NULL OR valid_from IS NULL OR valid_until >= valid_from),
  ADD CONSTRAINT admission_requirement_published_check
      CHECK (status <> 'published' OR published_at IS NOT NULL);
CREATE INDEX admission_requirement_status_idx ON admission_requirement (program_id, status);

-- ---------------------------------------------------------------------
-- 4. Modalites de paiement (nouveau) : un plan par formation et par annee,
--    decoupe en echeances (tranches).
-- ---------------------------------------------------------------------
CREATE TABLE payment_plan (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  program_id       uuid NOT NULL REFERENCES program(id) ON DELETE CASCADE,
  academic_year    academic_year NOT NULL,
  name             varchar(150) NOT NULL,                  -- 'Paiement comptant', 'Paiement en 3 tranches'
  description      text,
  payment_methods  text[] NOT NULL DEFAULT '{}'
                   CHECK (payment_methods <@ ARRAY['cash','bank_transfer','check','card','online']::text[]),
  discount_percent numeric(5,2) CHECK (discount_percent BETWEEN 0 AND 100),
  currency         char(3) NOT NULL DEFAULT 'TND' CHECK (currency ~ '^[A-Z]{3}$'),
  conditions       text,                                   -- penalites de retard, pieces a fournir...
  position         smallint NOT NULL DEFAULT 0,
  status           text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','published','archived')),
  valid_from       date,
  valid_until      date,
  published_at     timestamptz,
  published_by_id  uuid REFERENCES app_user(id) ON DELETE SET NULL,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT payment_plan_validity_check
      CHECK (valid_until IS NULL OR valid_from IS NULL OR valid_until >= valid_from),
  CONSTRAINT payment_plan_published_check
      CHECK (status <> 'published' OR published_at IS NOT NULL)
);
CREATE UNIQUE INDEX payment_plan_name_key ON payment_plan (program_id, academic_year, lower(name))
  WHERE status <> 'archived';
CREATE INDEX payment_plan_program_status_idx ON payment_plan (program_id, status);
CREATE TRIGGER trg_payment_plan_updated_at BEFORE UPDATE ON payment_plan
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Echeances : soit un pourcentage du total, soit un montant fixe (au moins l'un des deux).
CREATE TABLE payment_installment (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  payment_plan_id uuid NOT NULL REFERENCES payment_plan(id) ON DELETE CASCADE,
  position        smallint NOT NULL CHECK (position >= 1),
  label           varchar(150) NOT NULL,                   -- '1re tranche'
  due_date        date,
  due_description varchar(150),                            -- 'A l''inscription', 'Avant le 15 janvier'
  percentage      numeric(5,2) CHECK (percentage > 0 AND percentage <= 100),
  amount          numeric(10,2) CHECK (amount >= 0),
  CHECK (percentage IS NOT NULL OR amount IS NOT NULL),
  UNIQUE (payment_plan_id, position)
);

-- ---------------------------------------------------------------------
-- 5. Vues "officielles" : ce que voient les candidats et l'agent IA
-- ---------------------------------------------------------------------
CREATE VIEW v_official_tuition_fee AS
SELECT f.id, f.program_id, p.code AS program_code, p.name AS program_name, i.code AS institution_code,
       f.academic_year, f.study_year, f.fee_type, f.amount, f.currency, f.description,
       f.valid_from, f.valid_until, f.published_at
FROM tuition_fee f
JOIN program p     ON p.id = f.program_id AND p.is_active
JOIN institution i ON i.id = p.institution_id
WHERE catalog_is_official(f.status, f.valid_from, f.valid_until);

CREATE VIEW v_official_admission_requirement AS
SELECT r.id, r.program_id, p.code AS program_code, p.name AS program_name, i.code AS institution_code,
       r.category, r.kind, r.description, r.min_average, r.accepted_bac_series,
       r.required_program_id, rp.name AS required_program_name,
       r.academic_year, r.is_mandatory, r.position, r.valid_from, r.valid_until, r.published_at
FROM admission_requirement r
JOIN program p       ON p.id = r.program_id AND p.is_active
JOIN institution i   ON i.id = p.institution_id
LEFT JOIN program rp ON rp.id = r.required_program_id
WHERE catalog_is_official(r.status, r.valid_from, r.valid_until);

CREATE VIEW v_official_payment_plan AS
SELECT pp.id, pp.program_id, p.code AS program_code, p.name AS program_name, i.code AS institution_code,
       pp.academic_year, pp.name, pp.description, pp.payment_methods, pp.discount_percent, pp.currency,
       pp.conditions, pp.position, pp.valid_from, pp.valid_until, pp.published_at,
       coalesce((SELECT jsonb_agg(jsonb_build_object(
                          'id', pi.id, 'position', pi.position, 'label', pi.label,
                          'due_date', pi.due_date, 'due_description', pi.due_description,
                          'percentage', pi.percentage, 'amount', pi.amount)
                        ORDER BY pi.position)
                 FROM payment_installment pi WHERE pi.payment_plan_id = pp.id), '[]'::jsonb) AS installments
FROM payment_plan pp
JOIN program p     ON p.id = pp.program_id AND p.is_active
JOIN institution i ON i.id = p.institution_id
WHERE catalog_is_official(pp.status, pp.valid_from, pp.valid_until);
