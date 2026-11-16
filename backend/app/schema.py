"""Relational schema. JSON payloads are stored as TEXT (portable); everything queried/filtered is a real column."""

TABLES = """
CREATE TABLE IF NOT EXISTS organizations (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at {TS} NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS ux_org_name ON organizations(LOWER(name));

CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('candidate','recruiter','admin')),
  status TEXT NOT NULL CHECK (status IN ('active','pending','suspended')),
  failed_logins INTEGER NOT NULL DEFAULT 0,
  locked_until {TS},
  created_at {TS} NOT NULL, last_login_at {TS});
CREATE UNIQUE INDEX IF NOT EXISTS ux_users_email ON users(email);
CREATE INDEX IF NOT EXISTS ix_users_role_status ON users(role, status);

CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  csrf_token TEXT NOT NULL, ip TEXT, user_agent TEXT,
  created_at {TS} NOT NULL, expires_at {TS} NOT NULL);
CREATE INDEX IF NOT EXISTS ix_sessions_user ON sessions(user_id);

CREATE TABLE IF NOT EXISTS recruiters (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
  organization_id TEXT NOT NULL REFERENCES organizations(id),
  full_name TEXT NOT NULL, approved_by TEXT, approved_at {TS});
CREATE INDEX IF NOT EXISTS ix_recruiters_org ON recruiters(organization_id);

CREATE TABLE IF NOT EXISTS candidates (
  id TEXT PRIMARY KEY,
  user_id TEXT UNIQUE REFERENCES users(id) ON DELETE SET NULL,
  managed_by_org_id TEXT REFERENCES organizations(id) ON DELETE SET NULL,
  email TEXT NOT NULL, full_name TEXT NOT NULL, phone TEXT,
  profile TEXT, profile_status TEXT NOT NULL DEFAULT 'empty'
     CHECK (profile_status IN ('empty','draft','confirmed')),
  total_years REAL, top_skills TEXT,
  created_at {TS} NOT NULL, updated_at {TS} NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS ux_cand_email ON candidates(email);
CREATE INDEX IF NOT EXISTS ix_cand_name ON candidates(LOWER(full_name));
CREATE INDEX IF NOT EXISTS ix_cand_org ON candidates(managed_by_org_id, created_at);
CREATE INDEX IF NOT EXISTS ix_cand_created ON candidates(created_at);

CREATE TABLE IF NOT EXISTS cvs (
  id TEXT PRIMARY KEY,
  candidate_id TEXT NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
  storage_key TEXT NOT NULL, original_name TEXT NOT NULL, mime TEXT NOT NULL,
  size INTEGER NOT NULL, sha256 TEXT NOT NULL,
  stage TEXT NOT NULL DEFAULT 'uploaded'
     CHECK (stage IN ('uploaded','extracting','analysing','ready','failed')),
  error_code TEXT, error_message TEXT,
  extracted_text TEXT, extraction TEXT,
  created_at {TS} NOT NULL, updated_at {TS} NOT NULL);
CREATE INDEX IF NOT EXISTS ix_cvs_cand ON cvs(candidate_id, created_at);

CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL REFERENCES organizations(id),
  created_by TEXT NOT NULL REFERENCES users(id),
  title TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'job' CHECK (kind IN ('job','competition')),
  description TEXT NOT NULL DEFAULT '',
  required_skills TEXT NOT NULL, preferred_skills TEXT NOT NULL DEFAULT '[]',
  custom_requirements TEXT NOT NULL DEFAULT '[]',
  min_years REAL NOT NULL DEFAULT 0, education_level TEXT NOT NULL DEFAULT 'none',
  task_brief TEXT, status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('draft','open','closed')),
  deadline TEXT, created_at {TS} NOT NULL, updated_at {TS} NOT NULL);
CREATE INDEX IF NOT EXISTS ix_jobs_org_status ON jobs(organization_id, status, created_at);

CREATE TABLE IF NOT EXISTS applications (
  id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  candidate_id TEXT NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
  cv_id TEXT REFERENCES cvs(id) ON DELETE SET NULL,
  status TEXT NOT NULL DEFAULT 'applied',
  match_score REAL, final_decision TEXT,
  created_at {TS} NOT NULL, updated_at {TS} NOT NULL,
  UNIQUE (job_id, candidate_id));
CREATE INDEX IF NOT EXISTS ix_app_job_status ON applications(job_id, status);
CREATE INDEX IF NOT EXISTS ix_app_job_score ON applications(job_id, match_score);
CREATE INDEX IF NOT EXISTS ix_app_cand ON applications(candidate_id);

CREATE TABLE IF NOT EXISTS assessments (
  id TEXT PRIMARY KEY,
  application_id TEXT NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
  attempt INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'draft'
     CHECK (status IN ('generating','draft','sent','started','submitted','evaluated','failed')),
  task TEXT, minutes INTEGER NOT NULL DEFAULT 45, model TEXT,
  sent_at {TS}, started_at {TS}, submitted_at {TS}, due_at {TS},
  created_at {TS} NOT NULL,
  UNIQUE (application_id, attempt));

CREATE TABLE IF NOT EXISTS assessment_responses (
  id TEXT PRIMARY KEY,
  assessment_id TEXT NOT NULL UNIQUE REFERENCES assessments(id) ON DELETE CASCADE,
  answers TEXT NOT NULL, saved_at {TS} NOT NULL, submitted_at {TS});

CREATE TABLE IF NOT EXISTS evaluations (
  id TEXT PRIMARY KEY,
  assessment_id TEXT NOT NULL UNIQUE REFERENCES assessments(id) ON DELETE CASCADE,
  result TEXT NOT NULL, overall REAL NOT NULL, confidence REAL NOT NULL,
  needs_attention INTEGER NOT NULL DEFAULT 0,
  model TEXT NOT NULL, prompt_version TEXT NOT NULL, created_at {TS} NOT NULL);

CREATE TABLE IF NOT EXISTS matches (
  id TEXT PRIMARY KEY,
  application_id TEXT NOT NULL UNIQUE REFERENCES applications(id) ON DELETE CASCADE,
  score REAL NOT NULL, provisional INTEGER NOT NULL DEFAULT 1,
  breakdown TEXT NOT NULL, ai_analysis TEXT, computed_at {TS} NOT NULL);

CREATE TABLE IF NOT EXISTS reviews (
  id TEXT PRIMARY KEY,
  application_id TEXT NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
  reviewer_id TEXT NOT NULL REFERENCES users(id),
  task_score REAL, note TEXT NOT NULL DEFAULT '', decision TEXT,
  created_at {TS} NOT NULL);
CREATE INDEX IF NOT EXISTS ix_reviews_app ON reviews(application_id, created_at);

CREATE TABLE IF NOT EXISTS activity_logs (
  id TEXT PRIMARY KEY,
  actor_id TEXT, actor_role TEXT, action TEXT NOT NULL,
  entity_type TEXT, entity_id TEXT, detail TEXT, ip TEXT,
  created_at {TS} NOT NULL);
CREATE INDEX IF NOT EXISTS ix_log_entity ON activity_logs(entity_type, entity_id, created_at);
CREATE INDEX IF NOT EXISTS ix_log_actor ON activity_logs(actor_id, created_at);

CREATE TABLE IF NOT EXISTS task_queue (
  id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','done','failed')),
  attempts INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL DEFAULT 3,
  run_after {TS} NOT NULL, last_error TEXT, locked_at {TS}, created_at {TS} NOT NULL);
CREATE INDEX IF NOT EXISTS ix_queue_pick ON task_queue(status, run_after, created_at);

CREATE TABLE IF NOT EXISTS email_outbox (
  id TEXT PRIMARY KEY, to_email TEXT NOT NULL, subject TEXT NOT NULL, body TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','sent','failed')),
  error TEXT, created_at {TS} NOT NULL, sent_at {TS});
"""


# Versioned changes applied after the baseline TABLES. Never edit an applied entry: append a new one.
# Each entry: (version, description, SQL). {TS} is expanded per database.
MIGRATIONS = [
    (1, "shared rate-limit counters", """
CREATE TABLE IF NOT EXISTS rate_hits (key TEXT NOT NULL, ts DOUBLE PRECISION NOT NULL);
CREATE INDEX IF NOT EXISTS ix_rate_key_ts ON rate_hits(key, ts);
"""),
    (2, "jobs: automatic assessment on apply", """
ALTER TABLE jobs ADD COLUMN auto_assessment INTEGER NOT NULL DEFAULT 0;
"""),
    # Identity + reproducibility. Every column is nullable so existing rows stay valid; app.backfill fills them in.
    (3, "CV ownership checks, application snapshots, scoring state and score history", """
ALTER TABLE cvs ADD COLUMN identity_status TEXT;
ALTER TABLE cvs ADD COLUMN identity_detail TEXT;
ALTER TABLE candidates ADD COLUMN active_cv_id TEXT;
ALTER TABLE applications ADD COLUMN profile_snapshot TEXT;
ALTER TABLE applications ADD COLUMN cv_match_score REAL;
ALTER TABLE applications ADD COLUMN scoring_version TEXT;
ALTER TABLE assessments ADD COLUMN eval_status TEXT;
ALTER TABLE assessments ADD COLUMN eval_error TEXT;
ALTER TABLE assessment_responses ADD COLUMN task_hash TEXT;
CREATE TABLE IF NOT EXISTS match_history (
  id TEXT PRIMARY KEY,
  application_id TEXT NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
  score REAL NOT NULL, breakdown TEXT NOT NULL, computed_at {TS} NOT NULL,
  replaced_at {TS} NOT NULL, reason TEXT);
CREATE INDEX IF NOT EXISTS ix_match_hist_app ON match_history(application_id, replaced_at);
"""),
    (4, "email outbox: message kind and delivery result", """
ALTER TABLE email_outbox ADD COLUMN kind TEXT;
ALTER TABLE email_outbox ADD COLUMN delivery TEXT;
"""),
    # Evidence for a human reviewer only: never read by the scoring code, never changes a stage.
    (5, "originality checks (CV similarity, answer plagiarism) and skill-test size per opening", """
CREATE TABLE IF NOT EXISTS originality_checks (
  id TEXT PRIMARY KEY,
  application_id TEXT NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
  kind TEXT NOT NULL CHECK (kind IN ('cv','answers')),
  level TEXT NOT NULL CHECK (level IN ('none','low','medium','high')),
  score REAL NOT NULL DEFAULT 0,
  detail TEXT NOT NULL, evidence_hash TEXT,
  verdict TEXT CHECK (verdict IN ('cleared','confirmed')), verdict_note TEXT, verdict_by TEXT, verdict_at {TS},
  computed_at {TS} NOT NULL,
  UNIQUE (application_id, kind));
CREATE INDEX IF NOT EXISTS ix_orig_kind_level ON originality_checks(kind, level);
ALTER TABLE jobs ADD COLUMN test_questions INTEGER NOT NULL DEFAULT 4;
"""),
    (6, "follow-up messages from a reviewer are linked to their application", """
ALTER TABLE email_outbox ADD COLUMN application_id TEXT;
ALTER TABLE email_outbox ADD COLUMN sender_id TEXT;
CREATE INDEX IF NOT EXISTS ix_outbox_app ON email_outbox(application_id, created_at);
"""),
    (7, "how a test was taken: counts and durations only (left the page, pasted, typed)", """
CREATE TABLE IF NOT EXISTS assessment_events (
  id TEXT PRIMARY KEY,
  assessment_id TEXT NOT NULL REFERENCES assessments(id) ON DELETE CASCADE,
  kind TEXT NOT NULL CHECK (kind IN ('left_page','pointer_out','paste','typed')),
  question_id TEXT, seconds REAL, chars INTEGER,
  at {TS} NOT NULL);
CREATE INDEX IF NOT EXISTS ix_events_assessment ON assessment_events(assessment_id, at);
"""),
]


def migration_statements(sql, pg):
    sql = sql.replace("{TS}", "TIMESTAMPTZ" if pg else "TEXT")
    return [x.strip() for x in sql.split(";") if x.strip()]


def ddl(pg):
    ts = "TIMESTAMPTZ" if pg else "TEXT"
    sql = TABLES.replace("{TS}", ts)
    return [s.strip() for s in sql.split(";") if s.strip()]
