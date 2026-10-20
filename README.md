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

pip install -e ".[api]"       # then run the web API
ghostless serve               # http://127.0.0.1:8000/docs
```

No Python? Run it all in Docker:

```bash
docker compose --profile app run --rm tracker verify
docker compose --profile app run --rm tracker ingest
```

## Website

The `web/` folder holds the Ghostless website, built with Next.js on top of the API. See [web/README.md](web/README.md).

What people can do on it:

- **Search** tech jobs with true posting ages, ghost signals and the evidence behind each flag, by role (software, data engineering, data and analytics, AI and ML, hardware, security), level, location, freshness, risk and pay.
- **Check a resume.** Upload a PDF or Word file, or write one in the builder, and get a strength score with the fixes that matter most. Every job then shows a match score read from the whole posting and the whole resume: required and nice-to-have skills (a skill used in a job or project counts for more than one only named in a list), years of experience, degree, whether you must be in school, and the posting's own key terms. Each requirement comes back checked, with what to change. The matches page ranks every open tech job for you. All of this is rule based and free; an optional AI review can be switched on (see below).
- **Build a resume** with live preview, three templates, bullet-writing tips and PDF export.
- **Track applications.** Saved jobs become a tracker with a status (saved, applied, interviewing, offer, not moving forward) and private notes.
- **Accounts** with email or Google and GitHub sign-in, email confirmation, password reset, sign-out everywhere, data export and account deletion. Settings for theme, text size, density, motion and link underlines follow the account to every device.
- **Report problems** with any job or page.
- **Admin dashboard** (`/admin`, admins only): accounts, active users, visitors, resume checks, problem reports with a status workflow, client errors, and the health of the daily data run.

To work on it without waiting for a real ingest, load demo data first. It uses fictional companies so it can never be mistaken for real postings:

```bash
python scripts/seed_demo.py --yes   # refuses to touch a database with real data
```

### Should resume scoring use AI?

It doesn't need to. Scoring and suggestions come from rules: skills matched against each posting, level fit (an intern or new grad resume against a senior role), role fit, title words, and resume quality checks such as measurable results, strong verbs, length and contact details. That is free, instant, works for every job at once, and gives the same answer every time.

An AI review is available as an extra for one job at a time: it rewrites suggestions in context and points out how to present existing experience. It's off unless `ANTHROPIC_API_KEY` is set on the API, with daily caps per user and for the whole site so costs stay predictable (a review costs well under a cent with Claude Haiku). It never invents experience.

## Commands

| Command | What it does |
|---|---|
| `ghostless verify` | Checks every source and prints OK (with a job count), WARN (0 jobs), or FAIL (with the reason). Fast: skips per-job detail requests. |
| `ghostless ingest` | Runs the full pipeline into PostgreSQL. |
| `ghostless discover [--boards N]` | Reads the job lists, registers new job boards they link to, crawls the discovered boards that are due (at most `N`) and stores list-only postings. `ghostless ingest` does this after the configured companies; run it alone to grow coverage without a full ingest. |
| `ghostless ingest --shard K/N` | Collects only part `K` of `N`: one of several machines running at once (the daily workflow uses 4). Every site belongs to exactly one part. |
| `ghostless finish` | After every part of a sharded ingest: reads the job lists, refreshes the ghost signals and cleans up. Takes seconds. |
| `ghostless seed-boards [--dry-run]` | Finds job boards in Common Crawl's URL index and registers new ones as candidates (needs `pip install '.[index]'` and `GHOSTLESS_INDEX_SEEDING=1`; `--dry-run` only counts). Run monthly by `discover.yml`. |
| `ghostless health` | Prints the last run's health report: per source, boards read, failed and unchanged (304), seconds, and postings seen, new and closed, plus boards that returned suspiciously few postings. Each run also stores it in `ingest_runs.health` and, on GitHub Actions, writes it to the run summary. |
| `ghostless gap --have "..."` | Ranks the skills that active postings ask for and marks which ones you have. Defaults to intern and new grad software roles in Canada or remote; change with `--role`, `--level` (both repeatable) and `--anywhere`. |
| `ghostless reprocess` | Re-derives pay, disclosures, fingerprints and repost links for every stored posting, and syncs company names and domains from `companies.yaml`. Fetches nothing. Run it once after upgrading so improved parsing applies to existing data. |
| `ghostless admin add <email>` | Makes an existing account an admin (also `remove` and `list`). |
| `ghostless serve` | Runs the web API (needs `pip install -e ".[api]"`). `--host 0.0.0.0` when deploying, `--port`, `--reload` for development. |
| `--only <company>` | Runs for one company, by name or slug, e.g. `--only "Capital One"`. |
| `--dump [DIR]` | Saves every raw response to `DIR` (default `.debug/`) so you can see exactly what a site returned. |
| `-v` | Detailed logs. |

## Configuration

| Setting | Where | Purpose |
|---|---|---|
| `DATABASE_URL` | `.env` | PostgreSQL connection string |
| `GHOSTLESS_CONTACT` | `.env` | Your URL or email, sent in the User-Agent so site owners can reach you |
| `GHOSTLESS_COMPANIES` | `.env` | Optional path to a different companies file |
| `GHOSTLESS_CORS_ORIGINS` | API host | Comma-separated origins allowed to call the API (default `*`) |
| `GHOSTLESS_API_POOL_SIZE` | API host | Maximum database connections the API opens (default 4) |
| `GHOSTLESS_WORKERS` | `.env` or workflow | Threads collecting at once (default 16). The real limits are per site, below. |
| `GHOSTLESS_DISCOVERED_PER_RUN` | `.env` or workflow | A cap on discovered boards crawled per run (default 5000, so every board that's due) |
| `GHOSTLESS_SNOWBALL` | `.env` or workflow | Off by default. `1` registers Greenhouse, Lever, Ashby and Workday boards linked from postings as candidates, and checks them (one request each) before they're read |
| `GHOSTLESS_JSONLD` | `.env` or workflow | Off by default. `1` finds company career sites from job list links, checks them, and reads the ones that publish JSON-LD job postings |
| `GHOSTLESS_INDEX_SEEDING` | repository variable | Off by default. `1` runs the monthly `discover.yml` workflow, which finds Greenhouse, Ashby and Workday boards in Common Crawl's URL index (its Hugging Face mirror) and registers them as candidates; the daily ingest checks them. Needs the optional `index` extra (pyarrow), which only that workflow installs |
| `GHOSTLESS_VERIFY_PER_RUN` | `.env` or workflow | Candidates checked per run when either switch is on (default 100) |
| `GHOSTLESS_JSONLD_PAGES_PER_SITE` | `.env` or workflow | Job pages read per career site per run (default 25; each page is read once, then only when its sitemap entry changes) |
| `GHOSTLESS_JSONLD_SITEMAPS` / `GHOSTLESS_JSONLD_URLS` | `.env` or workflow | Sitemap files read (default 3) and job links considered (default 2000) per career site |
| `companies.yaml` | repo root | Which employers to track, and which public job lists to read (`lists:`; `lists: []` turns discovery off) |

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

"Relevant roles" means descriptions are fetched for tech roles in Canada, remote, or with an unknown location first, up to 250 per company per run, and each only once: later runs reuse it.

### Finding jobs beyond companies.yaml

`companies.yaml` is a starting set, not the limit. Every run also reads public job lists that students maintain on GitHub, from raw.githubusercontent.com: the [SimplifyJobs internship](https://github.com/SimplifyJobs/Summer2027-Internships) and [new grad](https://github.com/SimplifyJobs/New-Grad-Positions) lists, [vanshb03's internships](https://github.com/vanshb03/Summer2027-Internships), and the Canadian lists [Canadian Tech Internships 2027](https://github.com/negarprh/Canadian-Tech-Internships-2027) and [Canadian Internship List](https://github.com/Bobwillrule/Canadian-Internship-List). Three formats are understood (SimplifyJobs' `listings.json`, a README table, and a `jobs` JSON file), so most lists can be added to `companies.yaml` without code. A posting in several lists is kept once.

1. **Boards register themselves.** When a list entry links to a Greenhouse, Lever, Ashby or Workday board that isn't configured, it goes into the `discovered_boards` table. No one edits a file.
2. **Each board is revisited by how often it changes.** A board whose postings changed is read again the next day. One that keeps not changing is read every few days, up to weekly, the revisit policy search engines use to spend visits where things change. Boards with open internships or new grad roles are never left more than two days. A board that fails waits 1, 2, 4, 8 ... days, up to a month. Greenhouse, Lever and Ashby boards are read in full. Workday boards are searched for "intern", "co-op" and "new grad", since a full crawl of hundreds of large employers would take hours; closures there apply only to intern and new grad postings.
3. **Everything else comes from the list.** Companies on other systems (iCIMS, SmartRecruiters, custom sites) are stored from the list entry itself: title, link, places and season (`platform = 'list'`). They close when they leave the list, or once the company's own board is tracked, so a posting never shows twice.

Season ("Summer 2027") is read from the list or the title and is filterable on the website and with `/jobs?term=`.

### How a run stays fast and polite

Thousands of companies don't mean thousands of slow requests, because each site is limited on its own terms:

- **Requests in flight per site.** Most sites get one at a time. The public job-board APIs that Greenhouse, Lever and Ashby publish for exactly this get a few at once (4, 4 and 2), with a minimum gap between requests. Each Workday employer gets one at a time, and every Workday server cluster (the `wd1`, `wd3`, `wd5` in the address) gets at most 4 from one machine.
- **Backing off.** A "too many requests" answer doubles that site's gap and halves its requests at once for the rest of the run, and the site's `Retry-After` is honoured.
- **Several machines.** The daily workflow runs `ghostless ingest --shard K/4` on four GitHub machines at once, then `ghostless finish`. A site is never split between machines.
- **Visiting by change rate.** Quiet discovered boards are read every few days instead of daily (above).

In a simulated day of about 1,300 boards, this takes a run from about 30 minutes to about 4. The floor is the largest single employer, which still gets one request at a time.

**Not included: LinkedIn.** Its user agreement and robots.txt prohibit automated collection, and its postings for tech roles are mostly copies of postings on employers' own career sites, which Ghostless reads directly.

**Not included: Meta.** metacareers.com's robots.txt prohibits automated collection without written permission.

## Web API

`ghostless serve` starts a read-only REST API with interactive docs at `/docs`.

| Endpoint | Returns |
|---|---|
| `GET /jobs` | Paginated postings with filters: `q`, `level`, `role`, `company`, `skill`, `risk`, `location` (`canada`, `remote`, `canada_or_remote`), `status`, `new_within_days`, `has_salary`, `sort` (`newest`, `oldest`, `salary`, `company`). List filters repeat: `?level=intern&level=new_grad` |
| `GET /jobs/{id}` | One posting with its description, every earlier posting of the same role, and `evidence`: the sentence each disclosure was read from |
| `GET /companies` | Each employer with open (all and tech) postings, high-risk and new-this-week counts, and its typical time to fill |
| `GET /companies/{slug}` | One employer in depth: roles, levels, top skills, and new vs closed postings for the last 12 weeks |
| `GET /trends/weekly` | New and closed postings per week (tech roles unless `role` is given) |
| `GET /stats` | Totals and the latest ingest run |
| `GET /skills/top` | Most requested skills for a role and level |
| `GET /skills/gap?have=Python,SQL` | Your skills against current demand |
| `GET /calendar` | When each employer opened intern and new grad roles |
| `GET /health` | Liveness check that does not touch the database |

Every job carries its ghost `signals` (risk, flags, days open, and whether that age is exact), its true `first_seen` date, any disclosed `salary`, and the Ontario `vacancy` and `ai_screening` disclosures.

Example: fresh, low-risk intern and new grad software roles in Canada or remote:

```
GET /jobs?level=intern&level=new_grad&role=sde&location=canada_or_remote&risk=low&new_within_days=14
```

Design notes:

- **Signals are precomputed.** Ghost signals need a pass over every posting, so they live in a materialized view refreshed at the end of each ingest run (`REFRESH ... CONCURRENTLY`, so the API keeps reading during the refresh). With 34,000 postings the refresh takes about 5 seconds and every endpoint answers in under 100 ms.
- **Friendly to serverless databases.** The connection pool keeps no idle connections (`min_size=0`) and health-checks each connection before use, so Neon can sleep between requests and the first request after a nap still works.
- **Read-only and cache-friendly.** Only GET is allowed, responses carry `Cache-Control: public, max-age=300`, and CORS origins are set with `GHOSTLESS_CORS_ORIGINS`.
- **Validated input.** Every parameter is typed and bounded (for example `limit` is 1 to 100), and search text is always a bound parameter, never part of the SQL.

### Deploying

Ghostless runs as three pieces: the database (Neon), the API (Render, Railway or Fly.io) and the website (Vercel). The daily ingest keeps running on GitHub Actions.

**1. Database.** Your Neon database already holds the job data. The API creates the account tables itself on first start.

**2. API**, on Render, Railway or Fly.io:

- Build command: `pip install ".[api]"`
- Start command: `ghostless serve --host 0.0.0.0` (the port comes from `$PORT`)
- Health check path: `/health`
- Environment:

| Variable | Value |
|---|---|
| `DATABASE_URL` | Neon connection string |
| `GHOSTLESS_SITE_URL` | the website's URL, for links in emails |
| `GHOSTLESS_INTERNAL_KEY` | a long random secret, the same on the website |
| `GHOSTLESS_ANALYTICS_SALT` | another long random secret |
| `RESEND_API_KEY`, `GHOSTLESS_EMAIL_FROM` | for confirmation and password reset emails ([Resend](https://resend.com), free tier) |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | optional, "Continue with Google" (see below) |
| `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET` | optional, "Continue with GitHub" (see below) |
| `ANTHROPIC_API_KEY` | optional, turns on the AI resume review |

Generate secrets with `python -c "import secrets; print(secrets.token_urlsafe(32))"`.

**3. Website**, on Vercel: import the repo, set the root directory to `web`, and set `GHOSTLESS_API_URL` (the API's URL), `NEXT_PUBLIC_SITE_URL` (the site's URL) and `GHOSTLESS_INTERNAL_KEY` (the same secret as the API).

**Google and GitHub sign-in (optional, free).** Each button appears once its two values are set on the API. The callback addresses below must match `GHOSTLESS_SITE_URL` exactly; for local testing, add a second set with `http://localhost:3000`.

- *Google:* in [Google Cloud Console](https://console.cloud.google.com/), create a project, set up the OAuth consent screen (External, app name Ghostless, scopes `openid`, `email`, `profile`), then under Credentials create an *OAuth client ID* of type *Web application*. Authorized redirect URI: `https://your-site/api/auth/oauth/google/callback`. Put the client ID and secret in `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`. Publish the consent screen when you launch, so anyone can sign in, not just test users.
- *GitHub:* in GitHub, go to Settings, Developer settings, OAuth Apps, New OAuth App. Homepage URL: your site. Authorization callback URL: `https://your-site/api/auth/oauth/github/callback`. Generate a client secret, then set `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET`.

Someone signing in with Google or GitHub for the first time gets a new account with no password (they can add one later). If an account already uses the same email, the sign-in joins that account, because the provider has verified the person owns the address.

**4. Make yourself an admin.** Sign up on the live site, then run `ghostless admin add you@example.com` with `DATABASE_URL` pointing at Neon.

**Database access.** The API reads job data and writes account data. To give it less than owner access:

```sql
-- run as the owner role the pipeline uses
CREATE ROLE ghostless_api LOGIN PASSWORD '...';
GRANT SELECT ON ALL TABLES IN SCHEMA public TO ghostless_api;
GRANT SELECT, INSERT, UPDATE, DELETE ON users, sessions, email_tokens, saved_jobs, resumes, reports, events TO ghostless_api;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO ghostless_api;
-- views recreated by later ingest runs get read access automatically
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO ghostless_api;
```

With a separate role, run `ghostless ingest` once with the owner role after upgrading, so the new tables exist before the API starts.

## How the signals work

### Ghost job risk (`job_signals` view)

Each posting gets `ghost_risk` (`low`, `medium`, `high`) plus the `flags` behind it, so a user always sees *why*:

| Flag | Meaning |
|---|---|
| `not_existing_vacancy` | The posting says this about itself: "not for an existing vacancy", "this posting is for a future vacancy", "evergreen requisition" and similar. Phrases that also appear in job duties or privacy notices ("future hiring needs", "talent community") don't count. Always high risk, and the API returns the sentence as evidence. |
| `reposted` | The same role at the same company was posted before, usually taken down and put back up under a new id. |
| `duplicate_posting` | Identical copies of the role, with the same title, locations and description, are live at the same time. Postings without a description are never called duplicates. |
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
| `hiring_calendar` (view) | When each employer opened intern and new grad roles, by year (Toronto time) |
| `job_signals_mv` | Cached copy of `job_signals`, refreshed after every run, read by the API |

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
- Workday (banks and several big tech employers) and Microsoft need one request per posting for its description. Each posting is fetched once and stored; new postings are fetched in priority order, up to `GHOSTLESS_MAX_DETAILS` (default 250) per company per run, so a large backlog fills in over a few daily runs.
- Some employers (Stripe, for example) show pay only on their own careers site, not in their job board data, so their pay is missing here.

## Roadmap

- [x] Ingestion for 10 platforms, robots.txt compliance, adaptive rate limiting, classification, skills, CLI, CI, scheduled runs
- [x] Ghost job signals, repost detection, Ontario disclosures, salary ranges, hiring calendar, skills gap
- [x] Read-only REST API with filters, job detail, skills, calendar and stats
- [x] Website: split-view search, posting records with quoted evidence, company pages, skills gap, hiring calendar
- [x] Accounts, settings, application tracker, resume checks and job matching, resume builder, problem reports, admin dashboard
- [x] Self-growing coverage from public job lists, requirement-by-requirement resume scoring, builder import and live tailoring
- [ ] Email alerts for saved searches and new matches
- [ ] Browser extension showing ghost signals on career sites
- [ ] Skill and salary trends over time

## Contributing

Bug reports, new companies, and new adapters are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)
