from ninja import Schema
from typing import Optional


class UserRegistrationIn(Schema):
    email: str
    password: str
    name: str
    last_name: str


class UserRegistrationOut(Schema):
    id: int
    email: str
    name: str
    last_name: str
    role: str

    class Config:
        from_attributes = True


class UserLoginIn(Schema):
    email: str
    password: str


class AuthTokenOut(Schema):
    token: str


class UserUpdateIn(Schema):
    name: Optional[str] = None
    last_name: Optional[str] = None
    role: Optional[str] = None


class UserProfileOut(Schema):
    id: int
    email: str
    name: str
    last_name: str
    role: str

    class Config:
        from_attributes = True
