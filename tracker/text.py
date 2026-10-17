import html
import re

_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")


def html_to_text(raw: str | None) -> str:
    """Convert (possibly HTML-escaped) HTML into plain, single-spaced text."""
    if not raw:
        return ""
    text = html.unescape(raw)  # Greenhouse double-escapes content
    text = _TAG.sub(" ", text)
    text = html.unescape(text)
    return _SPACE.sub(" ", text).strip()
