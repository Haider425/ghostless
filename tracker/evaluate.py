"""Accuracy of what Ghostless extracts from postings, against the labelled
test set (tests/fixtures/labelled; crawler plan, stage C3).

    ghostless evaluate           on the committed excerpts (what CI checks)
    ghostless evaluate --full    on the full text in tests/fixtures/labelled/private (local only)
    ghostless evaluate --holdout on the 50 held-out postings, labelled before the rules were tuned on
                                 the 200: the honest estimate of accuracy on new postings

Each posting runs through the same steps as a crawled one (`classify.enrich`),
from its title, location and text. A field the code doesn't extract yet is
reported as "not extracted".
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from tracker.classify import enrich
from tracker.models import Job

LABELLED = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "labelled"

# (report name, expected key, how to read the prediction from a Job)
FIELDS = (
    "level",
    "seniority",
    "role_type",
    "employment_type",
    "workplace",
    "countries",
    "is_canada",
    "is_remote",
    "sponsorship",
    "min_years_experience",
    "pay",
    "salary_min",
    "salary_max",
    "salary_currency",
    "salary_period",
)
_MISSING = object()


def load(path: Path = LABELLED / "labels.jsonl") -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def to_job(record: dict, full: bool = False) -> Job:
    text = "\n".join(record.get("excerpt") or [])
    if full:
        private = LABELLED / "private" / f"{record['id']}.json"
        if private.is_file():
            text = json.loads(private.read_text(encoding="utf-8")).get("description") or text
    return Job(
        external_id=str(record["id"]),
        title=record["title"],
        url="",
        location=record["location"],
        description=text,
    )


def _number_equal(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) < 0.01


def predicted(job: Job, name: str):
    if name == "pay":
        return tuple(getattr(job, f"salary_{k}") for k in ("min", "max", "currency", "period"))
    if name in ("is_canada", "is_remote"):
        return getattr(job, name)
    value = getattr(job, name, _MISSING)
    if name == "countries" and value is not _MISSING:
        return sorted(value or [])
    return value


def expected(record: dict, name: str):
    exp = record["expected"]
    if name == "pay":
        return tuple(exp[f"salary_{k}"] for k in ("min", "max", "currency", "period"))
    if name == "is_canada":
        return "CA" in exp["countries"]
    if name == "is_remote":
        return exp["workplace"] == "remote"
    return exp[name]


def matches(name: str, got, want) -> bool:
    if name == "pay":
        return all(
            _number_equal(g, w) if i < 2 else g == w for i, (g, w) in enumerate(zip(got, want, strict=True))
        )
    if name in ("salary_min", "salary_max", "min_years_experience"):
        return _number_equal(got, want)
    return got == want


@dataclass
class Score:
    right: int = 0
    total: int = 0
    extracted: bool = True
    misses: list = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        return self.right / self.total if self.total else 0.0


def evaluate(records: list[dict], full: bool = False) -> dict[str, Score]:
    scores = {name: Score() for name in FIELDS}
    for record in records:
        job = enrich(to_job(record, full), [])
        for name in FIELDS:
            score = scores[name]
            got = predicted(job, name)
            if got is _MISSING:
                score.extracted = False
                continue
            want = expected(record, name)
            score.total += 1
            if matches(name, got, want):
                score.right += 1
            else:
                score.misses.append((record["id"], record["title"], got, want))
    return scores


def report(scores: dict[str, Score], label: str) -> str:
    lines = [f"Accuracy on {label}", "", "| Field | Accuracy | Right |", "|---|---:|---:|"]
    for name, score in scores.items():
        if not score.extracted:
            lines.append(f"| {name} | not extracted | |")
        else:
            lines.append(f"| {name} | {score.accuracy:.0%} | {score.right}/{score.total} |")
    return "\n".join(lines)


def main(full: bool = False, misses: str | None = None, holdout: bool = False) -> None:
    records = load(LABELLED / ("holdout.jsonl" if holdout else "labels.jsonl"))
    reviewed = sum(1 for r in records if r.get("reviewed"))
    scores = evaluate(records, full)
    which = "held-out " if holdout else ""
    label = f"{len(records)} {which}labelled postings ({'full text' if full else 'excerpts'}; {reviewed} labels reviewed)"
    print(report(scores, label))
    if misses:
        print(f"\nMisses for {misses}:")
        for job_id, title, got, want in scores[misses].misses:
            print(f"  {job_id} {title[:60]!r}: got {got!r}, expected {want!r}")
