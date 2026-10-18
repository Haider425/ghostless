"""Owner dashboard: users, traffic, resumes, reports, errors and ingest health.
Days are Toronto days.
Every endpoint needs an admin account (`ghostless admin add you@example.com`)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from tracker.api.deps import AdminUser, Conn

router = APIRouter(prefix="/admin", tags=["admin"])

ReportStatus = Literal["open", "in_progress", "resolved", "dismissed"]


class Overview(BaseModel):
    users_total: int
    users_new_7d: int
    users_active_7d: int
    users_active_30d: int
    users_verified: int
    pageviews_today: int
    pageviews_7d: int
    visitors_today: int
    visitors_7d: int
    resumes_stored: int
    analyses_7d: int
    ai_feedback_7d: int
    saved_jobs: int
    reports_open: int
    errors_24h: int
    jobs_active: int
    last_run: dict[str, Any] | None


class DayStats(BaseModel):
    day: date
    signups: int
    pageviews: int
    visitors: int
    active_users: int
    analyses: int


class PathCount(BaseModel):
    path: str
    views: int


class AdminUserRow(BaseModel):
    id: int
    email: str
    name: str | None
    role: str
    email_verified: bool
    created_at: datetime
    last_active_at: datetime | None
    saved_jobs: int
    resumes: int


class UserPage(BaseModel):
    total: int
    items: list[AdminUserRow]


class ReportRow(BaseModel):
    id: int
    category: str
    message: str
    page: str | None
    job_id: int | None
    job_title: str | None
    email: str | None
    user_id: int | None
    status: ReportStatus
    admin_note: str | None
    created_at: datetime
    resolved_at: datetime | None


class ReportUpdate(BaseModel):
    status: ReportStatus
    admin_note: str | None = Field(None, max_length=2000)


class ErrorRow(BaseModel):
    id: int
    path: str | None
    message: str | None
    digest: str | None
    created_at: datetime


class RunRow(BaseModel):
    started_at: datetime
    finished_at: datetime | None
    companies_ok: int
    companies_failed: int
    jobs_seen: int
    jobs_new: int
    jobs_closed: int
    duration_seconds: float | None


@router.get("/overview", response_model=Overview, summary="Headline numbers")
def overview(admin: AdminUser, conn: Conn):
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(
            """
            SELECT
              (SELECT count(*) FROM users)::int AS users_total,
              (SELECT count(*) FROM users WHERE created_at >= now() - interval '7 days')::int AS users_new_7d,
              (SELECT count(*) FROM users WHERE last_active_at >= now() - interval '7 days')::int AS users_active_7d,
              (SELECT count(*) FROM users WHERE last_active_at >= now() - interval '30 days')::int AS users_active_30d,
              (SELECT count(*) FROM users WHERE email_verified_at IS NOT NULL)::int AS users_verified,
              (SELECT count(*) FROM events WHERE kind = 'pageview' AND created_at >= (date_trunc('day', now() AT TIME ZONE 'America/Toronto') AT TIME ZONE 'America/Toronto'))::int
                  AS pageviews_today,
              (SELECT count(*) FROM events WHERE kind = 'pageview' AND created_at >= now() - interval '7 days')::int
                  AS pageviews_7d,
              (SELECT count(DISTINCT visitor) FROM events
                WHERE kind = 'pageview' AND created_at >= (date_trunc('day', now() AT TIME ZONE 'America/Toronto') AT TIME ZONE 'America/Toronto'))::int AS visitors_today,
              (SELECT count(DISTINCT (visitor, (created_at AT TIME ZONE 'America/Toronto')::date)) FROM events
                WHERE kind = 'pageview' AND created_at >= now() - interval '7 days')::int AS visitors_7d,
              (SELECT count(*) FROM resumes)::int AS resumes_stored,
              (SELECT count(*) FROM events WHERE kind = 'resume_analyzed'
                AND created_at >= now() - interval '7 days')::int AS analyses_7d,
              (SELECT count(*) FROM events WHERE kind = 'ai_feedback'
                AND created_at >= now() - interval '7 days')::int AS ai_feedback_7d,
              (SELECT count(*) FROM saved_jobs)::int AS saved_jobs,
              (SELECT count(*) FROM reports WHERE status IN ('open', 'in_progress'))::int AS reports_open,
              (SELECT count(*) FROM events WHERE kind = 'error' AND created_at >= now() - interval '1 day')::int
                  AS errors_24h,
              (SELECT count(*) FROM jobs WHERE is_active)::int AS jobs_active
            """
        ).fetchone()
        last_run = cur.execute(
            """SELECT started_at, finished_at, companies_ok, companies_failed, jobs_seen, jobs_new, jobs_closed,
                      duration_seconds::float AS duration_seconds
               FROM ingest_runs ORDER BY started_at DESC LIMIT 1"""
        ).fetchone()
    return {**row, "last_run": last_run}


@router.get("/daily", response_model=list[DayStats], summary="Per-day activity, oldest first")
def daily(admin: AdminUser, conn: Conn, days: int = Query(30, ge=7, le=180)):
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            """
            WITH d AS (
                SELECT generate_series((now() AT TIME ZONE 'America/Toronto')::date - (%(days)s - 1), (now() AT TIME ZONE 'America/Toronto')::date, interval '1 day')::date AS day
            )
            SELECT d.day,
              (SELECT count(*) FROM users u WHERE (u.created_at AT TIME ZONE 'America/Toronto')::date = d.day)::int AS signups,
              (SELECT count(*) FROM events e WHERE e.kind = 'pageview' AND (e.created_at AT TIME ZONE 'America/Toronto')::date = d.day)::int
                  AS pageviews,
              (SELECT count(DISTINCT visitor) FROM events e
                WHERE e.kind = 'pageview' AND (e.created_at AT TIME ZONE 'America/Toronto')::date = d.day)::int AS visitors,
              (SELECT count(DISTINCT user_id) FROM events e
                WHERE e.user_id IS NOT NULL AND (e.created_at AT TIME ZONE 'America/Toronto')::date = d.day)::int AS active_users,
              (SELECT count(*) FROM events e WHERE e.kind = 'resume_analyzed' AND (e.created_at AT TIME ZONE 'America/Toronto')::date = d.day)::int
                  AS analyses
            FROM d ORDER BY d.day
            """,
            {"days": days},
        ).fetchall()


@router.get("/top-pages", response_model=list[PathCount], summary="Most viewed pages")
def top_pages(
    admin: AdminUser, conn: Conn, days: int = Query(7, ge=1, le=90), limit: int = Query(15, ge=1, le=100)
):
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            """SELECT
                 -- group job and company pages so one popular page type doesn't flood the list
                 regexp_replace(regexp_replace(path, '^/jobs/[0-9]+$', '/jobs/:id'), '^/companies/[^/]+$',
                                '/companies/:slug') AS path,
                 count(*)::int AS views
               FROM events WHERE kind = 'pageview' AND path IS NOT NULL
                 AND created_at >= now() - make_interval(days => %s)
               GROUP BY 1 ORDER BY views DESC LIMIT %s""",
            (days, limit),
        ).fetchall()


@router.get("/users", response_model=UserPage, summary="Accounts, newest first")
def users(
    admin: AdminUser,
    conn: Conn,
    q: str | None = Query(None, max_length=100),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    where, params = "", {"limit": limit, "offset": offset}
    if q:
        where = "WHERE u.email ILIKE %(q)s OR u.name ILIKE %(q)s"
        params["q"] = f"%{q.replace('%', '').replace('_', '')}%"
    with conn.cursor(row_factory=dict_row) as cur:
        total = cur.execute(f"SELECT count(*) AS n FROM users u {where}", params).fetchone()["n"]
        items = cur.execute(
            f"""SELECT u.id, u.email, u.name, u.role, u.email_verified_at IS NOT NULL AS email_verified,
                       u.created_at, u.last_active_at,
                       (SELECT count(*) FROM saved_jobs s WHERE s.user_id = u.id)::int AS saved_jobs,
                       (SELECT count(*) FROM resumes r WHERE r.user_id = u.id)::int AS resumes
                FROM users u {where} ORDER BY u.created_at DESC LIMIT %(limit)s OFFSET %(offset)s""",
            params,
        ).fetchall()
    return {"total": total, "items": items}


@router.get("/reports", response_model=list[ReportRow], summary="Problem reports, newest first")
def reports(
    admin: AdminUser, conn: Conn, status: ReportStatus | None = None, limit: int = Query(100, ge=1, le=500)
):
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            f"""SELECT r.id, r.category, r.message, r.page, r.job_id, j.title AS job_title, r.email, r.user_id,
                       r.status, r.admin_note, r.created_at, r.resolved_at
                FROM reports r LEFT JOIN jobs j ON j.id = r.job_id
                {"WHERE r.status = %(status)s" if status else ""}
                ORDER BY (r.status IN ('open', 'in_progress')) DESC, r.created_at DESC LIMIT %(limit)s""",
            {"status": status, "limit": limit},
        ).fetchall()


@router.patch("/reports/{report_id}", response_model=ReportRow, summary="Update a report's status")
def update_report(report_id: int, body: ReportUpdate, admin: AdminUser, conn: Conn):
    closed = body.status in ("resolved", "dismissed")
    updated = conn.execute(
        """UPDATE reports SET status = %s, admin_note = coalesce(%s, admin_note),
                  resolved_at = CASE WHEN %s THEN coalesce(resolved_at, now()) ELSE NULL END
           WHERE id = %s""",
        (body.status, body.admin_note, closed, report_id),
    ).rowcount
    if not updated:
        raise HTTPException(status_code=404, detail="report not found")
    return next(r for r in reports(admin, conn, None, 500) if r["id"] == report_id)


@router.get("/errors", response_model=list[ErrorRow], summary="Recent errors reported by the website")
def errors(admin: AdminUser, conn: Conn, limit: int = Query(50, ge=1, le=500)):
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            """SELECT id, path, detail->>'message' AS message, detail->>'digest' AS digest, created_at
               FROM events WHERE kind = 'error' ORDER BY created_at DESC LIMIT %s""",
            (limit,),
        ).fetchall()


@router.get("/runs", response_model=list[RunRow], summary="Recent ingest runs")
def runs(admin: AdminUser, conn: Conn, limit: int = Query(14, ge=1, le=100)):
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            """SELECT started_at, finished_at, companies_ok, companies_failed, jobs_seen, jobs_new, jobs_closed,
                      duration_seconds::float AS duration_seconds
               FROM ingest_runs ORDER BY started_at DESC LIMIT %s""",
            (limit,),
        ).fetchall()
