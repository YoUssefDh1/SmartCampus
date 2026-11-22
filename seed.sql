-- SmartCampus AI - minimal seed. Run AFTER schema.sql. Every value below is a DEFAULT TO CONFIRM.

-- Institutions: fill in the real names/addresses (I did not guess the long names).
INSERT INTO institution (code, name) VALUES
  ('IIT', 'IIT'),
  ('ISB', 'ISB')
ON CONFLICT (code) DO NOTHING;

INSERT INTO system_setting (key, value, description) VALUES
  ('guest_token_ttl_hours',      '24',   'Lifetime of a guest session (SA-5 example: 24 h)'),
  ('upload_max_bytes_candidate', '10485760', 'Candidate upload limit, 10 MB (SA-5). API enforces it, answers 413'),
  ('chat_audio_max_bytes',       '10485760', 'Voice message limit, 10 MB (SA-5)'),
  ('guest_messages_per_minute',  '20',   'Rate limit for guests, answers 429 (value is a guess)'),
  ('reminder_inactivity_days',   '7',    'Days without activity before the first reminder (guess)'),
  ('reminder_interval_days',     '3',    'Days between reminders (guess)'),
  ('reminder_max_attempts',      '3',    'Unanswered reminders before escalation to an advisor (guess)'),
  ('auto_actions',               '{"emails": true, "interview_invitations": true, "reminders": true}',
                                         'Automatic actions the admin allows (SA-3 human-in-the-loop rule)')
ON CONFLICT (key) DO NOTHING;

-- =====================================================================
-- Catalogue de DEMONSTRATION (Membre 3 - SA-20 / SA-21). Requiert la migration 002.
-- Noms, montants, dates et conditions sont FICTIFS : a remplacer par les informations officielles.
-- Reexecutable : aucune ligne n'est dupliquee.
-- =====================================================================
DO $$
DECLARE
  v_iit uuid := (SELECT id FROM institution WHERE code = 'IIT');
  v_isb uuid := (SELECT id FROM institution WHERE code = 'ISB');
  v_prepa uuid; v_info uuid; v_lic uuid; v_master uuid;
  v_sp_soft uuid; v_sp_data uuid;
  v_cur uuid; v_plan uuid; v_subject uuid;
  v_year constant text := '2026-2027';
  v_from constant date := DATE '2026-09-01';
  v_to   constant date := DATE '2027-08-31';
  r record;
BEGIN
  -- Formations -----------------------------------------------------------
  INSERT INTO program (institution_id, code, name, description, cycle, duration_years, degree, capacity,
                       teaching_languages, career_outcomes) VALUES
    (v_iit, 'PREPA-INT', 'Cycle préparatoire intégré',
     'Deux années de mathématiques, physique et informatique qui préparent au cycle ingénieur de l''IIT.',
     'preparatory', 2, 'Attestation de réussite du cycle préparatoire', 120, '{fr,en}',
     'Accès direct au cycle ingénieur de l''IIT.'),
    (v_iit, 'ING-INFO', 'Cycle ingénieur en génie informatique',
     'Formation d''ingénieurs en développement logiciel, data science et réseaux.',
     'engineering', 3, 'Diplôme national d''ingénieur', 90, '{fr,en}',
     'Ingénieur logiciel, data scientist, architecte cloud, ingénieur cybersécurité.'),
    (v_isb, 'LIC-GEST', 'Licence en sciences de gestion',
     'Bases solides en management, comptabilité, marketing et finance.',
     'bachelor', 3, 'Licence nationale', 150, '{fr}',
     'Assistant de gestion, chargé de clientèle, poursuite en master.'),
    (v_isb, 'MP-FIN', 'Master professionnel en finance',
     'Finance d''entreprise, marchés financiers et contrôle de gestion.',
     'master', 2, 'Master professionnel', 40, '{fr,en}',
     'Analyste financier, contrôleur de gestion, auditeur.')
  ON CONFLICT (institution_id, code) DO NOTHING;

  SELECT id INTO v_prepa  FROM program WHERE institution_id = v_iit AND code = 'PREPA-INT';
  SELECT id INTO v_info   FROM program WHERE institution_id = v_iit AND code = 'ING-INFO';
  SELECT id INTO v_lic    FROM program WHERE institution_id = v_isb AND code = 'LIC-GEST';
  SELECT id INTO v_master FROM program WHERE institution_id = v_isb AND code = 'MP-FIN';

  -- Specialites -----------------------------------------------------------
  INSERT INTO specialty (program_id, name, description) VALUES
    (v_info, 'Génie logiciel', 'Conception et développement d''applications.'),
    (v_info, 'Data science et IA', 'Apprentissage automatique, big data, IA générative.'),
    (v_info, 'Réseaux et cybersécurité', 'Infrastructures, sécurité des systèmes.'),
    (v_lic,  'Management', NULL),
    (v_lic,  'Marketing', NULL)
  ON CONFLICT (program_id, name) DO NOTHING;
  SELECT id INTO v_sp_soft FROM specialty WHERE program_id = v_info AND name = 'Génie logiciel';
  SELECT id INTO v_sp_data FROM specialty WHERE program_id = v_info AND name = 'Data science et IA';

  -- Matieres --------------------------------------------------------------
  INSERT INTO subject (code, name, description) VALUES
    ('MATH-ANA1', 'Analyse 1', 'Suites, fonctions, intégrales.'),
    ('MATH-ALG1', 'Algèbre linéaire', 'Espaces vectoriels, matrices.'),
    ('PHY-MEC',   'Mécanique du point', NULL),
    ('INF-ALGO',  'Algorithmique et programmation', 'Python et structures de données.'),
    ('INF-POO',   'Programmation orientée objet', 'Java.'),
    ('INF-BD',    'Bases de données', 'Modèle relationnel, SQL.'),
    ('INF-ML',    'Apprentissage automatique', NULL),
    ('INF-GL',    'Génie logiciel et tests', NULL),
    ('GES-CPT',   'Comptabilité générale', NULL),
    ('GES-MKT',   'Fondamentaux du marketing', NULL),
    ('LANG-EN',   'Anglais', NULL)
  ON CONFLICT (code) DO NOTHING;

  -- Programmes pedagogiques (curriculum) -----------------------------------
  INSERT INTO curriculum (program_id, academic_year, version, description)
  SELECT v_prepa, v_year, 1, 'Programme commun du cycle préparatoire'
  WHERE NOT EXISTS (SELECT 1 FROM curriculum WHERE program_id = v_prepa AND specialty_id IS NULL
                      AND academic_year = v_year AND version = 1);
  SELECT id INTO v_cur FROM curriculum WHERE program_id = v_prepa AND specialty_id IS NULL
                         AND academic_year = v_year AND version = 1;
  FOR r IN SELECT * FROM (VALUES ('MATH-ANA1',1,1,4.0,6),('MATH-ALG1',1,1,3.0,5),('PHY-MEC',1,1,3.0,5),
                                 ('INF-ALGO',1,2,3.0,5),('LANG-EN',1,2,1.0,2)) t(code, y, s, coef, cr) LOOP
    SELECT id INTO v_subject FROM subject WHERE code = r.code;
    INSERT INTO curriculum_subject (curriculum_id, subject_id, study_year, semester, coefficient, credits)
    VALUES (v_cur, v_subject, r.y, r.s, r.coef, r.cr) ON CONFLICT DO NOTHING;
  END LOOP;

  INSERT INTO curriculum (program_id, specialty_id, academic_year, version, description)
  SELECT v_info, v_sp_data, v_year, 1, 'Parcours Data science et IA'
  WHERE NOT EXISTS (SELECT 1 FROM curriculum WHERE program_id = v_info AND specialty_id = v_sp_data
                      AND academic_year = v_year AND version = 1);
  SELECT id INTO v_cur FROM curriculum WHERE program_id = v_info AND specialty_id = v_sp_data
                         AND academic_year = v_year AND version = 1;
  FOR r IN SELECT * FROM (VALUES ('INF-POO',1,1,3.0,5,true),('INF-BD',1,1,3.0,5,true),
                                 ('INF-ML',1,2,4.0,6,true),('LANG-EN',1,2,1.0,2,false)) t(code, y, s, coef, cr, mand) LOOP
    SELECT id INTO v_subject FROM subject WHERE code = r.code;
    INSERT INTO curriculum_subject (curriculum_id, subject_id, study_year, semester, coefficient, credits, is_mandatory)
    VALUES (v_cur, v_subject, r.y, r.s, r.coef, r.cr, r.mand) ON CONFLICT DO NOTHING;
  END LOOP;

  -- Conditions d'admission (publiees, valables pour l'annee 2026-2027) -------
  FOR r IN SELECT * FROM (VALUES
      (v_prepa,  'admission',    'bac_series',      'Baccalauréat scientifique', NULL::numeric,
                 '{Mathématiques,Sciences expérimentales,Sciences techniques,Informatique}'::text[], NULL::uuid, 1),
      (v_prepa,  'admission',    'minimum_average', 'Moyenne au baccalauréat d''au moins 12/20', 12, NULL, NULL, 2),
      (v_prepa,  'admission',    'document',        'Relevé de notes du baccalauréat', NULL, NULL, NULL, 3),
      (v_info,   'prerequisite', 'prior_diploma',   'Réussite du cycle préparatoire intégré (ou équivalent)', NULL, NULL, v_prepa, 1),
      (v_info,   'admission',    'entrance_exam',   'Étude du dossier et entretien de motivation', NULL, NULL, NULL, 2),
      (v_lic,    'admission',    'bac_series',      'Tout baccalauréat', NULL,
                 '{Économie et gestion,Mathématiques,Sciences expérimentales,Lettres,Informatique,Sciences techniques}', NULL, 1),
      (v_lic,    'admission',    'document',        'Relevé de notes du baccalauréat et pièce d''identité', NULL, NULL, NULL, 2),
      (v_master, 'admission',    'prior_diploma',   'Licence en gestion, finance ou économie', NULL, NULL, NULL, 1),
      (v_master, 'admission',    'minimum_average', 'Moyenne de licence d''au moins 11/20', 11, NULL, NULL, 2)
    ) t(program_id, category, kind, description, min_avg, bac, req_prog, pos) LOOP
    INSERT INTO admission_requirement (program_id, category, kind, description, min_average, accepted_bac_series,
                                       required_program_id, academic_year, position, status, valid_from, valid_until,
                                       published_at)
    SELECT r.program_id, r.category, r.kind, r.description, r.min_avg, r.bac, r.req_prog, v_year, r.pos,
           'published', v_from, v_to, now()
    WHERE NOT EXISTS (SELECT 1 FROM admission_requirement a
                      WHERE a.program_id = r.program_id AND a.kind = r.kind AND a.description = r.description);
  END LOOP;

  -- Frais de scolarite ------------------------------------------------------
  INSERT INTO tuition_fee (program_id, academic_year, fee_type, amount, description, status,
                           valid_from, valid_until, published_at) VALUES
    (v_prepa,  v_year, 'registration', 300,  'Frais d''inscription', 'published', v_from, v_to, now()),
    (v_prepa,  v_year, 'tuition',      6500, 'Frais de scolarité annuels', 'published', v_from, v_to, now()),
    (v_info,   v_year, 'registration', 300,  'Frais d''inscription', 'published', v_from, v_to, now()),
    (v_info,   v_year, 'tuition',      7800, 'Frais de scolarité annuels', 'published', v_from, v_to, now()),
    (v_lic,    v_year, 'registration', 250,  'Frais d''inscription', 'published', v_from, v_to, now()),
    (v_lic,    v_year, 'tuition',      4900, 'Frais de scolarité annuels', 'published', v_from, v_to, now()),
    (v_master, v_year, 'application',  100,  'Frais d''étude de dossier', 'published', v_from, v_to, now()),
    (v_master, v_year, 'tuition',      8500, 'Frais de scolarité annuels', 'published', v_from, v_to, now())
  ON CONFLICT DO NOTHING;
  -- Brouillon : visible par les responsables uniquement (exemple du workflow de publication)
  INSERT INTO tuition_fee (program_id, academic_year, fee_type, amount, description, status, valid_from, valid_until)
  VALUES (v_info, '2027-2028', 'tuition', 8100, 'Projet de tarif 2027-2028 (non publié)', 'draft',
          DATE '2027-09-01', DATE '2028-08-31')
  ON CONFLICT DO NOTHING;

  -- Modalites de paiement -----------------------------------------------------
  FOR r IN SELECT id FROM program WHERE id IN (v_prepa, v_info, v_lic, v_master) LOOP
    INSERT INTO payment_plan (program_id, academic_year, name, description, payment_methods, discount_percent,
                              position, status, valid_from, valid_until, published_at)
    VALUES (r.id, v_year, 'Paiement comptant', 'Totalité des frais réglée à l''inscription.',
            '{cash,bank_transfer,check}', 5, 1, 'published', v_from, v_to, now())
    ON CONFLICT DO NOTHING;
    SELECT id INTO v_plan FROM payment_plan
     WHERE program_id = r.id AND academic_year = v_year AND name = 'Paiement comptant' AND status <> 'archived';
    INSERT INTO payment_installment (payment_plan_id, position, label, due_description, percentage)
    VALUES (v_plan, 1, 'Paiement unique', 'À l''inscription', 100) ON CONFLICT DO NOTHING;

    INSERT INTO payment_plan (program_id, academic_year, name, description, payment_methods, position,
                              conditions, status, valid_from, valid_until, published_at)
    VALUES (r.id, v_year, 'Paiement en 3 tranches', 'Frais de scolarité répartis sur l''année.',
            '{bank_transfer,check}', 2, 'Pénalité de retard possible après 15 jours.',
            'published', v_from, v_to, now())
    ON CONFLICT DO NOTHING;
    SELECT id INTO v_plan FROM payment_plan
     WHERE program_id = r.id AND academic_year = v_year AND name = 'Paiement en 3 tranches' AND status <> 'archived';
    INSERT INTO payment_installment (payment_plan_id, position, label, due_date, due_description, percentage) VALUES
      (v_plan, 1, '1re tranche', NULL,               'À l''inscription', 40),
      (v_plan, 2, '2e tranche',  DATE '2027-01-15', NULL,                30),
      (v_plan, 3, '3e tranche',  DATE '2027-04-15', NULL,                30)
    ON CONFLICT DO NOTHING;
  END LOOP;
END $$;
