"""First-party, cookie-free analytics and error capture.

Page views are counted per visitor per day without cookies or stored IP
addresses: the visitor id is a hash of the IP address, the browser's user
agent and a salt that changes every day (the approach Plausible uses). It
can count unique visitors for a day, but can't follow anyone across days or
be turned back into an IP address.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
from datetime import date
from typing import Any, Literal
from urllib.parse import urlparse

import psycopg
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field

from tracker.api.deps import Conn, OptionalUser, client_ip, limiter

log = logging.getLogger(__name__)
router = APIRouter(tags=["analytics"])

_SECRET = os.environ.get("GHOSTLESS_ANALYTICS_SALT") or secrets.token_hex(16)


def visitor_id(ip: str, user_agent: str, day: date | None = None) -> str:
    day = day or date.today()
    raw = f"{_SECRET}:{day.isoformat()}:{ip}:{user_agent}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def record(
    conn: psycopg.Connection,
    kind: str,
    *,
    path: str | None = None,
    referrer: str | None = None,
    visitor: str | None = None,
    user_id: int | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    """Store an event. Analytics must never break a request, so errors are logged and swallowed."""
    try:
        conn.execute(
            """INSERT INTO events (kind, path, referrer, visitor, user_id, detail)
               VALUES (%s, %s, %s, %s, %s, %s::jsonb)""",
            (kind, path, referrer, visitor, user_id, json.dumps(detail, default=str) if detail else None),
        )
    except psycopg.Error as exc:
        log.warning("could not record %s event: %s", kind, exc)


def _clean_path(value: str | None) -> str | None:
    if not value:
        return None
    path = urlparse(value).path or "/"
    # job and company ids are kept; anything after them (tokens in links) isn't
    return path[:200]


def _referrer_host(value: str | None) -> str | None:
    if not value:
        return None
    host = urlparse(value).hostname
    return host[:100] if host else None


class EventIn(BaseModel):
    kind: Literal["pageview", "error"]
    path: str | None = Field(None, max_length=500)
    referrer: str | None = Field(None, max_length=500)
    message: str | None = Field(None, max_length=1000, description="errors only")
    digest: str | None = Field(None, max_length=100, description="errors only: the server error id")


@router.post("/events", status_code=204, summary="Record a page view or a client error")
def post_event(body: EventIn, request: Request, user: OptionalUser, conn: Conn):
    ip = client_ip(request)
    limiter.check(f"events:{ip}", 240, 60)
    ua = request.headers.get("x-client-user-agent") or request.headers.get("user-agent") or ""
    if body.kind == "pageview" and _looks_like_bot(ua):
        return Response(status_code=204)
    detail = {"message": body.message, "digest": body.digest} if body.kind == "error" else None
    record(
        conn,
        body.kind,
        path=_clean_path(body.path),
        referrer=_referrer_host(body.referrer),
        visitor=visitor_id(ip, ua),
        user_id=user["id"] if user else None,
        detail=detail,
    )
    return Response(status_code=204)


_BOT = ("bot", "crawler", "spider", "slurp", "headless", "lighthouse", "preview")


def _looks_like_bot(user_agent: str) -> bool:
    ua = user_agent.lower()
    return not ua or any(word in ua for word in _BOT)
