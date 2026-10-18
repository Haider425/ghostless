"""The Ghostless web API: read-only access to collected postings and signals.

Run it with `ghostless serve`, then open http://localhost:8000/docs.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from contextlib import asynccontextmanager
from typing import Annotated, Literal

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from psycopg_pool import ConnectionPool

from tracker import __version__
from tracker.api import queries
from tracker.api.schemas import (
    CalendarEntry,
    Company,
    GapReport,
    GhostRisk,
    JobDetail,
    JobPage,
    Level,
    RoleType,
    SkillCount,
    Stats,
)

log = logging.getLogger(__name__)

CACHE_SECONDS = 300  # data changes once a day, so short client caching is safe
Location = Literal["any", "canada", "remote", "canada_or_remote"]
Status = Literal["active", "closed", "all"]
Sort = Literal["newest", "oldest", "salary", "company"]

DESCRIPTION = """
Honest job data for Canadian tech students: real postings, true first-seen dates,
ghost job signals and Ontario pay and vacancy disclosures, collected daily from 54 employers.

Data refreshes once a day. Every posting links to the employer's own page.
"""


def _pool(dsn: str) -> ConnectionPool:
    return ConnectionPool(
        conninfo=dsn,
        # min_size=0 and a short max_idle let a serverless database (Neon)
        # sleep between requests; check= replaces connections the database
        # dropped while asleep, so the first request after a nap still works.
        min_size=0,
        max_size=int(os.environ.get("GHOSTLESS_API_POOL_SIZE", "4")),
        max_idle=60,
        check=ConnectionPool.check_connection,
        kwargs={"autocommit": True, "connect_timeout": 30},
        open=True,
    )


def create_app(dsn: str | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        from tracker.config import database_url

        app.state.pool = _pool(dsn or database_url())
        try:
            yield
        finally:
            app.state.pool.close()

    app = FastAPI(
        title="Ghostless API",
        version=__version__,
        description=DESCRIPTION,
        lifespan=lifespan,
    )

    origins = [o.strip() for o in os.environ.get("GHOSTLESS_CORS_ORIGINS", "*").split(",") if o.strip()]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET"], allow_headers=["*"])

    @app.middleware("http")
    async def cache_headers(request: Request, call_next):
        response = await call_next(request)
        if request.method == "GET" and response.status_code == 200 and request.url.path not in ("/health",):
            response.headers.setdefault("Cache-Control", f"public, max-age={CACHE_SECONDS}")
        return response

    @app.exception_handler(psycopg.errors.UndefinedTable)
    async def not_ingested(request: Request, exc: Exception):
        return JSONResponse(
            status_code=503,
            content={"detail": "No data yet: run `ghostless ingest` at least once."},
        )

    @app.exception_handler(psycopg.OperationalError)
    async def database_down(request: Request, exc: Exception):
        log.error("database unavailable: %s", exc)
        return JSONResponse(status_code=503, content={"detail": "Database unavailable, try again shortly."})

    register_routes(app)
    return app


def get_conn(request: Request) -> Iterator[psycopg.Connection]:
    with request.app.state.pool.connection() as conn:
        yield conn


Conn = Annotated[psycopg.Connection, Depends(get_conn)]


def _split(value: str | None) -> list[str]:
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def register_routes(app: FastAPI) -> None:
    @app.get("/", include_in_schema=False)
    def root():
        return {"name": "Ghostless API", "version": __version__, "docs": "/docs"}

    @app.get("/health", tags=["meta"], summary="Liveness check (does not touch the database)")
    def health():
        return {"status": "ok"}

    @app.get("/stats", response_model=Stats, tags=["meta"], summary="Totals and the latest ingest run")
    def get_stats(conn: Conn):
        return queries.stats(conn)

    @app.get("/jobs", response_model=JobPage, tags=["jobs"], summary="Search postings")
    def list_jobs(
        conn: Conn,
        q: Annotated[str | None, Query(max_length=100, description="text in the title")] = None,
        level: Annotated[list[Level] | None, Query(description="repeatable")] = None,
        role: Annotated[list[RoleType] | None, Query(description="repeatable")] = None,
        company: Annotated[list[str] | None, Query(description="repeatable, case-insensitive")] = None,
        skill: Annotated[list[str] | None, Query(description="postings asking for any of these")] = None,
        risk: Annotated[list[GhostRisk] | None, Query(description="ghost risk, repeatable")] = None,
        location: Location = "any",
        status: Status = "active",
        new_within_days: Annotated[int | None, Query(ge=1, le=365)] = None,
        has_salary: bool = False,
        sort: Sort = "newest",
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
        offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
    ):
        filters = queries.JobFilters(
            q=q,
            levels=level or [],
            roles=role or [],
            companies=company or [],
            skills=skill or [],
            risks=risk or [],
            location=location,
            status=status,
            new_within_days=new_within_days,
            has_salary=has_salary,
        )
        return queries.list_jobs(conn, filters, sort, limit, offset)

    @app.get("/jobs/{job_id}", response_model=JobDetail, tags=["jobs"], summary="One posting in full")
    def get_job(conn: Conn, job_id: int):
        job = queries.get_job(conn, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        return job

    @app.get("/companies", response_model=list[Company], tags=["companies"], summary="Tracked employers")
    def list_companies(conn: Conn):
        return queries.list_companies(conn)

    @app.get("/skills/top", response_model=list[SkillCount], tags=["skills"], summary="Most requested skills")
    def top_skills(
        conn: Conn,
        role: Annotated[list[RoleType] | None, Query()] = None,
        level: Annotated[list[Level] | None, Query()] = None,
        anywhere: Annotated[bool, Query(description="include postings outside Canada and remote")] = False,
        limit: Annotated[int, Query(ge=1, le=50)] = 20,
    ):
        report = queries.skill_demand(
            conn, [], tuple(role or ["sde"]), tuple(level or ["intern", "new_grad"]), anywhere, limit
        )
        return [{"skill": s.skill, "postings": s.postings, "share": s.share} for s in report.skills]

    @app.get("/skills/gap", response_model=GapReport, tags=["skills"], summary="Compare your skills")
    def skills_gap(
        conn: Conn,
        have: Annotated[
            str, Query(min_length=1, max_length=500, description='comma separated, e.g. "Python, SQL"')
        ],
        role: Annotated[list[RoleType] | None, Query()] = None,
        level: Annotated[list[Level] | None, Query()] = None,
        anywhere: bool = False,
        limit: Annotated[int, Query(ge=1, le=50)] = 15,
    ):
        report = queries.skill_demand(
            conn,
            _split(have),
            tuple(role or ["sde"]),
            tuple(level or ["intern", "new_grad"]),
            anywhere,
            limit,
        )
        return {
            "total_postings": report.total_postings,
            "recognized": report.recognized,
            "unrecognized": report.unrecognized,
            "missing_top_10": report.missing(),
            "skills": [
                {"skill": s.skill, "postings": s.postings, "share": s.share, "have": s.have}
                for s in report.skills
            ],
        }

    @app.get(
        "/calendar",
        response_model=list[CalendarEntry],
        tags=["calendar"],
        summary="When employers opened intern and new grad roles",
    )
    def calendar(
        conn: Conn,
        level: Annotated[list[Literal["intern", "new_grad"]] | None, Query()] = None,
        role: Annotated[list[RoleType] | None, Query()] = None,
        company: Annotated[list[str] | None, Query()] = None,
    ):
        return queries.hiring_calendar(conn, level or [], role or [], company or [])