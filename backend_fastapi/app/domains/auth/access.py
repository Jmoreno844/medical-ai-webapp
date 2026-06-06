from __future__ import annotations

from fastapi import HTTPException, status

from app.db.models import User

CLINICAL_ACCESS_DENIED_DETAIL = "Clinical access is not enabled for this account"


def require_clinical_access(user: User) -> None:
    if not user.clinical_access_enabled:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            CLINICAL_ACCESS_DENIED_DETAIL,
        )
