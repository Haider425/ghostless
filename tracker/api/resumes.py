"""Resume endpoints: analyze, score against jobs, recommend jobs, store
resumes and builder documents, and optional AI feedback.

Analysis works without an account: the website keeps the resulting profile
in the visitor's browser and sends it back with match requests. Signed-in
users can store resumes so their matches follow them across devices.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import PurePath
from typing import Annotated, Any, Literal

import psycopg
from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from tracker.api import cache, events, queries
from tracker.api.deps import Conn, CurrentUser, OptionalUser, client_ip, limiter
from tracker.api.schemas import JobSummary
from tracker.resume import ai
from tracker.resume.document import ResumeDocument, document_to_text
from tracker.resume.extract import MAX_BYTES, UnreadableResume, extract_text
from tracker.resume.match import recommend, score_job
from tracker.resume.profile import build_profile
from tracker.resume.quality import check_resume
from tracker.resume.to_document import text_to_document

router = APIRouter(tags=["resumes"])

Level = Literal["student", "new_grad", "experienced", "senior"]


class ProfileModel(BaseModel):
    skills: list[str] = Field(default_factory=list, max_length=300)
    level: Level = "new_grad"
    target_levels: list[str] = Field(default_factory=list, max_length=4)
    months_experience: int = 0
    education: dict[str, Any] = Field(default_factory=dict)
    roles: dict[str, float] = Field(default_factory=dict)
    top_role: str = "sde"
    contact: dict[str, bool] = Field(default_factory=dict)
    sections: list[str] = Field(default_factory=list, max_length=20)
    bullet_count: int = 0
    quantified_bullets: int = 0
    weak_bullets: list[str] = Field(default_factory=list, max_length=10)
    unquantified_examples: list[str] = Field(default_factory=list, max_length=10)
    long_bullets: int = 0
    word_count: int = 0
    keywords: list[str] = Field(default_factory=list, max_length=4000)
    phrases: list[str] = Field(default_factory=list, max_length=4000)
    skill_evidence: dict[str, Literal["work", "project", "listed"]] = Field(default_factory=dict)


class CheckModel(BaseModel):
    id: str
    severity: Literal["high", "medium", "low"]
    title: str
    detail: str
    examples: list[str] = Field(default_factory=list)


class Analysis(BaseModel):
    profile: ProfileModel
    checks: list[CheckModel]
    strength: int = Field(description="0 to 100, from the checks")
    resume_id: int | None = Field(None, description="set when the resume was saved to the account")


class TextIn(BaseModel):
    text: str = Field(min_length=50, max_length=60_000)


class PartModel(BaseModel):
    key: str
    label: str
    points: float
    max: int
    detail: str


class RequirementModel(BaseModel):
    text: str
    status: Literal["met", "partial", "missing"]
    detail: str
    kind: Literal["skill", "preferred", "experience", "education", "enrollment"]


class MatchModel(BaseModel):
    score: int
    label: str
    skills_matched: list[str]
    skills_missing: list[str]
    components: dict[str, float]
    suggestions: list[str]
    limited: bool
    notes: list[str]
    breakdown: list[PartModel] = Field(
        default_factory=list, description="points per part, adding up to the score"
    )
    requirements: list[RequirementModel] = Field(
        default_factory=list, description="what the posting asks for, checked"
    )
    terms_matched: list[str] = Field(default_factory=list)
    terms_missing: list[str] = Field(default_factory=list)


class TailorIn(BaseModel):
    text: str = Field(min_length=1, max_length=60_000)
    job_id: int


class TailorOut(BaseModel):
    job: JobSummary
    match: MatchModel
    strength: int


class MatchIn(BaseModel):
    profile: ProfileModel | None = None
    resume_id: int | None = None
    job_ids: list[int] = Field(min_length=1, max_length=100)


class Recommendation(BaseModel):
    job: JobSummary
    match: MatchModel


class RecommendationsIn(BaseModel):
    profile: ProfileModel | None = None
    resume_id: int | None = None
    location: Literal["any", "canada", "remote", "canada_or_remote"] = "any"
    include_high_risk: bool = False
    limit: int = Field(30, ge=1, le=100)
    offset: int = Field(0, ge=0, le=1000)


class RecommendationPage(BaseModel):
    total: int
    items: list[Recommendation]


class ResumeSummary(BaseModel):
    id: int
    kind: Literal["upload", "built"]
    title: str
    file_name: str | None
    is_primary: bool
    strength: int | None
    created_at: datetime
    updated_at: datetime


class StoredResume(ResumeSummary):
    text: str | None
    analysis: Analysis | None
    document: ResumeDocument | None


class BuiltIn(BaseModel):
    title: str = Field("My resume", min_length=1, max_length=80)
    document: ResumeDocument


class ImportIn(BaseModel):
    title: str = Field("My resume", min_length=1, max_length=80)
    analysis: Analysis


class RenameIn(BaseModel):
    title: str = Field(min_length=1, max_length=80)


class AIStatus(BaseModel):
    enabled: bool
    remaining_today: int | None = Field(None, description="for the signed-in user")


class AIIn(BaseModel):
    job_id: int
    resume_id: int | None = None
    text: str | None = Field(None, max_length=60_000)


class Rewrite(BaseModel):
    original: str
    improved: str


class AIFeedbackOut(BaseModel):
    summary: str
    strengths: list[str]
    gaps: list[str]
    rewrites: list[Rewrite]
    keywords: list[str]
    remaining_today: int


# ---------- helpers ----------


# Bump when the profile or the checks change, so saved resumes are re-read
# with the current rules (2: link words in the header count as links).
ANALYSIS_VERSION = 2


def analyze_text(text: str) -> dict:
    profile = build_profile(text)
    checks, strength = check_resume(text, profile)
    return {
        "profile": profile.to_dict(),
        "checks": [c.to_dict() for c in checks],
        "strength": strength,
        "version": ANALYSIS_VERSION,
    }


def _store_resume(
    conn: psycopg.Connection,
    user_id: int,
    kind: str,
    title: str,
    file_name: str | None,
    text: str | None,
    analysis: dict,
    document: dict | None,
) -> int:
    with conn.transaction():
        first = conn.execute(
            "SELECT NOT EXISTS (SELECT 1 FROM resumes WHERE user_id = %s)", (user_id,)
        ).fetchone()[0]
        row = conn.execute(
            """INSERT INTO resumes (user_id, kind, title, file_name, text, profile, document, is_primary)
               VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s) RETURNING id""",
            (
                user_id,
                kind,
                title[:80],
                file_name,
                text,
                json.dumps(analysis),
                json.dumps(document) if document else None,
                first,
            ),
        ).fetchone()
        count = conn.execute("SELECT count(*) FROM resumes WHERE user_id = %s", (user_id,)).fetchone()[0]
        if count > 20:
            raise HTTPException(status_code=400, detail="You can keep up to 20 resumes. Delete one first.")
    return row[0]


def _own_resume(conn: psycopg.Connection, user_id: int, resume_id: int) -> dict:
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(
            """SELECT id, kind, title, file_name, is_primary, created_at, updated_at, text, profile, document
               FROM resumes WHERE id = %s AND user_id = %s""",
            (resume_id, user_id),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="resume not found")
    stored = row["profile"] or {}
    if row["text"] and len(row["text"]) >= 50 and stored.get("version") != ANALYSIS_VERSION:
        # analysed under older rules: re-read once from the stored text and keep the result
        row["profile"] = analyze_text(row["text"])
        conn.execute(
            "UPDATE resumes SET profile = %s::jsonb WHERE id = %s AND user_id = %s",
            (json.dumps(row["profile"]), resume_id, user_id),
        )  # the pool's connections autocommit; inside a caller's transaction it joins that
    return row


def _profile_for(
    conn: psycopg.Connection, user: dict | None, profile: ProfileModel | None, resume_id: int | None
) -> dict:
    if resume_id is not None:
        if user is None:
            raise HTTPException(status_code=401, detail="Sign in to use a saved resume.")
        analysis = _own_resume(conn, user["id"], resume_id)["profile"] or {}
        return analysis.get("profile") or {}
    if profile is None:
        raise HTTPException(status_code=422, detail="Send a profile or a resume_id.")
    return profile.model_dump()


def _summary(row: dict) -> dict:
    analysis = row.get("profile") or {}
    return {
        **{k: row[k] for k in ("id", "kind", "title", "file_name", "is_primary", "created_at", "updated_at")},
        "strength": analysis.get("strength"),
    }


# ---------- analysis ----------


@router.post("/resume/analyze", response_model=Analysis, summary="Analyze a resume file (PDF or Word)")
async def analyze_file(
    request: Request,
    user: OptionalUser,
    conn: Conn,
    file: Annotated[UploadFile, File(description="PDF or Word (.docx), up to 5 MB")],
    save: Annotated[bool, Query(description="store it on the signed-in account")] = False,
):
    limiter.check(f"analyze:{client_ip(request)}", 30, 3600)
    data = await file.read(MAX_BYTES + 1)
    try:
        text = extract_text(data, file.filename or "", file.content_type or "")
    except UnreadableResume as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    analysis = analyze_text(text)
    if save:
        if user is None:
            raise HTTPException(status_code=401, detail="Sign in to save resumes.")
        name = PurePath(file.filename or "resume").name[:120]
        analysis["resume_id"] = _store_resume(
            conn, user["id"], "upload", PurePath(name).stem or "Resume", name, text, analysis, None
        )
    events.record(
        conn,
        "resume_analyzed",
        user_id=user["id"] if user else None,
        detail={"source": "upload", "strength": analysis["strength"]},
    )
    return analysis


@router.post(
    "/resume/to-document",
    response_model=ResumeDocument,
    summary="Read a resume file (PDF or Word) into a builder document",
)
async def file_to_document(
    request: Request, file: Annotated[UploadFile, File(description="PDF or Word (.docx), up to 5 MB")]
):
    limiter.check(f"analyze:{client_ip(request)}", 30, 3600)
    data = await file.read(MAX_BYTES + 1)
    try:
        text = extract_text(data, file.filename or "", file.content_type or "")
    except UnreadableResume as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return text_to_document(text)


@router.post("/resume/analyze-text", response_model=Analysis, summary="Analyze resume text")
def analyze_plain(body: TextIn, request: Request, user: OptionalUser, conn: Conn):
    limiter.check(f"analyze:{client_ip(request)}", 30, 3600)
    analysis = analyze_text(body.text)
    events.record(
        conn,
        "resume_analyzed",
        user_id=user["id"] if user else None,
        detail={"source": "text", "strength": analysis["strength"]},
    )
    return analysis


# ---------- matching ----------


@router.post("/resume/match", response_model=dict[int, MatchModel], summary="Score a resume against jobs")
def match(body: MatchIn, user: OptionalUser, conn: Conn):
    profile = _profile_for(conn, user, body.profile, body.resume_id)
    jobs = queries.jobs_by_ids(conn, body.job_ids)
    texts = cache.descriptions(conn, [job["id"] for job in jobs])
    return {
        job["id"]: score_job(profile, {**job, "description": texts.get(job["id"], "")}).to_dict()
        for job in jobs
    }


@router.post("/resume/tailor", response_model=TailorOut, summary="Score a resume draft against one job, live")
def tailor(body: TailorIn, request: Request, conn: Conn):
    """For the builder: rescored as the person types, so it has its own, larger allowance."""
    limiter.check(f"tailor:{client_ip(request)}", 400, 3600)
    jobs = queries.jobs_by_ids(conn, [body.job_id])
    if not jobs:
        raise HTTPException(status_code=404, detail="That job isn't in Ghostless anymore.")
    job = jobs[0]
    analysis = analyze_text(body.text)
    texts = cache.descriptions(conn, [job["id"]])
    match = score_job(analysis["profile"], {**job, "description": texts.get(job["id"], "")})
    return {"job": job, "match": match.to_dict(), "strength": analysis["strength"]}


@router.post(
    "/resume/recommendations", response_model=RecommendationPage, summary="Open tech jobs ranked by fit"
)
def recommendations(body: RecommendationsIn, request: Request, user: OptionalUser, conn: Conn):
    limiter.check(f"recommend:{client_ip(request)}", 60, 3600)
    profile = _profile_for(conn, user, body.profile, body.resume_id)
    pool = cache.job_pool(conn, body.location, body.include_high_risk)
    ranked = recommend(
        profile, pool, body.limit, body.offset, describe=lambda ids: cache.descriptions(conn, ids)
    )
    return {"total": len(pool), "items": [{"job": job, "match": m.to_dict()} for job, m in ranked]}


# ---------- stored resumes ----------


@router.get("/me/resumes", response_model=list[ResumeSummary], summary="Your resumes")
def my_resumes(user: CurrentUser, conn: Conn):
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            """SELECT id, kind, title, file_name, is_primary, created_at, updated_at, profile
               FROM resumes WHERE user_id = %s ORDER BY is_primary DESC, updated_at DESC""",
            (user["id"],),
        ).fetchall()
    return [_summary(r) for r in rows]


@router.get("/me/resumes/{resume_id}", response_model=StoredResume, summary="One of your resumes")
def my_resume(resume_id: int, user: CurrentUser, conn: Conn):
    row = _own_resume(conn, user["id"], resume_id)
    return {**_summary(row), "text": row["text"], "analysis": row["profile"], "document": row["document"]}


@router.get(
    "/me/resumes/{resume_id}/as-document",
    response_model=ResumeDocument,
    summary="One of your resumes as a builder document (uploads are read into one)",
)
def my_resume_as_document(resume_id: int, user: CurrentUser, conn: Conn):
    row = _own_resume(conn, user["id"], resume_id)
    if row["document"]:
        return row["document"]
    return text_to_document(row["text"] or "")


@router.post(
    "/me/resumes", response_model=StoredResume, status_code=201, summary="Save a resume made in the builder"
)
def create_built(body: BuiltIn, user: CurrentUser, conn: Conn):
    document = body.document.model_dump()
    text = document_to_text(body.document)
    analysis = analyze_text(text) if len(text) >= 50 else None
    resume_id = _store_resume(conn, user["id"], "built", body.title, None, text, analysis or {}, document)
    return my_resume(resume_id, user, conn)


@router.post(
    "/me/resumes/import",
    response_model=StoredResume,
    status_code=201,
    summary="Keep a resume checked before signing in (its analysis; the file was never stored)",
)
def import_checked(body: ImportIn, user: CurrentUser, conn: Conn):
    analysis = body.analysis.model_dump()
    analysis.pop("resume_id", None)
    resume_id = _store_resume(conn, user["id"], "upload", body.title, None, None, analysis, None)
    return my_resume(resume_id, user, conn)


@router.put("/me/resumes/{resume_id}", response_model=StoredResume, summary="Update a builder resume")
def update_built(resume_id: int, body: BuiltIn, user: CurrentUser, conn: Conn):
    row = _own_resume(conn, user["id"], resume_id)
    if row["kind"] != "built":
        raise HTTPException(
            status_code=400, detail="Uploaded resumes can't be edited; upload a new version instead."
        )
    text = document_to_text(body.document)
    analysis = analyze_text(text) if len(text) >= 50 else {}
    conn.execute(
        """UPDATE resumes SET title = %s, text = %s, profile = %s::jsonb, document = %s::jsonb, updated_at = now()
           WHERE id = %s""",
        (body.title, text, json.dumps(analysis), json.dumps(body.document.model_dump()), resume_id),
    )
    return my_resume(resume_id, user, conn)


@router.patch("/me/resumes/{resume_id}", response_model=StoredResume, summary="Rename a resume")
def rename(resume_id: int, body: RenameIn, user: CurrentUser, conn: Conn):
    _own_resume(conn, user["id"], resume_id)
    conn.execute("UPDATE resumes SET title = %s, updated_at = now() WHERE id = %s", (body.title, resume_id))
    return my_resume(resume_id, user, conn)


@router.post(
    "/me/resumes/{resume_id}/primary",
    response_model=list[ResumeSummary],
    summary="Use this resume for matching",
)
def make_primary(resume_id: int, user: CurrentUser, conn: Conn):
    _own_resume(conn, user["id"], resume_id)
    with conn.transaction():
        conn.execute("UPDATE resumes SET is_primary = (id = %s) WHERE user_id = %s", (resume_id, user["id"]))
    return my_resumes(user, conn)


@router.delete("/me/resumes/{resume_id}", response_model=list[ResumeSummary], summary="Delete a resume")
def delete_resume(resume_id: int, user: CurrentUser, conn: Conn):
    row = _own_resume(conn, user["id"], resume_id)
    with conn.transaction():
        conn.execute("DELETE FROM resumes WHERE id = %s", (resume_id,))
        if row["is_primary"]:  # the newest remaining one takes over
            conn.execute(
                """UPDATE resumes SET is_primary = true WHERE id = (
                       SELECT id FROM resumes WHERE user_id = %s ORDER BY updated_at DESC LIMIT 1)""",
                (user["id"],),
            )
    return my_resumes(user, conn)


# ---------- AI feedback ----------


def _ai_used_today(conn: psycopg.Connection, user_id: int | None) -> int:
    clause, params = ("AND user_id = %s", (user_id,)) if user_id is not None else ("", ())
    return conn.execute(
        f"SELECT count(*) FROM events WHERE kind = 'ai_feedback' AND created_at >= now() - interval '1 day' {clause}",
        params,
    ).fetchone()[0]


@router.get("/resume/ai-status", response_model=AIStatus, summary="Whether AI feedback is available")
def ai_status(user: OptionalUser, conn: Conn):
    if not ai.enabled():
        return {"enabled": False}
    remaining = max(0, ai.per_user_limit() - _ai_used_today(conn, user["id"])) if user else None
    return {"enabled": True, "remaining_today": remaining}


@router.post("/resume/ai-feedback", response_model=AIFeedbackOut, summary="Detailed AI feedback for one job")
def ai_feedback(body: AIIn, user: CurrentUser, conn: Conn):
    if not ai.enabled():
        raise HTTPException(status_code=503, detail="AI feedback isn't turned on for this site.")
    used = _ai_used_today(conn, user["id"])
    if used >= ai.per_user_limit():
        raise HTTPException(
            status_code=429, detail=f"You've used today's {ai.per_user_limit()} AI reviews. More tomorrow."
        )
    if _ai_used_today(conn, None) >= ai.total_limit():
        raise HTTPException(
            status_code=429, detail="AI reviews are at today's limit for the whole site. Try tomorrow."
        )
    if body.resume_id is not None:
        text = _own_resume(conn, user["id"], body.resume_id)["text"] or ""
    else:
        text = body.text or ""
    if len(text) < 200:
        raise HTTPException(status_code=422, detail="Upload or build a resume first.")
    job = queries.get_job(conn, body.job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if not job.get("description"):
        raise HTTPException(
            status_code=422, detail="This posting has no description yet, so there's nothing to compare."
        )
    try:
        result = ai.feedback(text, job["title"], job["company"], job["description"])
    except ai.AIUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    events.record(conn, "ai_feedback", user_id=user["id"], detail={"job_id": body.job_id})
    return {**result.model_dump(), "remaining_today": max(0, ai.per_user_limit() - used - 1)}
