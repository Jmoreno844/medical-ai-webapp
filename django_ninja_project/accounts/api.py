# api/api.py
from django.urls import path
from ninja import Router
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.hashers import make_password
from ninja.security import django_auth
from typing import List
from datetime import datetime, timedelta
import jwt

from .models import User
from .schemas import (
    UserRegistrationIn,
    UserRegistrationOut,
    UserLoginIn,
    AuthTokenOut,
    UserUpdateIn,
    UserProfileOut,
)

router = Router()


@router.post("/registro", response={201: UserRegistrationOut, 400: dict})
def register_user(request, data: UserRegistrationIn):
    """Register a new user"""
    if User.objects.filter(email=data.email).exists():
        return 400, {"message": "Email already registered"}

    user = User.objects.create(
        username=data.email,
        email=data.email,
        password=make_password(data.password),
        name=data.name,
        lastName=data.lastName,
        role="medico",  # Force role as 'medico'
    )
    return 201, user


@router.post("/login", response={200: AuthTokenOut, 401: dict})
def login_user(request, data: UserLoginIn):
    """Login user and return session token"""
    user = authenticate(request, username=data.email, password=data.password)
    if user is None:
        return 401, {"message": "Invalid credentials"}

    login(request, user)
    return 200, {"token": "session-authenticated"}


@router.post("/jwt-token", response={200: AuthTokenOut, 401: dict})
def create_jwt_token(request, data: UserLoginIn):
    """Create JWT token for external services"""
    user = authenticate(request, username=data.email, password=data.password)
    if user is None:
        return 401, {"message": "Invalid credentials"}

    payload = {
        "user_id": user.id,
        "exp": datetime.utcnow() + timedelta(days=1),
        "iat": datetime.utcnow(),
    }
    token = jwt.encode(payload, "your-secret-key", algorithm="HS256")
    return {"token": token}


@router.get("/users", response=List[UserProfileOut], auth=django_auth)
def list_users(request):
    """List all users (requires authentication)"""
    return User.objects.all()


@router.get("/users/{user_id}", response=UserProfileOut, auth=django_auth)
def get_user(request, user_id: int):
    """Get user details by ID"""
    return User.objects.get(id=user_id)


@router.put("/users/{user_id}", response=UserProfileOut, auth=django_auth)
def update_user(request, user_id: int, data: UserUpdateIn):
    """Update user information"""
    user = User.objects.get(id=user_id)
    for field, value in data.dict(exclude_unset=True).items():
        setattr(user, field, value)
    user.save()
    return user


@router.delete("/users/{user_id}", auth=django_auth)
def delete_user(request, user_id: int):
    """Delete a user"""
    User.objects.get(id=user_id).delete()
    return {"success": True}


@router.get("/me", response={200: bool, 401: dict})
def me(request):
    """Return True if session validated, else False"""
    if request.user and request.user.is_authenticated:
        return True
    return 401, {"message": "Session not validated"}


@router.get("/me/data", response={200: UserProfileOut, 401: dict})
def me_data(request):
    """Return user profile data if session validated, else return error"""
    if request.user and request.user.is_authenticated:
        return request.user
    return 401, {"message": "Session not validated"}
