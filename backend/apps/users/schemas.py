from ninja import Schema
from typing import Optional


class UserRegistrationIn(Schema):
    email: str
    password: str
    name: str
    lastName: str


class UserRegistrationOut(Schema):
    id: int
    email: str
    name: str
    lastName: str
    role: str

    class Config:
        from_attributes = True


class UserLoginIn(Schema):
    email: str
    password: str


class AuthTokenOut(Schema):
    token: str


class UserUpdateIn(Schema):
    name: Optional[str]
    lastName: Optional[str]
    role: Optional[str]


class UserProfileOut(Schema):
    id: int
    email: str
    name: str
    lastName: str
    role: str

    class Config:
        from_attributes = True
