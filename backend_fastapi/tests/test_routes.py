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
        "/api/v1/auth/register",
        "/api/v1/auth/forgot-password",
        "/api/v1/auth/me",
        "/api/v1/auth/refresh",
        "/api/v1/auth/logout",
        "/api/v1/encounters",
        "/api/v1/encounters/{encounter_id}",
        "/api/v1/encounters/{encounter_id}/audio/upload-url",
        "/api/v1/encounters/{encounter_id}/audio/exists",
        "/api/v1/encounters/{encounter_id}/audio",
        "/api/v1/documents",
        "/api/v1/documents/encounter/{encounter_id}",
        "/api/v1/documents/by-editor/{document_id}",
        "/api/v1/documents/by-function/{document_id}",
        "/api/v1/documents/generate",
        "/api/v1/documents/generation-chunk",
        "/api/v1/documents/{document_id}",
        "/api/v1/documents/{document_id}/sse-token",
        "/api/v1/transcription/start",
        "/api/v1/transcription/notify-complete",
        "/api/v1/sse/documents/{document_id}/{token}",
        "/api/v1/patients",
        "/api/v1/patients/search",
        "/api/v1/doctor-templates",
        "/api/v1/doctor-templates/short",
        "/api/v1/doctor-templates/{template_id}",
        "/api/v1/doctor-templates/{template_id}/usage",
        "/api/v1/copilot/sessions",
        "/api/v1/copilot/messages",
        "/api/v1/copilot/runs/{run_id}",
        "/api/v1/copilot/runs/{run_id}/patches",
        "/api/v1/copilot/runs/{run_id}/patch-sets",
        "/api/v1/copilot/runs/{run_id}/stream",
        "/api/v1/copilot/runs/{run_id}/review",
        "/api/v1/copilot/patch-sets/{patch_set_id}",
        "/api/v1/copilot/patch-sets/{patch_set_id}/accept-patch",
        "/api/v1/copilot/patch-sets/{patch_set_id}/reject-patch",
        "/api/v1/copilot/patch-sets/{patch_set_id}/accept-all",
        "/api/v1/copilot/patch-sets/{patch_set_id}/reject-all",
        "/api/v1/copilot/patch-sets/{patch_set_id}/apply-accepted",
        "/api/v1/copilot/patch-sets/{patch_set_id}/finalize-review",
        "/api/v1/internal/copilot/tools/open-documents",
        "/api/v1/internal/copilot/tools/encounter-documents",
        "/api/v1/internal/copilot/tools/read-document",
        "/api/v1/internal/copilot/tools/read-document-summary",
        "/api/v1/internal/copilot/tools/read-document-span",
        "/api/v1/internal/copilot/tools/search-documents",
        "/api/v1/internal/copilot/tools/read-patch-history",
        "/api/v1/internal/copilot/tools/read-encounter-context",
    }

    assert expected_paths.issubset(paths)
    assert "/api/v1/generate-sse-token/{document_id}" not in paths
    assert "/api/v1/sse/document/{document_id}/{token}" not in paths
    assert "/api/v1/copilot" not in paths


def test_copilot_internal_tool_routes_preserve_agent_contract() -> None:
    paths = {route.path for route in app.routes}

    assert "/api/internal/copilot/tools/read-document" in paths
    assert "/api/internal/copilot/tools/search-documents" in paths


def test_csrf_endpoint_sets_fastapi_cookie() -> None:
    response = TestClient(app).get("/api/v1/csrf")

    assert response.status_code == 200
    assert response.json()["csrfToken"]
    assert "_xsrf=" in response.headers["set-cookie"]

