-- SA-26 : mémoire temporaire des conversations.
-- profile_draft = état visiteur consolidé au fil de l'eau par l'agent
-- (langue détectée, niveau d'études, centres d'intérêt, institutions IIT/ISB).
-- Rattaché à `conversation` (et non à une table dédiée) : le claim SA-29 le
-- fusionnera dans candidate_profile sans changer de support.
ALTER TABLE conversation
  ADD COLUMN profile_draft jsonb NOT NULL DEFAULT '{}'::jsonb;
