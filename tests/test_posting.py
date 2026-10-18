"""Reading a posting in full, and scoring a resume against all of it."""

from datetime import date

from tests.test_resume import STRONG, WEAK
from tracker.resume.match import score_job
from tracker.resume.posting import analyze_posting, degree_required, key_terms, split_posting, years_required
from tracker.resume.profile import build_profile

TODAY = date(2026, 6, 1)

POSTING = """About us
We move money for millions of Canadians and have been in business for 20 years.

What you'll do
- Build data pipelines for our payments platform
- Own data quality checks on payment events
- Work with analysts on payments reporting

What you'll bring
- Currently enrolled in a Bachelor's in Computer Science or a related field
- Experience with Python and SQL
- Exposure to Spark or Airflow

Nice to have
- Kafka
- Kubernetes

Benefits
- Health and dental, Java lunch club, Rust stipend
"""


def test_posting_parts_and_needs():
    parts = split_posting(POSTING)
    assert "required" in parts and "preferred" in parts and "duties" in parts
    assert "Health and dental" in parts["skip"]
    needs = analyze_posting("Data Engineering Intern, Payments", POSTING)
    assert {"Python", "SQL", "Spark", "Airflow"} <= set(needs.required_skills)
    assert needs.preferred_skills == ["Kafka", "Kubernetes"]
    assert "Java" not in needs.required_skills and "Rust" not in needs.required_skills  # benefits ignored
    assert needs.enrolled and needs.degree == "bachelor" and needs.degree_fields == ["computer science"]
    assert needs.years is None  # "20 years" is the company's age
    assert any("payment" in t for t in needs.key_terms)


def test_years_and_degrees():
    assert years_required("3+ years of experience with Go; 5 years experience preferred") == 3
    assert years_required("Founded 12 years ago") is None
    assert degree_required("Master's or PhD in Statistics, or equivalent experience") == (
        "master",
        ["statistics"],
        True,
    )


def test_key_terms_need_repetition_or_the_title():
    terms = key_terms("Platform Engineer", {"general": "We like turtles.\nWe build platform tooling."}, set())
    assert "platform" in terms and "turtles" not in terms


def test_full_posting_score_explains_itself():
    profile = build_profile(STRONG, TODAY).to_dict()
    job = {
        "id": 1,
        "title": "Data Engineering Intern, Payments",
        "level": "intern",
        "role_type": "data_eng",
        "skills": [],
        "description": POSTING,
        "signals": {},
    }
    match = score_job(profile, job)
    assert not match.limited
    assert (
        sum(p.points for p in match.breakdown) == match.score
        or abs(sum(p.points for p in match.breakdown) - match.score) <= 1
    )
    assert {p.key for p in match.breakdown} == {
        "skills",
        "preferred",
        "terms",
        "experience",
        "education",
        "role",
    }
    status = {r.text: r.status for r in match.requirements}
    assert status["Python"] == "met" and status["Kafka"] == "missing" and status["Kubernetes"] == "met"
    assert status["Currently enrolled in school"] == "met"
    assert match.score >= 65


def test_skills_only_in_a_list_count_less():
    profile = build_profile(STRONG, TODAY).to_dict()
    job = {
        "id": 2,
        "title": "Platform Intern",
        "level": "intern",
        "role_type": "devops",
        "skills": [],
        "description": "Requirements\n- Kubernetes\n- Java\n- Linux experience with Kubernetes clusters\n",
        "signals": {},
    }
    match = score_job(profile, job)
    k8s = next(r for r in match.requirements if r.text == "Kubernetes")
    assert k8s.status == "partial" and "skills list" in k8s.detail
    assert any("only in your skills list" in s for s in match.suggestions)


def test_a_weak_resume_scores_low_on_a_full_posting():
    weak = build_profile(WEAK, TODAY).to_dict()
    job = {
        "id": 3,
        "title": "Software Engineer",
        "level": "mid",
        "role_type": "sde",
        "skills": [],
        "description": "Requirements\n- 3+ years of experience with Go and PostgreSQL\n- Bachelor's degree in Computer Science\n",
        "signals": {},
    }
    match = score_job(weak, job)
    assert match.score < 40
    kinds = {r.kind: r.status for r in match.requirements}
    assert kinds["experience"] == "missing" and kinds["education"] == "missing"


def test_a_senior_role_is_capped_for_a_student_whatever_the_skills():
    profile = build_profile(STRONG, TODAY).to_dict()
    job = {
        "id": 4,
        "title": "Senior Data Engineer",
        "level": "senior",
        "role_type": "data_eng",
        "skills": [],
        "description": "Requirements\\n- Python, SQL, Spark and Airflow\\n- Data pipelines at scale\\n",
        "signals": {},
    }
    match = score_job(profile, job)
    assert match.score < 35 and match.label == "Long shot"
    assert any("Capped" in n for n in match.notes)
