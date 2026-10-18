"""SQL behind each endpoint.

Every function takes an open connection and returns plain dicts shaped like
the response models. WHERE clauses are built only from fixed fragments in
this file; user input is always passed as a bound parameter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import psycopg
from psycopg.rows import dict_row

from tracker import insights

LOCATIONS = {
    "any": None,
    "canada": "j.is_canada",
    "remote": "j.is_remote",
    "canada_or_remote": "(j.is_canada OR j.is_remote)",
}
STATUSES = {"active": "j.is_active", "closed": "NOT j.is_active", "all": None}
SORTS = {
    "newest": "j.first_seen DESC, j.id DESC",
    "oldest": "j.first_seen ASC, j.id ASC",
    "salary": "j.salary_max DESC NULLS LAST, j.first_seen DESC, j.id DESC",
    "company": "c.name ASC, j.first_seen DESC, j.id DESC",
}

# Postings first seen on a company's very first run were already open, so
# they must not count as "new". This is that first run's timestamp.
TRACKING_START = """
    WITH tracking AS (SELECT company_id, min(first_seen) AS started FROM jobs GROUP BY company_id)
"""

JOB_COLUMNS = """
    j.id, c.name AS company, j.title, j.location, j.url, j.level, j.role_type,
    j.is_canada, j.is_remote, j.first_seen, j.closed_at, j.is_active,
    j.salary_min, j.salary_max, j.salary_period, j.salary_currency,
    j.vacancy, j.ai_screening,
    floor(extract(epoch FROM coalesce(j.closed_at, now()) - j.first_seen) / 86400)::int AS days_open,
    s.ghost_risk, s.flags, s.age_known, s.typical_days_open, s.times_posted_before
"""

JOB_FROM = """
    FROM jobs j
    JOIN companies c ON c.id = j.company_id
    LEFT JOIN job_signals_mv s ON s.job_id = j.id
"""


@dataclass
class JobFilters:
    q: str | None = None
    levels: list[str] = field(default_factory=list)
    roles: list[str] = field(default_factory=list)
    companies: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    location: str = "any"
    status: str = "active"
    new_within_days: int | None = None
    has_salary: bool = False

    def where(self) -> tuple[str, dict[str, Any]]:
        clauses: list[str] = []
        params: dict[str, Any] = {}
        if STATUSES[self.status]:
            clauses.append(STATUSES[self.status])
        if LOCATIONS[self.location]:
            clauses.append(LOCATIONS[self.location])
        if self.q:
            clauses.append("j.title ILIKE %(q)s")
            escaped = self.q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            params["q"] = f"%{escaped}%"
        if self.levels:
            clauses.append("j.level = ANY(%(levels)s)")
            params["levels"] = self.levels
        if self.roles:
            clauses.append("j.role_type = ANY(%(roles)s)")
            params["roles"] = self.roles
        if self.companies:
            clauses.append("lower(c.name) = ANY(%(companies)s)")
            params["companies"] = [name.lower() for name in self.companies]
        if self.skills:
            clauses.append(
                """EXISTS (SELECT 1 FROM job_skills js JOIN skills sk ON sk.id = js.skill_id
                           WHERE js.job_id = j.id AND lower(sk.name) = ANY(%(skills)s))"""
            )
            params["skills"] = [name.lower() for name in self.skills]
        if self.risks:
            clauses.append("s.ghost_risk = ANY(%(risks)s)")
            params["risks"] = self.risks
        if self.new_within_days is not None:
            clauses.append(
                "j.first_seen >= now() - make_interval(days => %(new_days)s) AND j.first_seen > t.started"
            )
            params["new_days"] = self.new_within_days
        if self.has_salary:
            clauses.append("j.salary_min IS NOT NULL")
        return ("WHERE " + " AND ".join(clauses)) if clauses else "", params


def _cursor(conn: psycopg.Connection):
    return conn.cursor(row_factory=dict_row)


def _shape_job(row: dict, skills: list[str]) -> dict:
    salary = None
    if row["salary_min"] is not None:
        salary = {
            "min": float(row["salary_min"]),
            "max": float(row["salary_max"]),
            "period": row["salary_period"],
            "currency": row["salary_currency"],
        }
    return {
        "id": row["id"],
        "company": row["company"],
        "title": row["title"],
        "location": row["location"],
        "url": row["url"],
        "level": row["level"],
        "role_type": row["role_type"],
        "is_canada": row["is_canada"],
        "is_remote": row["is_remote"],
        "first_seen": row["first_seen"],
        "closed_at": row["closed_at"],
        "is_active": row["is_active"],
        "salary": salary,
        "vacancy": row["vacancy"],
        "ai_screening": row["ai_screening"],
        "skills": skills,
        "signals": {
            "risk": row["ghost_risk"],
            "flags": row["flags"] or [],
            "days_open": row["days_open"],
            "age_known": row["age_known"],
            "typical_days_open": row["typical_days_open"],
            "times_posted_before": row["times_posted_before"] or 0,
        },
    }


def _skills_for(conn: psycopg.Connection, job_ids: list[int]) -> dict[int, list[str]]:
    if not job_ids:
        return {}
    rows = conn.execute(
        """SELECT js.job_id, array_agg(s.name ORDER BY s.name)
           FROM job_skills js JOIN skills s ON s.id = js.skill_id
           WHERE js.job_id = ANY(%s) GROUP BY js.job_id""",
        (job_ids,),
    ).fetchall()
    return dict(rows)


def list_jobs(conn: psycopg.Connection, filters: JobFilters, sort: str, limit: int, offset: int) -> dict:
    where, params = filters.where()
    base = f"{TRACKING_START} SELECT {{columns}} {JOB_FROM} JOIN tracking t ON t.company_id = j.company_id {where}"
    total = conn.execute(base.format(columns="count(*)"), params).fetchone()[0]
    with _cursor(conn) as cur:
        rows = cur.execute(
            base.format(columns=JOB_COLUMNS) + f" ORDER BY {SORTS[sort]} LIMIT %(limit)s OFFSET %(offset)s",
            {**params, "limit": limit, "offset": offset},
        ).fetchall()
    skills = _skills_for(conn, [r["id"] for r in rows])
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [_shape_job(r, skills.get(r["id"], [])) for r in rows],
    }


def get_job(conn: psycopg.Connection, job_id: int) -> dict | None:
    with _cursor(conn) as cur:
        row = cur.execute(
            f"""SELECT {JOB_COLUMNS}, j.department, j.description, j.posted_at, j.last_seen,
                       j.company_id, j.fingerprint
                {JOB_FROM} WHERE j.id = %s""",
            (job_id,),
        ).fetchone()
        if row is None:
            return None
        history = cur.execute(
            """SELECT id, url, first_seen, closed_at, is_active FROM jobs
               WHERE company_id = %s AND fingerprint = %s AND fingerprint <> '' AND id <> %s
               ORDER BY first_seen""",
            (row["company_id"], row["fingerprint"], job_id),
        ).fetchall()
    job = _shape_job(row, _skills_for(conn, [job_id]).get(job_id, []))
    job.update(
        department=row["department"],
        description=row["description"],
        source_posted_at=row["posted_at"],
        last_seen=row["last_seen"],
        posting_history=history,
    )
    return job


def list_companies(conn: psycopg.Connection) -> list[dict]:
    with _cursor(conn) as cur:
        return cur.execute(
            f"""{TRACKING_START}
            SELECT c.name, c.platform,
                   count(*) FILTER (WHERE j.is_active)::int AS active_jobs,
                   count(*) FILTER (WHERE j.is_active AND s.ghost_risk = 'high')::int AS high_risk_jobs,
                   count(*) FILTER (WHERE j.first_seen > t.started
                                      AND j.first_seen >= now() - interval '7 days')::int AS new_last_7_days
            FROM companies c
            JOIN jobs j ON j.company_id = c.id
            JOIN tracking t ON t.company_id = c.id
            LEFT JOIN job_signals_mv s ON s.job_id = j.id
            GROUP BY c.name, c.platform
            ORDER BY active_jobs DESC, c.name"""
        ).fetchall()


def stats(conn: psycopg.Connection) -> dict:
    with _cursor(conn) as cur:
        row = cur.execute(
            f"""{TRACKING_START}
            SELECT count(*) FILTER (WHERE j.is_active)::int AS active_jobs,
                   count(DISTINCT j.company_id)::int AS companies,
                   count(*) FILTER (WHERE j.first_seen > t.started
                                      AND j.first_seen >= now() - interval '7 days')::int AS new_last_7_days,
                   count(*) FILTER (WHERE j.is_active AND j.is_canada)::int AS canada_active_jobs,
                   count(*) FILTER (WHERE j.is_active AND s.ghost_risk = 'high')::int AS high_risk_active_jobs,
                   count(*) FILTER (WHERE j.is_active AND j.salary_min IS NOT NULL)::int
                       AS with_salary_active_jobs,
                   max(s.computed_at) AS signals_computed_at
            FROM jobs j
            JOIN tracking t ON t.company_id = j.company_id
            LEFT JOIN job_signals_mv s ON s.job_id = j.id"""
        ).fetchone()
        last_run = cur.execute(
            """SELECT started_at, finished_at, companies_ok, companies_failed, jobs_seen,
                      jobs_new, jobs_closed, duration_seconds::float AS duration_seconds
               FROM ingest_runs ORDER BY started_at DESC LIMIT 1"""
        ).fetchone()
    return {**row, "last_run": last_run}


def skill_demand(
    conn: psycopg.Connection,
    have: list[str],
    roles: tuple[str, ...],
    levels: tuple[str, ...],
    anywhere: bool,
    limit: int,
) -> insights.GapReport:
    return insights.skills_gap(
        conn, have=have, role_types=roles, levels=levels, canada_or_remote=not anywhere, limit=limit
    )


def hiring_calendar(
    conn: psycopg.Connection, levels: list[str], roles: list[str], companies: list[str]
) -> list[dict]:
    clauses, params = [], {}
    if levels:
        clauses.append("level = ANY(%(levels)s)")
        params["levels"] = levels
    if roles:
        clauses.append("role_type = ANY(%(roles)s)")
        params["roles"] = roles
    if companies:
        clauses.append("lower(company) = ANY(%(companies)s)")
        params["companies"] = [c.lower() for c in companies]
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with _cursor(conn) as cur:
        return cur.execute(
            f"SELECT * FROM hiring_calendar {where} ORDER BY year DESC, first_opened, company", params
        ).fetchall()