from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import update

from src.api.config import Settings
from src.auth.database import AuthDatabase, normalize_database_url
from src.auth.mailer import AuthMailer
from src.auth.models import AuthSession
from src.auth.oauth import OAuthService
from src.auth.repository import AuthRepository
from src.auth.router import AuthContext, create_auth_router


@pytest.fixture
def auth_app(tmp_path: Path) -> tuple[FastAPI, AuthRepository]:
    settings = Settings(
        app_env="development",
        app_base_url="http://testserver",
        allowed_origins="http://testserver",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'auth.db'}",
        auth_required=True,
        auth_auto_migrate=False,
        session_cookie_secure=False,
        superadmin_emails="admin@example.com",
        resend_api_key=None,
        google_oauth_client_id=None,
        google_oauth_client_secret=None,
        apple_client_id=None,
        apple_team_id=None,
        apple_key_id=None,
        apple_private_key=None,
    )
    database = AuthDatabase(settings.database_url)
    asyncio.run(database.create_schema())
    repository = AuthRepository(database, superadmin_emails={"admin@example.com"})
    mailer = AuthMailer(api_key=None, from_email="auth@example.com", base_url=settings.app_base_url)
    context = AuthContext(settings, repository)
    oauth = OAuthService(settings, repository)
    app = FastAPI()
    app.include_router(create_auth_router(settings, repository, mailer, oauth, context))

    @app.post("/protected")
    async def protected(request: Request) -> dict[str, str]:
        return {"owner_id": await context.owner_id(request)}

    return app, repository


def test_neon_database_url_is_compatible_with_asyncpg() -> None:
    normalized = normalize_database_url(
        "postgresql://user:pass@example.neon.tech/db"
        "?sslmode=require&channel_binding=require"
    )
    assert normalized.startswith("postgresql+asyncpg://")
    assert "ssl=require" in normalized
    assert "sslmode" not in normalized
    assert "channel_binding" not in normalized


def register_and_verify(client: TestClient, email: str = "creator@example.com") -> dict:
    registration = client.post(
        "/v1/auth/register",
        json={
            "email": email,
            "display_name": "Creative Owner",
            "password": "correct horse battery staple",
        },
    )
    assert registration.status_code == 201, registration.text
    debug_url = registration.json()["debug_url"]
    token = parse_qs(urlparse(debug_url).query)["token"][0]
    verification = client.post("/v1/auth/verify-email", json={"token": token})
    assert verification.status_code == 200, verification.text
    return verification.json()


def test_registration_verification_session_and_logout(
    auth_app: tuple[FastAPI, AuthRepository],
) -> None:
    app, repository = auth_app
    with TestClient(app) as client:
        verified = register_and_verify(client, "admin@example.com")
        assert verified["user"]["role"] == "superadmin"
        assert verified["user"]["email_verified"] is True
        stored = asyncio.run(repository.get_user_by_email("admin@example.com"))
        assert stored is not None
        assert stored.password_hash != "correct horse battery staple"
        assert stored.password_hash and stored.password_hash.startswith("$argon2")

        current = client.get("/v1/auth/session")
        assert current.status_code == 200
        csrf_token = current.json()["csrf_token"]
        protected = client.post("/protected", headers={"X-CSRF-Token": csrf_token})
        assert protected.status_code == 200
        assert protected.json()["owner_id"] == verified["user"]["id"]

        rejected = client.post("/protected")
        assert rejected.status_code == 403
        logged_out = client.post("/v1/auth/logout", headers={"X-CSRF-Token": csrf_token})
        assert logged_out.status_code == 204
        assert client.get("/v1/auth/session").status_code == 401


def test_login_recovery_and_single_use_reset(
    auth_app: tuple[FastAPI, AuthRepository],
) -> None:
    app, _repository = auth_app
    with TestClient(app) as client:
        register_and_verify(client)
        session = client.get("/v1/auth/session").json()
        client.post("/v1/auth/logout", headers={"X-CSRF-Token": session["csrf_token"]})

        bad_login = client.post(
            "/v1/auth/login",
            json={"email": "creator@example.com", "password": "wrong-password-value"},
        )
        assert bad_login.status_code == 401
        login = client.post(
            "/v1/auth/login",
            json={
                "email": "CREATOR@example.com",
                "password": "correct horse battery staple",
            },
        )
        assert login.status_code == 200

        recovery = client.post(
            "/v1/auth/forgot-password", json={"email": "creator@example.com"}
        )
        unknown = client.post(
            "/v1/auth/forgot-password", json={"email": "unknown@example.com"}
        )
        assert recovery.json()["message"] == unknown.json()["message"]
        token = parse_qs(urlparse(recovery.json()["debug_url"]).query)["token"][0]

        reset = client.post(
            "/v1/auth/reset-password",
            json={"token": token, "password": "a brand new secure password"},
        )
        assert reset.status_code == 200
        reused = client.post(
            "/v1/auth/reset-password",
            json={"token": token, "password": "another secure password"},
        )
        assert reused.status_code == 400


def test_origin_validation_and_oauth_state_failure(
    auth_app: tuple[FastAPI, AuthRepository],
) -> None:
    app, _repository = auth_app
    with TestClient(app, follow_redirects=False) as client:
        rejected = client.post(
            "/v1/auth/register",
            headers={"Origin": "https://attacker.example"},
            json={
                "email": "owner@example.com",
                "display_name": "Owner",
                "password": "correct horse battery staple",
            },
        )
        assert rejected.status_code == 403
        disabled = client.get("/v1/auth/oauth/google")
        assert disabled.status_code == 503
        invalid_state = client.get(
            "/v1/auth/oauth/google/callback?code=fake&state=fake"
        )
        assert invalid_state.status_code == 303
        assert "oauth_state" in invalid_state.headers["location"]


def test_profile_and_password_update_keep_the_current_session(
    auth_app: tuple[FastAPI, AuthRepository],
) -> None:
    app, _repository = auth_app
    with TestClient(app) as client:
        register_and_verify(client)
        session = client.get("/v1/auth/session").json()
        csrf = session["csrf_token"]
        updated = client.patch(
            "/v1/auth/profile",
            json={"display_name": "Studio Owner"},
            headers={"X-CSRF-Token": csrf},
        )
        assert updated.status_code == 200
        assert updated.json()["user"]["display_name"] == "Studio Owner"
        csrf = updated.json()["csrf_token"]
        changed = client.post(
            "/v1/auth/change-password",
            json={
                "current_password": "correct horse battery staple",
                "new_password": "a brand new studio password",
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert changed.status_code == 200
        still = client.get("/v1/auth/session")
        assert still.status_code == 200
        client.post("/v1/auth/logout", headers={"X-CSRF-Token": still.json()["csrf_token"]})
        login = client.post(
            "/v1/auth/login",
            json={
                "email": "creator@example.com",
                "password": "a brand new studio password",
            },
        )
        assert login.status_code == 200


def test_expired_session_and_account_isolation(
    auth_app: tuple[FastAPI, AuthRepository],
) -> None:
    app, repository = auth_app
    with TestClient(app) as first_client:
        first = register_and_verify(first_client, "first@example.com")
    with TestClient(app) as second_client:
        second = register_and_verify(second_client, "second@example.com")
    assert first["user"]["id"] != second["user"]["id"]

    bundle = asyncio.run(
        repository.create_session(first["user"]["id"], ttl_hours=1)
    )

    async def expire_session() -> None:
        async with repository.database.sessions() as session:
            await session.execute(
                update(AuthSession)
                .where(AuthSession.id == bundle.session.id)
                .values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
            )
            await session.commit()

    asyncio.run(expire_session())
    assert asyncio.run(repository.resolve_session(bundle.token)) is None


def test_missing_resend_returns_action_url_in_production(tmp_path: Path) -> None:
    settings = Settings(
        app_env="production",
        app_base_url="https://aivatar-staging.vercel.app",
        allowed_origins="https://aivatar-staging.vercel.app",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'auth.db'}",
        auth_required=True,
        auth_auto_migrate=False,
        session_cookie_secure=False,
        resend_api_key=None,
    )
    database = AuthDatabase(settings.database_url)
    asyncio.run(database.create_schema())
    repository = AuthRepository(database, superadmin_emails=set())
    mailer = AuthMailer(api_key=None, from_email="auth@example.com", base_url=settings.app_base_url)
    context = AuthContext(settings, repository)
    oauth = OAuthService(settings, repository)
    app = FastAPI()
    app.include_router(create_auth_router(settings, repository, mailer, oauth, context))
    with TestClient(app) as client:
        registration = client.post(
            "/v1/auth/register",
            json={
                "email": "staging@example.com",
                "display_name": "Staging User",
                "password": "correct horse battery staple",
            },
        )
        recovery = client.post(
            "/v1/auth/forgot-password", json={"email": "staging@example.com"}
        )
    assert registration.status_code == 201
    assert "/?view=verify&token=" in (registration.json()["debug_url"] or "")
    assert "/?view=reset&token=" in (recovery.json()["debug_url"] or "")

