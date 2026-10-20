# Crawler research

Research for the crawler upgrade (see [crawler-plan.md](crawler-plan.md)). Written October 2026. Everything marked "checked" was tested from this machine with an identifying user agent, one request per endpoint; everything else is cited.

## 1. Where the crawler stands today (audit)

### How a run works

The **Daily ingest** workflow (`.github/workflows/ingest.yml`) runs at 10:17 UTC in three steps:

1. **prepare:** `ghostless migrate` applies `tracker/schema.sql` once.
2. **collect:** four machines run `ghostless ingest --shard N/4`. Each one:
   - fetches its share of the 52 companies in `companies.yaml` (`tracker/ingest.py`);
   - crawls its share of the discovered boards that are due (`tracker/discovery/run.py: crawl_boards`).

   Work is grouped by site (`tracker/parallel.py`), with 16 threads per machine. The HTTP layer (`tracker/sources/http.py`) enforces:
   - robots.txt;
   - a minimum gap between requests to one host (0.25 s to 2 s);
   - a cap on requests in flight per host (1 by default; Greenhouse 4, Lever 4, Ashby 2);
   - a cap of 4 per Workday server cluster;
   - backoff on 429s and 5xx, with up to 5 attempts.
3. **finish:** `ghostless finish` runs once. It:
   - reads the five GitHub job lists (`tracker/discovery/lists.py`);
   - registers any Greenhouse, Lever, Ashby or Workday board their links point to (`discovery/boards.py: board_from_url`);
   - saves list-only postings and merges duplicates (`discovery/dedupe.py`);
   - refreshes the ghost signals.

Every fetched posting goes through `classify.enrich`, which sets level, role, Canada/remote, season, pay, vacancy and the fingerprint. `db.save_company_jobs` then stores it. That function closes postings that disappeared, unless the drop looks like a failed fetch (`db.suspicious_drop`), and links reposts.

Discovered boards are revisited on an adaptive schedule (`next_visit_days`):
- a board that changed comes back the next day;
- a quiet board backs off to weekly;
- a board with student roles is visited at least every 2 days;
- a failing board backs off up to 30 days.

### Size (read-only queries on the production database, 19 October 2026)

| | |
|---|---|
| Configured companies | 52 |
| Discovered boards | 1,249: Workday 570, Ashby 293, Greenhouse 283, Lever 103 |
| Companies known only from lists | 1,842 |
| Open postings | 145,257 (148,087 stored in all) |
| Postings without a description | 68,902, of which 59,981 are on discovered Workday boards |
| Postings with pay | 35,200 (24%) |
| Roles | 77% "other" (not tech); levels 49% mid, 39% senior, 10% intern, 2% new grad |
| Database | 625 MB; `jobs` is 544 MB, descriptions 264 MB, about 3.9 KB per posting with indexes |
| Postgres | 18.6 (Neon) |

### Where the time goes

The four parts of a run take **7 to 19 minutes each**, according to the last two days' `ingest_runs` rows. The per-company "slowest" lines are in the GitHub Actions logs, which I couldn't read from here because the GitHub CLI isn't installed, so I timed a random sample of boards without writing anything:

| Source | Seconds per board | Notes |
|---|---|---|
| Greenhouse, Lever, Ashby | 1 to 3 | One request each. Lever occasionally times out and costs about 25 s in retries. |
| Workday, student search only | 15 to 21 | Three searches ("intern", "co-op", "new grad") of up to 100 results each, 20 per page, one request at a time per host. |

**Workday is most of the run.** 570 boards at about 18 s each is about 2.9 machine-hours of serial host time, spread over 4 machines and the cluster limits.

The student search also over-matches. "intern" finds "International" and "Internal", so Tyson Foods returned 1,001 hits, of which 204 were kept, and the listing was marked partial. That's why discovered Workday boards hold 70,000 mostly non-student postings and 60,000 empty descriptions (15 descriptions per board per run).

Other costs per run:
- Greenhouse is fetched with `content=true`, so every run downloads every description. Stripe's board is 2 MB with content and 38 KB without.
- No source uses conditional requests, so an unchanged board costs a full download.
- `http.py` calls `requests.request` directly, so every request opens a new TCP and TLS connection, with no keep-alive.

### What each source misses

| Source | Misses |
|---|---|
| Greenhouse | Pay is only in the text. The per-job endpoint has `pay_transparency=true` with structured ranges, which isn't used. Descriptions are re-downloaded daily. |
| Lever | `salaryRange` and `workplaceType` beyond "remote" aren't read. |
| Ashby | `includeCompensation=true` isn't used: Ashby returns structured min, max, currency and interval. `workplaceType` hybrid and onsite, and `employmentType` (Intern), aren't read. |
| Workday | Descriptions are capped per run, so 60k are missing. The search over-matches. `remoteType` (hybrid) and `timeType` are ignored. Non-student postings at discovered boards are never closed, because closing is limited to student levels. |
| Lists | No description at all for 1,842 list-only companies. |
| All | Location stays a free-text string. Work authorization, years of experience and employment type aren't extracted. Level comes from the title only. |

## 2. How aggregators find employers and stay fresh

- **Link mining from what's already read.** A posting's apply link, a list entry or a company careers page names the board it lives on. Ghostless already does this for list entries; it's the cheapest growth path. Other collectors use the same technique, for example [jobforge](https://pkg.go.dev/github.com/0xcryptj/jobforge), which treats public board APIs as the "stable import surface".
- **Web-scale URL indexes.** Common Crawl publishes a URL index of each monthly crawl:
  - a CDXJ index at `index.commoncrawl.org`;
  - a columnar Parquet "URL index", which is large ([CDXJ index](https://commoncrawl.org/cdxj-index), [URL index](https://blog.commoncrawl.org/url-index)).

  Filtering it for `boards.greenhouse.io/*`, `jobs.lever.co/*`, `jobs.ashbyhq.com/*` and `*.myworkdayjobs.com/*` gives candidate boards. The CDXJ index is sorted by reversed host (SURT), so all of one platform's URLs sit in one contiguous range and can be read with a few HTTP range requests rather than the whole index.
- **schema.org JobPosting.** Employers that want Google for Jobs listings publish `JobPosting` JSON-LD on each job page and list those pages in their sitemaps ([Google's JobPosting guide](https://developers.google.com/search/docs/appearance/structured-data/job-posting)).

  The required fields are `title`, `description`, `datePosted`, `hiringOrganization` and `jobLocation`. Useful optional ones:
  - `baseSalary` (a MonetaryAmount with `unitText` HOUR, DAY, WEEK, MONTH or YEAR);
  - `employmentType`, including `INTERN`;
  - `jobLocationType` `TELECOMMUTE` and `applicantLocationRequirements`, for remote work;
  - `validThrough`;
  - `experienceRequirements.monthsOfExperience` and `educationRequirements`.

  This makes a generic reader possible for career sites on any system.
- **Conditional requests.** Fetching only what changed is how large collectors stay fresh cheaply. Most board APIs below support it (see 4).
- **Revisit scheduling.** Ghostless's `next_visit_days` already follows the standard "visit what changes" policy.

## 3. Common Crawl: access and robots.txt

Common Crawl's guide says data is downloaded over HTTPS from `https://data.commoncrawl.org/` with tools like curl, "There is no need to create an AWS account" ([Get started](https://commoncrawl.org/get-started)). Its FAQ asks users to slow down on HTTP 503 and avoid parallel requests from one IP ([FAQ](https://commoncrawl.org/faq)).

Its [terms of use](https://commoncrawl.org/terms-of-use) don't set a rate or forbid commercial use. They do forbid disrupting the service, disguising request origin, and harvesting personal information. Using URLs to find public job boards is none of these, and job pages carry their own owners' terms.

**The conflict: every Common Crawl host disallows automated access in robots.txt (checked).**

| Host | robots.txt (checked) |
|---|---|
| `index.commoncrawl.org` | `Disallow: /`, allowing only the home page and `collinfo.json` |
| `data.commoncrawl.org` | `Disallow: /` |
| `ds5q9oxwqwsfj.cloudfront.net` (their CloudFront prefix) | `Disallow: /` |
| `commoncrawl.s3.amazonaws.com` over plain HTTPS | 403 without AWS credentials |

A third-party page says recent crawls, including the URL index, are mirrored to a Hugging Face storage bucket ([demo page](https://davanstrien-common-crawl-april-2026.static.hf.space/index.html)), and `huggingface.co` allows crawling. I couldn't confirm the mirror from official documentation.

**Result:** under the rule "respect robots.txt", Ghostless can't use Common Crawl as published. This needs a decision (see the plan).

## 4. Hiring systems with public job feeds

All were checked with one request each on 19 October 2026. "robots" is the robots.txt of the host the adapter would call. Ghostless's HTTP layer re-checks robots.txt for every company subdomain at run time, so a company that disallows crawling is skipped automatically.

| System | Endpoint (checked) | Key? | robots.txt (checked) | ETag/304 | Notes |
|---|---|---|---|---|---|
| Greenhouse (in use) | `boards-api.greenhouse.io/v1/boards/{slug}/jobs`, `content=true` optional; `/jobs/{id}?pay_transparency=true` | no ([docs](https://docs.greenhouse.io/job-board.html)) | `Disallow: /embed/` only | yes | Without content, 50x smaller. The list has `updated_at`, so changed jobs can be re-fetched one by one. |
| Lever (in use) | `api.lever.co/v0/postings/{slug}?mode=json` | no | `Allow: /`, `Crawl-delay: 1` | yes | Ghostless already paces Lever at 0.25 s × 4 in flight. Crawl-delay 1 means one request per second; see the plan. |
| Ashby (in use) | `api.ashbyhq.com/posting-api/job-board/{name}?includeCompensation=true` | no ([docs](https://developers.ashbyhq.com/docs/public-job-posting-api)) | none served (401 on `/robots.txt`), treated as allowed | yes | Structured pay; `workplaceType` OnSite, Remote or Hybrid; `employmentType` Intern. |
| **Workable** | `apply.workable.com/api/v1/widget/accounts/{slug}` | no | `Disallow:` (nothing) | **no** | Public widget API (third-party write-ups: [1](https://dev.to/zsevic/integration-with-workable-public-jobs-api-3nk4), [2](https://dev.to/devil_scrapes/workable-jobs-scraper-pull-every-posting-from-any-workable-careers-board-31lg)). Whether `details=true` returns full descriptions is disputed; test before building. |
| **Teamtailor** | `{company}.teamtailor.com/jobs.rss`, with `offset` and `per_page` | no ([official guide](https://support.teamtailor.com/en/articles/11171756-rss-feed-how-to-guide)) | allows all except app paths | yes | Title, description, URL, remote status, locations, department. 100 per page by default. |
| **Personio** | `{company}.jobs.personio.de/xml?language=en` | no ([help article](https://support.personio.de/hc/en-us/articles/207576365)) | `Allow: /` | yes | The company has to turn the feed on. Has seniority and employment type fields. |
| **Breezy** | `{company}.breezy.hr/json` | no (checked) | allows all except assets | yes | Third-party sources disagree on the URL and whether all customers have it ([jobspipe](https://jobspipe.dev/sources/breezy)); the feed has no full description. |
| **Rippling** | `api.rippling.com/platform/api/ats/v1/board/{slug}/jobs` | no (checked) | none (404), so allowed | no | No official docs found. |
| Recruitee | `{company}.recruitee.com/api/offers/` | no ([support](https://support.recruitee.com/en/articles/1066282)) | `api.recruitee.com` disallows all; company subdomains vary | ? | The careers endpoint is on company subdomains, which robots allows unless the company opts out. Its "legacy" status is unverified. |
| **SmartRecruiters** | `api.smartrecruiters.com/v1/companies/{id}/postings` | officially a key ([Posting API](https://developers.smartrecruiters.com/docs/posting-api)); in practice public | **`User-agent: * Disallow: /`** (only LinkedInBot allowed) | ? | **Blocked by robots.txt.** I sent one test request to this endpoint by mistake after reading its robots.txt; the build won't call it. Possible robots-compliant route: company career pages on `careers.smartrecruiters.com` and job pages on `jobs.smartrecruiters.com` (no robots.txt) through the JSON-LD reader. |
| Pinpoint | `{company}.pinpointhq.com/postings.json` | no | `Disallow: /` on the subdomain checked | n/a | Excluded unless a company's subdomain allows it (the HTTP layer checks). |
| Dover | `app.dover.com/api/...` | n/a | `Disallow: /api/` | n/a | Excluded. |
| BambooHR | `{company}.bamboohr.com/careers/list` | no | allows all but embeds | ? | Redirected in the check; needs a real company to test. |
| JazzHR | `{company}.applytojob.com` | n/a | `Disallow: /api/` | n/a | HTML job pages only; covered by the JSON-LD reader if they publish it. |

**Conditional requests (checked):**
- **Return 304 to a repeat request with the ETag:** Greenhouse (with and without content), Lever, Ashby, Teamtailor, Personio, Breezy, and GitHub raw files (the job lists).
- **No ETag:** Workable and Rippling.
- **Not applicable:** Workday, whose search is a POST.

## 5. Parsing references

- Structured pay is available from Ashby compensation components (min, max, currency, interval), Greenhouse `pay_input_ranges`, Lever `salaryRange` (min, max, currency, interval), JSON-LD `baseSalary` and Personio's XML. Text parsing stays the fallback (`tracker/disclosures.py: parse_salary`).
- Remote, hybrid and onsite come from Ashby `workplaceType`, Lever `workplaceType`, Workday `remoteType`, JSON-LD `jobLocationType` and Teamtailor's remote status.
- Level hints come from Ashby `employmentType` Intern, JSON-LD `employmentType` INTERN, Personio seniority, and Workday `timeType` (part time and temporary).
