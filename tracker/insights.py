"""Read-side queries over collected data. The CLI uses these today and the
web API will use the same functions."""

from __future__ import annotations

from dataclasses import dataclass

import psycopg

from tracker.classify import ROLE_TYPES
from tracker.skills import extract_skills

__all__ = ["ROLE_TYPES", "LEVELS"]

LEVELS = ("intern", "new_grad", "mid", "senior")


@dataclass(frozen=True)
class SkillDemand:
    skill: str
    postings: int
    share: float  # 0..1 of matching postings that ask for it
    have: bool


@dataclass(frozen=True)
class GapReport:
    total_postings: int
    skills: list[SkillDemand]
    recognized: list[str]  # the user's skills, normalized
    unrecognized: list[str]  # what we could not map to a known skill

    def missing(self, top: int = 10) -> list[str]:
        return [s.skill for s in self.skills[:top] if not s.have]


def normalize_skills(raw: list[str]) -> tuple[list[str], list[str]]:
    """Map free text ("postgres", "node") to canonical skill names."""
    recognized: set[str] = set()
    unrecognized = []
    for item in raw:
        item = item.strip()
        if not item:
            continue
        found = extract_skills(item)
        if found:
            recognized.update(found)
        else:
            unrecognized.append(item)
    return sorted(recognized), unrecognized


def skills_gap(
    conn: psycopg.Connection,
    have: list[str],
    role_types: tuple[str, ...] = ("sde",),
    levels: tuple[str, ...] = ("intern", "new_grad"),
    canada_or_remote: bool = True,
    limit: int = 15,
) -> GapReport:
    """Most requested skills in active matching postings, marked against `have`.

    Shares are computed over postings with at least one extracted skill, so
    sources without descriptions do not dilute the numbers.
    """
    recognized, unrecognized = normalize_skills(have)
    params = {
        "roles": list(role_types),
        "levels": list(levels),
        "location_filter": canada_or_remote,
        "limit": limit,
    }
    matching = """
        SELECT DISTINCT j.id FROM jobs j JOIN job_skills js ON js.job_id = j.id
        WHERE j.is_active
          AND j.role_type = ANY(%(roles)s)
          AND j.level = ANY(%(levels)s)
          AND (NOT %(location_filter)s OR j.is_canada OR j.is_remote)
    """
    total = conn.execute(f"SELECT count(*) FROM ({matching}) m", params).fetchone()[0]
    rows = conn.execute(
        f"""
        SELECT s.name, count(*) AS postings
        FROM ({matching}) m
        JOIN job_skills js ON js.job_id = m.id
        JOIN skills s ON s.id = js.skill_id
        GROUP BY s.name
        ORDER BY postings DESC, s.name
        LIMIT %(limit)s
        """,
        params,
    ).fetchall()
    have_set = set(recognized)
    skills = [
        SkillDemand(skill=name, postings=count, share=count / total if total else 0.0, have=name in have_set)
        for name, count in rows
    ]
    return GapReport(total, skills, recognized, unrecognized)


def format_gap(report: GapReport, description: str) -> str:
    if report.total_postings == 0:
        return f"No active {description} postings with extracted skills yet. Run `ghostless ingest` first."
    lines = [
        f"Top skills in {report.total_postings} active {description} postings",
        "",
        f"     {'Skill':<14}{'Postings':>9}{'Share':>8}",
    ]
    for item in report.skills:
        mark = "  ✓  " if item.have else "  ✗  "
        lines.append(f"{mark}{item.skill:<14}{item.postings:>9}{item.share:>8.0%}")
    top = report.skills[:10]
    have_count = sum(s.have for s in top)
    lines.append("")
    lines.append(f"You have {have_count} of the top {len(top)}.")
    missing = report.missing()
    if missing:
        lines.append(f"Biggest gaps: {', '.join(missing[:5])}")
    if report.unrecognized:
        lines.append(f"Not recognized (ignored): {', '.join(report.unrecognized)}")
    return "\n".join(lines)
