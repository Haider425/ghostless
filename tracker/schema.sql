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
ALTER TABLE companies DROP CONSTRAINT IF EXISTS companies_platform_check;
ALTER TABLE companies ADD CONSTRAINT companies_platform_check
    CHECK (platform IN ('greenhouse', 'lever', 'ashby', 'workday', 'amazon',
                        'eightfold', 'google', 'apple', 'sitemap', 'rss'));

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

CREATE INDEX IF NOT EXISTS idx_jobs_active_filters
    ON jobs (is_active, level, role_type) WHERE is_active;
CREATE INDEX IF NOT EXISTS idx_jobs_first_seen ON jobs (first_seen DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_fingerprint ON jobs (company_id, fingerprint);

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
           j.first_seen > t.tracking_start AS age_known,
           floor(extract(epoch FROM coalesce(j.closed_at, now()) - j.first_seen) / 86400)::int AS days_open,
           round(ty.median_days)::int AS typical_days_open,
           (SELECT count(*) FROM jobs p
             WHERE p.company_id = j.company_id AND p.fingerprint = j.fingerprint
               AND j.fingerprint <> '' AND p.first_seen < j.first_seen)::int AS times_posted_before,
           (SELECT count(*) FROM jobs d
             WHERE d.company_id = j.company_id AND d.fingerprint = j.fingerprint
               AND j.fingerprint <> '' AND d.id <> j.id AND d.is_active AND j.is_active)::int
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

-- Hiring calendar: when each employer opened intern and new grad roles, by
-- year. Only postings first seen after tracking began count, because older
-- ones have no reliable open date. Next year's opening is usually close to
-- this year's first_opened.
DROP VIEW IF EXISTS hiring_calendar;
CREATE VIEW hiring_calendar AS
WITH tracking AS (
    SELECT company_id, min(first_seen) AS tracking_start
    FROM jobs GROUP BY company_id
)
SELECT c.name AS company,
       j.level,
       j.role_type,
       extract(year FROM j.first_seen)::int AS year,
       min(j.first_seen)::date AS first_opened,
       max(j.first_seen)::date AS last_opened,
       count(*)::int AS postings
FROM jobs j
JOIN companies c ON c.id = j.company_id
JOIN tracking t ON t.company_id = j.company_id
WHERE j.first_seen > t.tracking_start
  AND j.level IN ('intern', 'new_grad')
GROUP BY c.name, j.level, j.role_type, extract(year FROM j.first_seen);
