"""Accounts, reports, analytics and admin endpoints against a real PostgreSQL.
Skipped unless TEST_DATABASE_URL is set."""

import os
from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from tests.conftest import reset_database  # noqa: E402
from tracker import db  # noqa: E402
from tracker.accounts import mailer, store  # noqa: E402
from tracker.api import create_app  # noqa: E402
from tracker.api.deps import limiter  # noqa: E402
from tracker.classify import enrich  # noqa: E402
from tracker.models import Company, Job  # noqa: E402
from tracker.skills import extract_skills  # noqa: E402

DSN = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DSN, reason="TEST_DATABASE_URL not set")

PASSWORD = "correct horse battery"


@pytest.fixture
def client():
    with db.connect(DSN) as conn:
        reset_database(conn)
        db.apply_schema(conn)
        cid = db.upsert_company(conn, Company("Acme", "greenhouse", "acme"))
        jobs = [
            enrich(
                Job(
                    external_id=str(i),
                    title=title,
                    url=f"https://acme.example/{i}",
                    location="Toronto, ON",
                    description="Build APIs in Python and SQL.",
                ),
                extract_skills(f"{title} Python SQL"),
            )
            for i, title in enumerate(["Software Engineer Intern", "Data Engineer"])
        ]
        db.save_company_jobs(conn, cid, jobs, datetime.now(timezone.utc) - timedelta(days=1))
        db.refresh_signals(conn)
        conn.commit()
    limiter.reset()
    mailer.outbox.clear()
    with TestClient(create_app(DSN)) as c:
        yield c


def signup(client, email="sam@example.com", password=PASSWORD, name="Sam"):
    response = client.post("/auth/signup", json={"email": email, "password": password, "name": name})
    assert response.status_code == 201, response.text
    return response.json()


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def job_ids(client):
    return [j["id"] for j in client.get("/jobs", params={"role": ["sde", "data_eng"]}).json()["items"]]


def test_signup_login_and_me(client):
    session = signup(client, email="  Sam@Example.com ")
    assert session["user"]["email"] == "sam@example.com"
    assert session["user"]["email_verified"] is False
    assert session["user"]["settings"]["theme"] == "system"
    assert mailer.outbox[-1].subject.startswith("Confirm your email")

    me = client.get("/me", headers=auth(session["token"]))
    assert me.status_code == 200 and me.json()["name"] == "Sam"
    assert me.headers["cache-control"] == "private, no-store"

    login = client.post("/auth/login", json={"email": "SAM@example.com", "password": PASSWORD})
    assert login.status_code == 200
    assert (
        client.post(
            "/auth/login", json={"email": "sam@example.com", "password": "wrong password!"}
        ).status_code
        == 401
    )
    assert (
        client.post("/auth/login", json={"email": "nobody@example.com", "password": PASSWORD}).status_code
        == 401
    )


def test_signup_rejects_weak_passwords_bad_emails_and_duplicates(client):
    assert client.post("/auth/signup", json={"email": "a@b.co", "password": "short"}).status_code == 422
    assert (
        client.post("/auth/signup", json={"email": "not-an-email", "password": PASSWORD}).status_code == 422
    )
    signup(client)
    assert (
        client.post("/auth/signup", json={"email": "sam@example.com", "password": PASSWORD}).status_code
        == 409
    )


def test_signed_out_requests_are_refused(client):
    assert client.get("/me").status_code == 401
    assert client.get("/me", headers=auth("made-up-token")).status_code == 401
    assert client.get("/admin/overview").status_code == 401


def test_logout_ends_the_session(client):
    token = signup(client)["token"]
    assert client.post("/auth/logout", headers=auth(token)).status_code == 204
    assert client.get("/me", headers=auth(token)).status_code == 401


def test_email_verification_link_works_once(client):
    signup(client)
    link = mailer.outbox[-1].link
    token = link.split("token=")[1]
    assert client.post("/auth/verify-email", json={"token": token}).json()["email_verified"] is True
    assert client.post("/auth/verify-email", json={"token": token}).status_code == 400


def test_password_reset_flow_signs_out_other_devices(client):
    old_token = signup(client)["token"]
    reply = client.post("/auth/forgot-password", json={"email": "sam@example.com"})
    assert reply.status_code == 202
    # the same reply for unknown emails, so accounts can't be discovered
    assert client.post("/auth/forgot-password", json={"email": "ghost@example.com"}).json() == reply.json()
    token = mailer.outbox[-1].link.split("token=")[1]

    weak = client.post("/auth/reset-password", json={"token": token, "password": "short"})
    assert weak.status_code == 422
    reset = client.post("/auth/reset-password", json={"token": token, "password": "a brand new passphrase"})
    assert reset.status_code == 200
    assert client.get("/me", headers=auth(old_token)).status_code == 401
    assert (
        client.post(
            "/auth/login", json={"email": "sam@example.com", "password": "a brand new passphrase"}
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/auth/reset-password", json={"token": token, "password": "another passphrase"}
        ).status_code
        == 400
    )


def test_settings_profile_and_password_change(client):
    token = signup(client)["token"]
    settings = {
        "theme": "dark",
        "text_size": "lg",
        "density": "compact",
        "reduce_motion": True,
        "underline_links": True,
        "default_location": "canada",
        "hide_high_risk": True,
        "analytics": False,
    }
    saved = client.put("/me/settings", json=settings, headers=auth(token)).json()
    assert saved["settings"] == settings
    assert (
        client.put("/me/settings", json={**settings, "theme": "neon"}, headers=auth(token)).status_code == 422
    )
    assert client.patch("/me", json={"name": "Samira"}, headers=auth(token)).json()["name"] == "Samira"

    other_device = client.post("/auth/login", json={"email": "sam@example.com", "password": PASSWORD}).json()[
        "token"
    ]
    wrong = client.post(
        "/me/password",
        json={"current_password": "nope nope nope", "new_password": "new passphrase here"},
        headers=auth(token),
    )
    assert wrong.status_code == 400
    changed = client.post(
        "/me/password",
        json={"current_password": PASSWORD, "new_password": "new passphrase here"},
        headers=auth(token),
    )
    assert changed.status_code == 200
    assert client.get("/me", headers=auth(token)).status_code == 200  # this device stays signed in
    assert client.get("/me", headers=auth(other_device)).status_code == 401


def test_saved_jobs_sync(client):
    token = signup(client)["token"]
    first, second = job_ids(client)
    saved_ids = client.post(
        "/me/saved", json={"job_ids": [first, second, 999999]}, headers=auth(token)
    ).json()
    assert sorted(saved_ids) == sorted([first, second])  # the unknown id is ignored
    saved = client.get("/me/saved", headers=auth(token)).json()
    assert {e["job"]["id"] for e in saved} == {first, second}
    assert {e["status"] for e in saved} == {"saved"}
    assert sorted(client.get("/me/saved/ids", headers=auth(token)).json()) == sorted([first, second])

    # track an application: status and private notes
    update = {"status": "interviewing", "notes": "Phone screen Tuesday"}
    assert client.patch(f"/me/saved/{first}", json=update, headers=auth(token)).status_code == 200
    entry = next(e for e in client.get("/me/saved", headers=auth(token)).json() if e["job"]["id"] == first)
    assert (entry["status"], entry["notes"]) == ("interviewing", "Phone screen Tuesday")
    assert client.patch(f"/me/saved/{first}", json={"notes": ""}, headers=auth(token)).status_code == 200
    entry = next(e for e in client.get("/me/saved", headers=auth(token)).json() if e["job"]["id"] == first)
    assert (entry["status"], entry["notes"]) == ("interviewing", None)  # notes cleared, status kept
    assert (
        client.patch(f"/me/saved/{first}", json={"status": "hired"}, headers=auth(token)).status_code == 422
    )
    assert (
        client.patch("/me/saved/999999", json={"status": "applied"}, headers=auth(token)).status_code == 404
    )

    assert client.delete(f"/me/saved/{first}", headers=auth(token)).json() == [second]


def test_recording_an_application_is_idempotent_and_never_moves_backwards(client):
    token = signup(client)["token"]
    first, second = job_ids(client)[:2]

    # "yes, I applied" on a job that wasn't saved: saved once, as applied, with today's date
    recorded = client.post(f"/me/applications/{first}", json={}, headers=auth(token)).json()
    assert (recorded["status"], recorded["changed"]) == ("applied", True)
    assert recorded["applied_at"] is not None

    # asked again (a second tab, a double click): nothing changes, nothing is duplicated
    again = client.post(f"/me/applications/{first}", json={}, headers=auth(token)).json()
    assert (again["status"], again["changed"], again["applied_at"]) == (
        "applied",
        False,
        recorded["applied_at"],
    )
    assert client.get("/me/saved/ids", headers=auth(token)).json() == [first]

    # further along on the tracker: a later "yes, I applied" doesn't move it back
    client.patch(f"/me/saved/{first}", json={"status": "interviewing"}, headers=auth(token))
    later = client.post(f"/me/applications/{first}", json={}, headers=auth(token)).json()
    assert (later["status"], later["changed"]) == ("interviewing", False)

    # a job saved earlier moves from saved to applied
    client.post("/me/saved", json={"job_ids": [second]}, headers=auth(token))
    assert client.post(f"/me/applications/{second}", json={}, headers=auth(token)).json()["changed"] is True

    assert client.post("/me/applications/999999", json={}, headers=auth(token)).status_code == 404
    assert client.post(f"/me/applications/{first}", json={}).status_code == 401

    with db.connect(DSN) as conn:
        history = conn.execute("SELECT job_id, status, source FROM application_events ORDER BY id").fetchall()
    assert history == [
        (first, "applied", "apply_prompt"),
        (first, "interviewing", "tracker"),
        (second, "applied", "apply_prompt"),
    ]


def test_applications_are_private_to_each_person(client):
    sam = signup(client)["token"]
    alex = signup(client, email="alex@example.com")["token"]
    job = job_ids(client)[0]
    client.post(f"/me/applications/{job}", json={}, headers=auth(sam))
    assert client.get("/me/saved", headers=auth(alex)).json() == []
    assert client.patch(f"/me/saved/{job}", json={"status": "offer"}, headers=auth(alex)).status_code == 404
    [entry] = client.get("/me/saved", headers=auth(sam)).json()
    assert entry["status"] == "applied"


def test_the_applied_date_can_be_set_and_cleared(client):
    token = signup(client)["token"]
    job = job_ids(client)[0]
    client.post("/me/saved", json={"job_ids": [job]}, headers=auth(token))

    def entry():
        return client.get("/me/saved", headers=auth(token)).json()[0]

    assert entry()["applied_at"] is None
    client.patch(f"/me/saved/{job}", json={"status": "applied"}, headers=auth(token))
    assert entry()["applied_at"] is not None  # moving to applied stamps the date
    client.patch(f"/me/saved/{job}", json={"applied_at": "2026-09-02T12:00:00Z"}, headers=auth(token))
    assert entry()["applied_at"].startswith("2026-09-02")
    client.patch(f"/me/saved/{job}", json={"notes": "Referral from Priya"}, headers=auth(token))
    assert entry()["applied_at"].startswith("2026-09-02")  # left out: kept
    client.patch(f"/me/saved/{job}", json={"applied_at": None}, headers=auth(token))
    assert entry()["applied_at"] is None


def test_export_and_delete_account(client):
    token = signup(client)["token"]
    client.post("/me/saved", json={"job_ids": job_ids(client)[:1]}, headers=auth(token))
    client.post(
        "/reports", json={"category": "site_bug", "message": "The button is broken"}, headers=auth(token)
    )
    client.post(f"/me/applications/{job_ids(client)[0]}", json={}, headers=auth(token))
    export = client.get("/me/export", headers=auth(token)).json()
    assert export["account"]["email"] == "sam@example.com"
    assert len(export["saved_jobs"]) == 1 and len(export["reports"]) == 1
    assert export["saved_jobs"][0]["status"] == "applied" and export["saved_jobs"][0]["applied_at"]
    assert [e["status"] for e in export["application_history"]] == ["applied"]

    assert (
        client.request("DELETE", "/me", json={"password": "wrong password"}, headers=auth(token)).status_code
        == 400
    )
    assert (
        client.request("DELETE", "/me", json={"password": PASSWORD}, headers=auth(token)).status_code == 204
    )
    assert client.get("/me", headers=auth(token)).status_code == 401
    with db.connect(DSN) as conn:
        assert conn.execute("SELECT count(*) FROM users").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM application_events").fetchone()[0] == 0
        # the report stays for the team, without the person's email
        assert conn.execute("SELECT user_id, email FROM reports").fetchone() == (None, None)


def test_login_is_rate_limited(client):
    signup(client)
    for _ in range(10):
        client.post("/auth/login", json={"email": "sam@example.com", "password": "wrong password!"})
    blocked = client.post("/auth/login", json={"email": "sam@example.com", "password": PASSWORD})
    assert blocked.status_code == 429 and "Retry-After" in blocked.headers


def test_reports_and_events(client):
    report = client.post(
        "/reports",
        json={
            "category": "wrong_job_info",
            "message": "This job is closed on their site",
            "job_id": job_ids(client)[0],
            "page": "/jobs/1",
            "email": "me@example.com",
        },
    )
    assert report.status_code == 201
    assert client.post("/reports", json={"category": "nonsense", "message": "hi there"}).status_code == 422

    headers = {"user-agent": "Mozilla/5.0 Test"}
    assert (
        client.post(
            "/events",
            json={"kind": "pageview", "path": "/jobs?q=x", "referrer": "https://google.com/s"},
            headers=headers,
        ).status_code
        == 204
    )
    assert (
        client.post(
            "/events", json={"kind": "pageview", "path": "/"}, headers={"user-agent": "Googlebot/2.1"}
        ).status_code
        == 204
    )
    client.post(
        "/events",
        json={"kind": "error", "path": "/jobs/5", "message": "boom", "digest": "123"},
        headers=headers,
    )
    with db.connect(DSN) as conn:
        rows = conn.execute("SELECT kind, path, referrer FROM events ORDER BY id").fetchall()
    assert rows == [("pageview", "/jobs", "google.com"), ("error", "/jobs/5", None)]  # the bot isn't counted


def test_admin_dashboard_needs_an_admin(client):
    token = signup(client)["token"]
    assert client.get("/admin/overview", headers=auth(token)).status_code == 403
    with db.connect(DSN) as conn:
        assert store.set_role(conn, "sam@example.com", "admin")
        conn.commit()
    client.post(
        "/events", json={"kind": "pageview", "path": "/jobs/12"}, headers={"user-agent": "Mozilla/5.0"}
    )
    client.post("/reports", json={"category": "site_bug", "message": "Filters reset"})

    overview = client.get("/admin/overview", headers=auth(token)).json()
    assert overview["users_total"] == 1 and overview["reports_open"] == 1
    assert overview["pageviews_today"] == 1 and overview["jobs_active"] == 2
    daily = client.get("/admin/daily", params={"days": 7}, headers=auth(token)).json()
    assert len(daily) == 7 and daily[-1]["signups"] == 1
    assert client.get("/admin/top-pages", headers=auth(token)).json() == [{"path": "/jobs/:id", "views": 1}]
    assert client.get("/admin/users", params={"q": "sam"}, headers=auth(token)).json()["total"] == 1

    report = client.get("/admin/reports", headers=auth(token)).json()[0]
    updated = client.patch(
        f"/admin/reports/{report['id']}",
        json={"status": "resolved", "admin_note": "Fixed"},
        headers=auth(token),
    )
    assert updated.json()["status"] == "resolved" and updated.json()["resolved_at"] is not None
    assert client.get("/admin/runs", headers=auth(token)).status_code == 200
    assert client.get("/admin/errors", headers=auth(token)).json() == []


def test_not_interested_and_training_consent_become_labels_only_with_consent(client):
    from tracker.resume.feedback import feedback_labels

    token = signup(client)["token"]
    other = signup(client, email="kim@example.com")["token"]
    first, second = job_ids(client)
    # "not interested", with a reason; repeating it just updates the reason
    assert client.put(
        f"/me/not-interested/{first}", json={"reason": "level"}, headers=auth(token)
    ).json() == [first]
    assert client.put(f"/me/not-interested/{first}", json={"reason": "role"}, headers=auth(token)).json() == [
        first
    ]
    assert (
        client.put(f"/me/not-interested/{first}", json={"reason": "salary"}, headers=auth(token)).status_code
        == 422
    )
    assert client.put("/me/not-interested/999999", json={}, headers=auth(token)).status_code == 404
    assert client.get("/me/not-interested/ids", headers=auth(other)).json() == []  # private to each person
    client.post("/me/saved", json={"job_ids": [second]}, headers=auth(token))
    client.post(f"/me/applications/{second}", json={"source": "tracker"}, headers=auth(token))

    with db.connect(DSN) as conn:
        assert feedback_labels(conn) == []  # no consent, no labels

    consent = client.get("/me/training-consent", headers=auth(token)).json()
    assert consent["given"] is False and consent["text"] and consent["current_version"]
    given = client.put("/me/training-consent", json={"given": True}, headers=auth(token)).json()
    assert given["given"] is True and given["version"] == given["current_version"] and given["given_at"]
    with db.connect(DSN) as conn:
        labels = {(lab.job_id, lab.fit, lab.signal) for lab in feedback_labels(conn)}
    assert labels == {(first, "weak", "not_interested"), (second, "strong", "applied")}

    exported = client.get("/me/export", headers=auth(token)).json()
    assert [row["job_id"] for row in exported["not_interested"]] == [first]
    assert exported["not_interested"][0]["reason"] == "role" and len(exported["training_consent"]) == 1

    client.put("/me/training-consent", json={"given": False}, headers=auth(token))  # withdrawn: no more use
    with db.connect(DSN) as conn:
        assert feedback_labels(conn) == []
    assert client.delete(f"/me/not-interested/{first}", headers=auth(token)).json() == []
    assert client.get("/me/not-interested/ids").status_code == 401
