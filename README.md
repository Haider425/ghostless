# Ghostless

[![CI](https://github.com/Haider425/ghostless/actions/workflows/ci.yml/badge.svg)](https://github.com/Haider425/ghostless/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**Honest job data for Canadian tech students:** real postings, true dates, and when companies actually hire.

A daily pipeline that collects tech job postings from **54 employers across 10 career platforms** (big tech, Canadian banks, and high-growth tech companies) and keeps the full history of every posting. That history powers what other job tools don't offer:

- **Ghost job signals.** Every posting gets an explainable risk level based on reposts, duplicate listings, unusually long open times, and the employer's own "not an existing vacancy" disclosure.
- **True first-seen dates**, instead of the refreshed "posted 2 days ago" dates that reposted listings show.
- **Ontario disclosures.** Pay ranges, existing vacancy statements, and AI screening disclosures, which Ontario has required in job postings since January 1, 2026, extracted into structured fields.
- **A hiring calendar** showing when each employer actually opened its intern and new grad roles, so you can be ready next year.
- **A skills gap check** comparing your skills with what current postings ask for.
- **Canada first**, including TD, RBC, BMO, CIBC, Scotiabank, Manulife and Sun Life, which US-focused internship lists mostly leave out.

## Quick start

You need Python 3.10+ and Docker (for PostgreSQL).

```bash
git clone https://github.com/Haider425/ghostless.git
cd ghostless
pip install -e .
cp .env.example .env          # then set GHOSTLESS_CONTACT to your own URL or email
docker compose up -d db       # local PostgreSQL

ghostless verify             # check that every source works
ghostless ingest             # collect postings into the database
ghostless gap --have "Python, SQL, React"   # see which in-demand skills you're missing
```

No Python? Run it all in Docker:

```bash
docker compose --profile app run --rm ghostless verify
docker compose --profile app run --rm ghostless ingest
```

## Commands

| Command | What it does |
|---|---|
| `ghostless verify` | Checks every source and prints OK (with a job count), WARN (0 jobs), or FAIL (with the reason). Fast: skips per-job detail requests. |
| `ghostless ingest` | Runs the full pipeline into PostgreSQL. |
| `ghostless gap --have "..."` | Ranks the skills that active postings ask for and marks which ones you have. Defaults to intern and new grad software roles in Canada or remote; change with `--role`, `--level` (both repeatable) and `--anywhere`. |
| `--only <company>` | Runs for one company, by name or slug, e.g. `--only "Capital One"`. |
| `--dump [DIR]` | Saves every raw response to `DIR` (default `.debug/`) so you can see exactly what a site returned. |
| `-v` | Detailed logs. |

## Configuration

| Setting | Where | Purpose |
|---|---|---|
| `DATABASE_URL` | `.env` | PostgreSQL connection string |
| `GHOSTLESS_CONTACT` | `.env` | Your URL or email, sent in the User-Agent so site owners can reach you |
| `GHOSTLESS_COMPANIES` | `.env` | Optional path to a different companies file |
| `companies.yaml` | repo root | Which employers to track |

To track a new employer, add it to `companies.yaml`; [CONTRIBUTING.md](CONTRIBUTING.md) shows how to find its platform and slug in under a minute.

## Sources

| Platform | Employers | Method | Descriptions |
|---|---|---|---|
| `greenhouse` | Stripe, Airbnb, Databricks, Datadog, Anthropic, +21 | Public board API | Full |
| `ashby` | OpenAI, Plaid, Wealthsimple, Cohere, +3 | Public board API | Full |
| `lever` | Palantir, Spotify | Public board API | Full |
| `workday` | TD, RBC, BMO, CIBC, Manulife, Sun Life, Nvidia, Salesforce, Adobe, Intel, +3 | Career site JSON API | Relevant roles |
| `amazon` | Amazon | amazon.jobs search JSON | Full |
| `eightfold` | Microsoft | Career site JSON API | Relevant roles |
| `google` | Google | HTML, first results page per search | Relevant roles |
| `apple` | Apple | Data embedded in result pages | Summaries |
| `sitemap` | Shopify | Careers XML sitemap | None |
| `rss` | Scotiabank | SAP SuccessFactors RSS feed | Full |

"Relevant roles" means descriptions are fetched only for tech roles in Canada, remote, or with an unknown location, which keeps request volume low on employers with thousands of postings.

**Not included: Meta.** metacareers.com's robots.txt prohibits automated collection without written permission.

## How the signals work

### Ghost job risk (`job_signals` view)

Each posting gets `ghost_risk` (`low`, `medium`, `high`) plus the `flags` behind it, so a user always sees *why*:

| Flag | Meaning |
|---|---|
| `not_existing_vacancy` | The employer's own posting says it is not for an existing vacancy (for example, a talent pool). Always high risk. |
| `reposted` | The same role at the same company was posted before, usually taken down and put back up under a new id. |
| `duplicate_posting` | Identical copies of the role are live at the same time. |
| `open_unusually_long` | Open longer than 60 days and more than twice that company's typical time for the role type. |

Two or more flags means high risk. A posting counts as "the same role" only when its title, location **and description** match after requisition ids and dates are removed, so large employers posting many different roles under one title are not falsely flagged. `age_known` is false for postings that were already open when tracking began; their `days_open` is a lower bound.

These are signals, not verdicts: a long-open posting can be a genuine hard-to-fill role.

### Ontario disclosures (`jobs` columns)

| Column | Values |
|---|---|
| `salary_min`, `salary_max`, `salary_period`, `salary_currency` | Parsed pay range; currency is `CAD` when stated or when a Canada-only posting uses `$` |
| `vacancy` | `existing`, `not_existing`, or `NULL` when the posting does not say |
| `ai_screening` | `true`, `false`, or `NULL` when not disclosed |

`NULL` always means "not stated", never "no".

### Hiring calendar (`hiring_calendar` view)

For each employer, level, role type and year: the date the first intern or new grad posting appeared and how many followed. Only postings first seen after tracking began count, since older ones have no reliable open date. This needs a year of daily runs to become a forecast, which is why starting the scheduled run early matters.

## Architecture

```
companies.yaml
      │
      ▼
┌───────────────────┐   one adapter per platform, one entry point:
│  tracker/sources  │   fetch_jobs(company) -> list[Job]
└─────────┬─────────┘
          │  every request goes through sources/http.py:
          │  robots.txt check → per-host pacing → retries / Retry-After → optional dump
          ▼
┌───────────────────┐
│ classify + skills │   level, role type, Canada / remote, 40+ skills
└─────────┬─────────┘
          ▼
┌───────────────────┐
│    PostgreSQL     │   idempotent upserts, closure tracking, run metrics
└───────────────────┘
```

| Table | Contents |
|---|---|
| `companies` | Tracked employers |
| `jobs` | Every posting: title, location, level, role type, disclosures, first seen, last seen, closed at, repost link |
| `skills`, `job_skills` | Skills extracted from each posting |
| `ingest_runs` | Per-run stats: companies ok / failed, jobs seen / new / closed, duration |
| `job_signals` (view) | Ghost risk, flags, days open, repost history for every posting |
| `hiring_calendar` (view) | When each employer opened intern and new grad roles, by year |

## Design decisions

- **Responsible collection is enforced in code.** Adapters never call `requests` directly; one HTTP layer checks robots.txt before every request. Python's built-in robots parser ignores the `*` and `$` wildcards real sites use, so `sources/robots.py` implements RFC 9309 matching (longest rule wins, Allow wins ties, an unreachable robots.txt means disallow).
- **Rate limits are handled adaptively.** Requests to each host are spaced out. On HTTP 429 the pipeline honours the server's `Retry-After` header and doubles that host's spacing for the rest of the run.
- **Idempotent upserts.** Postings are keyed on `(company_id, external_id)`, so reruns never duplicate data and `first_seen` is never overwritten.
- **Closure tracking with two safety rules.** A posting missing from today's fetch is marked closed only (1) after a *successful* fetch, so an outage never closes a company's jobs, and (2) for sources that return the *complete* listing. Google's robots.txt disallows paging, so its listing is partial and its jobs are never auto-closed.
- **Fault isolation.** One database transaction per company; a failed detail request keeps the job instead of failing the company.
- **Resilient parsers for HTML sources.** The Apple adapter tries embedded JSON first, then HTML links, then escaped links in scripts, so small markup changes do not break it.
- **Rules, not an LLM, for classification.** Regex rules are fast, free, deterministic, and every rule is unit tested, including edge cases like Java vs JavaScript, the word "go", and GitHub vs Git.

## Example queries

```sql
-- Fresh, low-risk new grad and intern postings in Canada, newest first
SELECT c.name, j.title, j.location, j.first_seen::date, j.salary_min, j.salary_max, j.url
FROM jobs j
JOIN companies c ON c.id = j.company_id
JOIN job_signals s ON s.job_id = j.id
WHERE j.is_active AND j.is_canada AND j.level IN ('intern', 'new_grad')
  AND s.ghost_risk = 'low'
ORDER BY j.first_seen DESC;

-- Employers with the most high-risk postings right now
SELECT c.name, count(*) FILTER (WHERE s.ghost_risk = 'high') AS high_risk, count(*) AS active
FROM jobs j JOIN companies c ON c.id = j.company_id JOIN job_signals s ON s.job_id = j.id
WHERE j.is_active GROUP BY c.name ORDER BY high_risk DESC;

-- When did each employer open its intern roles?
SELECT company, role_type, year, first_opened, postings
FROM hiring_calendar WHERE level = 'intern' ORDER BY first_opened;

-- Top skills in active new grad / intern software postings in Canada or remote
SELECT s.name, COUNT(*) AS postings
FROM jobs j
JOIN job_skills js ON js.job_id = j.id
JOIN skills s ON s.id = js.skill_id
WHERE j.is_active AND j.level IN ('intern', 'new_grad') AND j.role_type = 'sde'
  AND (j.is_canada OR j.is_remote)
GROUP BY s.name ORDER BY postings DESC LIMIT 20;

-- Median days a posting stays open, by role type
SELECT role_type,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY closed_at - first_seen) AS median_open
FROM jobs WHERE closed_at IS NOT NULL GROUP BY role_type;

-- Employers that opened the most intern postings in the last 30 days
SELECT c.name, COUNT(*) AS new_intern_postings
FROM jobs j JOIN companies c ON c.id = j.company_id
WHERE j.level = 'intern' AND j.first_seen > now() - interval '30 days'
GROUP BY c.name ORDER BY 2 DESC;
```

## Run it daily

1. Create a free PostgreSQL database on [Neon](https://neon.tech) or [Supabase](https://supabase.com).
2. In your fork, add its connection string as a repository secret named `DATABASE_URL`.
3. The `Daily ingest` workflow runs every morning. Trigger it by hand from the Actions tab to test.

A full run takes several minutes, because large employers have thousands of postings and requests are deliberately paced.

## Known limitations

- Google and Apple are parsed from HTML. If either changes its pages, `verify` reports WARN; `--dump` saves the response so the parser can be updated.
- Google coverage is limited to the first results page of each configured search.
- Shopify's sitemap has no descriptions or locations, so its postings have no extracted skills and use the configured `region`.
- Classification and disclosure parsing are rule based, so unusual wording can be missed. Fixes are a new rule plus a test case.
- Repost detection needs sources with descriptions and complete listings, so it does not apply to Google, and it is weaker for Apple and Shopify.

## Roadmap

- [x] Ingestion for 10 platforms, robots.txt compliance, adaptive rate limiting, classification, skills, CLI, CI, scheduled runs
- [x] Ghost job signals, repost detection, Ontario disclosures, salary ranges, hiring calendar, skills gap
- [ ] REST API and a web frontend
- [ ] Alerts when a tracked employer opens new intern or new grad roles
- [ ] Skill and salary trends over time

## Contributing

Bug reports, new companies, and new adapters are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)
