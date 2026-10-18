"""Turn an uploaded resume's text into a builder document.

Resumes have no fixed format, so this reads them the way a person would:
sections by their headings, entries as a few header lines (title, company,
dates, place) followed by bullet points, skills as "Label: a, b, c" lines.
What can't be placed confidently goes into the closest field so nothing is
lost; the person reviews it in the builder.
"""

from __future__ import annotations

import re

from tracker.resume.document import (
    Certification,
    Contact,
    Education,
    Experience,
    Link,
    Project,
    ResumeDocument,
    SkillGroup,
)
from tracker.resume.profile import _BULLET, _RANGE, _STRONG_VERBS, split_sections
from tracker.skills import extract_skills

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}")
_URL = re.compile(r"(?:https?://)?(?:www\.)?[\w-]+(?:\.[\w-]+)+(?:/[\w./%#?=&-]*)?", re.I)
_PROVINCES = r"(?:ON|QC|BC|AB|MB|SK|NS|NB|NL|PE|YT|NT|NU|Ontario|Quebec|British Columbia|Alberta|Manitoba|Saskatchewan|Nova Scotia|New Brunswick|[A-Z]{2})"
_PLACE = re.compile(
    rf"^(?:[A-Z][\w.'-]+(?: [A-Z][\w.'-]+){{0,3}}, {_PROVINCES}(?:, [A-Z][\w ]+)?|Remote|Hybrid)$"
)
_SINGLE_DATE = re.compile(
    r"(?:(?:expected|anticipated|graduating|grad\.?)\s+)?(?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?,?\s+|(?:spring|summer|fall|winter)\s+)?(?:19|20)\d{2}",
    re.I,
)
_SCHOOL = re.compile(
    r"universit|college|institute|polytechni|school|academy|cégep|cegep|\bUBC\b|\bUofT\b|\bMIT\b", re.I
)
_DEGREE = re.compile(
    r"bachelor|master|ph\.?d|doctor|diploma|certificate|b\.?\s?sc|m\.?\s?sc|b\.?eng|m\.?eng|b\.?a\.?\b|b\.?comm?|mba|"
    r"honours|honors|major|minor|degree|associate",
    re.I,
)
_SPLIT = re.compile(r"\s*(?:\||•|·|\t|\s{3,}|\s[–—-]\s)\s*")


_PROVINCE_ONLY = re.compile(rf"^{_PROVINCES}$")


def _parts(line: str) -> list[str]:
    parts = [p.strip(" ,;") for p in _SPLIT.split(line.strip()) if p.strip(" ,;")]
    if len(parts) == 1 and ", " in parts[0] and "(" not in parts[0]:
        # "Developer Co-op, Maple Bank, Toronto, ON": split on commas, keeping "Toronto, ON" together
        pieces: list[str] = []
        for piece in (x.strip() for x in parts[0].split(",")):
            if pieces and _PROVINCE_ONLY.match(piece):
                pieces[-1] += f", {piece}"
            elif piece:
                pieces.append(piece)
        if len(pieces) > 1 and all(len(x.split()) <= 8 for x in pieces):
            return pieces
    return parts


def _take_dates(line: str) -> tuple[str, str, str]:
    """(line without its dates, start, end)."""
    m = _RANGE.search(line)
    if m:
        rest = (line[: m.start()] + " " + line[m.end() :]).strip()
        return (
            rest,
            m["start"].strip(),
            m["end"].strip().capitalize() if m["end"].islower() else m["end"].strip(),
        )
    m = _SINGLE_DATE.search(line)
    if m and (m.end() == len(line.rstrip()) or len(_parts(line)) > 1):
        rest = (line[: m.start()] + " " + line[m.end() :]).strip()
        return rest, "", m.group(0).strip()
    return line, "", ""


def _is_bullet_text(line: str) -> bool:
    """A bullet whose glyph was lost (common in PDFs): a long line starting with a verb."""
    words = line.split()
    return (
        len(line) > 35
        and len(words) >= 5
        and bool(words)
        and words[0].lower().rstrip(",")
        in _STRONG_VERBS
        | {
            "responsible",
            "helped",
            "assisted",
            "worked",
        }
    )


def _blocks(text: str) -> list[tuple[list[str], list[str]]]:
    """[(header lines, bullets)] for a section of entries."""
    blocks: list[tuple[list[str], list[str]]] = []
    head: list[str] = []
    points: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if _BULLET.match(raw) or (_is_bullet_text(line) and head):
            text_ = _BULLET.sub("", raw).strip()
            if points and text_[:1].islower():
                points[-1] += " " + text_  # a bullet wrapped onto a second line
            else:
                points.append(text_)
            continue
        if points:  # a header line after bullets starts the next entry
            blocks.append((head, points))
            head, points = [], []
        elif head and len(head) >= 3 and not _RANGE.search(line):
            # a long line with no bullet after a full header: the wrapped end of a bullet
            if len(line) > 60:
                points.append(line)
                continue
        head.append(line)
    if head or points:
        blocks.append((head, points))
    return blocks


def _clip(value: str, n: int = 120) -> str:
    return value.strip()[:n]


def _experience(head: list[str], points: list[str]) -> Experience:
    start = end = ""
    pieces: list[str] = []
    for line in head:
        rest, s, e = _take_dates(line)
        if e and not end:
            start, end = s, e
        pieces += _parts(rest)
    location = next((p for p in pieces if _PLACE.match(p)), "")
    pieces = [p for p in pieces if p != location]
    title = company = ""
    if pieces and " at " in pieces[0]:
        title, company = (x.strip() for x in pieces[0].split(" at ", 1))
        pieces = pieces[1:]
    else:
        title = pieces.pop(0) if pieces else ""
        company = pieces.pop(0) if pieces else ""
    extra = [p for p in pieces if p]
    if extra and not location:
        location = extra.pop(0)
    return Experience(
        title=_clip(title),
        company=_clip(company),
        location=_clip(location),
        start=start[:30],
        end=end[:30],
        bullets=[_clip(b, 400) for b in (points + extra)][:10] or [""],
    )


def _education(head: list[str], points: list[str]) -> Education:
    start = end = ""
    pieces: list[str] = []
    for line in head:
        rest, s, e = _take_dates(line)
        if e and not end:
            start, end = s, e
        pieces += _parts(rest)
    school = next((p for p in pieces if _SCHOOL.search(p)), "")
    degree = next((p for p in pieces if p != school and _DEGREE.search(p)), "")
    location = next((p for p in pieces if _PLACE.match(p)), "")
    rest = [p for p in pieces if p not in (school, degree, location)]
    if not school and rest:
        school = rest.pop(0)
    if not degree and rest:
        degree = rest.pop(0)
    return Education(
        school=_clip(school),
        degree=_clip(", ".join([degree, *rest]) if rest and len(rest) < 3 else degree),
        location=_clip(location),
        start=start[:30],
        end=end[:30],
        details=[_clip(p, 200) for p in points][:8],
    )


def _project(head: list[str], points: list[str]) -> Project:
    date_ = ""
    pieces: list[str] = []
    for line in head:
        rest, s, e = _take_dates(line)
        if e and not date_:
            date_ = f"{s} – {e}" if s else e
        pieces += _parts(rest)
    link = next((p for p in pieces if _URL.fullmatch(p) and "." in p and " " not in p), "")
    pieces = [p for p in pieces if p != link]
    name = pieces.pop(0) if pieces else ""
    if ": " in name and not points:  # "Name: what it does, all on one line"
        name, about = name.split(": ", 1)
        points = [about]
    # "Name (Python, React)"
    m = re.match(r"^(.*?)\s*\((.+)\)$", name)
    tech = ""
    if m and extract_skills(m[2]):
        name, tech = m[1], m[2]
    if not tech:
        tech = next((p for p in pieces if extract_skills(p)), "")
    pieces = [p for p in pieces if p != tech]
    return Project(
        name=_clip(name),
        tech=_clip(tech, 200),
        link=_clip(link, 200),
        date=date_[:40],
        bullets=[_clip(b, 400) for b in points + pieces][:8] or [""],
    )


def _skills(text: str) -> list[SkillGroup]:
    groups: list[SkillGroup] = []
    loose: list[str] = []
    for raw in text.splitlines():
        line = _BULLET.sub("", raw).strip()
        if not line:
            continue
        m = re.match(r"^([A-Za-z][\w &/+-]{1,38}):\s*(.+)$", line)
        if m:
            groups.append(SkillGroup(label=m[1].strip(), items=_clip(m[2], 600)))
        else:
            loose.append(line)
    if loose:
        groups.append(SkillGroup(label="" if groups else "Skills", items=_clip(", ".join(loose), 600)))
    return groups[:8]


def _contact(header: str) -> Contact:
    lines = [line.strip() for line in header.splitlines() if line.strip()]
    text = " | ".join(lines)
    email = (_EMAIL.search(text) or [""])[0] if _EMAIL.search(text) else ""
    phone_m = _PHONE.search(text)
    links: list[Link] = []
    for part in _parts(text.replace(email, "")):
        for url in _URL.findall(part):
            lower = url.lower()
            if "." not in url or _PHONE.fullmatch(url) or len(links) >= 4:
                continue
            label = "LinkedIn" if "linkedin" in lower else "GitHub" if "github" in lower else "Website"
            if not any(link.url == url for link in links):
                links.append(Link(label=label, url=url[:200]))
    location = next((p for p in _parts(text) if _PLACE.match(p)), "")
    name = lines[0] if lines and not _EMAIL.search(lines[0]) else ""
    name = _parts(name)[0] if name else ""
    headline = ""
    if len(lines) > 1:
        second = lines[1]
        if not (
            _EMAIL.search(second) or _PHONE.search(second) or _URL.search(second) or _PLACE.match(second)
        ):
            headline = second
    return Contact(
        name=_clip(name),
        headline=_clip(headline),
        email=_clip(email),
        phone=phone_m.group(0)[:40] if phone_m else "",
        location=_clip(location),
        links=links,
    )


def _certifications(text: str) -> list[Certification]:
    out = []
    for raw in text.splitlines():
        line = _BULLET.sub("", raw).strip()
        if not line:
            continue
        rest, _, date_ = _take_dates(line)
        pieces = _parts(rest)
        name = pieces[0] if pieces else rest
        issuer = pieces[1] if len(pieces) > 1 else ""
        if not issuer and ", " in name:
            name, issuer = name.rsplit(", ", 1)
        out.append(Certification(name=_clip(name), issuer=_clip(issuer), date=date_[:30]))
    return out[:10]


_ORDER_KEYS = ("summary", "education", "experience", "projects", "skills", "certifications")


def text_to_document(text: str) -> ResumeDocument:
    sections = split_sections(text)
    experience = [_experience(h, p) for h, p in _blocks(sections.get("experience", "")) if h or p]
    # volunteering and leadership read like jobs
    experience += [_experience(h, p) for h, p in _blocks(sections.get("leadership", "")) if h or p]
    education = [_education(h, p) for h, p in _blocks(sections.get("education", "")) if h or p]
    awards = [
        _BULLET.sub("", line).strip() for line in sections.get("awards", "").splitlines() if line.strip()
    ]
    if awards:
        if education:
            education[0].details = (education[0].details + [f"Award: {a}" for a in awards])[:8]
        else:
            education.append(Education(details=[_clip(a, 200) for a in awards][:8]))
    order = [key for key in sections if key in _ORDER_KEYS]
    order += [
        key
        for key in ("education", "experience", "projects", "skills", "summary", "certifications")
        if key not in order
    ]
    summary = " ".join(line.strip() for line in sections.get("summary", "").splitlines() if line.strip())
    return ResumeDocument(
        contact=_contact(sections.get("header", "")),
        summary=summary[:600],
        education=education[:6],
        experience=experience[:12],
        projects=[_project(h, p) for h, p in _blocks(sections.get("projects", "")) if h or p][:10],
        skills=_skills(sections.get("skills", "")),
        certifications=_certifications(sections.get("certifications", "")),
        section_order=order,  # type: ignore[arg-type]
    )
