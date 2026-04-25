from pydantic import BaseModel


class SSETokenResponse(BaseModel):
    success: bool
    token: str | None = None
    error: str | None = None

