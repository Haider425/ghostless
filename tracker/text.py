import html
import re

_BLOCK_END = re.compile(r"</(?:p|div|h[1-6]|ul|ol|li|tr|table|section|blockquote)\s*>", re.I)
_BREAK = re.compile(r"<br\s*/?>", re.I)
_LIST_ITEM = re.compile(r"<li\b[^>]*>", re.I)
_TAG = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"[ \t\r\f\v\u00a0]+")
_BLANK_LINES = re.compile(r"\s*\n\s*\n\s*")
_LINE_SPACE = re.compile(r" *\n *")

BULLET = "• "


def html_to_text(raw: str | None) -> str:
    """Convert (possibly HTML-escaped) HTML into plain text that keeps its
    structure: paragraphs separated by a blank line, list items on their own
    line starting with a bullet."""
    if not raw:
        return ""
    text = html.unescape(raw)  # Greenhouse double-escapes content
    text = text.replace("\n", " ")  # source newlines are formatting, tags carry the structure
    text = _LIST_ITEM.sub("\n" + BULLET, text)
    text = _BLOCK_END.sub("\n\n", text)
    text = _BREAK.sub("\n", text)
    text = _TAG.sub(" ", text)
    text = html.unescape(text)
    text = _SPACES.sub(" ", text)
    text = _LINE_SPACE.sub("\n", text)
    text = _BLANK_LINES.sub("\n\n", text)
    # a bullet directly after a paragraph break stays in the list
    text = re.sub(r"\n\n(?=" + re.escape(BULLET) + ")", "\n", text)
    return text.strip()
