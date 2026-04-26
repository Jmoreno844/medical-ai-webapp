import json

import pytest

from apps.users.models import User


@pytest.fixture
def test_user_data():
    return {
        "name": "Test",
        "last_name": "User",
        "email": "test@example.com",
        "password": "testpass123",
    }


@pytest.mark.django_db
def test_register_user(client, test_user_data):
    response = client.post(
        "/api/auth/register",
        data=json.dumps(test_user_data),
        content_type="application/json",
    )
    assert response.status_code == 201
    assert User.objects.filter(email=test_user_data["email"]).exists()


@pytest.mark.django_db
def test_register_duplicate_email(client, test_user_data):
    client.post(
        "/api/auth/register",
        data=json.dumps(test_user_data),
        content_type="application/json",
    )
    response = client.post(
        "/api/auth/register",
        data=json.dumps(test_user_data),
        content_type="application/json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_login(client, test_user_data):
    client.post(
        "/api/auth/register",
        data=json.dumps(test_user_data),
        content_type="application/json",
    )

    response = client.post(
        "/api/auth/login",
        data=json.dumps(
            {
                "email": test_user_data["email"],
                "password": test_user_data["password"],
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Successfully logged in"


@pytest.mark.django_db
def test_jwt_token(client, test_user_data):
    client.post(
        "/api/auth/register",
        data=json.dumps(test_user_data),
        content_type="application/json",
    )

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
