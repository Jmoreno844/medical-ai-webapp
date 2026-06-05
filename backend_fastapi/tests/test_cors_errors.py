from fastapi.testclient import TestClient

from app.main import app, fastapi_app


def test_unhandled_exceptions_keep_cors_headers_for_allowed_origin() -> None:
    @fastapi_app.get("/__test_unhandled_cors")
    async def boom() -> None:
        raise RuntimeError("boom")

    response = TestClient(app, raise_server_exceptions=False).get(
        "/__test_unhandled_cors",
        headers={"Origin": "http://localhost:3000"},
    )

    assert response.status_code == 500
    assert response.json()["error_code"] == "RuntimeError"
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
