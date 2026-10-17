"""Health check for every source. Run it with `jobtracker verify`.

Reports OK with a job count, WARN when a source returns 0 jobs (for HTML
sources this usually means the site's markup changed), or FAIL with the
reason. Run it whenever you add companies.
"""

from __future__ import annotations

import time

from tracker.config import load_companies, select
from tracker.sources import FetchError, fetch_jobs


def run(only: str | None = None) -> int:
    """Check sources and return the number that need attention."""
    problems = 0
    for company in select(load_companies(), only):
        started = time.perf_counter()
        try:
            count = len(fetch_jobs(company, details=False))
            elapsed = time.perf_counter() - started
            status = "OK  " if count else "WARN"
            detail = f"{count:>5} jobs  ({elapsed:.1f}s)"
            if not count:
                problems += 1
                detail += "  rerun with --dump to save the raw response"
        except FetchError as exc:
            status, detail = "FAIL", str(exc)
            problems += 1
        print(f"{status}  {company.platform:<10} {company.name:<16} {detail}", flush=True)
    return problems


if __name__ == "__main__":  # backwards compatible: python -m tracker.verify
    from tracker.cli import main

    main(["verify"])
