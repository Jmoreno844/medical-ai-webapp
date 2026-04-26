from pydantic import BaseModel


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str
    last_name: str


class ForgotPasswordRequest(BaseModel):
    email: str


class UserProfile(BaseModel):
    id: int
    email: str
    name: str
    last_name: str
    role: str


class AuthResponse(BaseModel):
    success: bool = True
    user: UserProfile


class LogoutResponse(BaseModel):
    success: bool = True


class MessageResponse(BaseModel):
    success: bool = True
    message: str

