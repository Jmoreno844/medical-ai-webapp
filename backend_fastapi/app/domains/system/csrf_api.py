from fastapi import APIRouter, Depends, Response

from app.core.config import Settings, get_settings
from app.core.security import generate_csrf_token

router = APIRouter()


@router.get("/csrf")
async def csrf(response: Response, settings: Settings = Depends(get_settings)) -> dict:
    token = generate_csrf_token()
    response.set_cookie(
        settings.csrf_cookie_name,
        token,
        httponly=False,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
        max_age=settings.refresh_token_days * 24 * 60 * 60,
    )
    return {"csrfToken": token}

