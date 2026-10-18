"""Turn an uploaded resume file into plain text. The file itself is never stored."""

from __future__ import annotations

import io
import re
import zipfile

MAX_BYTES = 5 * 1024 * 1024
MAX_PAGES = 10


class UnreadableResume(ValueError):
    """The file isn't a resume we can read; the message is safe to show."""


def _clean(text: str) -> str:
    text = text.replace(" ", " ").replace("", "•").replace("•", "•").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _pdf(data: bytes) -> str:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise UnreadableResume(
                "This PDF is password protected. Save a copy without a password and try again."
            )
        pages = reader.pages[:MAX_PAGES]
        return "\n\n".join(page.extract_text() or "" for page in pages)
    except PdfReadError as exc:
        raise UnreadableResume(
            "This PDF couldn't be read. Try exporting it again, or upload a Word file."
        ) from exc


def _docx(data: bytes) -> str:
    import docx

    try:
        document = docx.Document(io.BytesIO(data))
    except (zipfile.BadZipFile, KeyError, ValueError) as exc:
        raise UnreadableResume("This Word file couldn't be read. Save it again as .docx and retry.") from exc
    lines = []
    for paragraph in document.paragraphs:
        style = (paragraph.style.name or "").lower() if paragraph.style is not None else ""
        prefix = "• " if "list" in style else ""
        lines.append(prefix + paragraph.text)
    for table in document.tables:  # some templates lay resumes out in tables
        for row in table.rows:
            lines.append(" | ".join(cell.text for cell in row.cells))
    return "\n".join(lines)


def extract_text(data: bytes, filename: str = "", content_type: str = "") -> str:
    if not data:
        raise UnreadableResume("The file is empty.")
    if len(data) > MAX_BYTES:
        raise UnreadableResume("Resumes can be up to 5 MB.")
    name = filename.lower()
    if data[:4] == b"%PDF" or name.endswith(".pdf"):
        text = _pdf(data)
    elif data[:2] == b"PK" or name.endswith(".docx"):
        text = _docx(data)
    elif name.endswith((".txt", ".md")) or content_type.startswith("text/"):
        text = data.decode("utf-8", errors="replace")
    elif name.endswith(".doc"):
        raise UnreadableResume("Old .doc files aren't supported. Save it as .docx or PDF and try again.")
    else:
        raise UnreadableResume("Upload a PDF or Word (.docx) file.")
    text = _clean(text)
    if len(text) < 200:
        raise UnreadableResume(
            "Almost no text came out of this file. If it's a scanned image, export a text PDF from your editor instead."
        )
    return text[:60_000]
