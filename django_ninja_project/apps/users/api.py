# api/api.py
from ninja import Router
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.hashers import make_password
from ninja.security import django_auth
from typing import List
from datetime import datetime, timedelta
import jwt
import os
from django.conf import settings
from django.middleware.csrf import get_token
import logging

logger = logging.getLogger(__name__)

from .models import User, UserRole
from .schemas import (
    UserRegistrationIn,
    UserRegistrationOut,
    UserLoginIn,
    AuthTokenOut,
    UserUpdateIn,
    UserProfileOut,
)

router = Router()


def create_token(user):
    expiration = datetime.utcnow() + timedelta(hours=1)
    secret_key = os.getenv("JWT_SECRET_KEY", settings.SECRET_KEY)
    payload = {
        "user_id": user.id,
        "exp": expiration,
    }
    return jwt.encode(payload, secret_key, algorithm="HS256")


@router.post("/registro", response={201: UserRegistrationOut, 400: dict})
def register_user(request, data: UserRegistrationIn):
    """Register a new user"""
    if User.objects.filter(email=data.email).exists():
        return 400, {"message": "Email already registered"}

    user = User.objects.create(
        email=data.email,
        password=make_password(data.password),
        name=data.name,
        lastName=data.lastName,
        role=UserRole.MEDICO,
    )
    return 201, user


@router.post("/login", response={200: dict, 401: dict})
def login_user(request, data: UserLoginIn):
    """
    Login user using session authentication

    Creates a server-side session and sets session cookie.
    """
    logger.info(f"Login attempt for email: {data.email}")
    user = authenticate(request, email=data.email, password=data.password)
    if user is None:
        logger.warning(f"Failed login attempt for email: {data.email}")
        return 401, {"message": "Invalid credentials"}

    login(request, user)
    # Configure session settings
    request.session.set_expiry(3600)  # 1 hour expiry
    logger.info(f"User logged in successfully: {user.id}")
    return 200, {"message": "Successfully logged in", "userId": user.id}


@router.post("/logout", response={200: dict})
def logout_user(request):
    """
    Logout the current user by invalidating their session
    """
    logout(request)
    return {"message": "Successfully logged out"}


@router.post("/jwt-token", response={200: AuthTokenOut, 401: dict})
def create_jwt_token(request, data: UserLoginIn):
    """Create JWT token for external services"""
    user = authenticate(request, email=data.email, password=data.password)
    if user is None:
        return 401, {"message": "Invalid credentials"}

    token = create_token(user)
    return 200, {"token": token}


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
    """
    Verify if the user's session is valid

    Returns:
        200: True if session is valid
        401: Error message if session is invalid or expired
    """
    logger.debug(
        f"Session check: authenticated={request.user.is_authenticated if hasattr(request, 'user') else 'No user'}"
    )
    logger.debug(f"Session ID: {request.session.session_key}")

    if request.user and request.user.is_authenticated:
        return 200, True
    return 401, {"message": "Session not validated"}


@router.get("/me/data", response={200: UserProfileOut, 401: dict})
def me_data(request):
    """
    Return user profile data if session is valid

    Returns:
        200: User profile data
        401: Error message if session is invalid
    """
    logger.debug(
        f"User data request: authenticated={request.user.is_authenticated if hasattr(request, 'user') else 'No user'}"
    )

    if request.user and request.user.is_authenticated:
        logger.info(f"Returning user data for ID: {request.user.id}")
        return 200, request.user
    return 401, {"message": "Session not validated"}


@router.get("/csrf-token", response={200: dict})
def get_csrf_token(request):
    """
    Get a CSRF token for use in forms and API requests

    This endpoint ensures CSRF protection for non-GET requests
    """
    csrf_token = get_token(request)
    return {"csrfToken": csrf_token}
