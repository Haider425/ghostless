"""Reading resume text into a builder document."""

import pytest

from tests.test_resume import STRONG
from tracker.resume.to_document import _split_place, text_to_document

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


# Text as pypdf gives it for a common two-column header layout: right-aligned
# places and dates glued to the left-aligned text, and bullets wrapped onto
# lines of their own.
PDF_SHAPED = """Alex Morgan
alex@example.com • (416-555-0140) • GitHub • LinkedIn • Portfolio
https://github.com/alexm | https://linkedin.com/in/alexm | https://alexm.dev
EDUCATION
Ontario Tech University Oshawa, Ontario
Bachelor of Science in Computer Science | Minors: Mathematics, Astronomy Graduating December 2027
EXPERIENCE
Software Developer Co-op Darlington, Ontario
Ontario Power Generation September 2026 – April 2027
• Developed a scheduling web app with Angular and ASP.NET Core that shows workers which days their form approvers
are in office, used by 20+ staff
• Combined employee and form data from 4 databases, using SQL to narrow over 1 million records to a few hundred
matches in under 4 seconds
Data Analyst Co-op Toronto, Ontario
Ontario Public Service – MPBSDP May 2026 – August 2026
• Analyzed datasets with SQL and Excel across 5+ projects, identifying trends to inform business
decisions
Software Engineer Remote
Square Root Technologies December 2025 – March 2026
• Built an AI pipeline to generate product pages from raw deal data, processing
100+ listings per hour
"""


def test_pdf_layout_keeps_entries_places_and_wrapped_bullets_together():
    doc = text_to_document(PDF_SHAPED)
    assert [(link.label, link.url) for link in doc.contact.links] == [
        ("GitHub", "https://github.com/alexm"),
        ("LinkedIn", "https://linkedin.com/in/alexm"),
        ("Website", "https://alexm.dev"),
    ]
    [school] = doc.education
    assert (school.school, school.location) == ("Ontario Tech University", "Oshawa, Ontario")
    rows = [(e.title, e.company, e.location, len(e.bullets)) for e in doc.experience]
    assert rows == [
        ("Software Developer Co-op", "Ontario Power Generation", "Darlington, Ontario", 2),
        ("Data Analyst Co-op", "Ontario Public Service – MPBSDP", "Toronto, Ontario", 1),
        ("Software Engineer", "Square Root Technologies", "Remote", 1),
    ]
    first = doc.experience[0].bullets[0]
    assert first.endswith("form approvers are in office, used by 20+ staff")
    assert doc.experience[2].bullets[0].endswith("processing 100+ listings per hour")


@pytest.mark.parametrize(
    "piece, expected",
    [
        ("Software Developer Co-op Darlington, Ontario", ["Software Developer Co-op", "Darlington, Ontario"]),
        ("Engineer New York, NY", ["Engineer", "New York, NY"]),
        ("Software Engineer Remote", ["Software Engineer", "Remote"]),
        ("Toronto, ON", ["Toronto, ON"]),
        ("Remote Sensing Analyst", ["Remote Sensing Analyst"]),
    ],
)
def test_split_place(piece, expected):
    assert _split_place(piece) == expected
