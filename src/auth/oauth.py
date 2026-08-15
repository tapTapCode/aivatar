from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
import jwt

from src.api.config import Settings
from src.auth.models import OAuthState
from src.auth.repository import AuthRepository
from src.auth.security import normalize_email, pkce_challenge, random_token, safe_next_path

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
APPLE_AUTH_URL = "https://appleid.apple.com/auth/authorize"
APPLE_TOKEN_URL = "https://appleid.apple.com/auth/token"
APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"


@dataclass(frozen=True)
class OAuthProfile:
    provider: str
    subject: str
    email: str
    display_name: str


class OAuthService:
    def __init__(self, settings: Settings, repository: AuthRepository) -> None:
        self.settings = settings
        self.repository = repository

    def enabled(self, provider: str) -> bool:
        if provider == "google":
            return bool(
                self.settings.google_oauth_client_id
                and self.settings.google_oauth_client_secret
            )
        if provider == "apple":
            if not self.settings.apple_sso_enabled:
                return False
            return all(
                (
                    self.settings.apple_client_id,
                    self.settings.apple_team_id,
                    self.settings.apple_key_id,
                    self.settings.apple_private_key,
                )
            )
        return False

    def public_origin(self) -> str:
        return (self.settings.auth_callback_url or self.settings.app_base_url).rstrip("/")

    def callback_url(self, provider: str) -> str:
        return f"{self.public_origin()}/v1/auth/oauth/{provider}/callback"

    @staticmethod
    def apple_display_name(user_json: str, fallback: str) -> str:
        if not user_json.strip():
            return fallback
        try:
            payload = json.loads(user_json)
        except json.JSONDecodeError:
            return fallback
        name = payload.get("name") if isinstance(payload, dict) else None
        if not isinstance(name, dict):
            return fallback
        combined = " ".join(
            part.strip()
            for part in (name.get("firstName"), name.get("lastName"))
            if isinstance(part, str) and part.strip()
        )
        return combined or fallback

    @staticmethod
    def apple_nonce_matches(claimed: object, raw: str) -> bool:
        digest = hashlib.sha256(raw.encode()).hexdigest()
        return claimed in {raw, digest}

    async def authorization_url(self, provider: str, next_path: str | None) -> str:
        if provider == "apple" and not self.settings.apple_sso_enabled:
            raise ValueError("Apple sign-in is paused.")
        if not self.enabled(provider):
            raise ValueError(f"{provider.title()} sign-in is not configured.")
        nonce = random_token()
        verifier = random_token(48)
        bundle = await self.repository.create_oauth_state(
            provider,
            nonce=nonce,
            code_verifier=verifier,
            next_path=safe_next_path(next_path),
        )
        if provider == "google":
            params = {
                "client_id": self.settings.google_oauth_client_id or "",
                "redirect_uri": self.callback_url(provider),
                "response_type": "code",
                "scope": "openid email profile",
                "state": bundle.state,
                "nonce": nonce,
                "code_challenge": pkce_challenge(verifier),
                "code_challenge_method": "S256",
                "prompt": "select_account",
            }
            return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"
        params = {
            "client_id": self.settings.apple_client_id or "",
            "redirect_uri": self.callback_url(provider),
            "response_type": "code",
            "response_mode": "form_post",
            "scope": "name email",
            "state": bundle.state,
            "nonce": nonce,
        }
        return f"{APPLE_AUTH_URL}?{urlencode(params)}"

    async def exchange(self, provider: str, code: str, state: OAuthState) -> OAuthProfile:
        if provider == "google":
            return await self._exchange_google(code, state)
        if provider == "apple":
            return await self._exchange_apple(code, state)
        raise ValueError("Unsupported OAuth provider.")

    async def _exchange_google(self, code: str, state: OAuthState) -> OAuthProfile:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": self.settings.google_oauth_client_id,
                    "client_secret": self.settings.google_oauth_client_secret,
                    "code": code,
                    "code_verifier": state.code_verifier,
                    "grant_type": "authorization_code",
                    "redirect_uri": self.callback_url("google"),
                },
            )
            response.raise_for_status()
            id_token = response.json().get("id_token")
        claims = self._decode_id_token(
            id_token,
            jwks_url=GOOGLE_JWKS_URL,
            audience=self.settings.google_oauth_client_id or "",
            issuers={"https://accounts.google.com", "accounts.google.com"},
        )
        if claims.get("nonce") != state.nonce or claims.get("email_verified") is not True:
            raise ValueError("Google did not return a verified identity.")
        email = normalize_email(str(claims["email"]))
        return OAuthProfile(
            provider="google",
            subject=str(claims["sub"]),
            email=email,
            display_name=str(claims.get("name") or email.split("@", 1)[0]),
        )

    async def _exchange_apple(self, code: str, state: OAuthState) -> OAuthProfile:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                APPLE_TOKEN_URL,
                data={
                    "client_id": self.settings.apple_client_id,
                    "client_secret": self._apple_client_secret(),
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": self.callback_url("apple"),
                },
            )
            response.raise_for_status()
            id_token = response.json().get("id_token")
        claims = self._decode_id_token(
            id_token,
            jwks_url=APPLE_JWKS_URL,
            audience=self.settings.apple_client_id or "",
            issuers={"https://appleid.apple.com"},
        )
        if not self.apple_nonce_matches(claims.get("nonce"), state.nonce):
            raise ValueError("Apple identity nonce did not match.")
        email = normalize_email(str(claims["email"]))
        if str(claims.get("email_verified", "")).lower() not in {"true", "1"}:
            raise ValueError("Apple did not return a verified email.")
        return OAuthProfile(
            provider="apple",
            subject=str(claims["sub"]),
            email=email,
            display_name=email.split("@", 1)[0],
        )

    def _apple_client_secret(self) -> str:
        now = int(time.time())
        private_key = (self.settings.apple_private_key or "").replace("\\n", "\n")
        return jwt.encode(
            {
                "iss": self.settings.apple_team_id,
                "iat": now,
                "exp": now + 300,
                "aud": "https://appleid.apple.com",
                "sub": self.settings.apple_client_id,
            },
            private_key,
            algorithm="ES256",
            headers={"kid": self.settings.apple_key_id},
        )

    @staticmethod
    def _decode_id_token(
        encoded: str | None,
        *,
        jwks_url: str,
        audience: str,
        issuers: set[str],
    ) -> dict[str, object]:
        if not encoded:
            raise ValueError("Identity provider did not return an ID token.")
        signing_key = jwt.PyJWKClient(jwks_url).get_signing_key_from_jwt(encoded)
        claims = jwt.decode(
            encoded,
            signing_key.key,
            algorithms=["RS256"],
            audience=audience,
            options={"require": ["exp", "iat", "sub", "iss"]},
        )
        if claims.get("iss") not in issuers:
            raise ValueError("Identity provider issuer did not match.")
        return claims
