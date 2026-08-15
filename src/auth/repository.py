from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from src.auth.database import AuthDatabase
from src.auth.models import ActionToken, AuthSession, OAuthIdentity, OAuthState, User
from src.auth.security import random_token, token_hash


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class SessionBundle:
    session: AuthSession
    token: str
    csrf_token: str


@dataclass(frozen=True)
class OAuthStateBundle:
    record: OAuthState
    state: str


class AuthRepository:
    def __init__(self, database: AuthDatabase, *, superadmin_emails: set[str]) -> None:
        self.database = database
        self.superadmin_emails = {email.casefold() for email in superadmin_emails}

    async def get_user(self, user_id: str) -> User | None:
        async with self.database.sessions() as session:
            return await session.get(User, user_id)

    async def get_user_by_email(self, email: str) -> User | None:
        async with self.database.sessions() as session:
            return await session.scalar(select(User).where(User.email == email))

    async def create_user(
        self,
        *,
        email: str,
        display_name: str,
        password_hash: str | None,
        email_verified: bool = False,
    ) -> User:
        now = utc_now()
        user = User(
            id=str(uuid.uuid4()),
            email=email,
            display_name=display_name.strip()[:120] or email.split("@", 1)[0],
            password_hash=password_hash,
            email_verified=email_verified,
            role="superadmin" if email in self.superadmin_emails else "member",
            created_at=now,
            updated_at=now,
        )
        async with self.database.sessions() as session:
            session.add(user)
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise ValueError("An account with this email already exists.") from exc
            await session.refresh(user)
            return user

    async def mark_email_verified(self, user_id: str) -> None:
        async with self.database.sessions() as session:
            await session.execute(
                update(User)
                .where(User.id == user_id)
                .values(email_verified=True, updated_at=utc_now())
            )
            await session.commit()

    async def update_display_name(self, user_id: str, display_name: str) -> User | None:
        name = display_name.strip()[:120]
        if not name:
            raise ValueError("display name is required")
        now = utc_now()
        async with self.database.sessions() as session:
            await session.execute(
                update(User)
                .where(User.id == user_id)
                .values(display_name=name, updated_at=now)
            )
            await session.commit()
        return await self.get_user(user_id)

    async def set_password(
        self, user_id: str, password_hash: str, *, revoke_sessions: bool = True
    ) -> None:
        now = utc_now()
        async with self.database.sessions() as session:
            await session.execute(
                update(User)
                .where(User.id == user_id)
                .values(password_hash=password_hash, updated_at=now)
            )
            if revoke_sessions:
                await session.execute(
                    update(AuthSession)
                    .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
                    .values(revoked_at=now)
                )
            await session.commit()

    async def create_action_token(
        self, user_id: str, purpose: str, *, ttl_minutes: int
    ) -> str:
        raw = random_token()
        now = utc_now()
        record = ActionToken(
            id=str(uuid.uuid4()),
            user_id=user_id,
            purpose=purpose,
            token_hash=token_hash(raw),
            expires_at=now + timedelta(minutes=ttl_minutes),
            created_at=now,
        )
        async with self.database.sessions() as session:
            await session.execute(
                update(ActionToken)
                .where(
                    ActionToken.user_id == user_id,
                    ActionToken.purpose == purpose,
                    ActionToken.used_at.is_(None),
                )
                .values(used_at=now)
            )
            session.add(record)
            await session.commit()
        return raw

    async def consume_action_token(self, raw: str, purpose: str) -> User | None:
        now = utc_now()
        async with self.database.sessions() as session:
            record = await session.scalar(
                select(ActionToken).where(
                    ActionToken.token_hash == token_hash(raw),
                    ActionToken.purpose == purpose,
                    ActionToken.used_at.is_(None),
                    ActionToken.expires_at > now,
                )
            )
            if record is None:
                return None
            record.used_at = now
            user = await session.get(User, record.user_id)
            await session.commit()
            return user

    async def create_session(
        self,
        user_id: str,
        *,
        ttl_hours: int,
        user_agent: str = "",
        ip_address: str = "",
    ) -> SessionBundle:
        raw = random_token()
        csrf = random_token()
        now = utc_now()
        record = AuthSession(
            id=str(uuid.uuid4()),
            user_id=user_id,
            token_hash=token_hash(raw),
            csrf_hash=token_hash(csrf),
            expires_at=now + timedelta(hours=ttl_hours),
            created_at=now,
            last_seen_at=now,
            user_agent=user_agent[:500],
            ip_address=ip_address[:64],
        )
        async with self.database.sessions() as session:
            session.add(record)
            await session.commit()
            await session.refresh(record)
        return SessionBundle(record, raw, csrf)

    async def resolve_session(self, raw: str) -> tuple[AuthSession, User] | None:
        now = utc_now()
        async with self.database.sessions() as session:
            row = (
                await session.execute(
                    select(AuthSession, User)
                    .join(User, User.id == AuthSession.user_id)
                    .where(
                        AuthSession.token_hash == token_hash(raw),
                        AuthSession.revoked_at.is_(None),
                        AuthSession.expires_at > now,
                    )
                )
            ).one_or_none()
            if row is None:
                return None
            auth_session, user = row
            auth_session.last_seen_at = now
            await session.commit()
            return auth_session, user

    async def revoke_session(self, raw: str) -> None:
        async with self.database.sessions() as session:
            await session.execute(
                update(AuthSession)
                .where(AuthSession.token_hash == token_hash(raw))
                .values(revoked_at=utc_now())
            )
            await session.commit()

    async def rotate_csrf(self, session_id: str) -> str:
        raw = random_token()
        async with self.database.sessions() as session:
            await session.execute(
                update(AuthSession)
                .where(AuthSession.id == session_id, AuthSession.revoked_at.is_(None))
                .values(csrf_hash=token_hash(raw))
            )
            await session.commit()
        return raw

    async def create_oauth_state(
        self, provider: str, *, nonce: str, code_verifier: str, next_path: str
    ) -> OAuthStateBundle:
        state = random_token()
        now = utc_now()
        record = OAuthState(
            id=str(uuid.uuid4()),
            state_hash=token_hash(state),
            provider=provider,
            nonce=nonce,
            code_verifier=code_verifier,
            next_path=next_path,
            expires_at=now + timedelta(minutes=10),
            created_at=now,
        )
        async with self.database.sessions() as session:
            session.add(record)
            await session.commit()
        return OAuthStateBundle(record, state)

    async def consume_oauth_state(self, raw: str, provider: str) -> OAuthState | None:
        now = utc_now()
        async with self.database.sessions() as session:
            record = await session.scalar(
                select(OAuthState).where(
                    OAuthState.state_hash == token_hash(raw),
                    OAuthState.provider == provider,
                    OAuthState.used_at.is_(None),
                    OAuthState.expires_at > now,
                )
            )
            if record is None:
                return None
            record.used_at = now
            await session.commit()
            return record

    async def upsert_oauth_user(
        self,
        *,
        provider: str,
        subject: str,
        email: str,
        display_name: str,
    ) -> User:
        now = utc_now()
        async with self.database.sessions() as session:
            identity = await session.scalar(
                select(OAuthIdentity)
                .options(selectinload(OAuthIdentity.user))
                .where(
                    OAuthIdentity.provider == provider,
                    OAuthIdentity.provider_subject == subject,
                )
            )
            if identity is not None:
                return identity.user
            user = await session.scalar(select(User).where(User.email == email))
            if user is None:
                user = User(
                    id=str(uuid.uuid4()),
                    email=email,
                    display_name=display_name.strip()[:120] or email.split("@", 1)[0],
                    email_verified=True,
                    role="superadmin" if email in self.superadmin_emails else "member",
                    created_at=now,
                    updated_at=now,
                )
                session.add(user)
            else:
                user.email_verified = True
                user.updated_at = now
            session.add(
                OAuthIdentity(
                    id=str(uuid.uuid4()),
                    user=user,
                    provider=provider,
                    provider_subject=subject,
                    provider_email=email,
                    created_at=now,
                )
            )
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                identity = await session.scalar(
                    select(OAuthIdentity)
                    .options(selectinload(OAuthIdentity.user))
                    .where(
                        OAuthIdentity.provider == provider,
                        OAuthIdentity.provider_subject == subject,
                    )
                )
                if identity is None:
                    raise
                return identity.user
            await session.refresh(user)
            return user
