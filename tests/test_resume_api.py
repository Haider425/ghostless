"""Resume endpoints against a real PostgreSQL. Skipped unless TEST_DATABASE_URL is set."""

import os
from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from tests.conftest import reset_database  # noqa: E402
from tests.test_resume import STRONG  # noqa: E402
from tracker import db  # noqa: E402
from tracker.api import create_app  # noqa: E402
from tracker.api import resumes as resume_routes  # noqa: E402
from tracker.api.deps import limiter  # noqa: E402
from tracker.classify import enrich  # noqa: E402
from tracker.models import Company, Job  # noqa: E402
from tracker.skills import extract_skills  # noqa: E402

DSN = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DSN, reason="TEST_DATABASE_URL not set")

POSTINGS = [
    ("de", "Data Engineering Intern", "Python, SQL, Spark and Airflow pipelines. Kafka a plus."),
    ("fe", "Frontend Developer Intern", "React and TypeScript for our web app."),
    ("hw", "Senior ASIC Design Engineer", "RTL in SystemVerilog, UVM verification."),
    ("pool", "Software Engineer Intern", "This posting is not for an existing vacancy. Python and Java."),
    ("rec", "Technical Recruiter", "Hire great engineers."),
]


@pytest.fixture
def client():
    with db.connect(DSN) as conn:
        reset_database(conn)
        db.apply_schema(conn)
        cid = db.upsert_company(conn, Company("Acme", "greenhouse", "acme"))
        jobs = [
            enrich(
                Job(
                    external_id=ext,
                    title=title,
                    url=f"https://acme.example/{ext}",
                    location="Toronto, ON",
                    description=text,
                ),
                extract_skills(f"{title} {text}"),
            )
            for ext, title, text in POSTINGS
        ]
        db.save_company_jobs(conn, cid, jobs, datetime.now(timezone.utc) - timedelta(days=1))
        db.refresh_signals(conn)
        conn.commit()
    limiter.reset()
    resume_routes._POOL_CACHE.clear()
    with TestClient(create_app(DSN)) as c:
        yield c


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def ids_by_title(client):
    items = client.get(
        "/jobs", params={"role": ["sde", "data_eng", "hardware", "other"], "limit": 50}
    ).json()["items"]
    return {j["title"]: j["id"] for j in items}


def test_analyze_text_and_file(client):
    analysis = client.post("/resume/analyze-text", json={"text": STRONG}).json()
    assert analysis["profile"]["level"] == "student"
    assert analysis["strength"] >= 85 and analysis["resume_id"] is None

    upload = client.post("/resume/analyze", files={"file": ("resume.txt", STRONG.encode(), "text/plain")})
    assert upload.status_code == 200 and upload.json()["profile"]["skills"] == analysis["profile"]["skills"]
    bad = client.post("/resume/analyze", files={"file": ("photo.png", b"\x89PNG....", "image/png")})
    assert bad.status_code == 422 and "PDF or Word" in bad.json()["detail"]
    # saving needs an account
    assert (
        client.post(
            "/resume/analyze?save=true", files={"file": ("r.txt", STRONG.encode(), "text/plain")}
        ).status_code
        == 401
    )


def test_match_and_recommendations_for_an_anonymous_profile(client):
    profile = client.post("/resume/analyze-text", json={"text": STRONG}).json()["profile"]
    ids = ids_by_title(client)
    scores = client.post("/resume/match", json={"profile": profile, "job_ids": list(ids.values())}).json()
    de, hw = scores[str(ids["Data Engineering Intern"])], scores[str(ids["Senior ASIC Design Engineer"])]
    assert de["score"] > hw["score"]
    assert "Kafka" in de["skills_missing"]

    recs = client.post("/resume/recommendations", json={"profile": profile, "limit": 10}).json()
    titles = [r["job"]["title"] for r in recs["items"]]
    assert "Technical Recruiter" not in titles  # tech roles only
    assert "Software Engineer Intern" not in titles  # high ghost risk is left out by default
    assert titles[0] in ("Data Engineering Intern", "Frontend Developer Intern")
    with_risky = client.post(
        "/resume/recommendations", json={"profile": profile, "include_high_risk": True}
    ).json()
    assert with_risky["total"] == recs["total"] + 1


def test_saved_resumes_and_builder(client):
    token = client.post(
        "/auth/signup", json={"email": "j@example.com", "password": "a long passphrase"}
    ).json()["token"]
    upload = client.post(
        "/resume/analyze?save=true",
        files={"file": ("Jordan Lee.txt", STRONG.encode(), "text/plain")},
        headers=auth(token),
    ).json()
    first = upload["resume_id"]
    document = {
        "contact": {"name": "Jordan Lee", "email": "j@example.com"},
        "experience": [
            {
                "title": "Software Developer Co-op",
                "company": "Maple Bank",
                "start": "May 2025",
                "end": "Aug 2025",
                "bullets": ["Built a React dashboard used by 40 analysts"],
            }
        ],
        "skills": [{"label": "Languages", "items": "Python, SQL, TypeScript"}],
    }
    built = client.post(
        "/me/resumes", json={"title": "Builder version", "document": document}, headers=auth(token)
    )
    assert built.status_code == 201
    built = built.json()
    assert built["kind"] == "built" and built["analysis"]["profile"]["skills"]

    listing = client.get("/me/resumes", headers=auth(token)).json()
    assert [r["id"] for r in listing][0] == first and listing[0]["is_primary"]  # the first one is primary

    document["skills"][0]["items"] = "Python, SQL, TypeScript, Kafka"
    updated = client.put(
        f"/me/resumes/{built['id']}", json={"title": "v2", "document": document}, headers=auth(token)
    ).json()
    assert updated["title"] == "v2" and "Kafka" in updated["analysis"]["profile"]["skills"]
    assert (
        client.put(
            f"/me/resumes/{first}", json={"title": "x", "document": document}, headers=auth(token)
        ).status_code
        == 400
    )

    assert (
        client.post(f"/me/resumes/{built['id']}/primary", headers=auth(token)).json()[0]["id"] == built["id"]
    )
    ids = ids_by_title(client)
    by_resume = client.post(
        "/resume/match",
        json={"resume_id": built["id"], "job_ids": [ids["Data Engineering Intern"]]},
        headers=auth(token),
    )
    assert by_resume.status_code == 200
    # another person's resume can't be used
    other = client.post(
        "/auth/signup", json={"email": "k@example.com", "password": "a long passphrase"}
    ).json()["token"]
    assert (
        client.post(
            "/resume/match", json={"resume_id": built["id"], "job_ids": [1]}, headers=auth(other)
        ).status_code
        == 404
    )

    remaining = client.delete(f"/me/resumes/{built['id']}", headers=auth(token)).json()
    assert [r["id"] for r in remaining] == [first] and remaining[0]["is_primary"]


def test_ai_feedback_is_off_without_a_key(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert client.get("/resume/ai-status").json() == {"enabled": False, "remaining_today": None}
    token = client.post(
        "/auth/signup", json={"email": "j@example.com", "password": "a long passphrase"}
    ).json()["token"]
    reply = client.post("/resume/ai-feedback", json={"job_id": 1, "text": STRONG}, headers=auth(token))
    assert reply.status_code == 503


def test_ai_feedback_respects_daily_limits(client, monkeypatch):
    from tracker.resume import ai

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setenv("GHOSTLESS_AI_DAILY_PER_USER", "1")
    monkeypatch.setattr(
        ai,
        "feedback",
        lambda *a: ai.AIFeedback(
            summary="Good fit", strengths=["Spark"], gaps=["Kafka"], rewrites=[], keywords=["Kafka"]
        ),
    )
    token = client.post(
        "/auth/signup", json={"email": "j@example.com", "password": "a long passphrase"}
    ).json()["token"]
    job = ids_by_title(client)["Data Engineering Intern"]
    first = client.post("/resume/ai-feedback", json={"job_id": job, "text": STRONG}, headers=auth(token))
    assert first.status_code == 200 and first.json()["remaining_today"] == 0
    assert (
        client.post(
            "/resume/ai-feedback", json={"job_id": job, "text": STRONG}, headers=auth(token)
        ).status_code
        == 429
    )
    assert client.get("/resume/ai-status", headers=auth(token)).json() == {
        "enabled": True,
        "remaining_today": 0,
    }


def test_a_resume_checked_before_signing_in_moves_to_the_account(client):
    analysis = client.post("/resume/analyze-text", json={"text": STRONG}).json()
    token = client.post(
        "/auth/signup", json={"email": "mover@example.com", "password": "correct horse battery"}
    ).json()["token"]
    imported = client.post(
        "/me/resumes/import", json={"title": "My resume", "analysis": analysis}, headers=auth(token)
    )
    assert imported.status_code == 201, imported.text
    body = imported.json()
    assert body["kind"] == "upload" and body["text"] is None and body["is_primary"] is True
    assert body["analysis"]["profile"]["skills"] == analysis["profile"]["skills"]

    # it now scores jobs like any account resume
    ids = list(ids_by_title(client).values())
    scores = client.post("/resume/match", json={"resume_id": body["id"], "job_ids": ids}, headers=auth(token))
    assert scores.status_code == 200 and len(scores.json()) == len(ids)

    # and another account can't use it
    other = client.post(
        "/auth/signup", json={"email": "other@example.com", "password": "correct horse battery"}
    ).json()["token"]
    assert (
        client.post(
            "/resume/match", json={"resume_id": body["id"], "job_ids": ids}, headers=auth(other)
        ).status_code
        == 404
    )
    assert client.post("/me/resumes/import", json={"analysis": analysis}).status_code == 401


def test_tailor_scores_a_draft_against_one_job(client):
    job_id = next(j["id"] for j in client.get("/jobs", params={"q": "Data Engineering"}).json()["items"])
    response = client.post("/resume/tailor", json={"text": STRONG, "job_id": job_id})
    assert response.status_code == 200
    body = response.json()
    assert body["job"]["id"] == job_id and body["match"]["score"] >= 60
    assert {r["text"] for r in body["match"]["requirements"]} >= {"Python", "SQL"}
    assert client.post("/resume/tailor", json={"text": STRONG, "job_id": 999999}).status_code == 404


def test_a_file_reads_into_a_builder_document(client):
    from pathlib import Path

    data = Path("web/tests/fixtures/resume.docx").read_bytes()
    response = client.post(
        "/resume/to-document",
        files={
            "file": (
                "resume.docx",
                data,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert response.status_code == 200
    doc = response.json()
    assert doc["contact"]["name"] == "Jordan Lee"
    assert doc["experience"][0]["company"] == "Maple Ledger Bank"
    assert len(doc["experience"][0]["bullets"]) == 4


def test_a_resume_saved_under_older_rules_is_re_read(client):
    import json

    token = client.post(
        "/auth/signup", json={"email": "h@example.com", "password": "a long passphrase"}
    ).json()["token"]
    # header link words with the addresses lost, as text pulled from a PDF
    text = STRONG.replace("linkedin.com/in/jordanlee | github.com/jordanlee", "GitHub • LinkedIn • Portfolio")
    saved = client.post(
        "/resume/analyze?save=true",
        files={"file": ("Jordan Lee.txt", text.encode(), "text/plain")},
        headers=auth(token),
    ).json()
    assert "no_linkedin" not in {c["id"] for c in saved["checks"]}

    # as an older version stored it: no version, and the wrong "add your LinkedIn" check
    old = {
        **saved,
        "checks": [
            {"id": "no_linkedin", "severity": "medium", "title": "Add your LinkedIn URL", "detail": ""}
        ],
    }
    old.pop("version", None)
    with db.connect(DSN) as conn:
        conn.execute("UPDATE resumes SET profile = %s::jsonb", (json.dumps(old),))
        conn.commit()

    stored = client.get(f"/me/resumes/{saved['resume_id']}", headers=auth(token)).json()
    assert "no_linkedin" not in {c["id"] for c in stored["analysis"]["checks"]}
    with db.connect(DSN) as conn:
        version = conn.execute("SELECT profile->>'version' FROM resumes").fetchone()[0]
    assert version == str(resume_routes.ANALYSIS_VERSION)  # re-read once, and kept
