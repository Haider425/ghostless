-- Ghostless schema (PostgreSQL)

CREATE TABLE IF NOT EXISTS companies (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    platform    TEXT NOT NULL,
    board_slug  TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (platform, board_slug)
);

-- Recreated on every run so adding a platform also updates existing databases.
-- v1.4: website domain, for logos
ALTER TABLE companies ADD COLUMN IF NOT EXISTS domain TEXT;

ALTER TABLE companies DROP CONSTRAINT IF EXISTS companies_platform_check;
ALTER TABLE companies ADD CONSTRAINT companies_platform_check
    CHECK (platform IN ('greenhouse', 'lever', 'ashby', 'workday', 'amazon',
                        'eightfold', 'google', 'apple', 'sitemap', 'rss', 'list'));

-- v2.2: where a company came from. configured: companies.yaml. discovered: a
-- job board found through a public job list. list: only known through the
-- lists, whose entries are stored as they appear there.
ALTER TABLE companies ADD COLUMN IF NOT EXISTS origin TEXT NOT NULL DEFAULT 'configured';

CREATE TABLE IF NOT EXISTS jobs (
    id           BIGSERIAL PRIMARY KEY,
    company_id   INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    external_id  TEXT NOT NULL,
    title        TEXT NOT NULL,
    location     TEXT,
    department   TEXT,
    url          TEXT NOT NULL,
    description  TEXT,
    level        TEXT NOT NULL,   -- intern | new_grad | mid | senior
    role_type    TEXT NOT NULL,   -- sde | data_eng | data | other
    is_canada    BOOLEAN NOT NULL DEFAULT false,
    is_remote    BOOLEAN NOT NULL DEFAULT false,
    posted_at    TIMESTAMPTZ,
    first_seen   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen    TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_active    BOOLEAN NOT NULL DEFAULT true,
    closed_at    TIMESTAMPTZ,
    UNIQUE (company_id, external_id)
);

-- v1.1: disclosures and repost tracking. ADD COLUMN IF NOT EXISTS upgrades
-- existing databases in place; nothing already collected is lost.
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS salary_min      NUMERIC(12, 2);
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS salary_max      NUMERIC(12, 2);
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS salary_period   TEXT;     -- year | hour
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS salary_currency TEXT;     -- CAD | USD | NULL (not stated)
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS vacancy         TEXT;     -- existing | not_existing | NULL
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS ai_screening    BOOLEAN;  -- NULL means not disclosed
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS fingerprint     TEXT NOT NULL DEFAULT '';
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS reposted_from   BIGINT REFERENCES jobs(id) ON DELETE SET NULL;
-- v2.2: seasons ("Summer 2027") and, for jobs found in a public list, which one
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS terms     TEXT[] NOT NULL DEFAULT '{}';
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS listed_in TEXT;

-- Job boards found through public job lists, crawled on a rotation.
CREATE TABLE IF NOT EXISTS discovered_boards (
    platform      TEXT NOT NULL,
    board_slug    TEXT NOT NULL,
    company_name  TEXT NOT NULL,
    found_in      TEXT,
    first_seen    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_crawled  TIMESTAMPTZ,
    last_ok       TIMESTAMPTZ,
    failures      INTEGER NOT NULL DEFAULT 0,
    jobs_last     INTEGER,
    PRIMARY KEY (platform, board_slug)
);

CREATE INDEX IF NOT EXISTS idx_jobs_active_filters
    ON jobs (is_active, level, role_type) WHERE is_active;
CREATE INDEX IF NOT EXISTS idx_jobs_first_seen ON jobs (first_seen DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_fingerprint ON jobs (company_id, fingerprint);
CREATE INDEX IF NOT EXISTS idx_jobs_company_first_seen ON jobs (company_id, first_seen);

CREATE TABLE IF NOT EXISTS skills (
    id    SERIAL PRIMARY KEY,
    name  TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS job_skills (
    job_id    BIGINT  NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    skill_id  INTEGER NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    PRIMARY KEY (job_id, skill_id)
);

-- One row per pipeline run. These numbers become your résumé metrics.
CREATE TABLE IF NOT EXISTS ingest_runs (
    id                 SERIAL PRIMARY KEY,
    started_at         TIMESTAMPTZ NOT NULL,
    finished_at        TIMESTAMPTZ,
    companies_ok       INTEGER NOT NULL DEFAULT 0,
    companies_failed   INTEGER NOT NULL DEFAULT 0,
    jobs_seen          INTEGER NOT NULL DEFAULT 0,
    jobs_new           INTEGER NOT NULL DEFAULT 0,
    jobs_closed        INTEGER NOT NULL DEFAULT 0,
    duration_seconds   NUMERIC(10, 2)
);

-- ---------------------------------------------------------------------------
-- Views. Recreated on every run, so they always match the code.
-- ---------------------------------------------------------------------------

-- Ghost job signals: an explainable risk level plus the reasons behind it.
--
--   age_known            false when the job was already open when tracking of
--                        its company began, so days_open is only a lower bound
--   days_open            days from first seen to closed (or to now)
--   typical_days_open    median for closed postings of the same company and
--                        role type (needs 5+ closed postings, else NULL)
--   times_posted_before  earlier postings of the same role at the same company
--   flags                not_existing_vacancy | reposted | duplicate_posting |
--                        open_unusually_long
--   ghost_risk           high (employer says no vacancy, or 2+ flags),
--                        medium (1 flag), low (no flags)
DROP MATERIALIZED VIEW IF EXISTS job_signals_mv;
DROP VIEW IF EXISTS job_signals;
CREATE VIEW job_signals AS
WITH tracking AS (
    SELECT company_id, min(first_seen) AS tracking_start
    FROM jobs GROUP BY company_id
),
typical AS (
    SELECT j.company_id, j.role_type,
           percentile_cont(0.5) WITHIN GROUP (
               ORDER BY extract(epoch FROM j.closed_at - j.first_seen) / 86400
           ) AS median_days
    FROM jobs j JOIN tracking t USING (company_id)
    WHERE j.closed_at IS NOT NULL AND j.first_seen > t.tracking_start
    GROUP BY j.company_id, j.role_type
    HAVING count(*) >= 5
),
base AS (
    SELECT j.id, j.company_id, j.role_type, j.vacancy, j.is_active, j.reposted_from,
           -- a job list dates its entries, so those postings' age is known from the start
           (j.first_seen > t.tracking_start OR (j.listed_in IS NOT NULL AND j.posted_at IS NOT NULL)) AS age_known,
           floor(extract(epoch FROM coalesce(j.closed_at, now()) - CASE
               WHEN j.listed_in IS NOT NULL AND j.posted_at < j.first_seen THEN j.posted_at
               ELSE j.first_seen END) / 86400)::int AS days_open,
           round(ty.median_days)::int AS typical_days_open,
           (SELECT count(*) FROM jobs p
             WHERE p.company_id = j.company_id AND p.fingerprint = j.fingerprint
               AND j.fingerprint <> '' AND p.first_seen < j.first_seen)::int AS times_posted_before,
           -- duplicates need a description in the fingerprint: title and
           -- location alone can't tell apart different teams' roles
           (SELECT count(*) FROM jobs d
             WHERE d.company_id = j.company_id AND d.fingerprint = j.fingerprint
               AND j.fingerprint ~ '\|[0-9a-f]{12}$' AND d.id <> j.id
               AND d.is_active AND j.is_active)::int
               AS active_duplicates
    FROM jobs j
    JOIN tracking t USING (company_id)
    LEFT JOIN typical ty ON ty.company_id = j.company_id AND ty.role_type = j.role_type
),
flagged AS (
    SELECT b.*,
           array_remove(ARRAY[
               CASE WHEN b.vacancy = 'not_existing' THEN 'not_existing_vacancy' END,
               CASE WHEN b.times_posted_before > 0 OR b.reposted_from IS NOT NULL THEN 'reposted' END,
               CASE WHEN b.active_duplicates > 0 THEN 'duplicate_posting' END,
               -- a lower-bound age that already exceeds the limit is still a valid signal
               CASE WHEN b.days_open > greatest(60, 2 * coalesce(b.typical_days_open, 45))
                    THEN 'open_unusually_long' END
           ], NULL) AS flags
    FROM base b
)
SELECT id AS job_id, company_id, age_known, days_open, typical_days_open,
       times_posted_before, active_duplicates, reposted_from, flags,
       CASE
           WHEN 'not_existing_vacancy' = ANY(flags) OR cardinality(flags) >= 2 THEN 'high'
           WHEN cardinality(flags) = 1 THEN 'medium'
           ELSE 'low'
       END AS ghost_risk
FROM flagged;

-- Cached copy of job_signals for the API. Computing signals means scanning
-- every job, so it is done once per ingest run (REFRESH at the end of each
-- run) instead of on every request. The unique index allows REFRESH
-- CONCURRENTLY, which keeps the cache readable while it updates.
CREATE MATERIALIZED VIEW job_signals_mv AS
SELECT *, now() AS computed_at FROM job_signals;
CREATE UNIQUE INDEX job_signals_mv_job_id ON job_signals_mv (job_id);
CREATE INDEX job_signals_mv_risk ON job_signals_mv (ghost_risk);

-- Hiring calendar: when each employer opened intern and new grad roles, by
-- year. Only postings first seen after tracking began count, because older
-- ones have no reliable open date. Next year's opening is usually close to
-- this year's first_opened. Dates are in Toronto time, independent of the
-- database's session timezone.
DROP VIEW IF EXISTS hiring_calendar;
CREATE VIEW hiring_calendar AS
WITH tracking AS (
    SELECT company_id, min(first_seen) AS tracking_start
    FROM jobs GROUP BY company_id
),
local AS (
    SELECT j.*, (j.first_seen AT TIME ZONE 'America/Toronto') AS seen_local
    FROM jobs j
    JOIN tracking t ON t.company_id = j.company_id
    WHERE j.first_seen > t.tracking_start
      AND j.level IN ('intern', 'new_grad')
)
SELECT c.name AS company,
       l.level,
       l.role_type,
       extract(year FROM l.seen_local)::int AS year,
       min(l.seen_local)::date AS first_opened,
       max(l.seen_local)::date AS last_opened,
       count(*)::int AS postings
FROM local l
JOIN companies c ON c.id = l.company_id
GROUP BY c.name, l.level, l.role_type, extract(year FROM l.seen_local);

-- ---------------------------------------------------------------------------
-- v2.0: accounts, resumes, reports and first-party analytics.
-- Personal data lives only in these tables. Deleting a user deletes their
-- sessions, saved jobs and resumes, and removes their email from reports.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS users (
    id                 BIGSERIAL PRIMARY KEY,
    email              TEXT NOT NULL,
    password_hash      TEXT NOT NULL,
    name               TEXT,
    role               TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
    email_verified_at  TIMESTAMPTZ,
    settings           JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_active_at     TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS users_email_lower ON users (lower(email));

-- v2.1: accounts made with Google or GitHub have no password until they set one.
ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL;

-- Google and GitHub identities linked to an account. `subject` is the
-- provider's permanent id for the person (their email can change).
CREATE TABLE IF NOT EXISTS oauth_accounts (
    provider    TEXT NOT NULL CHECK (provider IN ('google', 'github')),
    subject     TEXT NOT NULL,
    user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    email       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (provider, subject),
    UNIQUE (user_id, provider)
);

-- Session tokens are stored hashed, so a database leak doesn't hand out logins.
CREATE TABLE IF NOT EXISTS sessions (
    token_hash    TEXT PRIMARY KEY,
    user_id       BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at    TIMESTAMPTZ NOT NULL,
    user_agent    TEXT
);
CREATE INDEX IF NOT EXISTS sessions_user ON sessions (user_id);

-- One-time links for email verification and password reset, also hashed.
CREATE TABLE IF NOT EXISTS email_tokens (
    token_hash  TEXT PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    purpose     TEXT NOT NULL CHECK (purpose IN ('verify', 'reset')),
    expires_at  TIMESTAMPTZ NOT NULL,
    used_at     TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS saved_jobs (
    user_id   BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    job_id    BIGINT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    saved_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, job_id)
);
-- Application tracking: where each saved job stands, with private notes.
ALTER TABLE saved_jobs ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'saved';
ALTER TABLE saved_jobs ADD COLUMN IF NOT EXISTS notes TEXT;
ALTER TABLE saved_jobs ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE saved_jobs DROP CONSTRAINT IF EXISTS saved_jobs_status_check;
ALTER TABLE saved_jobs ADD CONSTRAINT saved_jobs_status_check
    CHECK (status IN ('saved', 'applied', 'interviewing', 'offer', 'rejected'));

-- Uploaded resumes keep their extracted text and profile, never the file.
-- Built resumes keep the builder document.
CREATE TABLE IF NOT EXISTS resumes (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL CHECK (kind IN ('upload', 'built')),
    title       TEXT NOT NULL,
    file_name   TEXT,
    text        TEXT,
    profile     JSONB,
    document    JSONB,
    is_primary  BOOLEAN NOT NULL DEFAULT false,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS resumes_user ON resumes (user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS reports (
    id           BIGSERIAL PRIMARY KEY,
    user_id      BIGINT REFERENCES users(id) ON DELETE SET NULL,
    email        TEXT,
    category     TEXT NOT NULL,
    message      TEXT NOT NULL,
    page         TEXT,
    job_id       BIGINT REFERENCES jobs(id) ON DELETE SET NULL,
    status       TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'in_progress', 'resolved', 'dismissed')),
    admin_note   TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at  TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS reports_status ON reports (status, created_at DESC);

-- First-party analytics. No cookies: `visitor` is a hash of IP address, user
-- agent and a salt that changes daily, so visits can be counted for a day
-- but never followed across days or linked to a person.
CREATE TABLE IF NOT EXISTS events (
    id          BIGSERIAL PRIMARY KEY,
    kind        TEXT NOT NULL,
    path        TEXT,
    referrer    TEXT,
    visitor     TEXT,
    user_id     BIGINT REFERENCES users(id) ON DELETE SET NULL,
    detail      JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS events_kind_time ON events (kind, created_at DESC);
CREATE INDEX IF NOT EXISTS events_user_kind ON events (user_id, kind, created_at DESC) WHERE user_id IS NOT NULL;
