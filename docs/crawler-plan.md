# Crawler upgrade plan

Goal: a crawler that is faster, finds new job boards by itself, understands each posting better, and closes postings reliably, without being any less polite. Based on the audit and research in [crawler-research.md](crawler-research.md). Stages are built in the order **A, D, B, C, E**. After each stage: the full test suite, new tests for the new behaviour, and a before and after comparison (run time, boards, postings, accuracy).

Rules that hold throughout:
- robots.txt and site limits are respected, now including `Crawl-delay`.
- No CAPTCHAs, logins or anti-bot workarounds.
- No LinkedIn or Indeed, and Meta stays excluded.
- Full descriptions are kept, and the current retry and wait behaviour stays.
- Schema changes go through `tracker/schema.sql` and `ghostless migrate`, and are safe to run twice.
- No new heavy dependencies or paid services without asking.
- Tests never touch Neon.

## Decisions (agreed 19 October 2026)

1. **Common Crawl:** use the Hugging Face mirror (`huggingface.co` allows crawling) if it can be confirmed to hold the URL index for recent crawls. Otherwise skip bulk seeding and grow from snowball discovery and JSON-LD. Common Crawl's own hosts, which disallow automated access, are not used.
2. **SmartRecruiters:** covered through public job pages (`jobs.smartrecruiters.com`) and the JSON-LD reader, in stage E. Its API host, which robots.txt blocks, is never called.
3. **Storage scope (revised 19 October 2026, applies everywhere):** Ghostless stores only two kinds of posting, with full descriptions:
   - student roles in any field: intern, co-op, new grad and graduate programmes;
   - tech roles at every level.

   **Where the filter applies:** every save path goes through `classify.keep_relevant`. That covers configured companies, existing and newly discovered boards, list-only postings, and the weekly Workday full read (which inserts nothing). Sources don't download descriptions for postings the filter will drop.

   **Postings that no longer pass:** a posting stored before the filter, that would fail it today, is never closed, deleted or counted as missing while its source still lists it. It's marked as seen, and it closes normally once the source stops listing it. Filtered postings also count towards what the site returned, so a board of mostly non-tech postings never trips the suspicious-drop guard.

   **Cleanup:** the non-tech postings already stored were removed on 19 October 2026, after a backup (`backups/2026-10-19-non-tech-postings/`, git-ignored).
4. **Labelled test set (the repo is public):**
   - **Committed:** the labels, plus a short excerpt per posting with only the lines each label depends on (title, location line, pay sentence, sponsorship sentence, and so on). CI checks the parsers on these.
   - **Local only:** the full posting text, kept in a git-ignored folder (`tests/fixtures/labelled/private/`) and rebuilt from posting IDs by a script, for the complete evaluation.

## Stage A: faster

Measure first. Before changing anything, per-source timing goes into the run summary (part of D2, pulled forward), so before and after numbers are real.

**A1. One connection pool per thread.** `http.py` gets a thread-local `requests.Session` (keep-alive, pooled connections), used for every request including robots.txt. Gates, intervals, 429 backoff, Retry-After, the 5 attempts and robots checks are untouched: the session only replaces `requests.request`, and its own retries stay off. **Tests:** one session per thread, reused across requests; all existing `http` tests still pass.

**A2. Honour `Crawl-delay` (a compliance fix found in the audit).** `robots.py` parses `Crawl-delay` for our group. The host's interval becomes at least that value, and its in-flight limit drops to 1. Lever (`Crawl-delay: 1`) goes from 4 requests at once every 0.25 s to 1 per second. Lever boards take 1 to 3 s each, so this costs a minute or two per run. **Tests:** parser cases, and the throttle using the delay.

**A3. Conditional requests where supported.** These were checked: Greenhouse, Lever, Ashby, Teamtailor, Personio, Breezy and the GitHub list files return 304. Workable, Rippling and Workday don't.
- A new `http_cache` table stores `(url, etag, last_modified, checked_at)`. `get_json` and `get_text` take `conditional=True` and return a `NotModified` marker on 304.
- On 304 the board is unchanged:
  - nothing is parsed or rewritten;
  - one `UPDATE jobs SET last_seen = run` keeps the postings' "last checked" date right;
  - nothing closes;
  - the revisit schedule counts it as a quiet visit.
- The cached validator is ignored if the board has no stored postings, so a bad first read can't stick.

**Tests:** 304 handling, the cache round trip, and that no closures happen on 304.

**A4. Greenhouse in two steps.** List without content (Stripe: 38 KB instead of 2 MB). For each job, compare `updated_at` with a stored `source_updated_at` (new column):
- unchanged: reuse the stored description;
- new or changed: one request to `/jobs/{id}?pay_transparency=true`, which also gives the structured pay used in C.

**Every job still ends with its full description.** If any detail request fails, that board falls back to the old single `content=true` request for this run. **Tests:** the planner (new, changed, unchanged), the fallback, and that no job is saved without a description when the board has descriptions.

**A5. Workday student search, more precise.** Hits from "intern", "co-op" and "new grad" searches are kept only if the title classifies as intern or new grad. That stops "International" and "Internal" postings being stored and sent for descriptions. The description cap then goes to postings that matter. **Tests:** the filter, with recorded responses.

**Expected effect (estimate, measured after the stage):**
- Most Greenhouse, Lever and Ashby boards answer 304 on a quiet day.
- Greenhouse traffic drops by roughly 95%.
- Workday stays the long pole, but its requests go to real student roles.

### Stage A results (built 19 October 2026)

**Built as planned, with these choices:**
- **Robots check stays inside the host and cluster limits**, so robots.txt fetches respect them too.
- **Very long Crawl-delays:** a site asking for more than 30 s between requests is skipped for the run rather than holding a worker for hours.
- **When a board is read in full:** a cached validator only skips the read while it vouches for what's stored. The board is read in full when there's nothing cached, the last full read is over 7 days old, the parsing or classifying code has changed (a hash of `classify.py`, `skills.py`, `disclosures.py`, `text.py` and `sources/boards.py`), or the board has no open stored postings. A read that tripped the suspicious-drop guard stores no validator.
- **Greenhouse full reads:** with more than 10 new or changed postings, one `content=true` request is used instead of one request per posting.
- **New run summary lines:** time per platform, plus requests, MB received and 304 answers per kind of site.

**Measured on real boards** (15 Greenhouse, 2 Lever, 5 Ashby from companies.yaml; no database):

| Read | Requests | Data received | 304 answers | Time |
|---|---|---|---|---|
| Before (one full read each) | 22 | 75.2 MB | 0 | 8.9 s |
| After, a full read (first or weekly) | 37 | 79.6 MB | 0 | 22.7 s |
| After, the next read, nothing changed | 22 | 0.0 MB | 22 | 6.6 s |

- **Full reads cost more:** a listing plus a full read, and Lever now runs at its Crawl-delay of 1 per second. That happens at most weekly.
- **On a day a Greenhouse board changes,** the listing is about 6% of the full read, plus about 13 KB per changed posting.

**Workday student searches** (3 employers):

| Employer | Search hits | Kept as student titles |
|---|---|---|
| TD | 234 | 19 |
| RBC | 239 | 29 |
| BMO | 183 | 3 |

Most of what's dropped is clearly not a student role ("Bank Manager", "Mortgage Specialist"). Two kinds of real student roles are missed because the level classifier doesn't recognise their titles: "Summer Associate" and "2027 … Program". The old code didn't keep them either, because they classified as non-tech and non-student. A classifier fix is proposed separately.

**Verification:**
- **Done:** 350 tests pass and ruff is clean.
- **Not yet run:** the database tests for `http_cache`, `mark_unchanged`, `stored_versions` and running migrate twice. They need a working local `TEST_DATABASE_URL`.

## Stage D: correctness

**D1. Weekly full read of every discovered Workday board, for closures only.**
- Each board gets a weekday from a hash of its slug, so about 1/7 of the 570 boards are read each day.
- On its day: the full listing (the existing `_crawl` with facet splitting), with no descriptions.
- If the listing came back complete, stored open postings at any level that aren't in it are closed, through the same `suspicious_drop` guard.
- Nothing new is inserted from this read, and nothing is deleted.
- A partial listing closes nothing.

**Cost:** about 80 boards a day at roughly 15 requests each. **Tests:** closes missing postings at every level, adds none, skips closing on partial or suspicious reads, and the staggering.

**D2. Health report after every run.** `ingest_runs` gets a `health JSONB` column holding, per source:
- boards read, failed and answered 304;
- seconds spent;
- postings seen, new and closed.

It also lists boards that returned 0 postings with 3 or more open (the guard's catches), and new boards registered. `ghostless health` prints the latest report. The workflow also writes it to the GitHub Actions run summary (`$GITHUB_STEP_SUMMARY`). **Tests:** the aggregation and the zero-posting detection.

### Classifier fix (built 19 October 2026, with stage D)

- **Student roles:**
  - internships in French, German, Spanish and Italian (stage, stagiaire, alternance, Praktikum, Werkstudent, prácticas, becario, tirocinio);
  - "Summer Analyst" and "Summer Associate";
  - graduate programmes ("2027 … Program", rotational programmes, and development programmes that hire graduates).
- **AI titles** with words between "AI" and engineer, developer or scientist ("AI Applied Engineer").
- **Kept out on purpose:**
  - "Stage Manager";
  - "Development Program Manager" (senior titles are checked first);
  - customer-facing AI roles (support, field, solutions);
  - "AI Benchmark Engineer | Native Language Specialist", a language rating job.
- **Effect on the deleted postings:** of the 100,625 removed in the non-tech cleanup, 814 classify as worth keeping under the new rules: 519 internships, 207 graduate programmes and 88 AI roles. The rules hash changed, so the next run reads every board in full. Any of those still posted come back, but with a new first-seen date. Restoring them from the backup instead would keep their real dates.

### Stage D results (built 19 October 2026)

**D1, the weekly full read: one change from the plan.** Facet splitting was too expensive. Genuine Parts Company took 1,542 requests and 15 minutes for a 2,733-posting listing. So the weekly full read only covers boards whose listing fits in one search (2,000 postings, at most 100 requests). A bigger board costs one request, counts as partial and closes nothing.

On 9 real discovered boards, read-only:
- **Cost:** 154 requests and 133 s in all, about 17 requests per board.
- **Closures:** 6 stored postings would close that a student search never could: mid and senior roles left from the old broad search, plus one new grad role. Across the database, 11,312 of the 21,948 open postings on discovered Workday boards are above student level, and only this read can close them.

**D2, the health report.**
- **Stored and printed:** `ingest_runs.health` holds the report, and `ghostless health` prints the latest run, with every part of a sharded run.
- **Sources covered:** configured boards by platform, discovered boards by platform, the weekly full read, the job lists, and list-only postings.
- **Guard catches:** recorded wherever the suspicious-drop guard fires, both in normal saves and in the full read.
- **GitHub run summary:** each ingest part writes its report, and `ghostless finish` adds the job lists. The workflow file doesn't need changing: the code writes to `$GITHUB_STEP_SUMMARY` when it's set.

**Verification:**
- **Done:** 378 tests pass and ruff is clean.
- **Not yet run:** the database tests for stages A and D (7 new ones). They're blocked on the local test database's password.

## Stage B: discovery that grows by itself

**B1. Snowball from everything Ghostless reads.** `board_from_url` learns the new platforms from stage E (Workable, Teamtailor, Personio, Breezy, Rippling, Recruitee). Board links are pulled from:
- list entries, as today;
- every posting's apply URL;
- links in descriptions ("apply at jobs.lever.co/...");
- career pages and JSON-LD read in B3.

Candidates go into `discovered_boards` with a new `state` column: `candidate`, then `active` or `empty` or `dead`.

A verification step calls each candidate's own API once and promotes it only if it responds and has postings. Empty boards are rechecked monthly, and dead ones are dropped after three failures. A per-run verification budget (default 300) keeps the load predictable.

**B2. Bulk seeding from a URL index, from the Hugging Face mirror only (decision 1). Skipped if the mirror can't be confirmed.** A monthly workflow (`discover.yml`):
1. reads the latest crawl's `cluster.idx`;
2. finds the index ranges for `com,greenhouse,boards)`, `io,greenhouse,job-boards)`, `co,lever,jobs)`, `com,ashbyhq,jobs)`, `com,myworkdayjobs,*)` and the new platforms' hosts (the index is sorted that way, so each is a contiguous range);
3. fetches only those blocks with range requests, one at a time;
4. extracts board slugs and feeds them into B1's verification queue.

It needs no new dependencies: `requests` and `gzip`.

**B3. Generic JSON-LD reader for any career site.** A new platform `jsonld`, whose board is a careers site:
- find job URLs from the site's sitemaps (from robots.txt `Sitemap:` lines or `/sitemap.xml`), using `lastmod` and conditional requests to fetch only new or changed pages;
- read each job page's `<script type="application/ld+json">` JobPosting into a `Job`: title, description, date posted, `validThrough`, location, `baseSalary`, `employmentType`, remote flags, experience and education;
- if a careers page links to a known hiring system, register that board instead, since the API is cheaper and complete.

Sites are found from companies' `domain` fields and from links in B1. Pages are fetched incrementally, like Workday details (once per posting, a capped batch per run).

**B4. Through the existing pipeline.** Every new board uses:
- `save_company_jobs` with the `suspicious_drop` guard;
- `next_visit_days`;
- `merge_duplicates`, extended for one company found on two platforms (an ATS board and its JSON-LD site, where the ATS wins);
- the storage scope from decision 3.

**Tests:**
- link extraction for every platform;
- the candidate state machine;
- the index range lookup on a recorded `cluster.idx` sample;
- JSON-LD parsing on recorded pages (including multiple JobPostings per page, `@graph`, and invalid JSON);
- dedupe across platforms.

## Stage C: smarter parsing

**C1. Structured data first, then rules.** Adapters fill new `Job` fields from source data:
- Ashby compensation components;
- Greenhouse `pay_input_ranges`;
- Lever `salaryRange` and `workplaceType`;
- Workday `remoteType` and `timeType`;
- Ashby `employmentType`;
- JSON-LD `baseSalary`, `employmentType`, `jobLocationType` and `experienceRequirements`.

`classify.enrich` uses those when present and falls back to its rules. "Fuzzier" means only heuristics on text: no AI services without your OK.

**C2. New and better fields (one migration, safe to run twice):**

| Field | Values | From |
|---|---|---|
| Pay | `salary_min`, `salary_max`, `salary_currency`, `salary_period` (existing columns, now also `month`, `week`, `day`) | structured first, then `parse_salary` |
| `seniority` (new) | intern, new_grad, junior, mid, senior, staff (staff and above) | title, structured hints, years of experience |
| `level` (unchanged) | the site's four levels, derived from `seniority` | keeps the website and API working as they are |
| `workplace` (new) | remote, hybrid, onsite | structured, then text |
| `locations` (new, JSONB) and `countries` (new, text[]) | `[{city, region, country}]`, ISO country codes | built-in tables of provinces, states and countries; no new dependency |
| `sponsorship` (new) | available, not_available, unknown | text: "unable to sponsor", "must be authorized to work in", ... |
| `min_years_experience` (new) | number | structured, then text ("3+ years of experience") |
| `employment_type` (new) | full_time, part_time, contract, temporary, internship | structured, then title and text |

`role_type` keeps its rules, with fixes driven by the test set.

**C3. Labelled test set and accuracy report.**
- At least 200 real postings, sampled across platforms, levels, countries and pay formats, with expected values for every field above. Labels and excerpts are committed and full text stays local (decision 4).
- `ghostless evaluate` prints accuracy per field.
- Run once on today's code (before) and after each change in C. The before and after table goes in the stage summary.

## Stage E: new sources

One adapter per hiring system that passed the checks, in this order:
1. **Workable**: test `details=true` first; if descriptions are missing, read each job's page JSON-LD incrementally.
2. **Teamtailor**: RSS, paged.
3. **Personio**: XML.
4. **Breezy**: JSON; descriptions from job pages' JSON-LD.
5. **Rippling**: JSON.
6. **Recruitee**: company subdomains.
7. **SmartRecruiters**: through public job pages and JSON-LD only (decision 2). The API host, which robots.txt blocks, is never called.

Each one gets:
- a `FETCHERS` entry;
- `board_from_url` rules (B1);
- an entry in the `companies_platform_check` constraint;
- host pacing for shared hosts;
- conditional requests where checked (A3);
- tests with recorded sample responses.

The HTTP layer already re-checks robots.txt per company subdomain, so a company that disallows crawling is skipped.

## Storage

Today it's 625 MB for 148k postings, about 3.9 KB per posting (row, description and indexes) plus about 0.5 KB in skills and signals. Descriptions are 264 MB of that. Closed postings are kept forever, so storage grows with history.

These figures are estimates, to be checked against real numbers after B and E:

| Scenario | Open postings | Size in about 3 months |
|---|---|---|
| Today's growth, no changes | ~150k | ~0.8 GB |
| Plan with decision 3 (tech plus student roles from new boards), B1, B3 and E | ~250k | ~1.2 to 1.5 GB |
| Plan with B2 (URL-index seeding), decision 3 applied | ~400k | ~2 to 2.5 GB |
| Plan with B2, storing every role | ~700k+ | ~3.5 to 4.5 GB |

**Ways to keep it down, which can be combined:**
- decision 3;
- `ALTER TABLE jobs ALTER COLUMN description SET COMPRESSION lz4`, which applies to new values (Postgres 18 supports it; the saving is measured before relying on it);
- dropping the descriptions of postings closed more than a year ago, keeping the record.

**Please check your Neon plan's storage limit against these numbers before B2 or E are switched on.** Each source is behind a setting, so it can be turned on gradually.

## Measuring before and after

After each stage, from the D2 health report and the database:
- run time per part and per source;
- boards by platform and state;
- open postings;
- the share of boards answering 304;
- postings without descriptions;
- pay coverage;
- the C3 accuracy table.

## Files expected to change

- **HTTP and robots:** `tracker/sources/http.py` (A1, A2, A3), `tracker/sources/robots.py` (A2).
- **Existing adapters:** `tracker/sources/boards.py` (A4, C1), `tracker/sources/workday.py` (A5, D1, C1).
- **New adapters:** `tracker/sources/` for jsonld (B3) and E.
- **Registry and pipeline:** `tracker/sources/__init__.py`, `tracker/models.py`, `tracker/classify.py`, `tracker/disclosures.py`, `tracker/ingest.py`, `tracker/parallel.py`.
- **Discovery:** `tracker/discovery/run.py`, `boards.py`, `dedupe.py`, and new `tracker/discovery/verify.py` and `index.py` (B).
- **Database and CLI:** `tracker/db.py`, `tracker/schema.sql`, `tracker/cli.py` (`health`, `evaluate`).
- **Workflows:** `.github/workflows/ingest.yml` (health summary), new `.github/workflows/discover.yml` (B2).
- **Tests and docs:** `tests/`, with recorded fixtures for every new source; `README.md` and these docs.
