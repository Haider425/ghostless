"""The labelled test set for `ghostless evaluate` (crawler plan, stage C3).

The repository is public, so only the labels and short excerpts are
committed (tests/fixtures/labelled/labels.jsonl): for each posting, its
title, location line, and the description sentences the labels depend on
(pay, sponsorship, years of experience, workplace, job type). The full text
of each posting stays local, in the git-ignored folder
tests/fixtures/labelled/private/, and is rebuilt from the posting ids.

    python scripts/build_labelled_set.py sample      draw a new sample (overwrites the excerpts; keeps no labels)
    python scripts/build_labelled_set.py holdout     draw 50 more postings, none from labels.jsonl, into holdout.jsonl:
                                                     labelled before the rules are changed for them, for an honest score
    python scripts/build_labelled_set.py rebuild     fetch the full text of the labelled postings again

Both only read the database (DATABASE_URL). Run from the repository root.
"""

from __future__ import annotations

import argparse
import json
import random
import re
from pathlib import Path

HERE = Path("tests/fixtures/labelled")
LABELS = HERE / "labels.jsonl"
HOLDOUT = HERE / "holdout.jsonl"
HOLDOUT_QUOTAS = {
    "workday": 14, "greenhouse": 14, "ashby": 8, "lever": 6, "amazon": 2,
    "rss": 2, "google": 1, "eightfold": 1, "apple": 1, "list": 1,
}  # fmt: skip
HOLDOUT_SEED = 20261021
PRIVATE = HERE / "private"

# how many postings from each platform (200 in all)
QUOTAS = {
    "workday": 55,
    "greenhouse": 55,
    "ashby": 30,
    "lever": 25,
    "amazon": 8,
    "rss": 8,
    "google": 5,
    "eightfold": 5,
    "apple": 5,
    "list": 4,
}
SEED = 20261020

_TOPICS = re.compile(
    r"\$|USD|CAD|€|£|salary|salaries|compensation|pay range|base pay|per hour|hourly|annual|"
    r"sponsor|visa|authori[sz]ed to work|work authori[sz]ation|work permit|citizen|clearance|eligible to work|right to work|"
    r"\byears?\b|\byrs\b|"
    r"remote|hybrid|on-?site|in-office|in office|office-based|days (a|per) week|work from home|telecommut|"
    r"full[- ]time|part[- ]time|contract|temporary|\btemp\b|intern|co-?op|fixed[- ]term|permanent|seasonal|hours per week",
    re.I,
)
MAX_SENTENCES = 30
MAX_CHARS = 400


def excerpt(description: str) -> list[str]:
    """The description sentences a label could depend on, in order."""
    pieces = re.split(r"(?<=[.!?])\s+|\n+", description or "")
    out = []
    for piece in pieces:
        piece = piece.strip(" •-*\t")
        if piece and _TOPICS.search(piece):
            out.append(piece[:MAX_CHARS])
            if len(out) >= MAX_SENTENCES:
                break
    return out


def _connect():
    import psycopg

    from tracker.cli import load_dotenv
    from tracker.config import database_url

    load_dotenv()
    conn = psycopg.connect(database_url(), connect_timeout=30)
    conn.read_only = True
    return conn


_COLUMNS = "j.id, c.platform, c.name, j.title, coalesce(j.location, ''), coalesce(j.description, ''), j.url"


def sample(
    quotas: dict = QUOTAS, seed: int = SEED, out_path: Path = LABELS, exclude: frozenset = frozenset()
) -> None:
    rng = random.Random(seed)
    chosen = []
    with _connect() as conn:
        for platform, quota in quotas.items():
            rows = conn.execute(
                f"""SELECT {_COLUMNS}, j.salary_min IS NOT NULL, j.is_canada, j.level
                    FROM jobs j JOIN companies c ON c.id = j.company_id
                    WHERE c.platform = %s AND j.is_active
                      AND (c.platform IN ('list', 'sitemap') OR coalesce(j.description, '') <> '')""",
                (platform,),
            ).fetchall()
            rows = [row for row in rows if row[0] not in exclude]
            rng.shuffle(rows)
            # spread across pay stated or not, Canada or not, and the four levels
            buckets: dict[tuple, list] = {}
            for row in rows:
                buckets.setdefault((row[7], row[8], row[9]), []).append(row)
            picked: list = []
            while len(picked) < quota and any(buckets.values()):
                for key in sorted(buckets, key=str):
                    if buckets[key] and len(picked) < quota:
                        picked.append(buckets[key].pop())
            chosen += picked
    PRIVATE.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as out:
        for job_id, platform, company, title, location, description, url, *_ in chosen:
            _save_private(job_id, platform, company, title, location, description, url)
            record = {
                "id": job_id,
                "platform": platform,
                "title": title,
                "location": location,
                "excerpt": excerpt(description),
                "reviewed": False,
                "expected": {},
            }
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"sampled {len(chosen)} postings into {out_path} (full text in {PRIVATE}, git-ignored)")


def holdout() -> None:
    labelled = frozenset(
        json.loads(line)["id"] for line in LABELS.read_text(encoding="utf-8").splitlines() if line
    )
    sample(HOLDOUT_QUOTAS, HOLDOUT_SEED, HOLDOUT, labelled)


def _save_private(job_id, platform, company, title, location, description, url) -> None:
    record = dict(
        id=job_id,
        platform=platform,
        company=company,
        title=title,
        location=location,
        description=description,
        url=url,
    )
    (PRIVATE / f"{job_id}.json").write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")


def rebuild() -> None:
    ids = [
        json.loads(line)["id"]
        for path in (LABELS, HOLDOUT)
        if path.exists()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    PRIVATE.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT {_COLUMNS} FROM jobs j JOIN companies c ON c.id = j.company_id WHERE j.id = ANY(%s)",
            (ids,),
        ).fetchall()
    for row in rows:
        _save_private(*row)
    print(f"rebuilt {len(rows)} of {len(ids)} postings' full text ({len(ids) - len(rows)} no longer stored)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("action", choices=["sample", "holdout", "rebuild"])
    {"sample": sample, "holdout": holdout, "rebuild": rebuild}[parser.parse_args().action]()
