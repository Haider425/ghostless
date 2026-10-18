"""Sign in with Google or GitHub (OAuth 2.0 authorization code flow).

The website starts the flow: it creates a random `state` and a PKCE code
verifier, keeps them in a short-lived httpOnly cookie, and sends the visitor
to the provider. When the provider sends them back with a code, the website
checks the state and passes the code and verifier here. This module, which
alone holds the client secrets, exchanges the code and reads the person's
verified email address.

A provider is on when its client id and secret are set:
  GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
  GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlencode

import requests

TIMEOUT = 15


@dataclass(frozen=True)
class Provider:
    name: str
    label: str
    authorize_url: str
    token_url: str
    scope: str
    pkce: bool


PROVIDERS: dict[str, Provider] = {
    "google": Provider(
        name="google",
        label="Google",
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        scope="openid email profile",
        pkce=True,
    ),
    "github": Provider(
        name="github",
        label="GitHub",
        authorize_url="https://github.com/login/oauth/authorize",
        token_url="https://github.com/login/oauth/access_token",
        scope="read:user user:email",
        pkce=True,
    ),
}


class OAuthError(Exception):
    """Something the person should see, worded for them."""


@dataclass(frozen=True)
class Identity:
    provider: str
    subject: str  # the provider's stable id for the person; emails can change
    email: str
    email_verified: bool
    name: str | None


def _credentials(provider: str) -> tuple[str, str] | None:
    prefix = provider.upper()
    client_id = os.environ.get(f"{prefix}_CLIENT_ID")
    secret = os.environ.get(f"{prefix}_CLIENT_SECRET")
    return (client_id, secret) if client_id and secret else None


def enabled() -> dict[str, bool]:
    return {name: _credentials(name) is not None for name in PROVIDERS}


def get_provider(name: str) -> Provider:
    provider = PROVIDERS.get(name)
    if provider is None or _credentials(name) is None:
        raise OAuthError("That sign-in option isn't available.")
    return provider


def authorize_url(name: str, redirect_uri: str, state: str, code_challenge: str) -> str:
    provider = get_provider(name)
    client_id, _ = _credentials(name)  # type: ignore[misc]
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": provider.scope,
        "state": state,
    }
    if provider.pkce:
        params |= {"code_challenge": code_challenge, "code_challenge_method": "S256"}
    if name == "google":
        params["prompt"] = "select_account"  # let people with several Google accounts choose
    if name == "github":
        params["allow_signup"] = "true"
    return f"{provider.authorize_url}?{urlencode(params)}"


def _post(url: str, data: dict) -> dict:
    try:
        response = requests.post(url, data=data, headers={"Accept": "application/json"}, timeout=TIMEOUT)
    except requests.RequestException:
        raise OAuthError("Couldn't reach the sign-in provider. Please try again.") from None
    try:
        body = response.json()
    except ValueError:
        body = {}
    if not response.ok or "error" in body:
        raise OAuthError("The sign-in didn't go through. Please try again.")
    return body


def _get(url: str, token: str) -> dict | list:
    try:
        response = requests.get(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "User-Agent": "Ghostless",
            },
            timeout=TIMEOUT,
        )
    except requests.RequestException:
        raise OAuthError("Couldn't reach the sign-in provider. Please try again.") from None
    if not response.ok:
        raise OAuthError("Couldn't read your account details from the provider. Please try again.")
    return response.json()


def exchange(name: str, code: str, redirect_uri: str, code_verifier: str) -> Identity:
    """Trade the authorization code for the person's identity."""
    provider = get_provider(name)
    client_id, secret = _credentials(name)  # type: ignore[misc]
    token = _post(
        provider.token_url,
        {
            "client_id": client_id,
            "client_secret": secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "code_verifier": code_verifier,
        },
    ).get("access_token")
    if not token:
        raise OAuthError("The sign-in didn't go through. Please try again.")
    return _google_identity(token) if name == "google" else _github_identity(token)


def _google_identity(token: str) -> Identity:
    info = _get("https://openidconnect.googleapis.com/v1/userinfo", token)
    assert isinstance(info, dict)
    if not info.get("sub") or not info.get("email"):
        raise OAuthError("Google didn't share an email address, which Ghostless needs for your account.")
    return Identity(
        provider="google",
        subject=str(info["sub"]),
        email=str(info["email"]),
        email_verified=bool(info.get("email_verified")),
        name=info.get("name"),
    )


def _github_identity(token: str) -> Identity:
    user = _get("https://api.github.com/user", token)
    emails = _get("https://api.github.com/user/emails", token)
    assert isinstance(user, dict) and isinstance(emails, list)
    # the primary address if it's verified, otherwise any verified one
    verified = [e for e in emails if isinstance(e, dict) and e.get("verified") and e.get("email")]
    chosen = next((e for e in verified if e.get("primary")), verified[0] if verified else None)
    if not user.get("id") or chosen is None:
        raise OAuthError(
            "Your GitHub account has no verified email address. Verify one on GitHub, then try again."
        )
    return Identity(
        provider="github",
        subject=str(user["id"]),
        email=str(chosen["email"]),
        email_verified=True,
        name=user.get("name") or user.get("login"),
    )
