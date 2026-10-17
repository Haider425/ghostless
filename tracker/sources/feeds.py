"""Feed-based sources: XML sitemaps (Shopify) and RSS job feeds (SAP
SuccessFactors sites such as Scotiabank).

Both list every open posting, so closure tracking works normally.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from urllib.parse import unquote, urlsplit

from tracker.models import Company, Job
from tracker.sources import http
from tracker.sources.common import parse_iso, slug_to_title
from tracker.sources.http import FetchError
from tracker.text import html_to_text

G_NS = "{http://base.google.com/ns/1.0}"

# Last URL segment like "senior-data-engineer_<uuid>" or "...-<numeric id>"
_JOB_SEGMENT = re.compile(
    r"^(?P<slug>.+?)[_-](?P<id>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|\d{5,})$",
    re.I,
)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse_xml(text: str) -> ET.Element:
    try:
        return ET.fromstring(text.encode("utf-8"))
    except ET.ParseError as exc:
        raise FetchError(f"invalid XML: {exc}") from exc


# ---------- Sitemap ----------


def parse_sitemap(xml_text: str) -> list[Job]:
    jobs: dict[str, Job] = {}
    for url_el in _parse_xml(xml_text).iter():
        if _local(url_el.tag) != "url":
            continue
        loc = lastmod = None
        for child in url_el:
            if _local(child.tag) == "loc":
                loc = (child.text or "").strip()
            elif _local(child.tag) == "lastmod":
                lastmod = (child.text or "").strip()
        if not loc:
            continue
        segment = unquote(urlsplit(loc).path.rstrip("/").rsplit("/", 1)[-1])
        match = _JOB_SEGMENT.match(segment)
        if not match:
            continue  # not a job page
        jobs.setdefault(
            match["id"],
            Job(
                external_id=match["id"],
                title=slug_to_title(match["slug"]),
                url=loc,
                posted_at=parse_iso(lastmod),
            ),
        )
    return list(jobs.values())


def fetch_sitemap(company: Company, details: bool = True) -> list[Job]:
    return parse_sitemap(http.get_text(company.board_slug))


# ---------- RSS job feed ----------


def _child_text(item: ET.Element, name: str) -> str:
    """Text of the first direct child with this (namespace-free) tag name."""
    for child in item:
        if _local(child.tag) == name:
            return (child.text or "").strip()
    return ""


def parse_rss(xml_text: str) -> list[Job]:
    jobs: dict[str, Job] = {}
    for item in _parse_xml(xml_text).iter("item"):
        job_id = (
            item.findtext(f"{G_NS}id") or _child_text(item, "guid") or _child_text(item, "link")
        ).strip()
        if not job_id or job_id in jobs:
            continue
        jobs[job_id] = Job(
            external_id=job_id,
            title=_child_text(item, "title"),
            url=_child_text(item, "link"),
            location=item.findtext(f"{G_NS}location") or "",
            department=item.findtext(f"{G_NS}job_function"),
            description=html_to_text(_child_text(item, "description")),
        )
    return list(jobs.values())


def fetch_rss(company: Company, details: bool = True) -> list[Job]:
    return parse_rss(http.get_text(company.board_slug))
