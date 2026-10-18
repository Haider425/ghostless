"""Problem reports from users: wrong job data, broken links, site bugs, ideas."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from tracker.api.deps import Conn, OptionalUser, client_ip, limiter

router = APIRouter(tags=["reports"])

Category = Literal["wrong_job_info", "broken_link", "site_bug", "suggestion", "other"]


class ReportIn(BaseModel):
    category: Category
    message: str = Field(min_length=3, max_length=4000)
    page: str | None = Field(None, max_length=500)
    job_id: int | None = None
    email: str | None = Field(None, max_length=254, description="for a reply; optional")


class ReportOut(BaseModel):
    id: int
    detail: str


@router.post(
    "/reports", response_model=ReportOut, status_code=201, summary="Report a problem or send feedback"
)
def create_report(body: ReportIn, request: Request, user: OptionalUser, conn: Conn):
    limiter.check(f"report:{client_ip(request)}", 10, 3600)
    email = (body.email or "").strip() or (user["email"] if user else None)
    job_id = body.job_id
    if job_id is not None and conn.execute("SELECT 1 FROM jobs WHERE id = %s", (job_id,)).fetchone() is None:
        job_id = None
    row = conn.execute(
        """INSERT INTO reports (user_id, email, category, message, page, job_id)
           VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
        (user["id"] if user else None, email, body.category, body.message.strip(), body.page, job_id),
    ).fetchone()
    return {"id": row[0], "detail": "Thanks. Your report reached the Ghostless team."}
