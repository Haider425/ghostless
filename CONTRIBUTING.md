# Contributing

Thanks for helping. The most useful contributions are new companies, fixes for broken sources, and new platform adapters.

## Setup

```bash
git clone https://github.com/Haider425/ghostless.git
cd ghostless
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
docker compose up -d db
```

Before opening a pull request:

```bash
ruff check . && ruff format --check .
pytest
```

CI runs the same checks on Python 3.10 and 3.13.

## Adding a company

1. Open the company's careers page, click into any job, and read the URL:

   | URL looks like | platform | slug |
   |---|---|---|
   | `boards.greenhouse.io/acme` | `greenhouse` | `acme` |
   | `jobs.lever.co/acme` | `lever` | `acme` |
   | `jobs.ashbyhq.com/acme` | `ashby` | `acme` |
   | `acme.wd5.myworkdayjobs.com/en-US/Careers` | `workday` | `acme.wd5.myworkdayjobs.com/Careers` |

   If the job stays on the company's own domain, check where the Apply button goes.

2. Add an entry to `companies.yaml` in the right section.
3. Run `ghostless verify --only "<name>"` and include the output in your pull request.

## Fixing a broken source

`ghostless verify` prints one of:

- **FAIL** with a reason: usually a moved board (fix the slug), a rate limit, or a robots.txt block.
- **WARN, 0 jobs**: the request worked but the parser found nothing, which usually means the site changed its markup or API. Run `ghostless verify --only "<name>" --dump`, look at the saved response in `.debug/`, update the parser, and add the new shape as a test fixture.

## Adding a platform adapter

1. Create `tracker/sources/<platform>.py` with:
   - a pure `parse_*` function that turns a raw response into `list[Job]`
   - a `fetch_<platform>(company, details=True)` function that makes requests **only** through `tracker.sources.http` (`get_json`, `get_text`, `request_json`). That layer handles robots.txt, rate limits, retries and `--dump` for you; never call `requests` directly.
   - `details=False` must skip any per-job requests, so `verify` stays fast.
2. Register it in `FETCHERS` in `tracker/sources/__init__.py`. If it can only return part of a company's postings, add it to `PARTIAL_LISTINGS` so missing jobs are not marked closed.
3. Add the platform to the `CHECK` constraint in `tracker/schema.sql`.
4. Add tests in `tests/` using a trimmed copy of a real response as the fixture. Tests must not make network requests; `tests/conftest.py` fails any test that tries.

## Responsible collection

Every source must respect the site's robots.txt (enforced automatically by the HTTP layer) and its terms. Do not add sources that require logging in, bypassing bot protection, or spoofing a browser. If a site prohibits automated collection, leave it out and note why in `companies.yaml`, as with Meta.
