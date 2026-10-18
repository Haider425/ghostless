"""Resumes made in the builder: a structured document, validated here and
turned into plain text for analysis."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Template = Literal["classic", "modern", "compact"]
_SHORT = 120
_LONG = 600


class Link(BaseModel):
    label: str = Field("", max_length=40)
    url: str = Field("", max_length=200)


class Contact(BaseModel):
    name: str = Field("", max_length=_SHORT)
    headline: str = Field("", max_length=_SHORT)
    email: str = Field("", max_length=_SHORT)
    phone: str = Field("", max_length=40)
    location: str = Field("", max_length=_SHORT)
    links: list[Link] = Field(default_factory=list, max_length=6)


class Education(BaseModel):
    school: str = Field("", max_length=_SHORT)
    degree: str = Field("", max_length=_SHORT)
    location: str = Field("", max_length=_SHORT)
    start: str = Field("", max_length=30)
    end: str = Field("", max_length=30)
    details: list[str] = Field(default_factory=list, max_length=8)


class Experience(BaseModel):
    title: str = Field("", max_length=_SHORT)
    company: str = Field("", max_length=_SHORT)
    location: str = Field("", max_length=_SHORT)
    start: str = Field("", max_length=30)
    end: str = Field("", max_length=30)
    bullets: list[str] = Field(default_factory=list, max_length=10)


class Project(BaseModel):
    name: str = Field("", max_length=_SHORT)
    tech: str = Field("", max_length=200)
    link: str = Field("", max_length=200)
    date: str = Field("", max_length=40)
    bullets: list[str] = Field(default_factory=list, max_length=8)


class SkillGroup(BaseModel):
    label: str = Field("", max_length=40)
    items: str = Field("", max_length=_LONG)


class Certification(BaseModel):
    name: str = Field("", max_length=_SHORT)
    issuer: str = Field("", max_length=_SHORT)
    date: str = Field("", max_length=30)


class ResumeDocument(BaseModel):
    template: Template = "classic"
    contact: Contact = Field(default_factory=Contact)
    summary: str = Field("", max_length=_LONG)
    education: list[Education] = Field(default_factory=list, max_length=6)
    experience: list[Experience] = Field(default_factory=list, max_length=12)
    projects: list[Project] = Field(default_factory=list, max_length=10)
    skills: list[SkillGroup] = Field(default_factory=list, max_length=8)
    certifications: list[Certification] = Field(default_factory=list, max_length=10)
    section_order: list[
        Literal["summary", "education", "experience", "projects", "skills", "certifications"]
    ] = Field(
        default_factory=lambda: ["summary", "education", "experience", "projects", "skills", "certifications"]
    )


def _dates(start: str, end: str) -> str:
    return f"{start} - {end}" if start and end else start or end


def document_to_text(doc: ResumeDocument) -> str:
    """The resume as plain text, laid out like a typical resume so the same
    analysis applies to built and uploaded resumes."""
    c = doc.contact
    lines = [c.name, c.headline, " | ".join(x for x in [c.email, c.phone, c.location] if x)]
    lines += [link.url for link in c.links if link.url]
    for section in doc.section_order:
        if section == "summary" and doc.summary.strip():
            lines += ["", "Summary", doc.summary.strip()]
        elif section == "education" and doc.education:
            lines += ["", "Education"]
            for e in doc.education:
                lines.append(
                    " | ".join(x for x in [e.school, e.degree, e.location, _dates(e.start, e.end)] if x)
                )
                lines += [f"• {d}" for d in e.details if d.strip()]
        elif section == "experience" and doc.experience:
            lines += ["", "Experience"]
            for e in doc.experience:
                lines.append(
                    " | ".join(x for x in [e.title, e.company, e.location, _dates(e.start, e.end)] if x)
                )
                lines += [f"• {b}" for b in e.bullets if b.strip()]
        elif section == "projects" and doc.projects:
            lines += ["", "Projects"]
            for p in doc.projects:
                lines.append(" | ".join(x for x in [p.name, p.tech, p.link, p.date] if x))
                lines += [f"• {b}" for b in p.bullets if b.strip()]
        elif section == "skills" and doc.skills:
            lines += ["", "Skills"]
            lines += [f"{g.label}: {g.items}" if g.label else g.items for g in doc.skills if g.items.strip()]
        elif section == "certifications" and doc.certifications:
            lines += ["", "Certifications"]
            lines += [
                " | ".join(x for x in [cert.name, cert.issuer, cert.date] if x) for cert in doc.certifications
            ]
    return "\n".join(line for line in lines if line is not None).strip()
