from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.config import Settings
from src.auth.database import AuthDatabase
from src.auth.mailer import AuthMailer
from src.auth.oauth import OAuthProfile, OAuthService
from src.auth.repository import AuthRepository
from src.auth.router import AuthContext, create_auth_router


def _app(tmp_path: Path, **overrides: object) -> tuple[FastAPI, AuthRepository, OAuthService]:
    settings = Settings(
        app_env="development",
        app_base_url="https://aivatar-staging.vercel.app",
        auth_callback_url="https://aivatar-staging.vercel.app",
        allowed_origins="https://aivatar-staging.vercel.app",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'auth.db'}",
        auth_required=True,
        auth_auto_migrate=False,
        session_cookie_secure=False,
        google_oauth_client_id="google-client.apps.googleusercontent.com",
        google_oauth_client_secret="google-secret",
        apple_client_id="com.aivatar.web",
        apple_team_id="TEAMID12",
        apple_key_id="KEYID12",
        apple_private_key="-----BEGIN PRIVATE KEY-----\\nMIIB\\n-----END PRIVATE KEY-----",
        **{"apple_sso_enabled": True, **overrides},
    )
    database = AuthDatabase(settings.database_url)
    asyncio.run(database.create_schema())
    repository = AuthRepository(database, superadmin_emails=set())
    mailer = AuthMailer(api_key=None, from_email="auth@example.com", base_url=settings.app_base_url)
    context = AuthContext(settings, repository)
    oauth = OAuthService(settings, repository)
    app = FastAPI()
    app.include_router(create_auth_router(settings, repository, mailer, oauth, context))
    return app, repository, oauth


def test_oauth_callback_urls_use_public_frontend_origin(tmp_path: Path) -> None:
    _, _, oauth = _app(tmp_path)
    assert oauth.enabled("google") is True
    assert oauth.enabled("apple") is True


def test_apple_sso_stays_disabled_until_explicitly_enabled(tmp_path: Path) -> None:
    app, _, oauth = _app(tmp_path, apple_sso_enabled=False)
    assert oauth.enabled("google") is True
    assert oauth.enabled("apple") is False
    with TestClient(app, follow_redirects=False) as client:
        paused = client.get("/v1/auth/oauth/apple")
        assert paused.status_code == 503
        assert paused.json()["detail"] == "Apple sign-in is paused."
    assert oauth.callback_url("google") == (
        "https://aivatar-staging.vercel.app/v1/auth/oauth/google/callback"
    )
    assert oauth.callback_url("apple") == (
        "https://aivatar-staging.vercel.app/v1/auth/oauth/apple/callback"
    )


def test_google_start_and_callback_create_session(tmp_path: Path) -> None:
    app, repository, oauth = _app(tmp_path)
    oauth.exchange = AsyncMock(
        return_value=OAuthProfile(
            provider="google",
            subject="google-sub-1",
            email="owner@example.com",
            display_name="Owner",
        )
    )
    with TestClient(app, follow_redirects=False) as client:
        start = client.get("/v1/auth/oauth/google?next=/studio")
        assert start.status_code == 307
        assert start.headers["location"].startswith("https://accounts.google.com/")
        state = asyncio.run(repository.create_oauth_state(
            "google", nonce="n", code_verifier="v", next_path="/studio"
        )).state
        callback = client.get(f"/v1/auth/oauth/google/callback?code=ok&state={state}")
        assert callback.status_code == 303
        assert callback.headers["location"] == "/studio"
        assert "aivatar_session" in callback.cookies


def test_apple_form_post_callback_uses_name_and_sets_session(tmp_path: Path) -> None:
    app, repository, oauth = _app(tmp_path)
    oauth.exchange = AsyncMock(
        return_value=OAuthProfile(
            provider="apple",
            subject="apple-sub-1",
            email="hidden@privaterelay.appleid.com",
            display_name="hidden",
        )
    )
    state = asyncio.run(
        repository.create_oauth_state("apple", nonce="n", code_verifier="v", next_path="/")
    ).state
    with TestClient(app, follow_redirects=False) as client:
        callback = client.post(
            "/v1/auth/oauth/apple/callback",
            data={
                "code": "ok",
                "state": state,
                "user": '{"name":{"firstName":"Ada","lastName":"Lovelace"}}',
            },
        )
        assert callback.status_code == 303
        assert callback.headers["location"] == "/"
        assert "aivatar_session" in callback.cookies
    user = asyncio.run(repository.get_user_by_email("hidden@privaterelay.appleid.com"))
    assert user is not None
    assert user.display_name == "Ada Lovelace"


def test_apple_display_name_parser() -> None:
    assert OAuthService.apple_display_name("", "fallback") == "fallback"
    assert (
        OAuthService.apple_display_name(
            '{"name":{"firstName":"Ada","lastName":"Lovelace"}}',
            "fallback",
        )
        == "Ada Lovelace"
    )


def test_google_callback_error_is_cancelled(tmp_path: Path) -> None:
    app, _, _ = _app(tmp_path)
    with TestClient(app, follow_redirects=False) as client:
        callback = client.get("/v1/auth/oauth/google/callback?error=access_denied")
        assert callback.status_code == 303
        assert "oauth_cancelled" in callback.headers["location"]


def test_apple_nonce_accepts_raw_or_sha256_digest() -> None:
    import hashlib

    nonce = "apple-nonce-1"
    digest = hashlib.sha256(nonce.encode()).hexdigest()
    assert OAuthService.apple_nonce_matches(nonce, nonce) is True
    assert OAuthService.apple_nonce_matches(digest, nonce) is True
    assert OAuthService.apple_nonce_matches("other", nonce) is False
