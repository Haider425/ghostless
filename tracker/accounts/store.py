"""Database access for accounts. Every function takes an open connection."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg
from psycopg.rows import dict_row

from tracker.accounts.security import hash_password, needs_rehash, new_token, token_hash, verify_password

SESSION_DAYS = 30
VERIFY_HOURS = 48
RESET_HOURS = 1
TOUCH_EVERY = timedelta(minutes=10)  # how often a session's last-seen time is updated

USER_COLUMNS = "id, email, name, role, email_verified_at, settings, created_at, last_active_at"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _cursor(conn: psycopg.Connection):
    return conn.cursor(row_factory=dict_row)


# ---------- users ----------


def get_user(conn: psycopg.Connection, user_id: int) -> dict | None:
    with _cursor(conn) as cur:
        return cur.execute(f"SELECT {USER_COLUMNS} FROM users WHERE id = %s", (user_id,)).fetchone()


def find_user_by_email(conn: psycopg.Connection, email: str) -> dict | None:
    with _cursor(conn) as cur:
        return cur.execute(
            f"SELECT {USER_COLUMNS}, password_hash FROM users WHERE lower(email) = %s",
            (normalize_email(email),),
        ).fetchone()


class EmailTaken(Exception):
    pass


def create_user(conn: psycopg.Connection, email: str, password: str, name: str | None = None) -> dict:
    try:
        with _cursor(conn) as cur:
            return cur.execute(
                f"""INSERT INTO users (email, password_hash, name) VALUES (%s, %s, %s)
                    RETURNING {USER_COLUMNS}""",
                (normalize_email(email), hash_password(password), (name or "").strip() or None),
            ).fetchone()
    except psycopg.errors.UniqueViolation:
        raise EmailTaken(email) from None


def authenticate(conn: psycopg.Connection, email: str, password: str) -> dict | None:
    """The user if the email and password match, else None (in constant-ish time)."""
    user = find_user_by_email(conn, email)
    if not verify_password(user["password_hash"] if user else None, password):
        return None
    assert user is not None
    if needs_rehash(user["password_hash"]):
        set_password(conn, user["id"], password)
    return {k: v for k, v in user.items() if k != "password_hash"}


def check_password(conn: psycopg.Connection, user_id: int, password: str) -> bool:
    row = conn.execute("SELECT password_hash FROM users WHERE id = %s", (user_id,)).fetchone()
    return verify_password(row[0] if row else None, password)


def has_password(conn: psycopg.Connection, user_id: int) -> bool:
    row = conn.execute("SELECT password_hash IS NOT NULL FROM users WHERE id = %s", (user_id,)).fetchone()
    return bool(row and row[0])


# ---------- Google and GitHub sign-in ----------


def linked_providers(conn: psycopg.Connection, user_id: int) -> list[str]:
    rows = conn.execute(
        "SELECT provider FROM oauth_accounts WHERE user_id = %s ORDER BY provider", (user_id,)
    ).fetchall()
    return [r[0] for r in rows]


class IdentityInUse(Exception):
    """The Google or GitHub account is already linked to a different Ghostless account."""


def user_for_identity(
    conn: psycopg.Connection, provider: str, subject: str, email: str, name: str | None
) -> tuple[dict, bool]:
    """The account for a verified Google or GitHub identity: (user, created).

    1. Already linked: that account.
    2. An account with the same email: link to it (the provider has verified
       the person owns that address) and mark the email confirmed.
    3. Otherwise a new account with no password.
    """
    row = conn.execute(
        "SELECT user_id FROM oauth_accounts WHERE provider = %s AND subject = %s", (provider, subject)
    ).fetchone()
    if row:
        return get_user(conn, row[0]), False  # type: ignore[return-value]
    existing = find_user_by_email(conn, email)
    if existing:
        link_identity(conn, existing["id"], provider, subject, email)
        mark_verified(conn, existing["id"])
        return get_user(conn, existing["id"]), False  # type: ignore[return-value]
    with _cursor(conn) as cur:
        user = cur.execute(
            f"""INSERT INTO users (email, password_hash, name, email_verified_at) VALUES (%s, NULL, %s, now())
                RETURNING {USER_COLUMNS}""",
            (normalize_email(email), (name or "").strip()[:80] or None),
        ).fetchone()
    link_identity(conn, user["id"], provider, subject, email)
    return user, True


def link_identity(conn: psycopg.Connection, user_id: int, provider: str, subject: str, email: str) -> None:
    """Attach a Google or GitHub identity to an account (replacing an older one from the same provider)."""
    row = conn.execute(
        "SELECT user_id FROM oauth_accounts WHERE provider = %s AND subject = %s", (provider, subject)
    ).fetchone()
    if row and row[0] != user_id:
        raise IdentityInUse(provider)
    conn.execute("DELETE FROM oauth_accounts WHERE user_id = %s AND provider = %s", (user_id, provider))
    conn.execute(
        "INSERT INTO oauth_accounts (provider, subject, user_id, email) VALUES (%s, %s, %s, %s)",
        (provider, subject, user_id, normalize_email(email)),
    )


def unlink_identity(conn: psycopg.Connection, user_id: int, provider: str) -> None:
    conn.execute("DELETE FROM oauth_accounts WHERE user_id = %s AND provider = %s", (user_id, provider))


def set_password(conn: psycopg.Connection, user_id: int, password: str) -> None:
    conn.execute("UPDATE users SET password_hash = %s WHERE id = %s", (hash_password(password), user_id))


def update_profile(conn: psycopg.Connection, user_id: int, name: str | None) -> dict | None:
    conn.execute("UPDATE users SET name = %s WHERE id = %s", ((name or "").strip() or None, user_id))
    return get_user(conn, user_id)


def update_settings(conn: psycopg.Connection, user_id: int, settings: dict[str, Any]) -> dict | None:
    conn.execute("UPDATE users SET settings = %s::jsonb WHERE id = %s", (json.dumps(settings), user_id))
    return get_user(conn, user_id)


def set_role(conn: psycopg.Connection, email: str, role: str) -> bool:
    return (
        conn.execute(
            "UPDATE users SET role = %s WHERE lower(email) = %s", (role, normalize_email(email))
        ).rowcount
        == 1
    )


def delete_user(conn: psycopg.Connection, user_id: int) -> None:
    # reports outlive the account (they're about the site), but not the person's email
    conn.execute("UPDATE reports SET email = NULL WHERE user_id = %s", (user_id,))
    conn.execute("DELETE FROM users WHERE id = %s", (user_id,))


# ---------- sessions ----------


def create_session(conn: psycopg.Connection, user_id: int, user_agent: str | None = None) -> str:
    token = new_token()
    conn.execute(
        "INSERT INTO sessions (token_hash, user_id, expires_at, user_agent) VALUES (%s, %s, %s, %s)",
        (token_hash(token), user_id, _now() + timedelta(days=SESSION_DAYS), (user_agent or "")[:300] or None),
    )
    conn.execute("UPDATE users SET last_active_at = now() WHERE id = %s", (user_id,))
    return token


def user_for_session(conn: psycopg.Connection, token: str) -> dict | None:
    """The signed-in user for a session token. Extends active sessions."""
    with _cursor(conn) as cur:
        row = cur.execute(
            f"""SELECT s.last_seen_at, {", ".join(f"u.{c.strip()}" for c in USER_COLUMNS.split(","))}
                FROM sessions s JOIN users u ON u.id = s.user_id
                WHERE s.token_hash = %s AND s.expires_at > now()""",
            (token_hash(token),),
        ).fetchone()
    if row is None:
        return None
    if _now() - row["last_seen_at"] > TOUCH_EVERY:
        conn.execute(
            "UPDATE sessions SET last_seen_at = now(), expires_at = %s WHERE token_hash = %s",
            (_now() + timedelta(days=SESSION_DAYS), token_hash(token)),
        )
        conn.execute("UPDATE users SET last_active_at = now() WHERE id = %s", (row["id"],))
    row.pop("last_seen_at")
    return row


def end_session(conn: psycopg.Connection, token: str) -> None:
    conn.execute("DELETE FROM sessions WHERE token_hash = %s", (token_hash(token),))


def end_all_sessions(conn: psycopg.Connection, user_id: int, keep_token: str | None = None) -> int:
    keep = token_hash(keep_token) if keep_token else ""
    return conn.execute(
        "DELETE FROM sessions WHERE user_id = %s AND token_hash <> %s", (user_id, keep)
    ).rowcount


# ---------- email links ----------


def create_email_token(conn: psycopg.Connection, user_id: int, purpose: str) -> str:
    hours = VERIFY_HOURS if purpose == "verify" else RESET_HOURS
    # one live link per purpose: a new one replaces older ones
    conn.execute("DELETE FROM email_tokens WHERE user_id = %s AND purpose = %s", (user_id, purpose))
    token = new_token()
    conn.execute(
        "INSERT INTO email_tokens (token_hash, user_id, purpose, expires_at) VALUES (%s, %s, %s, %s)",
        (token_hash(token), user_id, purpose, _now() + timedelta(hours=hours)),
    )
    return token


def use_email_token(conn: psycopg.Connection, token: str, purpose: str) -> int | None:
    """The user id for an unused, unexpired link, marking it used. None otherwise."""
    row = conn.execute(
        """UPDATE email_tokens SET used_at = now()
           WHERE token_hash = %s AND purpose = %s AND used_at IS NULL AND expires_at > now()
           RETURNING user_id""",
        (token_hash(token), purpose),
    ).fetchone()
    return row[0] if row else None


def mark_verified(conn: psycopg.Connection, user_id: int) -> None:
    conn.execute(
        "UPDATE users SET email_verified_at = coalesce(email_verified_at, now()) WHERE id = %s", (user_id,)
    )


# ---------- saved jobs ----------


def saved_job_ids(conn: psycopg.Connection, user_id: int) -> list[int]:
    rows = conn.execute(
        "SELECT job_id FROM saved_jobs WHERE user_id = %s ORDER BY saved_at DESC", (user_id,)
    ).fetchall()
    return [r[0] for r in rows]


def save_jobs(conn: psycopg.Connection, user_id: int, job_ids: list[int]) -> int:
    """Save jobs that exist; returns how many were newly saved."""
    if not job_ids:
        return 0
    return conn.execute(
        """INSERT INTO saved_jobs (user_id, job_id)
           SELECT %s, id FROM jobs WHERE id = ANY(%s)
           ON CONFLICT DO NOTHING""",
        (user_id, job_ids),
    ).rowcount


APPLICATION_STATUSES = ("saved", "applied", "interviewing", "offer", "rejected")


def saved_entries(conn: psycopg.Connection, user_id: int) -> list[dict]:
    """Each saved job's tracking state, newest first."""
    rows = conn.execute(
        """SELECT job_id, status, notes, saved_at, updated_at FROM saved_jobs
           WHERE user_id = %s ORDER BY saved_at DESC""",
        (user_id,),
    ).fetchall()
    return [
        {"job_id": r[0], "status": r[1], "notes": r[2], "saved_at": r[3], "updated_at": r[4]} for r in rows
    ]


def update_saved(
    conn: psycopg.Connection, user_id: int, job_id: int, status: str | None, notes: str | None
) -> bool:
    """Change a saved job's status and/or notes; False if it isn't saved."""
    return bool(
        conn.execute(
            """UPDATE saved_jobs SET status = coalesce(%s, status),
                      notes = CASE WHEN %s THEN %s ELSE notes END, updated_at = now()
               WHERE user_id = %s AND job_id = %s""",
            (status, notes is not None, (notes or "").strip() or None, user_id, job_id),
        ).rowcount
    )


def unsave_job(conn: psycopg.Connection, user_id: int, job_id: int) -> None:
    conn.execute("DELETE FROM saved_jobs WHERE user_id = %s AND job_id = %s", (user_id, job_id))


# ---------- export ----------


def export_user(conn: psycopg.Connection, user_id: int) -> dict:
    """Everything stored about a user, for the 'download my data' button."""
    with _cursor(conn) as cur:
        user = cur.execute(f"SELECT {USER_COLUMNS} FROM users WHERE id = %s", (user_id,)).fetchone()
        saved = cur.execute(
            """SELECT j.id, j.title, c.name AS company, j.url, s.saved_at
               FROM saved_jobs s JOIN jobs j ON j.id = s.job_id JOIN companies c ON c.id = j.company_id
               WHERE s.user_id = %s ORDER BY s.saved_at DESC""",
            (user_id,),
        ).fetchall()
        resumes = cur.execute(
            """SELECT id, kind, title, file_name, text, profile, document, is_primary, created_at, updated_at
               FROM resumes WHERE user_id = %s ORDER BY created_at""",
            (user_id,),
        ).fetchall()
        reports = cur.execute(
            "SELECT id, category, message, page, status, created_at FROM reports WHERE user_id = %s",
            (user_id,),
        ).fetchall()
        sessions = cur.execute(
            "SELECT created_at, last_seen_at, expires_at, user_agent FROM sessions WHERE user_id = %s",
            (user_id,),
        ).fetchall()
        activity = cur.execute(
            "SELECT kind, path, created_at FROM events WHERE user_id = %s ORDER BY created_at DESC LIMIT 1000",
            (user_id,),
        ).fetchall()
        sign_ins = cur.execute(
            "SELECT provider, email, created_at FROM oauth_accounts WHERE user_id = %s", (user_id,)
        ).fetchall()
    return {
        "exported_at": _now(),
        "account": user,
        "saved_jobs": saved,
        "resumes": resumes,
        "reports": reports,
        "sessions": sessions,
        "linked_sign_ins": sign_ins,
        "recent_activity": activity,
    }


def purge_expired(conn: psycopg.Connection, event_days: int = 400) -> None:
    """Housekeeping, run after each ingest: expired sessions and links, and
    analytics older than about 13 months."""
    conn.execute("DELETE FROM sessions WHERE expires_at < now()")
    conn.execute("DELETE FROM email_tokens WHERE expires_at < now() - interval '7 days'")
    conn.execute("DELETE FROM events WHERE created_at < now() - make_interval(days => %s)", (event_days,))
