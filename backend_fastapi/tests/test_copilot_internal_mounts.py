"""Copilot internal tools are mounted at /api/v1/internal/... and /api/internal/... for agent contract."""

from __future__ import annotations

from app.main import app

V1_PREFIX = "/api/v1/internal/copilot/tools"
UNVERSIONED_PREFIX = "/api/internal/copilot/tools"


def test_copilot_internal_tool_paths_match_v1_and_unversioned() -> None:
    v1_paths = {
        route.path
        for route in app.routes
        if getattr(route, "path", "").startswith(f"{V1_PREFIX}/")
    }
    unversioned_paths = {
        route.path
        for route in app.routes
        if getattr(route, "path", "").startswith(f"{UNVERSIONED_PREFIX}/")
    }
    assert v1_paths, "expected /api/v1/internal/copilot/tools/* routes"
    assert unversioned_paths, "expected /api/internal/copilot/tools/* routes"
    v1_suffixes = {p.removeprefix(f"{V1_PREFIX}/") for p in v1_paths}
    unv_suffixes = {p.removeprefix(f"{UNVERSIONED_PREFIX}/") for p in unversioned_paths}
    assert v1_suffixes == unv_suffixes
