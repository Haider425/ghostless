"""Transactional email (verification and password reset).

Sends through Resend (https://resend.com, free tier: 3,000 emails a month)
when RESEND_API_KEY and GHOSTLESS_EMAIL_FROM are set. Without them, emails
are logged instead, which is what you want in development: the link shows
up in the API's output.
"""

from __future__ import annotations

import html
import logging
import os
from dataclasses import dataclass

import requests

log = logging.getLogger(__name__)

# Every message "sent" in this process, newest last. Tests read it.
outbox: list[Message] = []


@dataclass(frozen=True)
class Message:
    to: str
    subject: str
    text: str
    link: str | None = None


def site_url() -> str:
    return os.environ.get("GHOSTLESS_SITE_URL", "http://localhost:3000").rstrip("/")


def configured() -> bool:
    return bool(os.environ.get("RESEND_API_KEY") and os.environ.get("GHOSTLESS_EMAIL_FROM"))


def _html(text: str, link: str | None, button: str | None) -> str:
    paragraphs = "".join(f"<p>{html.escape(p)}</p>" for p in text.split("\n\n") if p.strip())
    action = (
        f'<p><a href="{html.escape(link)}" style="display:inline-block;padding:10px 18px;'
        f'background:#2451c7;color:#ffffff;border-radius:8px;text-decoration:none">{html.escape(button)}</a></p>'
        if link and button
        else ""
    )
    return (
        '<div style="font-family:system-ui,sans-serif;font-size:15px;line-height:1.5;color:#16181d;max-width:520px">'
        f'<p style="font-weight:600;font-size:17px">Ghostless</p>{paragraphs}{action}</div>'
    )


def send(to: str, subject: str, text: str, link: str | None = None, button: str | None = None) -> bool:
    """Send an email. Returns False if it couldn't be sent (never raises)."""
    message = Message(to, subject, text, link)
    outbox.append(message)
    del outbox[:-50]
    if not configured():
        log.warning("email not configured; would send %r to %s: %s", subject, to, link or "")
        return False
    body = text + (f"\n\n{link}" if link else "")
    try:
        response = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {os.environ['RESEND_API_KEY']}"},
            json={
                "from": os.environ["GHOSTLESS_EMAIL_FROM"],
                "to": [to],
                "subject": subject,
                "text": body,
                "html": _html(text, link, button),
            },
            timeout=10,
        )
        if response.status_code >= 300:
            log.error("email to %s failed: %s %s", to, response.status_code, response.text[:200])
            return False
        return True
    except requests.RequestException as exc:
        log.error("email to %s failed: %s", to, exc)
        return False


def send_verification(to: str, token: str) -> bool:
    link = f"{site_url()}/verify-email?token={token}"
    return send(
        to,
        "Confirm your email for Ghostless",
        "Welcome to Ghostless. Confirm your email address so you can reset your password if you ever forget it."
        "\n\nThis link works for 48 hours. If you didn't sign up, you can ignore this email.",
        link,
        "Confirm my email",
    )


def send_password_reset(to: str, token: str) -> bool:
    link = f"{site_url()}/reset-password?token={token}"
    return send(
        to,
        "Reset your Ghostless password",
        "Someone asked to reset the password for this Ghostless account. Choose a new password with the link "
        "below.\n\nThe link works for one hour and only once. If it wasn't you, ignore this email and your "
        "password stays the same.",
        link,
        "Choose a new password",
    )
