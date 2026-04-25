from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import RevokedToken


async def revoke_token_id(
    session: AsyncSession,
    *,
    token_id: str,
    expires_at: datetime,
) -> None:
    if not token_id:
        return

    now = datetime.now(timezone.utc)
    await session.execute(delete(RevokedToken).where(RevokedToken.expires_at <= now))

    result = await session.execute(select(RevokedToken).where(RevokedToken.jti == token_id))
    revoked_token = result.scalar_one_or_none()
    if revoked_token:
        revoked_token.expires_at = expires_at
        revoked_token.revoked_at = now
        return

    session.add(
        RevokedToken(
            jti=token_id,
            expires_at=expires_at,
            revoked_at=now,
        )
    )


async def is_token_id_revoked(
    session: AsyncSession,
    token_id: str | None,
) -> bool:
    if not token_id:
        return True

    now = datetime.now(timezone.utc)
    result = await session.execute(
        select(RevokedToken.id).where(
            RevokedToken.jti == token_id,
            RevokedToken.expires_at > now,
        )
    )
    return result.scalar_one_or_none() is not None
