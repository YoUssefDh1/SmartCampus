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
