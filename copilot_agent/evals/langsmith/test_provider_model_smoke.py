from __future__ import annotations

import pytest

from evals.shared.live_eval_support import (
    all_promptfoo_provider_specs,
    build_promptfoo_planner,
    missing_promptfoo_eval_env,
)


@pytest.mark.live_llm
@pytest.mark.parametrize(
    "provider_spec",
    all_promptfoo_provider_specs(),
    ids=lambda provider_spec: provider_spec.provider_id,
)
def test_provider_model_smoke(provider_spec) -> None:
    missing = missing_promptfoo_eval_env(provider_spec.provider_family)
    if missing:
        pytest.skip(
            "Missing environment for provider smoke test "
            f"{provider_spec.provider_id}: {', '.join(missing)}"
        )

    planner = build_promptfoo_planner(
        {
            "provider_id": provider_spec.provider_id,
            "label": provider_spec.label,
            "provider_family": provider_spec.provider_family,
            "planner_model": provider_spec.planner_model,
            "patch_model": provider_spec.patch_model,
            "google_location": provider_spec.google_location,
        }
    )
    model = planner._planner_model_instance()
    try:
        response = model.invoke("Reply with exactly: ok")
    except Exception as exc:  # pragma: no cover - live provider failure path
        pytest.fail(
            "Provider/model smoke call failed for "
            f"{provider_spec.provider_id}: {type(exc).__name__}: {exc}",
            pytrace=False,
        )

    response_text = getattr(response, "text", None) or str(response.content or "")
    response_model = (
        str(response.response_metadata.get("model_name") or "")
        or str(response.response_metadata.get("model") or "")
    )

    assert response_text.strip()
    assert response_model.strip()
