from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.security import (
    clear_auth_cookies,
    create_token,
    decode_token,
    generate_csrf_token,
    password_session_fingerprint,
    set_auth_cookies,
    verify_csrf,
    verify_django_password,
)
from app.db.models import User
from app.db.session import get_db_session
from app.domains.auth.revocation import (
    is_token_id_revoked,
    revoke_token_id,
)


async def authenticate_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
) -> User | None:
    result = await session.execute(
        select(User).where(User.email == email, User.is_active.is_(True))
    )
    user = result.scalar_one_or_none()
    if not user or not verify_django_password(password, user.password):
        return None
    return user


def issue_browser_tokens(response: Response, user: User, settings: Settings) -> None:
    password_fingerprint = password_session_fingerprint(user.password, settings=settings)
    access_token, _ = create_token(
        subject=str(user.id),
        purpose="browser_access",
        audience=settings.browser_jwt_audience,
        expires_delta=timedelta(minutes=settings.access_token_minutes),
        extra_claims={
            "user_id": user.id,
            "role": user.role,
            "pwdv": password_fingerprint,
        },
        settings=settings,
    )
    refresh_token, _ = create_token(
        subject=str(user.id),
        purpose="browser_refresh",
        audience=settings.browser_jwt_audience,
        expires_delta=timedelta(days=settings.refresh_token_days),
        extra_claims={
            "user_id": user.id,
            "role": user.role,
            "pwdv": password_fingerprint,
        },
        settings=settings,
    )
    set_auth_cookies(
        response,
        access_token=access_token,
        refresh_token=refresh_token,
        csrf_token=generate_csrf_token(),
        settings=settings,
    )


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> User:
    token = request.cookies.get(settings.access_cookie_name)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")

    payload = decode_token(
        token,
        audience=settings.browser_jwt_audience,
        purpose="browser_access",
        settings=settings,
    )
    if await is_token_id_revoked(session, payload.get("jti")):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token revoked")

    result = await session.execute(
        select(User).where(User.id == int(payload["sub"]), User.is_active.is_(True))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    if payload.get("pwdv") != password_session_fingerprint(user.password, settings=settings):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
    return user


async def refresh_browser_session(
    request: Request,
    response: Response,
    session: AsyncSession,
    settings: Settings,
) -> User:
    verify_csrf(request, settings)
    token = request.cookies.get(settings.refresh_cookie_name)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token required")

    payload = decode_token(
        token,
        audience=settings.browser_jwt_audience,
        purpose="browser_refresh",
        settings=settings,
    )
    if await is_token_id_revoked(session, payload.get("jti")):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token revoked")

    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    await revoke_token_id(session, token_id=payload["jti"], expires_at=exp)

    result = await session.execute(
        select(User).where(User.id == int(payload["sub"]), User.is_active.is_(True))
    )
    user = result.scalar_one_or_none()
    if not user:
        clear_auth_cookies(response, settings)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    if payload.get("pwdv") != password_session_fingerprint(user.password, settings=settings):
        await revoke_token_id(session, token_id=payload["jti"], expires_at=exp)
        await session.commit()
        clear_auth_cookies(response, settings)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")

    issue_browser_tokens(response, user, settings)
    await session.commit()
    return user
