"""SQL behind each endpoint.

Every function takes an open connection and returns plain dicts shaped like
the response models. WHERE clauses are built only from fixed fragments in
this file; user input is always passed as a bound parameter.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import psycopg
from psycopg.rows import dict_row

from tracker import insights
from tracker.disclosures import ai_screening_evidence, parse_salary, vacancy_evidence

TECH_ROLES = ["sde", "data_eng", "data", "ml", "hardware", "security"]


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


LOCATIONS = {
    "any": None,
    "canada": "j.is_canada",
    "remote": "j.is_remote",
    "canada_or_remote": "(j.is_canada OR j.is_remote)",
}
STATUSES = {"active": "j.is_active", "closed": "NOT j.is_active", "all": None}
# When a posting went up, as best known. A posting Ghostless saw appear has its
# first_seen; one already open when tracking began (every posting from a
# company's first run shares that run's time) is dated by its own site, when
# the site says, and never later than first seen.
# By day: postings from the same day are mixed across companies in a stable
# order, so a page isn't one employer's whole board in a row.
LISTED = "date_trunc('day', least(j.first_seen, coalesce(j.posted_at, j.first_seen)), 'UTC')"
MIX = "hashtext(j.id::text), j.id"
# An employer that posts many roles in one day would fill whole pages: each
# extra posting it made that day is placed half a day further back.
SPREAD = (
    f"({LISTED} - (row_number() OVER (PARTITION BY j.company_id, {LISTED} ORDER BY {MIX}) - 1)"
    " * interval '12 hours')"
)
SORTS = {
    "newest": f"{SPREAD} DESC, {MIX}",
    "oldest": f"{LISTED} ASC, {MIX}",
    "salary": f"j.salary_max DESC NULLS LAST, {LISTED} DESC, {MIX}",
    "company": f"c.name ASC, {LISTED} DESC, j.id DESC",
}

# Postings first seen on a company's very first run were already open, so
# they must not count as "new". This is that first run's timestamp.
TRACKING_START = """
    WITH tracking AS (SELECT company_id, min(first_seen) AS started FROM jobs GROUP BY company_id)
"""

JOB_COLUMNS = """
    j.id, c.name AS company, c.domain AS company_domain, j.title, j.location, j.url, j.level, j.role_type,
    j.is_canada, j.is_remote, j.first_seen, j.closed_at, j.is_active,
    j.salary_min, j.salary_max, j.salary_period, j.salary_currency,
    j.vacancy, j.ai_screening,
    -- same age as job_signals, so a flag and the age shown beside it always agree
    floor(extract(epoch FROM coalesce(j.closed_at, now()) - CASE
        WHEN j.listed_in IS NOT NULL AND j.posted_at < j.first_seen THEN j.posted_at
        ELSE j.first_seen END) / 86400)::int AS days_open,
    s.ghost_risk, s.flags, s.age_known, s.typical_days_open, s.times_posted_before,
    j.terms, j.listed_in
"""

JOB_FROM = """
    FROM jobs j
    JOIN companies c ON c.id = j.company_id
    LEFT JOIN job_signals_mv s ON s.job_id = j.id
"""


def search_words(q: str) -> list[str]:
    """The words of a search, without filler: "jobs at amazon in toronto" is amazon and toronto."""
    filler = {"at", "in", "for", "the", "a", "an", "of", "and", "jobs", "job", "roles", "role", "positions"}
    words = [w.strip(",.;:!?\"'()") for w in q.split()]
    return [w for w in words if w and w.lower() not in filler][:6]


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
    terms: list[str] = field(default_factory=list)

    def where(self) -> tuple[str, dict[str, Any]]:
        clauses: list[str] = []
        params: dict[str, Any] = {}
        if STATUSES[self.status]:
            clauses.append(STATUSES[self.status])
        if LOCATIONS[self.location]:
            clauses.append(LOCATIONS[self.location])
        if self.q:
            # every word has to match the title, company, place, department or a skill
            for i, word in enumerate(search_words(self.q)):
                key = f"q{i}"
                clauses.append(
                    f"""(j.title ILIKE %({key})s OR c.name ILIKE %({key})s OR j.location ILIKE %({key})s
                         OR j.department ILIKE %({key})s
                         OR EXISTS (SELECT 1 FROM job_skills qs JOIN skills qk ON qk.id = qs.skill_id
                                    WHERE qs.job_id = j.id AND lower(qk.name) = %({key}_exact)s))"""
                )
                escaped = word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                params[key] = f"%{escaped}%"
                params[f"{key}_exact"] = word.lower()
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
        if self.terms:
            clauses.append("j.terms && %(terms)s::text[]")
            params["terms"] = self.terms
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
        "company_slug": slugify(row["company"]),
        "company_domain": row["company_domain"],
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
        "terms": row.get("terms") or [],
        "listed_in": row.get("listed_in"),
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


def jobs_by_ids(conn: psycopg.Connection, job_ids: list[int]) -> list[dict]:
    """Job summaries in the order given (for saved jobs and recommendations)."""
    if not job_ids:
        return []
    with _cursor(conn) as cur:
        rows = cur.execute(f"SELECT {JOB_COLUMNS} {JOB_FROM} WHERE j.id = ANY(%s)", (job_ids,)).fetchall()
    skills = _skills_for(conn, [r["id"] for r in rows])
    by_id = {r["id"]: _shape_job(r, skills.get(r["id"], [])) for r in rows}
    return [by_id[i] for i in job_ids if i in by_id]


def descriptions(conn: psycopg.Connection, job_ids: list[int]) -> dict[int, str]:
    """Posting descriptions by job id, for scoring a resume against them in full."""
    if not job_ids:
        return {}
    rows = conn.execute(
        "SELECT id, description FROM jobs WHERE id = ANY(%s) AND description IS NOT NULL", (list(job_ids),)
    ).fetchall()
    return {i: d for i, d in rows}


def matching_pool(
    conn: psycopg.Connection, location: str = "any", include_high_risk: bool = False
) -> list[dict]:
    """Every open tech posting, shaped like a job summary, for resume matching."""
    clauses = ["j.is_active", "j.role_type = ANY(%(roles)s)"]
    if LOCATIONS[location]:
        clauses.append(LOCATIONS[location])
    if not include_high_risk:
        clauses.append("coalesce(s.ghost_risk, 'low') <> 'high'")
    with _cursor(conn) as cur:
        rows = cur.execute(
            f"SELECT {JOB_COLUMNS} {JOB_FROM} WHERE {' AND '.join(clauses)}", {"roles": TECH_ROLES}
        ).fetchall()
    skills = dict(
        conn.execute(
            """SELECT js.job_id, array_agg(sk.name ORDER BY sk.name)
               FROM job_skills js JOIN skills sk ON sk.id = js.skill_id
               JOIN jobs j ON j.id = js.job_id WHERE j.is_active GROUP BY js.job_id"""
        ).fetchall()
    )
    return [_shape_job(r, skills.get(r["id"], [])) for r in rows]


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
    text = row["description"] or ""
    salary = parse_salary(text)
    job.update(
        evidence={
            "vacancy": vacancy_evidence(text)[1] if row["vacancy"] else None,
            "salary": salary.text if salary and row["salary_min"] is not None else None,
            "ai_screening": ai_screening_evidence(text)[1] if row["ai_screening"] is not None else None,
        },
        department=row["department"],
        description=row["description"],
        source_posted_at=row["posted_at"],
        last_seen=row["last_seen"],
        posting_history=history,
    )
    return job


COMPANY_SUMMARY = """
    WITH tracking AS (SELECT company_id, min(first_seen) AS started FROM jobs GROUP BY company_id),
    typical AS (
        SELECT j.company_id,
               round(percentile_cont(0.5) WITHIN GROUP (
                   ORDER BY extract(epoch FROM j.closed_at - j.first_seen) / 86400))::int AS days
        FROM jobs j JOIN tracking t ON t.company_id = j.company_id
        WHERE j.closed_at IS NOT NULL AND j.first_seen > t.started
        GROUP BY j.company_id HAVING count(*) >= 5
    )
    SELECT c.id, c.name, c.domain, c.platform, c.origin, t.started AS tracking_since,
           count(*) FILTER (WHERE j.is_active)::int AS active_jobs,
           count(*) FILTER (WHERE j.is_active AND j.role_type <> 'other')::int AS tech_active_jobs,
           count(*) FILTER (WHERE j.is_active AND s.ghost_risk = 'high')::int AS high_risk_jobs,
           count(*) FILTER (WHERE j.first_seen > t.started
                              AND j.first_seen >= now() - interval '7 days')::int AS new_last_7_days,
           count(*) FILTER (WHERE j.closed_at >= now() - interval '30 days')::int AS closed_last_30_days,
           count(*) FILTER (WHERE j.is_active AND j.salary_min IS NOT NULL)::int AS with_salary_active_jobs,
           ty.days AS typical_days_open
    FROM companies c
    JOIN jobs j ON j.company_id = c.id
    JOIN tracking t ON t.company_id = c.id
    LEFT JOIN typical ty ON ty.company_id = c.id
    LEFT JOIN job_signals_mv s ON s.job_id = j.id
"""


def _company_row(row: dict) -> dict:
    return {**row, "slug": slugify(row["name"])}


def list_companies(conn: psycopg.Connection) -> list[dict]:
    with _cursor(conn) as cur:
        rows = cur.execute(
            f"""{COMPANY_SUMMARY}
            GROUP BY c.id, c.name, c.domain, c.platform, c.origin, t.started, ty.days
            ORDER BY active_jobs DESC, c.name"""
        ).fetchall()
    return [_company_row(r) for r in rows]


WEEKLY = """
    WITH tracking AS (SELECT company_id, min(first_seen) AS started FROM jobs GROUP BY company_id),
    weeks AS (
        SELECT generate_series(
            date_trunc('week', (now() AT TIME ZONE 'America/Toronto')) - make_interval(weeks => %(weeks)s - 1),
            date_trunc('week', (now() AT TIME ZONE 'America/Toronto')),
            interval '1 week'
        )::date AS week_start
    ),
    scoped AS (
        SELECT j.*, t.started FROM jobs j JOIN tracking t ON t.company_id = j.company_id
        WHERE j.role_type = ANY(%(roles)s) {company_clause}
    )
    SELECT w.week_start,
           (SELECT count(*) FROM scoped j
             WHERE j.first_seen > j.started
               AND date_trunc('week', j.first_seen AT TIME ZONE 'America/Toronto')::date = w.week_start)::int AS new,
           (SELECT count(*) FROM scoped j
             WHERE j.closed_at IS NOT NULL
               AND date_trunc('week', j.closed_at AT TIME ZONE 'America/Toronto')::date = w.week_start)::int AS closed
    FROM weeks w ORDER BY w.week_start
"""


def weekly(
    conn: psycopg.Connection, weeks: int, roles: list[str], company_id: int | None = None
) -> list[dict]:
    clause = "AND j.company_id = %(company)s" if company_id is not None else ""
    with _cursor(conn) as cur:
        return cur.execute(
            WEEKLY.format(company_clause=clause),
            {"weeks": weeks, "roles": roles or TECH_ROLES, "company": company_id},
        ).fetchall()


def get_company(conn: psycopg.Connection, slug: str) -> dict | None:
    with _cursor(conn) as cur:
        rows = cur.execute(
            f"{COMPANY_SUMMARY} GROUP BY c.id, c.name, c.domain, c.platform, c.origin, t.started, ty.days"
        ).fetchall()
        row = next((r for r in rows if slugify(r["name"]) == slug), None)
        if row is None:
            return None
        roles = cur.execute(
            """SELECT role_type AS key, count(*)::int AS count FROM jobs
               WHERE company_id = %s AND is_active GROUP BY role_type ORDER BY count DESC""",
            (row["id"],),
        ).fetchall()
        levels = cur.execute(
            """SELECT level AS key, count(*)::int AS count FROM jobs
               WHERE company_id = %s AND is_active AND role_type <> 'other'
               GROUP BY level ORDER BY count DESC""",
            (row["id"],),
        ).fetchall()
        skills = cur.execute(
            """SELECT s.name AS skill, count(*)::int AS postings,
                      count(*)::float / nullif((SELECT count(*) FROM jobs
                          WHERE company_id = %(c)s AND is_active AND role_type <> 'other'), 0) AS share
               FROM jobs j JOIN job_skills js ON js.job_id = j.id JOIN skills s ON s.id = js.skill_id
               WHERE j.company_id = %(c)s AND j.is_active AND j.role_type <> 'other'
               GROUP BY s.name ORDER BY postings DESC, s.name LIMIT 12""",
            {"c": row["id"]},
        ).fetchall()
    return {
        **_company_row(row),
        "roles": roles,
        "levels": levels,
        "weekly": weekly(conn, 12, TECH_ROLES, row["id"]),
        "top_skills": [{**sk, "share": sk["share"] or 0} for sk in skills],
    }


def stats(conn: psycopg.Connection) -> dict:
    with _cursor(conn) as cur:
        row = cur.execute(
            f"""{TRACKING_START}
            SELECT count(*) FILTER (WHERE j.is_active)::int AS active_jobs,
                   count(*) FILTER (WHERE j.is_active AND j.role_type <> 'other')::int AS tech_active_jobs,
                   count(*) FILTER (WHERE j.role_type <> 'other' AND j.first_seen > t.started
                                      AND j.first_seen >= now() - interval '7 days')::int AS tech_new_last_7_days,
                   count(*) FILTER (WHERE j.is_active AND j.role_type <> 'other'
                                      AND s.ghost_risk = 'high')::int AS tech_high_risk_active_jobs,
                   count(*) FILTER (WHERE j.is_active AND j.role_type <> 'other'
                                      AND j.salary_min IS NOT NULL)::int AS tech_with_salary_active_jobs,
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


def term_counts(conn: psycopg.Connection) -> list[dict]:
    """Seasons named by open tech postings, soonest first."""
    rows = conn.execute(
        """SELECT term, count(*)::int FROM jobs, unnest(terms) AS term
           WHERE is_active AND role_type <> 'other' GROUP BY term"""
    ).fetchall()
    order = {"Winter": 0, "Spring": 1, "Summer": 2, "Fall": 3}
    rows.sort(key=lambda r: (r[0][-4:], order.get(r[0].split()[0], 9)))
    return [{"term": term, "jobs": jobs} for term, jobs in rows]
