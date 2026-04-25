from pydantic import BaseModel


class SuccessResponse(BaseModel):
    success: bool
    message: str | None = None

