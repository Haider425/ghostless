"""Eightfold career sites (Microsoft and other large employers).

Config slug: `<careers host>/<company domain>?<search filters>`, e.g.
  apply.careers.microsoft.com/microsoft.com?location=Canada

The search endpoint returns 10 positions per page without descriptions;
descriptions come from one detail request per relevant role.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from urllib.parse import quote

from tracker.models import Company, Job
from tracker.sources import http
from tracker.sources.common import wants_detail
from tracker.sources.http import FetchError
from tracker.text import html_to_text

log = logging.getLogger(__name__)

MAX_POSITIONS = 5_000  # safety stop


def parse_eightfold_slug(slug: str) -> tuple[str, str, str]:
    """Return (host, domain, extra query string)."""
    path, _, query = slug.strip().partition("?")
    host, _, domain = path.strip("/").partition("/")
    if not host or not domain:
        raise FetchError(f"bad eightfold slug {slug!r}; expected host/domain?filters")
    return host, domain, query


def parse_eightfold_position(position: dict, detail: dict | None, host: str) -> Job:
    info = detail or {}
    locations = position.get("standardizedLocations") or position.get("locations") or []
    posted = position.get("postedTs")
    return Job(
        external_id=str(position["id"]),
        title=(position.get("name") or "").strip(),
        url=info.get("publicUrl") or f"https://{host}{position.get('positionUrl') or ''}",
        location=" | ".join(locations),
        department=position.get("department"),
        description=html_to_text(info.get("jobDescription")),
        posted_at=datetime.fromtimestamp(posted, tz=timezone.utc) if posted else None,
        source_remote=(position.get("workLocationOption") or "").lower() == "remote",
    )


def fetch_eightfold(company: Company, details: bool = True) -> list[Job]:
    host, domain, query = parse_eightfold_slug(company.board_slug)
    base = f"https://{host}/api/pcsx"
    extra = f"&{query}" if query else ""

    positions: list[dict] = []
    start = 0
    while start < MAX_POSITIONS:
        data = (http.get_json(f"{base}/search?domain={quote(domain)}&start={start}{extra}") or {}).get(
            "data"
        ) or {}
        page = data.get("positions") or []
        positions.extend(page)
        start += len(page)
        if not page or start >= int(data.get("count") or 0):
            break

    jobs, seen = [], set()
    for position in positions:
        if position.get("id") is None or position["id"] in seen:
            continue
        seen.add(position["id"])
        detail = None
        location = " ".join(position.get("standardizedLocations") or [])
        if details and wants_detail(position.get("name", ""), location):
            try:
                detail = (
                    http.get_json(
                        f"{base}/position_details?position_id={position['id']}&domain={quote(domain)}"
                    )
                    or {}
                ).get("data")
            except FetchError as exc:
                log.warning("%s: detail fetch failed for %s: %s", company.name, position["id"], exc)
        jobs.append(parse_eightfold_position(position, detail, host))
    return jobs
