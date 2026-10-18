"""Google and GitHub sign-in. The providers are faked: tests never reach them."""

import os

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from tests.conftest import reset_database  # noqa: E402
from tracker import db  # noqa: E402
from tracker.accounts import oauth  # noqa: E402
from tracker.api import create_app  # noqa: E402
from tracker.api.deps import limiter  # noqa: E402

DSN = os.environ.get("TEST_DATABASE_URL")
SITE = "https://ghostless.example"
VERIFIER = "v" * 43


def callback(provider: str) -> str:
    return f"{SITE}/api/auth/oauth/{provider}/callback"


# ---------- the provider module (no database) ----------


def test_providers_are_off_until_configured(monkeypatch):
    for name in ("GOOGLE", "GITHUB"):
        monkeypatch.delenv(f"{name}_CLIENT_ID", raising=False)
        monkeypatch.delenv(f"{name}_CLIENT_SECRET", raising=False)
    assert oauth.enabled() == {"google": False, "github": False}
    monkeypatch.setenv("GITHUB_CLIENT_ID", "id")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "secret")
    assert oauth.enabled() == {"google": False, "github": True}
    with pytest.raises(oauth.OAuthError):
        oauth.get_provider("google")


def test_authorize_url_carries_state_and_pkce(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-123")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "s")
    url = oauth.authorize_url("google", callback("google"), "state-abcdefghijklmnop", "c" * 43)
    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    for part in (
        "client_id=client-123",
        "state=state-abcdefghijklmnop",
        "code_challenge_method=S256",
        "scope=openid+email+profile",
    ):
        assert part in url


def test_github_identity_uses_a_verified_email(monkeypatch):
    responses = {
        "https://api.github.com/user": {"id": 42, "login": "octo", "name": None},
        "https://api.github.com/user/emails": [
            {"email": "old@example.com", "verified": False, "primary": True},
            {"email": "octo@example.com", "verified": True, "primary": False},
        ],
    }
    monkeypatch.setattr(oauth, "_get", lambda url, token: responses[url])
    identity = oauth._github_identity("token")
    assert (identity.subject, identity.email, identity.name) == ("42", "octo@example.com", "octo")

    responses["https://api.github.com/user/emails"] = [{"email": "x@example.com", "verified": False}]
    with pytest.raises(oauth.OAuthError, match="no verified email"):
        oauth._github_identity("token")


# ---------- the API (needs a database) ----------

needs_db = pytest.mark.skipif(not DSN, reason="TEST_DATABASE_URL not set")


@pytest.fixture
def client(monkeypatch):
    if not DSN:
        pytest.skip("TEST_DATABASE_URL not set")
    for name in ("GOOGLE", "GITHUB"):
        monkeypatch.setenv(f"{name}_CLIENT_ID", f"{name.lower()}-id")
        monkeypatch.setenv(f"{name}_CLIENT_SECRET", "secret")
    monkeypatch.setenv("GHOSTLESS_SITE_URL", SITE)
    with db.connect(DSN) as conn:
        reset_database(conn)
        db.apply_schema(conn)
    limiter.reset()
    with TestClient(create_app(DSN)) as c:
        yield c


def fake_identity(
    monkeypatch, provider="google", subject="g-1", email="sam@example.com", verified=True, name="Sam"
):
    def exchange(name, code, redirect_uri, code_verifier):
        assert (name, code, code_verifier) == (provider, "the-code", VERIFIER)
        return oauth.Identity(provider, subject, email, verified, name)

    monkeypatch.setattr(oauth, "exchange", exchange)


def finish(client, provider="google", token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post(
        f"/auth/oauth/{provider}",
        json={"code": "the-code", "redirect_uri": callback(provider), "code_verifier": VERIFIER},
        headers=headers,
    )


@needs_db
def test_first_google_sign_in_creates_a_confirmed_account_without_password(client, monkeypatch):
    fake_identity(monkeypatch)
    response = finish(client)
    assert response.status_code == 200, response.text
    session = response.json()
    assert session["user"]["email"] == "sam@example.com" and session["user"]["email_verified"]

    me = client.get("/me", headers={"Authorization": f"Bearer {session['token']}"}).json()
    assert me["has_password"] is False and me["sign_in_providers"] == ["google"]

    # signing in again finds the same account
    again = finish(client).json()
    assert again["user"]["id"] == session["user"]["id"]
    # and a password sign-in can't get in, since there is no password
    login = client.post("/auth/login", json={"email": "sam@example.com", "password": "anything at all"})
    assert login.status_code == 401


@needs_db
def test_google_sign_in_joins_an_existing_account_with_the_same_email(client, monkeypatch):
    signup = client.post(
        "/auth/signup", json={"email": "Sam@Example.com", "password": "correct horse battery"}
    )
    user_id = signup.json()["user"]["id"]
    fake_identity(monkeypatch, email="sam@example.com")
    session = finish(client).json()
    assert session["user"]["id"] == user_id
    assert session["user"]["email_verified"] is True  # Google confirmed the address


@needs_db
def test_unverified_provider_email_is_refused(client, monkeypatch):
    fake_identity(monkeypatch, verified=False)
    response = finish(client)
    assert response.status_code == 400 and "isn't verified" in response.json()["detail"]


@needs_db
def test_callback_must_be_this_sites(client, monkeypatch):
    fake_identity(monkeypatch)
    bad = client.post(
        "/auth/oauth/google",
        json={"code": "the-code", "redirect_uri": "https://evil.example/cb", "code_verifier": VERIFIER},
    )
    assert bad.status_code == 400
    url = client.get(
        "/auth/oauth/google/authorize",
        params={"redirect_uri": callback("google"), "state": "s" * 20, "code_challenge": "c" * 43},
    )
    assert url.status_code == 200 and url.json()["url"].startswith("https://accounts.google.com/")
    assert (
        client.get(
            "/auth/oauth/google/authorize",
            params={"redirect_uri": "https://evil.example/cb", "state": "s" * 20, "code_challenge": "c" * 43},
        ).status_code
        == 400
    )


@needs_db
def test_link_github_then_unlink_rules(client, monkeypatch):
    fake_identity(monkeypatch)
    token = finish(client).json()["token"]
    auth = {"Authorization": f"Bearer {token}"}

    # signed in: GitHub is added to the same account, even with another email
    fake_identity(monkeypatch, provider="github", subject="gh-9", email="sam@users.github.example")
    linked = finish(client, "github", token=token)
    assert linked.status_code == 200, linked.text
    assert client.get("/me", headers=auth).json()["sign_in_providers"] == ["github", "google"]

    # one sign-in method must always remain
    assert client.delete("/me/oauth/google", headers=auth).status_code == 200
    assert client.delete("/me/oauth/github", headers=auth).status_code == 400

    # setting a first password needs no current password, and then unlinking is allowed
    assert (
        client.post("/me/password", json={"new_password": "a new long password"}, headers=auth).status_code
        == 200
    )
    assert client.delete("/me/oauth/github", headers=auth).status_code == 200
    me = client.get("/me", headers=auth).json()
    assert me["has_password"] is True and me["sign_in_providers"] == []


@needs_db
def test_an_identity_belongs_to_one_account(client, monkeypatch):
    fake_identity(monkeypatch, subject="g-1", email="first@example.com")
    finish(client)
    other = client.post(
        "/auth/signup", json={"email": "second@example.com", "password": "correct horse battery"}
    )
    fake_identity(monkeypatch, subject="g-1", email="first@example.com")
    response = finish(client, token=other.json()["token"])
    assert response.status_code == 409


@needs_db
def test_password_less_account_can_be_deleted(client, monkeypatch):
    fake_identity(monkeypatch)
    token = finish(client).json()["token"]
    auth = {"Authorization": f"Bearer {token}"}
    assert client.request("DELETE", "/me", json={}, headers=auth).status_code == 204
    assert client.get("/me", headers=auth).status_code == 401


def test_an_unreachable_provider_is_a_friendly_error(monkeypatch):
    import requests

    def down(*args, **kwargs):
        raise requests.ConnectionError("no route")

    monkeypatch.setenv("GOOGLE_CLIENT_ID", "id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret")
    monkeypatch.setattr(requests, "post", down)
    with pytest.raises(oauth.OAuthError, match="Couldn't reach"):
        oauth.exchange("google", "code", callback("google"), VERIFIER)
