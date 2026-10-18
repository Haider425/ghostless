"""Reading resume text into a builder document."""

from tests.test_resume import STRONG
from tracker.resume.to_document import text_to_document

PDF_STYLE = """Priya Shah
Software developer
priya@example.ca | (604) 555-0142 | Vancouver, BC | https://priya.dev

Work Experience
Backend Developer Intern at Fraser Labs                       Sept 2025 – Dec 2025
Vancouver, BC
Built a Go service that processes 2 million events a day with Kafka and PostgreSQL
Reduced p95 latency by 40% by adding Redis caching to the hottest endpoint

Teaching Assistant, Simon Fraser University    Jan 2025 – Apr 2025
Led weekly labs for 60 students in data structures

Education
Simon Fraser University
BSc Computing Science, Minor in Statistics        2022 – 2026

Projects
Course planner (Next.js, TypeScript, Supabase)
Planned schedules for 1,200 students in the first term after launch

Technical Skills
Python, Go, TypeScript, SQL, Kafka, Redis, Docker
"""


def test_a_typical_resume():
    doc = text_to_document(STRONG)
    assert doc.contact.name == "Jordan Lee" and doc.contact.email == "jordan.lee@example.com"
    assert doc.contact.location == "Toronto, ON"
    assert [link.label for link in doc.contact.links] == ["LinkedIn", "GitHub"]
    assert doc.education[0].school == "University of Waterloo"
    assert doc.education[0].end == "Expected April 2027"
    first = doc.experience[0]
    assert (first.title, first.company, first.start, first.end) == (
        "Software Developer Co-op",
        "Maple Bank",
        "May 2025",
        "Aug 2025",
    )
    assert len(first.bullets) == 3
    assert doc.projects[0].tech == "Python, PostgreSQL, Docker, AWS"
    assert [g.label for g in doc.skills] == ["Languages", "Tools"]
    assert doc.section_order[:4] == ["education", "experience", "projects", "skills"]


def test_a_pdf_that_lost_its_bullets():
    doc = text_to_document(PDF_STYLE)
    assert doc.contact.headline == "Software developer"
    assert doc.contact.phone == "(604) 555-0142" and doc.contact.links[0].url == "https://priya.dev"
    intern, ta = doc.experience
    assert (intern.title, intern.company, intern.location) == (
        "Backend Developer Intern",
        "Fraser Labs",
        "Vancouver, BC",
    )
    assert len(intern.bullets) == 2
    assert (ta.title, ta.company) == ("Teaching Assistant", "Simon Fraser University")
    assert ta.bullets == ["Led weekly labs for 60 students in data structures"]
    assert doc.education[0].degree.startswith("BSc Computing Science")
    assert (doc.education[0].start, doc.education[0].end) == ("2022", "2026")
    assert (doc.projects[0].name, doc.projects[0].tech) == ("Course planner", "Next.js, TypeScript, Supabase")
    assert doc.section_order[0] == "experience"


def test_empty_text_gives_an_empty_document():
    doc = text_to_document("")
    assert doc.experience == [] and doc.contact.name == ""
