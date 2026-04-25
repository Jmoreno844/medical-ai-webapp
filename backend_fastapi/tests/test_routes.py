from fastapi.testclient import TestClient

from app.main import app


def test_app_usable_routes_are_registered() -> None:
    paths = {
        route.path
        for route in app.routes
        if getattr(route, "path", "").startswith("/api/v1")
    }

    expected_paths = {
        "/api/v1/csrf",
        "/api/v1/auth/login",
        "/api/v1/auth/me",
        "/api/v1/encounters",
        "/api/v1/encounters/{encounter_id}",
        "/api/v1/encounters/{encounter_id}/audio/upload-url",
        "/api/v1/encounters/{encounter_id}/audio/exists",
        "/api/v1/encounters/{encounter_id}/audio",
        "/api/v1/documents",
        "/api/v1/documents/encounter/{encounter_id}",
        "/api/v1/documents/by-editor/{document_id}",
        "/api/v1/documents/{document_id}",
        "/api/v1/documents/{document_id}/sse-token",
        "/api/v1/sse/documents/{document_id}/{token}",
        "/api/v1/patients",
        "/api/v1/patients/search",
        "/api/v1/doctor-templates",
        "/api/v1/doctor-templates/short",
        "/api/v1/doctor-templates/{template_id}",
        "/api/v1/doctor-templates/{template_id}/usage",
    }

    assert expected_paths.issubset(paths)
    assert "/api/v1/generate-sse-token/{document_id}" not in paths
    assert "/api/v1/sse/document/{document_id}/{token}" not in paths


def test_csrf_endpoint_sets_fastapi_cookie() -> None:
    response = TestClient(app).get("/api/v1/csrf")

    assert response.status_code == 200
    assert response.json()["csrfToken"]
    assert "_xsrf=" in response.headers["set-cookie"]

