from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.security import clear_auth_cookies, decode_token, verify_csrf
from app.db.models import User
from app.db.session import get_db_session
from app.domains.audit.service import (
    actor_from_user,
    create_audit_user_session,
    end_audit_user_session,
    record_audit_event,
    record_security_event,
    user_capabilities,
)
from app.domains.auth.revocation import revoke_token_id
from app.domains.auth.service import (
    authenticate_user,
    get_current_user,
    issue_browser_tokens,
    register_doctor_user,
    refresh_browser_session,
)
from app.domains.auth.schemas import (
    AuthResponse,
    ForgotPasswordRequest,
    LoginRequest,
    LogoutResponse,
    MessageResponse,
    RegisterRequest,
    UserCapabilities,
    UserProfile,
)
from app.domains.auth.roles import normalize_user_role

router = APIRouter()


def _profile(user: User) -> UserProfile:
    return UserProfile(
        id=user.id,
        email=user.email,
        name=user.name,
        last_name=user.last_name,
        role=normalize_user_role(user.role),
        login_enabled=user.is_active,
        clinical_access_enabled=user.clinical_access_enabled,
        capabilities=UserCapabilities(**user_capabilities(user)),
    )


@router.post("/login", response_model=AuthResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> AuthResponse:
    user = await authenticate_user(session, email=payload.email, password=payload.password)
    if not user:
        await record_security_event(
            session,
            action="auth.login_failure",
            result="failure",
            request=request,
            settings=settings,
            actor=actor_from_user(None),
            error_code="InvalidCredentials",
            resource_type="auth_session",
        )
        await session.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")

    audit_session = await create_audit_user_session(
        session,
        user=user,
        request=request,
        settings=settings,
    )
    issue_browser_tokens(response, user, settings, session_id=audit_session.id)
    await record_security_event(
        session,
        action="auth.login_success",
        result="success",
        request=request,
        settings=settings,
        actor=actor_from_user(user),
        session_id=audit_session.id,
        resource_type="auth_session",
        resource_id=audit_session.id,
    )
    await session.commit()
    return AuthResponse(user=_profile(user))


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> AuthResponse:
    try:
        user = await register_doctor_user(
            session,
            email=payload.email,
            password=payload.password,
            name=payload.name,
            last_name=payload.last_name,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    await session.commit()
    await session.refresh(user)
    await record_audit_event(
        session,
        action="user.created",
        result="success",
        request=request,
        actor=actor_from_user(user),
        resource_type="user",
        resource_id=user.id,
    )
    audit_session = await create_audit_user_session(
        session,
        user=user,
        request=request,
        settings=settings,
    )
    issue_browser_tokens(response, user, settings, session_id=audit_session.id)
    await record_security_event(
        session,
        action="auth.login_success",
        result="success",
        request=request,
        settings=settings,
        actor=actor_from_user(user),
        session_id=audit_session.id,
        resource_type="auth_session",
        resource_id=audit_session.id,
    )
    await session.commit()
    return AuthResponse(user=_profile(user))


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    _payload: ForgotPasswordRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> MessageResponse:
    await record_security_event(
        session,
        action="auth.password_recovery_requested",
        result="success",
        request=request,
        settings=settings,
        actor=actor_from_user(None),
        resource_type="auth_session",
    )
    await session.commit()
    return MessageResponse(
        message=(
            "Si el correo existe en el sistema, recibirás instrucciones para "
            "restablecer tu contraseña."
        )
    )


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
    user: User = Depends(get_current_user),
) -> LogoutResponse:
    verify_csrf(request, settings)
    session_id: str | None = None
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
        if purpose == "browser_access":
            session_id = payload.get("sid")
        await revoke_token_id(
            session,
            token_id=payload["jti"],
            expires_at=datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
        )

    await end_audit_user_session(session, session_id=session_id)
    await record_security_event(
        session,
        action="auth.logout",
        result="success",
        request=request,
        settings=settings,
        actor=actor_from_user(user),
        session_id=session_id,
        resource_type="auth_session",
        resource_id=session_id,
    )
    await session.commit()
    clear_auth_cookies(response, settings)
    return LogoutResponse()


@router.get("/me", response_model=UserProfile)
async def me(user: User = Depends(get_current_user)) -> UserProfile:
    return _profile(user)
