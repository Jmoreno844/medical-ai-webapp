from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.security import clear_auth_cookies, decode_token, verify_csrf
from app.db.models import User
from app.db.session import get_db_session
from app.domains.auth.revocation import revoke_token_id
from app.domains.auth.service import (
    authenticate_user,
    get_current_user,
    issue_browser_tokens,
    refresh_browser_session,
)
from app.domains.auth.schemas import (
    AuthResponse,
    LoginRequest,
    LogoutResponse,
    UserProfile,
)

router = APIRouter()


def _profile(user: User) -> UserProfile:
    return UserProfile(
        id=user.id,
        email=user.email,
        name=user.name,
        last_name=user.last_name,
        role=user.role,
    )


@router.post("/login", response_model=AuthResponse)
async def login(
    payload: LoginRequest,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> AuthResponse:
    user = await authenticate_user(session, email=payload.email, password=payload.password)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")

    issue_browser_tokens(response, user, settings)
    return AuthResponse(user=_profile(user))


@router.post("/refresh", response_model=AuthResponse)
async def refresh(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> AuthResponse:
    user = await refresh_browser_session(request, response, session, settings)
    return AuthResponse(user=_profile(user))


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> LogoutResponse:
    verify_csrf(request, settings)
    for cookie_name, purpose in (
        (settings.access_cookie_name, "browser_access"),
        (settings.refresh_cookie_name, "browser_refresh"),
    ):
        token = request.cookies.get(cookie_name)
        if not token:
            continue
        try:
            payload = decode_token(
                token,
                audience=settings.browser_jwt_audience,
                purpose=purpose,
                settings=settings,
            )
        except HTTPException:
            continue
        await revoke_token_id(
            session,
            token_id=payload["jti"],
            expires_at=datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
        )

    await session.commit()
    clear_auth_cookies(response, settings)
    return LogoutResponse()


@router.get("/me", response_model=UserProfile)
async def me(user: User = Depends(get_current_user)) -> UserProfile:
    return _profile(user)
