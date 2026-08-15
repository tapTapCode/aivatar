from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Form, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse

from src.api.config import Settings
from src.api.security import SlidingWindowRateLimiter
from src.auth.mailer import AuthMailer
from src.auth.models import AuthSession, User
from src.auth.oauth import OAuthService
from src.auth.repository import AuthRepository, SessionBundle
from src.auth.schemas import (
    AuthUserResponse,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    ResetPasswordRequest,
    SessionResponse,
    UpdateProfileRequest,
    VerifyEmailRequest,
)
from src.auth.security import (
    hash_password,
    normalize_email,
    safe_next_path,
    token_hash,
    validate_password,
    verify_password,
)


def public_user(user: User) -> AuthUserResponse:
    return AuthUserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        email_verified=user.email_verified,
    )


class AuthContext:
    def __init__(self, settings: Settings, repository: AuthRepository) -> None:
        self.settings = settings
        self.repository = repository
        self.allowed_origins = {
            value.strip().rstrip("/")
            for value in settings.allowed_origins.split(",")
            if value.strip()
        }
        self.allowed_origins.add(settings.app_base_url.rstrip("/"))

    async def resolve(self, request: Request) -> tuple[AuthSession, User] | None:
        raw = request.cookies.get(self.settings.session_cookie_name)
        if not raw:
            return None
        return await self.repository.resolve_session(raw)

    def validate_origin(self, request: Request) -> None:
        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") not in self.allowed_origins:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "request origin is not allowed")

    async def require_session(self, request: Request) -> tuple[AuthSession, User]:
        resolved = await self.resolve(request)
        if resolved is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required")
        return resolved

    async def require_csrf(self, request: Request) -> tuple[AuthSession, User]:
        self.validate_origin(request)
        auth_session, user = await self.require_session(request)
        supplied = request.headers.get("x-csrf-token", "")
        if not supplied or token_hash(supplied) != auth_session.csrf_hash:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "invalid CSRF token")
        return auth_session, user

    async def owner_id(self, request: Request) -> str:
        supplied_key = request.headers.get("x-api-key")
        if self.settings.api_key and supplied_key == self.settings.api_key:
            owner_id = request.headers.get("x-owner-id", "").strip()
            if not owner_id:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "x-owner-id is required")
            return owner_id
        resolved = await self.resolve(request)
        if resolved is not None:
            auth_session, user = resolved
            if request.method not in {"GET", "HEAD", "OPTIONS"}:
                self.validate_origin(request)
                supplied_csrf = request.headers.get("x-csrf-token", "")
                if not supplied_csrf or token_hash(supplied_csrf) != auth_session.csrf_hash:
                    raise HTTPException(status.HTTP_403_FORBIDDEN, "invalid CSRF token")
            return user.id
        if self.settings.auth_required:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required")
        owner_id = request.headers.get("x-owner-id", "local-development").strip()
        if not owner_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "x-owner-id must not be empty")
        return owner_id

    def set_session_cookie(self, response: Response, bundle: SessionBundle) -> None:
        response.set_cookie(
            self.settings.session_cookie_name,
            bundle.token,
            max_age=self.settings.session_ttl_hours * 3600,
            httponly=True,
            secure=self.settings.session_cookie_secure,
            samesite="lax",
            path="/",
        )

    def clear_session_cookie(self, response: Response) -> None:
        response.delete_cookie(
            self.settings.session_cookie_name,
            httponly=True,
            secure=self.settings.session_cookie_secure,
            samesite="lax",
            path="/",
        )

    async def new_session(self, request: Request, user: User) -> SessionBundle:
        return await self.repository.create_session(
            user.id,
            ttl_hours=self.settings.session_ttl_hours,
            user_agent=request.headers.get("user-agent", ""),
            ip_address=request.client.host if request.client else "",
        )


def create_auth_router(
    settings: Settings,
    repository: AuthRepository,
    mailer: AuthMailer,
    oauth: OAuthService,
    context: AuthContext,
) -> APIRouter:
    router = APIRouter(prefix="/v1/auth", tags=["authentication"])
    login_limiter = SlidingWindowRateLimiter(10)
    recovery_limiter = SlidingWindowRateLimiter(5)

    def rate_key(request: Request, suffix: str) -> str:
        address = request.client.host if request.client else "unknown"
        return f"{address}:{suffix}"

    @router.get("/config")
    async def auth_config() -> dict[str, object]:
        return {
            "providers": [
                {"name": "Google", "enabled": oauth.enabled("google")},
                {"name": "Apple", "enabled": oauth.enabled("apple")},
            ],
            "registration_enabled": True,
            "password_reset_enabled": True,
        }

    @router.post(
        "/register", response_model=MessageResponse, status_code=status.HTTP_201_CREATED
    )
    async def register(payload: RegisterRequest, request: Request) -> MessageResponse:
        context.validate_origin(request)
        login_limiter.check(rate_key(request, normalize_email(payload.email)))
        try:
            user = await repository.create_user(
                email=normalize_email(payload.email),
                display_name=payload.display_name,
                password_hash=hash_password(payload.password),
            )
        except ValueError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
        token = await repository.create_action_token(
            user.id, "verify_email", ttl_minutes=settings.auth_token_ttl_minutes
        )
        delivered = await mailer.send_verification(user.email, user.display_name, token)
        debug_url = None if delivered else mailer.action_url("verify_email", token)
        return MessageResponse(
            message="Check your email to verify your account.",
            debug_url=debug_url,
        )

    @router.post("/verify-email", response_model=SessionResponse)
    async def verify_email(
        payload: VerifyEmailRequest, request: Request, response: Response
    ) -> SessionResponse:
        context.validate_origin(request)
        user = await repository.consume_action_token(payload.token, "verify_email")
        if user is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "verification link is invalid")
        await repository.mark_email_verified(user.id)
        user.email_verified = True
        bundle = await context.new_session(request, user)
        context.set_session_cookie(response, bundle)
        return SessionResponse(user=public_user(user), csrf_token=bundle.csrf_token)

    @router.post("/login", response_model=SessionResponse)
    async def login(
        payload: LoginRequest, request: Request, response: Response
    ) -> SessionResponse:
        context.validate_origin(request)
        email = normalize_email(payload.email)
        login_limiter.check(rate_key(request, email))
        user = await repository.get_user_by_email(email)
        if user is None or not verify_password(user.password_hash, payload.password):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid email or password")
        if not user.email_verified:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "verify your email before signing in")
        bundle = await context.new_session(request, user)
        context.set_session_cookie(response, bundle)
        return SessionResponse(user=public_user(user), csrf_token=bundle.csrf_token)

    @router.get("/session", response_model=SessionResponse)
    async def session_status(request: Request) -> SessionResponse:
        auth_session, user = await context.require_session(request)
        csrf_token = await repository.rotate_csrf(auth_session.id)
        return SessionResponse(user=public_user(user), csrf_token=csrf_token)

    @router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
    async def logout(request: Request, response: Response) -> Response:
        await context.require_csrf(request)
        raw = request.cookies.get(settings.session_cookie_name, "")
        await repository.revoke_session(raw)
        context.clear_session_cookie(response)
        response.status_code = status.HTTP_204_NO_CONTENT
        return response

    @router.post("/forgot-password", response_model=MessageResponse)
    async def forgot_password(
        payload: ForgotPasswordRequest, request: Request
    ) -> MessageResponse:
        context.validate_origin(request)
        email = normalize_email(payload.email)
        recovery_limiter.check(rate_key(request, email))
        user = await repository.get_user_by_email(email)
        debug_url = None
        if user is not None:
            token = await repository.create_action_token(
                user.id, "reset_password", ttl_minutes=settings.auth_token_ttl_minutes
            )
            delivered = await mailer.send_password_reset(user.email, user.display_name, token)
            if not delivered:
                debug_url = mailer.action_url("reset_password", token)
        return MessageResponse(
            message="If an account exists, a reset link has been sent.",
            debug_url=debug_url,
        )

    @router.post("/reset-password", response_model=SessionResponse)
    async def reset_password(
        payload: ResetPasswordRequest, request: Request, response: Response
    ) -> SessionResponse:
        context.validate_origin(request)
        validate_password(payload.password)
        user = await repository.consume_action_token(payload.token, "reset_password")
        if user is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "reset link is invalid")
        await repository.set_password(user.id, hash_password(payload.password))
        bundle = await context.new_session(request, user)
        context.set_session_cookie(response, bundle)
        return SessionResponse(user=public_user(user), csrf_token=bundle.csrf_token)

    @router.patch("/profile", response_model=SessionResponse)
    async def update_profile(
        payload: UpdateProfileRequest, request: Request
    ) -> SessionResponse:
        auth_session, user = await context.require_csrf(request)
        updated = await repository.update_display_name(user.id, payload.display_name)
        if updated is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")
        csrf_token = await repository.rotate_csrf(auth_session.id)
        return SessionResponse(user=public_user(updated), csrf_token=csrf_token)

    @router.post("/change-password", response_model=MessageResponse)
    async def change_password(
        payload: ChangePasswordRequest, request: Request
    ) -> MessageResponse:
        _, user = await context.require_csrf(request)
        try:
            hashed = hash_password(payload.new_password)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
        if user.password_hash is None:
            await repository.set_password(user.id, hashed, revoke_sessions=False)
            return MessageResponse(message="Password added to this account.")
        if not verify_password(user.password_hash, payload.current_password):
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, "current password is incorrect"
            )
        await repository.set_password(user.id, hashed, revoke_sessions=False)
        return MessageResponse(message="Password updated.")

    @router.get("/oauth/{provider}")
    async def oauth_start(provider: str, next: str | None = None) -> RedirectResponse:
        if provider not in {"google", "apple"}:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown provider")
        try:
            url = await oauth.authorization_url(provider, next)
        except ValueError as exc:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
        return RedirectResponse(url)

    async def finish_oauth(
        provider: str,
        *,
        code: str,
        state: str,
        request: Request,
        display_name: str | None = None,
    ) -> RedirectResponse:
        state_record = await repository.consume_oauth_state(state, provider)
        if state_record is None:
            return RedirectResponse("/?" + urlencode({"error": "oauth_state"}), 303)
        try:
            profile = await oauth.exchange(provider, code, state_record)
            user = await repository.upsert_oauth_user(
                provider=profile.provider,
                subject=profile.subject,
                email=profile.email,
                display_name=display_name or profile.display_name,
            )
            bundle = await context.new_session(request, user)
        except Exception:
            return RedirectResponse("/?" + urlencode({"error": "oauth_failed"}), 303)
        response = RedirectResponse(safe_next_path(state_record.next_path), 303)
        context.set_session_cookie(response, bundle)
        return response

    def cancelled() -> RedirectResponse:
        return RedirectResponse("/?" + urlencode({"error": "oauth_cancelled"}), 303)

    @router.get("/oauth/google/callback")
    async def google_callback(
        request: Request, code: str = "", state: str = "", error: str = ""
    ) -> RedirectResponse:
        if error or not code or not state:
            return cancelled()
        return await finish_oauth("google", code=code, state=state, request=request)

    @router.get("/oauth/apple/callback")
    async def apple_callback_get(
        request: Request, code: str = "", state: str = "", error: str = ""
    ) -> RedirectResponse:
        if error or not code or not state:
            return cancelled()
        return await finish_oauth("apple", code=code, state=state, request=request)

    @router.post("/oauth/apple/callback")
    async def apple_callback(
        request: Request,
        code: str = Form(""),
        state: str = Form(""),
        user: str = Form(""),
        error: str = Form(""),
    ) -> RedirectResponse:
        if error or not code or not state:
            return cancelled()
        display_name = OAuthService.apple_display_name(user, "")
        return await finish_oauth(
            "apple",
            code=code,
            state=state,
            request=request,
            display_name=display_name or None,
        )

    return router
