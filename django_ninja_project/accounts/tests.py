import pytest
from django.urls import reverse
from .models import User
import json


@pytest.fixture
def test_user_data():
    return {
        "name": "Test",
        "lastName": "User",
        "email": "test@example.com",
        "password": "testpass123",
    }


@pytest.mark.django_db
def test_register_user(client, test_user_data):
    response = client.post(
        "/api/auth/registro",
        data=json.dumps(test_user_data),
        content_type="application/json",
    )
    assert response.status_code == 201
    assert User.objects.filter(email=test_user_data["email"]).exists()


@pytest.mark.django_db
def test_register_duplicate_email(client, test_user_data):
    # First registration
    client.post(
        "/api/auth/registro",
        data=json.dumps(test_user_data),
        content_type="application/json",
    )
    # Second registration with same email
    response = client.post(
        "/api/auth/registro",  # Changed from /api/accounts/register
        data=json.dumps(test_user_data),
        content_type="application/json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_login(client, test_user_data):
    # Create user first
    client.post(
        "/api/auth/registro",  # Changed from /api/accounts/register
        data=json.dumps(test_user_data),
        content_type="application/json",
    )

    # Try to login
    response = client.post(
        "/api/auth/login",  # Changed from /api/accounts/login
        data=json.dumps(
            {
                "email": test_user_data["email"],
                "password": test_user_data["password"],
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert "token" in response.json()


@pytest.mark.django_db
def test_jwt_token(client, test_user_data):
    # Create user first
    client.post(
        "/api/auth/registro",  # Changed from /api/accounts/register
        data=json.dumps(test_user_data),
        content_type="application/json",
    )

    # Get JWT token
    response = client.post(
        "/api/auth/jwt-token",
        data=json.dumps(
            {
                "email": test_user_data["email"],
                "password": test_user_data["password"],
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert "token" in response.json()
