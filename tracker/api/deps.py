"""Shared request dependencies: database connections, the signed-in user,
the caller's IP address and rate limits."""

from __future__ import annotations

import os
import secrets
import threading
import time
from collections import defaultdict, deque
from collections.abc import Iterator
from typing import Annotated

import psycopg
from fastapi import Depends, HTTPException, Request

from tracker.accounts import store


def get_conn(request: Request) -> Iterator[psycopg.Connection]:
    with request.app.state.pool.connection() as conn:
        yield conn


Conn = Annotated[psycopg.Connection, Depends(get_conn)]


def client_ip(request: Request) -> str:
    """The visitor's IP. The website's server calls the API on visitors'
    behalf and passes their IP in X-Client-IP, which is trusted only when
    the request also carries the shared GHOSTLESS_INTERNAL_KEY."""
    key = os.environ.get("GHOSTLESS_INTERNAL_KEY")
    sent = request.headers.get("x-internal-key") or ""
    # constant-time comparison, so the key can't be guessed from response timing
    if key and secrets.compare_digest(sent.encode(), key.encode()) and request.headers.get("x-client-ip"):
        return request.headers["x-client-ip"].split(",")[0].strip()[:64]
    return request.client.host if request.client else "unknown"


def bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


def optional_user(request: Request, conn: Conn) -> dict | None:
    token = bearer_token(request)
    return store.user_for_session(conn, token) if token else None


def current_user(user: Annotated[dict | None, Depends(optional_user)]) -> dict:
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in to do that.")
    return user


def admin_user(user: Annotated[dict, Depends(current_user)]) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admins only.")
    return user


OptionalUser = Annotated[dict | None, Depends(optional_user)]
CurrentUser = Annotated[dict, Depends(current_user)]
AdminUser = Annotated[dict, Depends(admin_user)]


class RateLimiter:
    """Sliding-window limits kept in memory. Enough for one API instance;
    with several, put a shared store (Redis) behind the same interface."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window_seconds: float) -> None:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= now - window_seconds:
                hits.popleft()
            if len(hits) >= limit:
                retry = int(hits[0] + window_seconds - now) + 1
                raise HTTPException(
                    status_code=429,
                    detail="Too many attempts. Wait a little and try again.",
                    headers={"Retry-After": str(retry)},
                )
            hits.append(now)
            if len(self._hits) > 50_000:  # keep memory bounded
                for stale in [k for k, v in self._hits.items() if not v][:10_000]:
                    del self._hits[stale]

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()
