"""Account endpoints: sign-up, sign-in, email links, profile, settings,
saved jobs, data export and account deletion."""

from __future__ import annotations

import os
import re

from fastapi import APIRouter, HTTPException, Request, Response

from tracker.accounts import mailer, oauth, store
from tracker.accounts.security import password_problem
from tracker.api import events
from tracker.api.deps import Conn, CurrentUser, OptionalUser, bearer_token, client_ip, limiter
from tracker.api.schemas import (
    AuthorizeOut,
    EmailIn,
    LoginIn,
    Message,
    OAuthIn,
    OAuthProvider,
    PasswordChangeIn,
    PasswordIn,
    ProfileIn,
    Providers,
    ResetIn,
    SavedJob,
    SavedJobsIn,
    SavedUpdateIn,
    Session,
    Settings,
    SignupIn,
    TokenIn,
    User,
)

router = APIRouter(tags=["accounts"])

_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")


def public_user(row: dict) -> dict:
    return {
        "id": row["id"],
        "email": row["email"],
        "name": row["name"],
        "role": row["role"],
        "email_verified": row["email_verified_at"] is not None,
        "settings": Settings(
            **{k: v for k, v in (row["settings"] or {}).items() if k in Settings.model_fields}
        ),
        "created_at": row["created_at"],
    }


def _valid_email(email: str) -> str:
    email = store.normalize_email(email)
    if not _EMAIL.match(email):
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    return email


def _check_password(password: str, email: str = "") -> None:
    problem = password_problem(password, email)
    if problem:
        raise HTTPException(status_code=422, detail=problem)


# ---------- sign-up and sign-in ----------


@router.post("/auth/signup", response_model=Session, status_code=201, summary="Create an account")
def signup(body: SignupIn, request: Request, conn: Conn):
    ip = client_ip(request)
    limiter.check(f"signup:{ip}", 5, 3600)
    email = _valid_email(body.email)
    _check_password(body.password, email)
    try:
        with conn.transaction():
            user = store.create_user(conn, email, body.password, body.name)
            token = store.create_session(conn, user["id"], request.headers.get("user-agent"))
            verify = store.create_email_token(conn, user["id"], "verify")
    except store.EmailTaken:
        raise HTTPException(
            status_code=409, detail="An account with that email already exists. Try signing in."
        ) from None
    mailer.send_verification(email, verify)
    events.record(conn, "signup", user_id=user["id"])
    return {"token": token, "user": public_user(user)}


@router.post("/auth/login", response_model=Session, summary="Sign in")
def login(body: LoginIn, request: Request, conn: Conn):
    ip = client_ip(request)
    limiter.check(f"login-ip:{ip}", 20, 900)
    limiter.check(f"login-email:{store.normalize_email(body.email)}", 10, 900)
    user = store.authenticate(conn, body.email, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="That email and password don't match an account.")
    token = store.create_session(conn, user["id"], request.headers.get("user-agent"))
    events.record(conn, "login", user_id=user["id"])
    return {"token": token, "user": public_user(user)}


@router.post("/auth/logout", status_code=204, summary="Sign out of this device")
def logout(request: Request, conn: Conn):
    token = bearer_token(request)
    if token:
        store.end_session(conn, token)
    return Response(status_code=204)


@router.post("/auth/logout-everywhere", response_model=Message, summary="Sign out of every other device")
def logout_everywhere(request: Request, user: CurrentUser, conn: Conn):
    ended = store.end_all_sessions(conn, user["id"], keep_token=bearer_token(request))
    return {"detail": f"Signed out of {ended} other {'session' if ended == 1 else 'sessions'}."}


# ---------- email links ----------


@router.post("/auth/verify-email", response_model=User, summary="Confirm an email address")
def verify_email(body: TokenIn, conn: Conn):
    user_id = store.use_email_token(conn, body.token, "verify")
    if user_id is None:
        raise HTTPException(status_code=400, detail="This link has expired or was already used.")
    store.mark_verified(conn, user_id)
    return public_user(store.get_user(conn, user_id))


@router.post("/auth/resend-verification", response_model=Message, summary="Send the confirmation email again")
def resend_verification(user: CurrentUser, conn: Conn):
    if user["email_verified_at"]:
        return {"detail": "Your email is already confirmed."}
    limiter.check(f"verify:{user['id']}", 3, 3600)
    sent = mailer.send_verification(user["email"], store.create_email_token(conn, user["id"], "verify"))
    return {"detail": "Sent. Check your inbox." if sent else "Email isn't set up on this server yet."}


@router.post("/auth/forgot-password", response_model=Message, status_code=202, summary="Email a reset link")
def forgot_password(body: EmailIn, request: Request, conn: Conn):
    limiter.check(f"forgot:{client_ip(request)}", 5, 3600)
    user = store.find_user_by_email(conn, body.email)
    if user is not None:
        mailer.send_password_reset(user["email"], store.create_email_token(conn, user["id"], "reset"))
    # the same answer either way, so this can't reveal who has an account
    return {"detail": "If that email has an account, a reset link is on its way."}


@router.post("/auth/reset-password", response_model=Session, summary="Choose a new password")
def reset_password(body: ResetIn, request: Request, conn: Conn):
    limiter.check(f"reset:{client_ip(request)}", 10, 3600)
    with conn.transaction():
        user_id = store.use_email_token(conn, body.token, "reset")
        if user_id is None:
            raise HTTPException(
                status_code=400, detail="This link has expired or was already used. Ask for a new one."
            )
        user = store.get_user(conn, user_id)
        _check_password(body.password, user["email"])
        store.set_password(conn, user_id, body.password)
        store.end_all_sessions(conn, user_id)  # a reset signs out every device
        store.mark_verified(conn, user_id)  # they proved they read the inbox
        token = store.create_session(conn, user_id, request.headers.get("user-agent"))
    return {"token": token, "user": public_user(store.get_user(conn, user_id))}


# ---------- Google and GitHub ----------


def _expected_redirect(provider: str) -> str:
    site = os.environ.get("GHOSTLESS_SITE_URL", "http://localhost:3000").rstrip("/")
    return f"{site}/api/auth/oauth/{provider}/callback"


def _check_redirect(provider: str, redirect_uri: str) -> None:
    # only the website's own callback: a code must never be sent anywhere else
    if redirect_uri != _expected_redirect(provider):
        raise HTTPException(status_code=400, detail="That sign-in link isn't valid for this site.")


@router.get("/auth/providers", response_model=Providers, summary="Which Google and GitHub sign-ins are on")
def providers():
    return oauth.enabled()


@router.get(
    "/auth/oauth/{provider}/authorize",
    response_model=AuthorizeOut,
    summary="Where to send the visitor to sign in",
)
def oauth_authorize(provider: OAuthProvider, redirect_uri: str, state: str, code_challenge: str):
    _check_redirect(provider, redirect_uri)
    if not (16 <= len(state) <= 200) or not (43 <= len(code_challenge) <= 128):
        raise HTTPException(status_code=400, detail="That sign-in request isn't valid.")
    try:
        return {"url": oauth.authorize_url(provider, redirect_uri, state, code_challenge)}
    except oauth.OAuthError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.post(
    "/auth/oauth/{provider}",
    response_model=Session,
    summary="Finish signing in with Google or GitHub (links it instead when already signed in)",
)
def oauth_finish(provider: OAuthProvider, body: OAuthIn, request: Request, conn: Conn, viewer: OptionalUser):
    limiter.check(f"oauth:{client_ip(request)}", 20, 900)
    _check_redirect(provider, body.redirect_uri)
    try:
        identity = oauth.exchange(provider, body.code, body.redirect_uri, body.code_verifier)
    except oauth.OAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    if not identity.email_verified:
        raise HTTPException(
            status_code=400,
            detail=f"Your {oauth.PROVIDERS[provider].label} email address isn't verified yet.",
        )
    try:
        with conn.transaction():
            if viewer:  # signed in already: add this sign-in method to the account
                store.link_identity(conn, viewer["id"], provider, identity.subject, identity.email)
                user, created = store.get_user(conn, viewer["id"]), False
                token = bearer_token(request)
            else:
                user, created = store.user_for_identity(
                    conn, provider, identity.subject, identity.email, identity.name
                )
                token = store.create_session(conn, user["id"], request.headers.get("user-agent"))
    except store.IdentityInUse:
        raise HTTPException(
            status_code=409,
            detail=f"That {oauth.PROVIDERS[provider].label} account is already linked to a different Ghostless account.",
        ) from None
    events.record(conn, "signup" if created else "login", user_id=user["id"], detail={"via": provider})
    return {"token": token, "user": public_user(user)}


@router.delete("/me/oauth/{provider}", response_model=Message, summary="Unlink a Google or GitHub sign-in")
def oauth_unlink(provider: OAuthProvider, user: CurrentUser, conn: Conn):
    others = [p for p in store.linked_providers(conn, user["id"]) if p != provider]
    if not store.has_password(conn, user["id"]) and not others:
        raise HTTPException(
            status_code=400, detail="Set a password first, so you can still sign in after unlinking."
        )
    store.unlink_identity(conn, user["id"], provider)
    return {"detail": f"{oauth.PROVIDERS[provider].label} sign-in removed."}


# ---------- the signed-in user ----------


@router.get("/me", response_model=User, summary="The signed-in user")
def me(user: CurrentUser, conn: Conn):
    return {
        **public_user(user),
        "has_password": store.has_password(conn, user["id"]),
        "sign_in_providers": store.linked_providers(conn, user["id"]),
    }


@router.patch("/me", response_model=User, summary="Update your name")
def update_me(body: ProfileIn, user: CurrentUser, conn: Conn):
    return public_user(store.update_profile(conn, user["id"], body.name))


@router.put("/me/settings", response_model=User, summary="Save display and search settings")
def save_settings(body: Settings, user: CurrentUser, conn: Conn):
    return public_user(store.update_settings(conn, user["id"], body.model_dump()))


@router.post("/me/password", response_model=Message, summary="Change your password")
def change_password(body: PasswordChangeIn, request: Request, user: CurrentUser, conn: Conn):
    limiter.check(f"password:{user['id']}", 10, 3600)
    # accounts made with Google or GitHub can set a first password without one
    if store.has_password(conn, user["id"]) and not store.check_password(
        conn, user["id"], body.current_password
    ):
        raise HTTPException(status_code=400, detail="Your current password isn't right.")
    _check_password(body.new_password, user["email"])
    store.set_password(conn, user["id"], body.new_password)
    store.end_all_sessions(conn, user["id"], keep_token=bearer_token(request))
    return {"detail": "Password changed. Other devices have been signed out."}


@router.get("/me/export", summary="Download everything stored about you (JSON)")
def export(user: CurrentUser, conn: Conn):
    limiter.check(f"export:{user['id']}", 10, 3600)
    return store.export_user(conn, user["id"])


@router.delete("/me", status_code=204, summary="Delete your account and its data")
def delete_me(body: PasswordIn, user: CurrentUser, conn: Conn):
    if store.has_password(conn, user["id"]) and not store.check_password(conn, user["id"], body.password):
        raise HTTPException(status_code=400, detail="That password isn't right.")
    with conn.transaction():
        store.delete_user(conn, user["id"])
    return Response(status_code=204)


# ---------- saved jobs ----------


@router.get(
    "/me/saved", response_model=list[SavedJob], summary="Your saved jobs and where each application stands"
)
def saved(user: CurrentUser, conn: Conn):
    from tracker.api import queries

    entries = store.saved_entries(conn, user["id"])
    jobs = {j["id"]: j for j in queries.jobs_by_ids(conn, [e["job_id"] for e in entries])}
    return [{**e, "job": jobs[e["job_id"]]} for e in entries if e["job_id"] in jobs]


@router.get("/me/saved/ids", response_model=list[int], summary="Just the ids of your saved jobs")
def saved_ids(user: CurrentUser, conn: Conn):
    return store.saved_job_ids(conn, user["id"])


@router.patch("/me/saved/{job_id}", response_model=Message, summary="Update an application's status or notes")
def update_saved(job_id: int, body: SavedUpdateIn, user: CurrentUser, conn: Conn):
    if not store.update_saved(conn, user["id"], job_id, body.status, body.notes):
        raise HTTPException(status_code=404, detail="That job isn't in your saved jobs.")
    return {"detail": "Updated."}


@router.post(
    "/me/saved", response_model=list[int], summary="Save jobs (also merges jobs saved before signing in)"
)
def save(body: SavedJobsIn, user: CurrentUser, conn: Conn):
    store.save_jobs(conn, user["id"], body.job_ids)
    return store.saved_job_ids(conn, user["id"])


@router.delete("/me/saved/{job_id}", response_model=list[int], summary="Remove a saved job")
def unsave(job_id: int, user: CurrentUser, conn: Conn):
    store.unsave_job(conn, user["id"], job_id)
    return store.saved_job_ids(conn, user["id"])
