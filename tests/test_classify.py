from datetime import date, datetime, timezone

import pytest

from tracker.classify import (
    classify_level,
    classify_role,
    enrich,
    is_canada,
    is_remote,
    is_upcoming,
    parse_terms,
    term_start,
)
from tracker.models import Job


@pytest.mark.parametrize(
    "title, expected",
    [
        ("Software Engineering Intern (Summer 2027)", "intern"),
        ("Co-op Software Developer", "intern"),
        ("Software Engineer, New Grad", "new_grad"),
        ("Junior Backend Developer", "new_grad"),
        ("Software Engineer I", "new_grad"),
        ("Senior Software Engineer", "senior"),
        ("Staff Data Engineer", "senior"),
        ("Engineering Manager, Payments", "senior"),
        ("Software Engineer", "mid"),
        ("Backend Engineer, Ledger", "mid"),
    ],
)
def test_classify_level(title, expected):
    assert classify_level(title) == expected


@pytest.mark.parametrize(
    "title, expected",
    [
        ("Software Engineer, New Grad", "sde"),
        ("Full Stack Developer", "sde"),
        ("Backend Engineer, Ledger", "sde"),
        ("SWE Intern", "sde"),
        ("Data Engineer", "data_eng"),
        ("Analytics Engineer", "data_eng"),
        ("Senior Data Platform Engineer", "data_eng"),
        ("Data Scientist, Growth", "data"),
        ("Machine Learning Engineer", "ml"),
        ("Deep Learning Software Engineer", "ml"),
        ("Research Scientist, Generative AI", "ml"),
        ("Applied Scientist", "ml"),
        ("Senior ASIC Design Engineer", "hardware"),
        ("GPU Architect", "hardware"),
        ("Hardware Verification Engineer", "hardware"),
        ("Firmware Engineer", "hardware"),
        ("Physical Design Engineer", "hardware"),
        ("Security Engineer", "security"),
        ("Senior Manager, Cybersecurity", "security"),
        ("Site Reliability Engineer", "sde"),
        ("DevOps Engineer", "sde"),
        ("QA Automation Engineer", "sde"),
        ("Member of Technical Staff", "sde"),
        ("Senior Developer, Mainframe", "sde"),
        ("Senior Software Engineer, GPU Drivers", "sde"),
        ("Data Analyst", "data"),
        ("Quantitative Analyst", "data"),
        ("Account Executive", "other"),
        ("Product Designer", "other"),
        ("Technical Recruiter", "other"),
        ("Product Manager, AI Platform", "other"),
        ("Solutions Architect", "other"),
        ("Sales Engineer", "other"),
        ("Branch Teller", "other"),
    ],
)
def test_classify_role(title, expected):
    assert classify_role(title) == expected


@pytest.mark.parametrize(
    "location, expected",
    [
        ("Toronto, Canada", True),
        ("Waterloo, ON", True),
        ("Remote - Canada", True),
        ("Montréal", True),
        ("San Francisco, CA", False),
        ("Ontario, California", True),  # known false positive, documented on purpose
        ("", False),
    ],
)
def test_is_canada(location, expected):
    assert is_canada(location) == expected


def test_is_remote():
    assert is_remote("Remote - US")
    assert is_remote("New York", source_remote=True)
    assert not is_remote("New York")


# ---------- Seasons ----------


@pytest.mark.parametrize(
    "title, expected",
    [
        ("Software Engineer Intern (Summer 2027)", ["Summer 2027"]),
        ("Co-op, Winter-27", ["Winter 2027"]),
        ("2027 Summer Internship - PSG Product Analyst, APAC", ["Summer 2027"]),
        ("Software Engineering Intern (2027 Summer Internship)", ["Summer 2027"]),
        ("Spring/Summer 2027 Engineering Intern", ["Spring 2027", "Summer 2027"]),
        ("Co-op Engineer - Winter/Spring/Summer 2027", ["Winter 2027", "Spring 2027", "Summer 2027"]),
        ("Robotics Intern (Fall/Winter 2026)", ["Fall 2026", "Winter 2026"]),
        ("Run Perception Graduate Internship, R&D - Winter 2027", ["Winter 2027"]),  # a program, not a date
        # a graduation date is about the applicant, not the work term
        ("Software Engineer, Entry-Level (Graduation Date Winter 2026 - Spring/Summer 2027)", []),
        ("Software Engineer I, Entry-Level (Graduation Date: Fall 2026-Summer 2027)", []),
    ],
)
def test_parse_terms_from_titles(title, expected):
    assert parse_terms(title) == expected


@pytest.mark.parametrize(
    "description, expected",
    [
        (
            "The opportunity:\n• 12 month work-term beginning January 2027.\n• Full-time, paid",
            ["Winter 2027"],
        ),
        (
            "This position starts in January 2027 or June 2027 and runs four months.",
            ["Winter 2027", "Summer 2027"],
        ),
        ("You must be available for 10 weeks beginning May 24, 2027.", ["Summer 2027"]),
        ("• Duration : 8 months starting on January 4, 2027", ["Winter 2027"]),
        ("We are hiring for a co-op starting in September 2027.", ["Fall 2027"]),
        (
            "This application is for internship starts in Spring and Summer 2027.",
            ["Spring 2027", "Summer 2027"],
        ),
        ("• Program: Summer 2027 Internship", ["Summer 2027"]),
        # not the work term: company history, an old cohort, the hiring timeline, a graduation date
        ("Founded in Spring 2016, we have grown fast. Our Summer 2025 interns loved it.", []),
        ("We will begin reviewing applications and interviews starting August 2026.", []),
        ("You are graduating in May 2028 or later.", []),
    ],
)
def test_parse_terms_from_intern_descriptions(description, expected):
    assert parse_terms("Software Engineering Intern", description, "intern", 2026) == expected


def test_parse_terms_reads_descriptions_only_for_student_roles():
    text = "Our onboarding program starts in January 2027."
    assert parse_terms("Senior Engineer", text, "senior", 2026) == []
    assert parse_terms("New Grad Engineer", text, "new_grad", 2026) == ["Winter 2027"]


def test_a_season_in_the_title_wins_over_the_description():
    # the description still names last year's program
    text = "Join the RF-SMART Summer 2026 Internship Program, starting in May."
    assert parse_terms("Hardware Support Internship - Summer 2027", text, "intern", 2026) == ["Summer 2027"]


def test_description_seasons_must_be_near_the_year_the_posting_appeared():
    text = "The internship starts in January 2031."
    assert parse_terms("Intern", text, "intern", 2026) == []
    assert parse_terms("Intern", text, "intern", 2030) == ["Winter 2031"]


def test_term_order_and_upcoming():
    terms = ["Fall 2027", "Winter 2027", "Summer 2027", "Spring 2027", "Fall 2026", "Spring 2016"]
    assert sorted(terms, key=term_start) == [
        "Spring 2016",
        "Fall 2026",
        "Winter 2027",
        "Spring 2027",
        "Summer 2027",
        "Fall 2027",
    ]
    october = date(2026, 10, 18)
    assert [t for t in terms if is_upcoming(t, october)] == [
        "Fall 2027",
        "Winter 2027",
        "Summer 2027",
        "Spring 2027",
    ]
    assert is_upcoming("Fall 2026", date(2026, 8, 31)) and not is_upcoming("Fall 2026", date(2026, 9, 1))
    assert not is_upcoming("N/A", october)


def test_enrich_reads_seasons_from_the_description():
    next_year = datetime.now(timezone.utc).year + 1
    job = Job(
        external_id="1",
        title="Data Engineering Co-op",
        url="https://example.com/1",
        description=f"A 4-month work term beginning January {next_year}.",
    )
    assert enrich(job, []).terms == [f"Winter {next_year}"]


# ---------- what Ghostless stores ----------

from tracker.classify import keep_relevant, worth_storing  # noqa: E402
from tracker.models import JobList  # noqa: E402


def _job(title: str) -> Job:
    return enrich(Job(external_id=title, title=title, url="https://example.com"), [])


@pytest.mark.parametrize(
    "title, stored",
    [
        ("Senior Software Engineer", True),  # tech, any level
        ("Data Engineer II", True),
        ("Software Engineering Intern", True),
        ("Finance Intern - Summer 2027", True),  # a student role in any field
        ("Sales Development Associate, New Grad", True),
        ("Warehouse Associate", False),  # neither tech nor a student role
        ("Senior Accountant", False),
        ("Account Executive, Commercial", False),
    ],
)
def test_worth_storing(title, stored):
    assert worth_storing(_job(title)) is stored


def test_keep_relevant_keeps_the_listing_complete_flag():
    jobs = JobList([_job("Software Engineer"), _job("Warehouse Associate")], complete=False, total=7)
    kept = keep_relevant(jobs)
    assert [j.title for j in kept] == ["Software Engineer"]
    assert kept.complete is False and kept.total == 7  # closure tracking still sees a partial listing


@pytest.mark.parametrize(
    "title, level",
    [
        ("Stage – Assistant(e) Chef de Projet Événements (H/F/X) - Janvier 2027", "intern"),
        ("Stage ingénieur : Développement d'outils d'IA", "intern"),
        ("Stagiaire ingénieur de recherche (H/F)", "intern"),
        ("Alternant(e) HR Généraliste", "intern"),
        ("Praktikant (m/w/d) Chemielabor", "intern"),
        ("Werkstudent:in Marketing (w/m/d)", "intern"),
        ("Tirocinio Extracurriculare - Assistenza Tecnica", "intern"),
        ("2027 Summer Analyst - Risk Management - New York, NY", "intern"),
        ("2027 Capital Markets, Global Investment Banking Summer Associate", "intern"),
        ("2027 Invest in Success Program (New York)", "new_grad"),
        ("Finance Rotational Program - May 2027 Grads", "new_grad"),
        ("Operations Leadership Development Program – Class of 2027", "new_grad"),
        # English uses of the same words stay as they were
        ("Stage Manager", "senior"),
        ("Early Stage Venture Investor", "mid"),
        ("Development Program Manager (Q-Systems)", "senior"),
        ("Director Drug Development Program Management", "senior"),
        ("Community Instructor - Youth Development Program", "mid"),
    ],
)
def test_student_titles_in_other_languages_and_programs(title, level):
    assert classify_level(title) == level


@pytest.mark.parametrize(
    "title, role",
    [
        ("Senior AI Applied Engineer", "ml"),
        ("AI Product Engineer, Deployed", "ml"),
        ("AI Benchmark Engineer | Native Language Specialist - Dutch - Remote", "other"),
        ("AI Support Engineer - Toronto (Weekend Shift)", "other"),
        ("AI Field Engineer - Strategic Partnerships", "other"),
    ],
)
def test_ai_titles_with_words_between(title, role):
    assert classify_role(title) == role
