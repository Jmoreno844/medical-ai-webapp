from datetime import datetime, timedelta
import jwt
from django.conf import settings
from ninja.security import HttpBearer
from django.http import HttpRequest


def create_token(user):
    payload = {
        "user_id": user.id,
        "exp": datetime.utcnow() + timedelta(days=1),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


class SessionAuth(HttpBearer):
    def authenticate(self, request: HttpRequest, token: str = None):
        if request.user and request.user.is_authenticated:
            return request.user
        return None
