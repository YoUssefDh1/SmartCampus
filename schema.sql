-- =====================================================================
-- SmartCampus AI - PostgreSQL schema v1 (consolidated from Tasks 1-3 + SA-3/4/5)
--
-- Requires : PostgreSQL 14+, extensions vector (pgvector) and btree_gist (contrib)
-- Conventions
--   * English snake_case names (same vocabulary as the SA-5 API: program, preregistration...)
--   * UUID primary keys (gen_random_uuid), TIMESTAMPTZ everywhere
--   * text + CHECK instead of ENUM types (much easier to change with Alembic)
--   * ON DELETE: CASCADE for data owned by a candidate (erasure = delete the app_user row),
--                RESTRICT for anything pointing at staff or at the catalog.
--   * Staff are deactivated (is_active = false), never deleted.
-- NOT in this file: the LangGraph checkpoint tables. Let PostgresSaver.setup() create them,
--   in their own schema (e.g. search_path=langgraph on that connection). Do not hand-design them.
-- =====================================================================

BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- ---------------------------------------------------------------------
-- Domains (one definition, reused everywhere)
-- ---------------------------------------------------------------------
CREATE DOMAIN academic_year AS varchar(9)   CHECK (VALUE ~ '^\d{4}-\d{4}$');          -- 2026-2027
CREATE DOMAIN chat_language AS varchar(20)  CHECK (VALUE IN ('fr', 'tn', 'tn-arabizi'));
CREATE DOMAIN grade_20      AS numeric(4,2) CHECK (VALUE BETWEEN 0 AND 20);           -- Tunisian /20 scale

CREATE FUNCTION set_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END $$;

-- =====================================================================
-- 1. IDENTITY AND ACCESS
-- =====================================================================

CREATE TABLE institution (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code        varchar(20)  NOT NULL UNIQUE CHECK (code = upper(code)),   -- IIT, ISB
  name        varchar(150) NOT NULL,
  address     text,
  description text,
  website     text,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);

-- Authenticated accounts only (candidates + staff). Visitors are in guest_session.
-- 'guest' is NOT a role here: a guest has no account. It only exists as a JWT claim.
-- 'advisor' = the "conseiller" of SA-3 (escalation target). SA-5 forgot this role: add it there.
CREATE TABLE app_user (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  role              text NOT NULL CHECK (role IN
                      ('candidate','iit_manager','isb_manager','interviewer','advisor','direction','admin')),
  institution_id    uuid REFERENCES institution(id) ON DELETE RESTRICT,
  first_name        varchar(100) NOT NULL,
  last_name         varchar(100) NOT NULL,
  email             varchar(255) NOT NULL,
  phone             varchar(30),
  password_hash     text NOT NULL,                       -- argon2/bcrypt hash, never the password
  is_active         boolean NOT NULL DEFAULT true,
  email_verified_at timestamptz,
  last_login_at     timestamptz,
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT app_user_id_role_key UNIQUE (id, role),     -- target of the "role-typed" foreign keys below
  CONSTRAINT app_user_institution_scope CHECK (
        (role IN ('iit_manager','isb_manager') AND institution_id IS NOT NULL)
     OR (role = 'candidate' AND institution_id IS NULL)
     OR  role IN ('interviewer','advisor','direction','admin')
  )
);
CREATE UNIQUE INDEX app_user_email_key ON app_user (lower(email));
CREATE INDEX app_user_role_idx ON app_user (role);

-- Candidate extension of app_user. Every candidate-owned table points HERE, not at app_user:
-- this is what structurally guarantees "only a candidate can own a dossier / a conversation".
CREATE TABLE candidate_profile (
  user_id            uuid PRIMARY KEY,
  role               text NOT NULL DEFAULT 'candidate' CHECK (role = 'candidate'),
  current_level      varchar(100),
  bac_series         varchar(100),
  graduation_year    smallint CHECK (graduation_year BETWEEN 1990 AND 2100),
  average            grade_20,
  interests          jsonb NOT NULL DEFAULT '[]'::jsonb,   -- raw, filled by the chatbot
  goals              text,
  computed_profile   jsonb,                                -- output of the orientation agent
  preferred_language chat_language,
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (user_id, role) REFERENCES app_user (id, role) ON DELETE CASCADE
);

-- Anonymous visitor. The session id is the JWT 'sub' (no token hash needed: the JWT is signed).
-- DO NOT delete rows to purge: the funnel needs the visitor counts. Purge the conversations
-- of expired, unclaimed sessions instead.
CREATE TABLE guest_session (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at         timestamptz NOT NULL DEFAULT now(),
  expires_at         timestamptz NOT NULL,
  last_seen_at       timestamptz NOT NULL DEFAULT now(),
  language           chat_language,
  ip_hash            text,                                 -- hashed, for abuse / rate limit only
  claimed_at         timestamptz,
  claimed_by_user_id uuid REFERENCES candidate_profile(user_id) ON DELETE SET NULL,
  CHECK (expires_at > created_at),
  CHECK (claimed_by_user_id IS NULL OR claimed_at IS NOT NULL)
);
CREATE INDEX guest_session_expires_idx ON guest_session (expires_at);

-- Needed by POST /auth/refresh: without a stored (hashed) token you cannot revoke anything.
CREATE TABLE refresh_token (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id        uuid NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
  token_hash     text NOT NULL UNIQUE,
  expires_at     timestamptz NOT NULL,
  revoked_at     timestamptz,
  replaced_by_id uuid REFERENCES refresh_token(id) ON DELETE SET NULL,   -- rotation chain
  created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX refresh_token_user_idx ON refresh_token (user_id);

-- Consent is a record, not a boolean. Separate purposes: you cannot train the LoRA model on
-- candidate conversations with a consent that only covers the preregistration.
CREATE TABLE consent (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  candidate_id   uuid NOT NULL REFERENCES candidate_profile(user_id) ON DELETE CASCADE,
  purpose        text NOT NULL CHECK (purpose IN ('data_processing','ai_training','communications')),
  policy_version varchar(30) NOT NULL,
  granted_at     timestamptz NOT NULL DEFAULT now(),
  withdrawn_at   timestamptz,
  ip_hash        text,
  CHECK (withdrawn_at IS NULL OR withdrawn_at >= granted_at),
  UNIQUE (id, candidate_id)
);
CREATE INDEX consent_candidate_idx ON consent (candidate_id, purpose);

-- =====================================================================
-- 2. ACADEMIC CATALOG  (Task 1: 11 tables -> 8)
--    program = "formation" = what SA-5 calls /programs.
--    curriculum = "programme_etude" (renamed: two different "programmes" was a trap).
--    Removed: formation_specialite (specialty belongs to ONE program),
--             prerequis + formation_prerequis (merged into admission_requirement).
-- =====================================================================

CREATE TABLE program (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  institution_id     uuid NOT NULL REFERENCES institution(id) ON DELETE RESTRICT,
  code               varchar(30)  NOT NULL,
  name               varchar(200) NOT NULL,
  description        text,
  cycle              text NOT NULL CHECK (cycle IN ('preparatory','engineering','bachelor','master','other')),
  duration_years     smallint CHECK (duration_years > 0),
  degree             varchar(150),
  capacity           integer CHECK (capacity >= 0),
  teaching_languages text[] NOT NULL DEFAULT '{}',
  career_outcomes    text,                                  -- chatbot asks about "debouches" constantly
  is_active          boolean NOT NULL DEFAULT true,
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now(),
  search_tsv         tsvector GENERATED ALWAYS AS (
                       to_tsvector('simple', coalesce(name,'') || ' ' || coalesce(description,''))) STORED,
  UNIQUE (institution_id, code)
);
CREATE INDEX program_institution_idx ON program (institution_id);
CREATE INDEX program_search_idx ON program USING gin (search_tsv);

CREATE TABLE specialty (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  program_id  uuid NOT NULL REFERENCES program(id) ON DELETE CASCADE,
  name        varchar(150) NOT NULL,
  description text,
  is_active   boolean NOT NULL DEFAULT true,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (program_id, name),
  UNIQUE (id, program_id)                                   -- lets other tables prove "same program"
);

-- Versioned curriculum. specialty_id is NULL when the curriculum is common to the whole program
-- (task 1 forgot that engineering curricula differ per specialty).
CREATE TABLE curriculum (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  program_id    uuid NOT NULL REFERENCES program(id) ON DELETE CASCADE,
  specialty_id  uuid,
  academic_year academic_year NOT NULL,
  version       integer NOT NULL DEFAULT 1 CHECK (version >= 1),
  description   text,
  is_active     boolean NOT NULL DEFAULT true,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (specialty_id, program_id) REFERENCES specialty (id, program_id) ON DELETE RESTRICT
);
CREATE UNIQUE INDEX curriculum_version_key ON curriculum
  (program_id, coalesce(specialty_id, '00000000-0000-0000-0000-000000000000'::uuid), academic_year, version);
CREATE UNIQUE INDEX curriculum_one_active_key ON curriculum
  (program_id, coalesce(specialty_id, '00000000-0000-0000-0000-000000000000'::uuid), academic_year)
  WHERE is_active;

CREATE TABLE subject (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code        varchar(30)  NOT NULL UNIQUE,
  name        varchar(150) NOT NULL,
  description text,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);

-- semester = global semester number inside the curriculum (1..n); study_year = 1..n
CREATE TABLE curriculum_subject (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  curriculum_id uuid NOT NULL REFERENCES curriculum(id) ON DELETE CASCADE,
  subject_id    uuid NOT NULL REFERENCES subject(id) ON DELETE RESTRICT,
  study_year    smallint NOT NULL CHECK (study_year BETWEEN 1 AND 8),
  semester      smallint NOT NULL CHECK (semester BETWEEN 1 AND 16),
  coefficient   numeric(4,2) CHECK (coefficient >= 0),
  credits       smallint CHECK (credits >= 0),
  is_mandatory  boolean NOT NULL DEFAULT true,
  UNIQUE (curriculum_id, subject_id, semester)
);
CREATE INDEX curriculum_subject_subject_idx ON curriculum_subject (subject_id);

-- Admission conditions AND prerequisites in one table (they were the same concept split in two).
-- Structured columns exist so the orientation agent / rules engine can evaluate eligibility in SQL,
-- not by re-reading free text.
CREATE TABLE admission_requirement (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  program_id          uuid NOT NULL REFERENCES program(id) ON DELETE CASCADE,
  category            text NOT NULL CHECK (category IN ('admission','prerequisite')),
  kind                text NOT NULL CHECK (kind IN
                        ('bac_series','minimum_average','prior_diploma','entrance_exam','document','skill','other')),
  description         text NOT NULL,
  min_average         grade_20,
  accepted_bac_series text[],
  required_program_id uuid REFERENCES program(id) ON DELETE RESTRICT,   -- e.g. engineering requires the prep cycle
  academic_year       academic_year,                                    -- NULL = every year
  is_mandatory        boolean NOT NULL DEFAULT true,
  position            smallint NOT NULL DEFAULT 0,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),
  CHECK (kind <> 'minimum_average' OR min_average IS NOT NULL)
);
CREATE INDEX admission_requirement_program_idx ON admission_requirement (program_id);

CREATE TABLE tuition_fee (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  program_id    uuid NOT NULL REFERENCES program(id) ON DELETE CASCADE,
  academic_year academic_year NOT NULL,
  study_year    smallint CHECK (study_year BETWEEN 1 AND 8),           -- NULL = all years
  fee_type      text NOT NULL CHECK (fee_type IN ('application','registration','tuition','other')),
  amount        numeric(10,2) NOT NULL CHECK (amount >= 0),
  currency      char(3) NOT NULL DEFAULT 'TND' CHECK (currency ~ '^[A-Z]{3}$'),
  description   text,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX tuition_fee_key ON tuition_fee (program_id, academic_year, fee_type, coalesce(study_year, 0));

-- =====================================================================
-- 3. CONFIGURATION (SA-3 admin: templates, orientation rules, AI agents, settings)
--    None of this was in tasks 1-3.
-- =====================================================================

CREATE TABLE message_template (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code          varchar(80) NOT NULL,                       -- 'interview_invitation', 'reminder_1', 'qcm_default'
  kind          text NOT NULL CHECK (kind IN ('email','qcm_blueprint')),
  locale        text NOT NULL DEFAULT 'fr' CHECK (locale IN ('fr','ar','en','tn')),
  subject       varchar(250),
  body          text NOT NULL,
  config        jsonb NOT NULL DEFAULT '{}'::jsonb,         -- QCM: question count, topics, difficulty mix
  is_active     boolean NOT NULL DEFAULT true,
  updated_by_id uuid REFERENCES app_user(id) ON DELETE SET NULL,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (code, locale)
);

-- One row per (component, version). Rolling back a prompt or a LoRA adapter = flip is_active.
CREATE TABLE ai_config (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  component     text NOT NULL CHECK (component IN
                  ('supervisor','orientation','rag','preregistration_qcm','followup','embedding','stt')),
  version       integer NOT NULL CHECK (version >= 1),
  model_name    varchar(200) NOT NULL,                      -- base LLM, embedding model, whisper size...
  adapter_uri   text,                                       -- LoRA/QLoRA adapter location
  system_prompt text,
  temperature   numeric(3,2) CHECK (temperature BETWEEN 0 AND 2),
  params        jsonb NOT NULL DEFAULT '{}'::jsonb,
  is_active     boolean NOT NULL DEFAULT false,
  notes         text,
  created_by_id uuid REFERENCES app_user(id) ON DELETE SET NULL,
  created_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (component, version)
);
CREATE UNIQUE INDEX ai_config_one_active_key ON ai_config (component) WHERE is_active;

CREATE TABLE system_setting (
  key           varchar(100) PRIMARY KEY,
  value         jsonb NOT NULL,
  description   text,
  updated_by_id uuid REFERENCES app_user(id) ON DELETE SET NULL,
  updated_at    timestamptz NOT NULL DEFAULT now()
);

-- "Regles d'orientation" managed by the admin and read by the orientation agent.
CREATE TABLE orientation_rule (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name          varchar(150) NOT NULL,
  description   text,
  program_id    uuid REFERENCES program(id) ON DELETE CASCADE,   -- NULL = global rule
  condition     jsonb NOT NULL,                                  -- e.g. {"bac_series":["Maths"],"min_average":13}
  weight        numeric(5,2) NOT NULL DEFAULT 1,
  is_active     boolean NOT NULL DEFAULT true,
  updated_by_id uuid REFERENCES app_user(id) ON DELETE SET NULL,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX orientation_rule_program_idx ON orientation_rule (program_id);

-- =====================================================================
-- 4. CONVERSATIONS AND AI TRACE
-- =====================================================================

-- A conversation starts under a guest_session; /auth/claim then sets candidate_id.
-- Purging an unclaimed guest conversation = DELETE the conversation (messages cascade).
CREATE TABLE conversation (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  guest_session_id   uuid REFERENCES guest_session(id) ON DELETE SET NULL,
  candidate_id       uuid REFERENCES candidate_profile(user_id) ON DELETE CASCADE,
  language           chat_language,
  status             varchar(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active','closed','archived')),
  started_at         timestamptz NOT NULL DEFAULT now(),
  last_message_at    timestamptz,
  summary            text,
  summary_points     jsonb,                                -- "points a approfondir" for the interviewer
  summary_updated_at timestamptz,
  CHECK (guest_session_id IS NOT NULL OR candidate_id IS NOT NULL)
);
CREATE INDEX conversation_candidate_idx ON conversation (candidate_id);
CREATE INDEX conversation_guest_idx ON conversation (guest_session_id);

-- One row per LLM/agent invocation: latency, tokens, tool calls. Feeds /admin/logs and your evaluation.
CREATE TABLE agent_run (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id uuid REFERENCES conversation(id) ON DELETE CASCADE,
  component       text NOT NULL,
  ai_config_id    uuid REFERENCES ai_config(id) ON DELETE SET NULL,
  status          text NOT NULL CHECK (status IN ('success','error','handover','timeout')),
  latency_ms      integer CHECK (latency_ms >= 0),
  input_tokens    integer CHECK (input_tokens >= 0),
  output_tokens   integer CHECK (output_tokens >= 0),
  tool_calls      jsonb,
  error           text,
  created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX agent_run_conversation_idx ON agent_run (conversation_id);
CREATE INDEX agent_run_created_idx ON agent_run (created_at);

CREATE TABLE message (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id uuid NOT NULL REFERENCES conversation(id) ON DELETE CASCADE,
  role            text NOT NULL CHECK (role IN ('user','assistant','system')),   -- not visitor/candidate: ownership is on the conversation
  content         text NOT NULL,                       -- for voice messages: the Whisper transcript
  language        chat_language,
  audio_path      text,                                -- file storage path (SA-4 stores audio as files)
  sources         jsonb,                               -- [{program_id,title,origin}] as in SA-5
  next_action     text CHECK (next_action IN
                    ('ask_question','explain_program','compare_programs','start_preregistration','handover_human')),
  profile_updates jsonb,
  agent_run_id    uuid REFERENCES agent_run(id) ON DELETE SET NULL,
  created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX message_conversation_idx ON message (conversation_id, created_at);

-- =====================================================================
-- 5. APPLICATION WORKFLOW
-- =====================================================================

-- Orientation shortlist (2-3 programs). PATCH /candidates/{id}/recommendation lands here.
-- Adjusting = old row 'adjusted' + new row origin 'manager' with replaces_id.
CREATE TABLE recommendation (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  candidate_id   uuid NOT NULL REFERENCES candidate_profile(user_id) ON DELETE CASCADE,
  program_id     uuid NOT NULL REFERENCES program(id) ON DELETE RESTRICT,
  rank           smallint NOT NULL DEFAULT 1 CHECK (rank >= 1),
  score          numeric(5,2) CHECK (score BETWEEN 0 AND 100),
  justification  text NOT NULL,
  sources        jsonb NOT NULL DEFAULT '[]'::jsonb,
  origin         text NOT NULL DEFAULT 'ai' CHECK (origin IN ('ai','manager')),
  status         text NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed','confirmed','adjusted','superseded')),
  replaces_id    uuid REFERENCES recommendation(id) ON DELETE SET NULL,
  agent_run_id   uuid REFERENCES agent_run(id) ON DELETE SET NULL,
  reviewed_by_id uuid REFERENCES app_user(id) ON DELETE RESTRICT,
  reviewed_at    timestamptz,
  review_comment text,
  created_at     timestamptz NOT NULL DEFAULT now(),
  CHECK (status NOT IN ('confirmed','adjusted') OR (reviewed_by_id IS NOT NULL AND reviewed_at IS NOT NULL))
);
CREATE INDEX recommendation_candidate_idx ON recommendation (candidate_id);
CREATE INDEX recommendation_program_idx ON recommendation (program_id);
CREATE UNIQUE INDEX recommendation_live_key ON recommendation (candidate_id, program_id)
  WHERE status IN ('proposed','confirmed');

-- Status flow (SA-3):
--   submitted -> qcm_completed (= awaiting academic validation) -> validated -> interview_scheduled
--   -> interviewed -> accepted | rejected | complement_required (loops back) -> enrolled
--   side exits: withdrawn (candidate), abandoned (inactive + escalation exhausted)
-- accepted / rejected / enrolled REQUIRE a human decider: decided_by_id points to app_user,
-- and an AI agent is not an app_user. "Never the AI" is enforced by the schema, not by good intentions.
CREATE TABLE preregistration (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  candidate_id     uuid NOT NULL REFERENCES candidate_profile(user_id) ON DELETE CASCADE,
  program_id       uuid NOT NULL REFERENCES program(id) ON DELETE RESTRICT,
  specialty_id     uuid,
  academic_year    academic_year NOT NULL,                  -- intake year (was missing)
  phone            varchar(30) NOT NULL,                    -- snapshot at submission time
  school_level     varchar(150) NOT NULL,
  declared_average grade_20,
  consent_id       uuid NOT NULL,                           -- consent must exist BEFORE the row
  status           text NOT NULL DEFAULT 'submitted' CHECK (status IN
                     ('submitted','qcm_completed','validated','interview_scheduled','interviewed',
                      'complement_required','accepted','rejected','enrolled','withdrawn','abandoned')),
  decided_by_id    uuid REFERENCES app_user(id) ON DELETE RESTRICT,
  decided_at       timestamptz,
  decision_comment text,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (consent_id, candidate_id) REFERENCES consent (id, candidate_id),
  FOREIGN KEY (specialty_id, program_id) REFERENCES specialty (id, program_id) ON DELETE RESTRICT,
  CONSTRAINT preregistration_human_decision CHECK (
    status NOT IN ('accepted','rejected','enrolled') OR (decided_by_id IS NOT NULL AND decided_at IS NOT NULL))
);
CREATE INDEX preregistration_candidate_idx ON preregistration (candidate_id);
CREATE INDEX preregistration_program_idx ON preregistration (program_id, status);
-- One live preregistration per candidate/program/year (SA-5 409 CONFLICT). Confirm with your business owner.
CREATE UNIQUE INDEX preregistration_live_key ON preregistration (candidate_id, program_id, academic_year)
  WHERE status NOT IN ('withdrawn','abandoned','rejected');

-- Written automatically by a trigger. Without it, the funnel (SA-3 direction dashboard) is impossible.
CREATE TABLE preregistration_status_history (
  id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  preregistration_id uuid NOT NULL REFERENCES preregistration(id) ON DELETE CASCADE,
  from_status        text,
  to_status          text NOT NULL,
  changed_by_id      uuid REFERENCES app_user(id) ON DELETE SET NULL,   -- NULL = system / agent
  changed_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX preregistration_history_idx ON preregistration_status_history (preregistration_id, changed_at);
CREATE INDEX preregistration_history_status_idx ON preregistration_status_history (to_status);

-- Missing from tasks 1-3: SA-5 has /qcm/generate, /submit, /result and no table existed.
-- Questions are generated per candidate, so answers live ON the question row (no qcm_answer table).
CREATE TABLE qcm (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  preregistration_id uuid NOT NULL REFERENCES preregistration(id) ON DELETE CASCADE,
  template_id        uuid REFERENCES message_template(id) ON DELETE SET NULL,
  ai_config_id       uuid REFERENCES ai_config(id) ON DELETE SET NULL,
  status             text NOT NULL DEFAULT 'generated' CHECK (status IN ('generated','in_progress','graded','expired')),
  score              numeric(5,2) CHECK (score BETWEEN 0 AND 100),
  synthesis          jsonb,                                -- {strengths:[], difficulties:[], motivations:[]}
  generated_at       timestamptz NOT NULL DEFAULT now(),
  submitted_at       timestamptz,
  graded_at          timestamptz
);
CREATE INDEX qcm_preregistration_idx ON qcm (preregistration_id);
CREATE UNIQUE INDEX qcm_one_open_key ON qcm (preregistration_id) WHERE status IN ('generated','in_progress');

CREATE TABLE qcm_question (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  qcm_id          uuid NOT NULL REFERENCES qcm(id) ON DELETE CASCADE,
  position        smallint NOT NULL CHECK (position >= 1),
  topic           varchar(150),
  difficulty      text CHECK (difficulty IN ('easy','medium','hard')),
  prompt          text NOT NULL,
  options         jsonb NOT NULL CHECK (jsonb_typeof(options) = 'array'),   -- [{"id":"a","text":"..."}]
  correct_option  varchar(10) NOT NULL,                    -- never serialize this to the candidate
  explanation     text,
  selected_option varchar(10),
  answered_at     timestamptz,
  is_correct      boolean GENERATED ALWAYS AS (selected_option = correct_option) STORED,
  UNIQUE (qcm_id, position)
);

-- "Passerelle / equivalence". The AI answer is advisory; only a human sets confirmed/refused
-- (SA-3 is vague on whether an unambiguous AI answer is final: I assumed NO).
CREATE TABLE equivalence_request (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  candidate_id       uuid NOT NULL REFERENCES candidate_profile(user_id) ON DELETE CASCADE,
  target_program_id  uuid NOT NULL REFERENCES program(id) ON DELETE RESTRICT,
  origin_degree      varchar(200) NOT NULL,
  origin_institution varchar(200),
  background         text NOT NULL,
  status             text NOT NULL DEFAULT 'pending' CHECK (status IN
                       ('pending','ai_assessed','under_review','confirmed','refused')),
  ai_assessment      jsonb,                                -- {suggested_program_id, confidence, sources:[...]}
  is_ambiguous       boolean NOT NULL DEFAULT false,
  decided_by_id      uuid REFERENCES app_user(id) ON DELETE RESTRICT,
  decision_comment   text,
  decided_at         timestamptz,
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now(),
  CHECK (status NOT IN ('confirmed','refused') OR (decided_by_id IS NOT NULL AND decided_at IS NOT NULL))
);
CREATE INDEX equivalence_candidate_idx ON equivalence_request (candidate_id);
CREATE INDEX equivalence_target_idx ON equivalence_request (target_program_id, status);

-- Candidate uploads (POST /documents). Different world from document_source (the RAG corpus).
-- Missing from tasks 1-3 although SA-5 and Task 3 both mention it. The 10 MB limit is enforced
-- by the API (413), not here, so it stays configurable.
CREATE TABLE candidate_document (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  candidate_id      uuid NOT NULL REFERENCES candidate_profile(user_id) ON DELETE CASCADE,
  doc_type          text NOT NULL CHECK (doc_type IN ('transcript','identity','other')),
  original_filename varchar(255) NOT NULL,
  storage_path      text NOT NULL UNIQUE,
  mime_type         varchar(100) NOT NULL CHECK (mime_type IN ('application/pdf','image/jpeg','image/png')),
  size_bytes        bigint NOT NULL CHECK (size_bytes > 0),
  checksum_sha256   char(64),
  created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX candidate_document_candidate_idx ON candidate_document (candidate_id);

-- "Le systeme propose un creneau autorise": allowed slots must exist somewhere.
-- interviewer_role is a constant that makes the FK prove the user really has the interviewer role.
CREATE TABLE interview_slot (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  interviewer_id   uuid NOT NULL,
  interviewer_role text NOT NULL DEFAULT 'interviewer' CHECK (interviewer_role = 'interviewer'),
  starts_at        timestamptz NOT NULL,
  ends_at          timestamptz NOT NULL,
  location_or_link text,
  created_at       timestamptz NOT NULL DEFAULT now(),
  CHECK (ends_at > starts_at),
  FOREIGN KEY (interviewer_id, interviewer_role) REFERENCES app_user (id, role) ON DELETE RESTRICT,
  EXCLUDE USING gist (interviewer_id WITH =, tstzrange(starts_at, ends_at) WITH &&)   -- no overlapping slots
);
CREATE INDEX interview_slot_time_idx ON interview_slot (starts_at);

-- rendez_vous + entretien merged: they were 1:0..1, duplicated candidate_id and interviewer_id,
-- and every appointment in SA-3 is an interview. Times and interviewer come from the slot.
CREATE TABLE interview (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  preregistration_id uuid NOT NULL REFERENCES preregistration(id) ON DELETE CASCADE,
  slot_id            uuid NOT NULL REFERENCES interview_slot(id) ON DELETE RESTRICT,
  status             text NOT NULL DEFAULT 'proposed' CHECK (status IN
                       ('proposed','confirmed','cancelled','completed','no_show')),
  ics_uid            uuid NOT NULL DEFAULT gen_random_uuid(),   -- stable id for .ics updates/cancellations
  confirmed_at       timestamptz,
  outcome            text CHECK (outcome IN ('proceed','complement_required','refused')),
  observations       text,
  outcome_comment    text,
  outcome_entered_at timestamptz,
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now(),
  CHECK (outcome IS NULL OR status = 'completed')
);
CREATE INDEX interview_preregistration_idx ON interview (preregistration_id);
CREATE UNIQUE INDEX interview_one_open_per_dossier ON interview (preregistration_id)
  WHERE status IN ('proposed','confirmed');
CREATE UNIQUE INDEX interview_slot_taken_key ON interview (slot_id)
  WHERE status IN ('proposed','confirmed','completed','no_show');

-- Where next_action = 'handover_human', ambiguous equivalences and exhausted reminders land.
-- SA-5 returns handover_human with HTTP 200; without this table that signal goes nowhere.
CREATE TABLE handover (
  id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  reason                 text NOT NULL CHECK (reason IN
                           ('no_reliable_answer','ambiguous_equivalence','inactivity_escalation','user_request','other')),
  status                 text NOT NULL DEFAULT 'open' CHECK (status IN ('open','assigned','resolved','cancelled')),
  conversation_id        uuid REFERENCES conversation(id) ON DELETE CASCADE,
  candidate_id           uuid REFERENCES candidate_profile(user_id) ON DELETE CASCADE,
  preregistration_id     uuid REFERENCES preregistration(id) ON DELETE CASCADE,
  equivalence_request_id uuid REFERENCES equivalence_request(id) ON DELETE CASCADE,
  assigned_to_id         uuid REFERENCES app_user(id) ON DELETE SET NULL,
  context                jsonb,
  resolution_note        text,
  created_at             timestamptz NOT NULL DEFAULT now(),
  updated_at             timestamptz NOT NULL DEFAULT now(),
  resolved_at            timestamptz,
  CHECK (conversation_id IS NOT NULL OR candidate_id IS NOT NULL
         OR preregistration_id IS NOT NULL OR equivalence_request_id IS NOT NULL),
  CHECK (status <> 'resolved' OR resolved_at IS NOT NULL)
);
CREATE INDEX handover_status_idx ON handover (status, created_at);

-- Emails (SMTP outbox) and in-app notifications in one table. Reminder count and escalation
-- timing are derived from rows with purpose = 'reminder'. dedupe_key makes the scheduler idempotent.
CREATE TABLE notification (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id            uuid NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
  channel            text NOT NULL CHECK (channel IN ('email','in_app')),
  purpose            text NOT NULL CHECK (purpose IN
                       ('reminder','interview_invitation','interview_update','status_update','escalation','other')),
  subject            varchar(250),
  body               text NOT NULL,
  template_id        uuid REFERENCES message_template(id) ON DELETE SET NULL,
  preregistration_id uuid REFERENCES preregistration(id) ON DELETE CASCADE,
  interview_id       uuid REFERENCES interview(id) ON DELETE SET NULL,
  to_address         varchar(255),
  status             text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','sent','failed','cancelled')),
  dedupe_key         text UNIQUE,                         -- e.g. 'reminder:<preregistration_id>:2'
  attempts           smallint NOT NULL DEFAULT 0,
  last_error         text,
  scheduled_at       timestamptz NOT NULL DEFAULT now(),
  sent_at            timestamptz,
  read_at            timestamptz,
  created_at         timestamptz NOT NULL DEFAULT now(),
  CHECK (channel <> 'email' OR to_address IS NOT NULL)
);
CREATE INDEX notification_user_idx ON notification (user_id, created_at DESC);
CREATE INDEX notification_due_idx ON notification (scheduled_at) WHERE status = 'pending';
CREATE INDEX notification_preregistration_idx ON notification (preregistration_id, purpose);

-- =====================================================================
-- 6. RAG CORPUS  (Task 3: 5 tables -> 4)
--    traitement_document + evenement_synchronisation were the same queue twice -> ingestion_job.
--    is_current + current_version_id were the same fact twice -> only current_version_id.
-- =====================================================================

CREATE TABLE document_source (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  institution_id        uuid REFERENCES institution(id) ON DELETE SET NULL,
  program_id            uuid REFERENCES program(id) ON DELETE SET NULL,
  title                 varchar(250) NOT NULL,
  description           text,
  doc_type              text NOT NULL CHECK (doc_type IN
                          ('brochure','regulation','curriculum','admission_conditions','equivalence_rules','other')),
  original_filename     varchar(255) NOT NULL,
  status                text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','active','archived','deleted')),
  current_version_id    uuid,                              -- FK added below (circular)
  created_by_id         uuid NOT NULL REFERENCES app_user(id) ON DELETE RESTRICT,
  created_at            timestamptz NOT NULL DEFAULT now(),
  updated_at            timestamptz NOT NULL DEFAULT now(),
  deleted_at            timestamptz,
  CHECK ((status = 'deleted') = (deleted_at IS NOT NULL))
);
CREATE INDEX document_source_status_idx ON document_source (status);

CREATE TABLE document_version (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id     uuid NOT NULL REFERENCES document_source(id) ON DELETE CASCADE,
  version_number  integer NOT NULL CHECK (version_number >= 1),
  storage_path    text NOT NULL UNIQUE,
  mime_type       varchar(100) NOT NULL,
  size_bytes      bigint NOT NULL CHECK (size_bytes > 0),
  checksum_sha256 char(64) NOT NULL CHECK (checksum_sha256 ~ '^[0-9a-f]{64}$'),
  language        varchar(20),
  uploaded_by_id  uuid NOT NULL REFERENCES app_user(id) ON DELETE RESTRICT,
  uploaded_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (document_id, version_number),
  UNIQUE (document_id, checksum_sha256),                   -- same file twice = same version
  UNIQUE (id, document_id)
);

-- current_version_id must point at a version OF THE SAME document.
ALTER TABLE document_source
  ADD CONSTRAINT document_source_current_version_fk
  FOREIGN KEY (current_version_id, id) REFERENCES document_version (id, document_id);

-- Job queue + outbox + processing trace. Worker pattern:
--   SELECT ... FROM ingestion_job WHERE status = 'queued' AND run_after <= now()
--   ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1;
-- Create the job in the SAME transaction as the document_version row. Recover jobs stuck in
-- 'running' with locked_at older than your timeout.
CREATE TABLE ingestion_job (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id     uuid NOT NULL REFERENCES document_source(id) ON DELETE CASCADE,
  version_id      uuid REFERENCES document_version(id) ON DELETE CASCADE,
  action          text NOT NULL CHECK (action IN ('add','update','delete','reindex')),
  status          text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','succeeded','failed','cancelled')),
  current_step    text CHECK (current_step IN ('extract','chunk','embed','index','cleanup')),
  attempt_count   integer NOT NULL DEFAULT 0,
  max_attempts    integer NOT NULL DEFAULT 3,
  run_after       timestamptz NOT NULL DEFAULT now(),      -- retry backoff
  locked_at       timestamptz,
  locked_by       varchar(100),
  embedding_model varchar(150),
  passages_count  integer,
  last_error      text,
  requested_by_id uuid REFERENCES app_user(id) ON DELETE SET NULL,
  created_at      timestamptz NOT NULL DEFAULT now(),
  started_at      timestamptz,
  finished_at     timestamptz
);
CREATE INDEX ingestion_job_queue_idx ON ingestion_job (run_after) WHERE status = 'queued';
CREATE INDEX ingestion_job_document_idx ON ingestion_job (document_id, created_at DESC);
-- Idempotent enqueue: at most one live job per (document, action, version).
CREATE UNIQUE INDEX ingestion_job_live_key ON ingestion_job
  (document_id, action, coalesce(version_id, '00000000-0000-0000-0000-000000000000'::uuid))
  WHERE status IN ('queued','running');

-- DECIDE THE EMBEDDING DIMENSION BEFORE YOU RUN THIS. vector(1024) fits BGE-M3 and
-- multilingual-e5-large (verify against the model card). Changing it later = new column + full re-embedding.
-- pgvector HNSW/IVFFlat indexes on the plain vector type stop at 2000 dimensions.
CREATE TABLE passage (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_version_id uuid NOT NULL REFERENCES document_version(id) ON DELETE CASCADE,
  ingestion_job_id    uuid REFERENCES ingestion_job(id) ON DELETE SET NULL,
  institution_id      uuid REFERENCES institution(id) ON DELETE SET NULL,   -- copied at ingest, for IIT/ISB filtering
  program_id          uuid REFERENCES program(id) ON DELETE SET NULL,       -- copied at ingest: the SA-5 "program_id" citation
  chunk_index         integer NOT NULL CHECK (chunk_index >= 0),
  content             text NOT NULL,
  token_count         integer,
  page_start          integer,
  page_end            integer,
  language            varchar(20),
  metadata            jsonb NOT NULL DEFAULT '{}'::jsonb,
  embedding           vector(1024) NOT NULL,
  embedding_model     varchar(150) NOT NULL,                 -- never mix models in one index
  is_active           boolean NOT NULL DEFAULT false,        -- maintained by triggers, do not set by hand
  content_tsv         tsvector GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED,  -- hybrid search
  created_at          timestamptz NOT NULL DEFAULT now(),
  CHECK (page_end IS NULL OR page_start IS NULL OR page_end >= page_start),
  UNIQUE (document_version_id, chunk_index, embedding_model)            -- idempotent re-processing
);
CREATE INDEX passage_embedding_hnsw ON passage USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64) WHERE is_active;
CREATE INDEX passage_tsv_idx ON passage USING gin (content_tsv) WHERE is_active;
CREATE INDEX passage_version_idx ON passage (document_version_id);
CREATE INDEX passage_institution_idx ON passage (institution_id) WHERE is_active;
-- Query with "WHERE is_active" so the planner can use the partial indexes.

-- =====================================================================
-- 7. AUDIT (SA-4: "journal des actions des agents et des decisions humaines")
--    Append-only. No foreign keys on purpose: erasing a candidate must not rewrite history.
-- =====================================================================
CREATE TABLE audit_log (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  occurred_at   timestamptz NOT NULL DEFAULT now(),
  actor_type    text NOT NULL CHECK (actor_type IN ('user','agent','system')),
  actor_user_id uuid,
  actor_label   varchar(100),                              -- agent / job name
  action        varchar(100) NOT NULL,
  entity_type   varchar(60),
  entity_id     uuid,
  details       jsonb NOT NULL DEFAULT '{}'::jsonb,
  request_id    varchar(64),
  ip_hash       text
);
CREATE INDEX audit_log_entity_idx ON audit_log (entity_type, entity_id);
CREATE INDEX audit_log_time_idx ON audit_log (occurred_at);
CREATE INDEX audit_log_actor_idx ON audit_log (actor_user_id);

-- =====================================================================
-- 8. TRIGGERS: integrity rules that plain constraints cannot express
-- =====================================================================

-- updated_at maintenance
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['institution','app_user','candidate_profile','program','specialty','curriculum',
        'subject','admission_requirement','tuition_fee','preregistration','interview','document_source',
        'message_template','orientation_rule','system_setting','equivalence_request','handover']
  LOOP
    EXECUTE format('CREATE TRIGGER trg_%1$s_updated_at BEFORE UPDATE ON %1$I
                    FOR EACH ROW EXECUTE FUNCTION set_updated_at()', t);
  END LOOP;
END $$;

-- iit_manager must belong to IIT, isb_manager to ISB.
CREATE FUNCTION check_manager_institution() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE v_code text;
BEGIN
  IF NEW.role IN ('iit_manager','isb_manager') THEN
    SELECT code INTO v_code FROM institution WHERE id = NEW.institution_id;
    IF v_code IS DISTINCT FROM upper(split_part(NEW.role, '_', 1)) THEN
      RAISE EXCEPTION '% must belong to institution %', NEW.role, upper(split_part(NEW.role, '_', 1));
    END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_app_user_manager_institution
  BEFORE INSERT OR UPDATE OF role, institution_id ON app_user
  FOR EACH ROW EXECUTE FUNCTION check_manager_institution();

-- Every candidate account gets its profile row automatically (1:1 always holds).
CREATE FUNCTION create_candidate_profile() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  INSERT INTO candidate_profile (user_id) VALUES (NEW.id);
  RETURN NEW;
END $$;
CREATE TRIGGER trg_app_user_candidate_profile
  AFTER INSERT ON app_user
  FOR EACH ROW WHEN (NEW.role = 'candidate')
  EXECUTE FUNCTION create_candidate_profile();

-- Decisions must come from an allowed STAFF role, scoped to the right school.
-- args: (staff column, program column, comma-separated allowed roles)
CREATE FUNCTION enforce_staff_decision() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  j         jsonb  := to_jsonb(NEW);
  v_staff   uuid   := (j ->> TG_ARGV[0])::uuid;
  v_program uuid   := (j ->> TG_ARGV[1])::uuid;
  v_allowed text[] := string_to_array(TG_ARGV[2], ',');
  v_role text; v_inst uuid; v_prog_inst uuid;
BEGIN
  IF v_staff IS NULL THEN RETURN NEW; END IF;
  SELECT role, institution_id INTO v_role, v_inst FROM app_user WHERE id = v_staff;
  IF v_role IS NULL OR NOT (v_role = ANY (v_allowed)) THEN
    RAISE EXCEPTION '% on % requires one of (%), got %', TG_ARGV[0], TG_TABLE_NAME, TG_ARGV[2], v_role;
  END IF;
  IF v_role IN ('iit_manager','isb_manager') THEN
    SELECT institution_id INTO v_prog_inst FROM program WHERE id = v_program;
    IF v_prog_inst IS DISTINCT FROM v_inst THEN
      RAISE EXCEPTION 'a % can only act on programs of their own institution', v_role;
    END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_preregistration_decision BEFORE INSERT OR UPDATE ON preregistration
  FOR EACH ROW EXECUTE FUNCTION enforce_staff_decision('decided_by_id','program_id','iit_manager,isb_manager,interviewer,admin');
CREATE TRIGGER trg_equivalence_decision BEFORE INSERT OR UPDATE ON equivalence_request
  FOR EACH ROW EXECUTE FUNCTION enforce_staff_decision('decided_by_id','target_program_id','iit_manager,isb_manager,admin');
CREATE TRIGGER trg_recommendation_review BEFORE INSERT OR UPDATE ON recommendation
  FOR EACH ROW EXECUTE FUNCTION enforce_staff_decision('reviewed_by_id','program_id','iit_manager,isb_manager,admin');

-- Status history, written by the database so the app cannot forget it.
-- Optional: the API sets  SET LOCAL app.user_id = '<uuid>'  at the start of the transaction
-- to record who did it; unset = system/agent.
CREATE FUNCTION log_preregistration_status() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'INSERT' OR NEW.status IS DISTINCT FROM OLD.status THEN
    INSERT INTO preregistration_status_history (preregistration_id, from_status, to_status, changed_by_id)
    VALUES (NEW.id,
            CASE WHEN TG_OP = 'UPDATE' THEN OLD.status END,
            NEW.status,
            NULLIF(current_setting('app.user_id', true), '')::uuid);
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_preregistration_history
  AFTER INSERT OR UPDATE OF status ON preregistration
  FOR EACH ROW EXECUTE FUNCTION log_preregistration_status();

-- passage.is_active = "belongs to the current version of an ACTIVE document". Kept in sync both ways:
--   (a) new passages inherit the right value on insert (reindex of the live version works instantly)
--   (b) switching current_version_id / status flips every passage in one statement (atomic swap)
CREATE FUNCTION passage_default_active() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.is_active := EXISTS (
    SELECT 1 FROM document_source d
    WHERE d.current_version_id = NEW.document_version_id AND d.status = 'active');
  RETURN NEW;
END $$;
CREATE TRIGGER trg_passage_active BEFORE INSERT ON passage
  FOR EACH ROW EXECUTE FUNCTION passage_default_active();

CREATE FUNCTION sync_passage_activity() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  UPDATE passage p
     SET is_active = (NEW.status = 'active' AND p.document_version_id = NEW.current_version_id)
   WHERE p.document_version_id IN (SELECT id FROM document_version WHERE document_id = NEW.id)
     AND p.is_active IS DISTINCT FROM (NEW.status = 'active' AND p.document_version_id = NEW.current_version_id);
  RETURN NEW;
END $$;
CREATE TRIGGER trg_document_source_passages
  AFTER UPDATE OF current_version_id, status ON document_source
  FOR EACH ROW
  WHEN (OLD.current_version_id IS DISTINCT FROM NEW.current_version_id OR OLD.status IS DISTINCT FROM NEW.status)
  EXECUTE FUNCTION sync_passage_activity();

-- Audit log is append-only. (For a retention job: ALTER TABLE audit_log DISABLE TRIGGER ... in that job only.)
CREATE FUNCTION audit_log_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'audit_log is append-only';
END $$;
CREATE TRIGGER trg_audit_log_immutable BEFORE UPDATE OR DELETE ON audit_log
  FOR EACH ROW EXECUTE FUNCTION audit_log_immutable();

-- =====================================================================
-- 9. VIEWS for the Direction dashboard (aggregated only, never nominative: SA-5 rule)
-- =====================================================================
CREATE VIEW v_visitor_funnel AS
SELECT (SELECT count(*) FROM guest_session)                                  AS guest_sessions,
       (SELECT count(*) FROM guest_session WHERE claimed_at IS NOT NULL)     AS accounts_created,
       (SELECT count(DISTINCT candidate_id) FROM preregistration)            AS candidates_with_preregistration;

CREATE VIEW v_preregistration_funnel AS
SELECT i.code AS institution_code,
       p.academic_year,
       count(*)                                                        AS preregistrations,
       count(*) FILTER (WHERE r.qcm_completed)                         AS qcm_completed,
       count(*) FILTER (WHERE r.validated)                             AS validated,
       count(*) FILTER (WHERE r.interview_scheduled)                   AS interview_scheduled,
       count(*) FILTER (WHERE r.accepted)                              AS accepted,
       count(*) FILTER (WHERE r.enrolled)                              AS enrolled,
       count(*) FILTER (WHERE p.status IN ('withdrawn','abandoned'))   AS dropped_out
FROM preregistration p
JOIN program pr     ON pr.id = p.program_id
JOIN institution i  ON i.id = pr.institution_id
CROSS JOIN LATERAL (
  SELECT coalesce(bool_or(h.to_status = 'qcm_completed'), false)       AS qcm_completed,
         coalesce(bool_or(h.to_status = 'validated'), false)           AS validated,
         coalesce(bool_or(h.to_status = 'interview_scheduled'), false) AS interview_scheduled,
         coalesce(bool_or(h.to_status = 'accepted'), false)            AS accepted,
         coalesce(bool_or(h.to_status = 'enrolled'), false)            AS enrolled
  FROM preregistration_status_history h
  WHERE h.preregistration_id = p.id
) r
GROUP BY i.code, p.academic_year;

COMMIT;
