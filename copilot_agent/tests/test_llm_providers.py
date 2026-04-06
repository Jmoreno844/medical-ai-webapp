from types import SimpleNamespace

from app.llm.providers import resolve_runtime_provider_specs


def test_runtime_provider_specs_default_to_openai_minis():
    planner_spec, patch_spec = resolve_runtime_provider_specs(
        SimpleNamespace(
            llm_provider_family="openai",
            planner_provider_family=None,
            planner_model=None,
            patch_provider_family=None,
            patch_model=None,
            google_location=None,
            planner_google_location=None,
            patch_google_location=None,
            gcp_region=None,
            vertex_model="gemini-2.5-flash",
        )
    )

    assert planner_spec.provider_family == "openai"
    assert planner_spec.model_name == "gpt-5.4-mini"
    assert patch_spec.provider_family == "openai"
    assert patch_spec.model_name == "gpt-5.4-mini"


def test_runtime_provider_specs_keep_legacy_google_vertex_model_when_requested():
    planner_spec, patch_spec = resolve_runtime_provider_specs(
        SimpleNamespace(
            llm_provider_family="google",
            planner_provider_family=None,
            planner_model=None,
            patch_provider_family=None,
            patch_model=None,
            google_location=None,
            planner_google_location=None,
            patch_google_location=None,
            gcp_region="us-east1",
            vertex_model="gemini-2.5-flash",
        )
    )

    assert planner_spec.provider_family == "google"
    assert planner_spec.model_name == "gemini-2.5-flash"
    assert planner_spec.google_location == "us-east1"
    assert patch_spec.provider_family == "google"
    assert patch_spec.model_name == "gemini-2.5-flash"
    assert patch_spec.google_location == "us-east1"


def test_runtime_provider_specs_allow_split_planner_and_patch_providers():
    planner_spec, patch_spec = resolve_runtime_provider_specs(
        SimpleNamespace(
            llm_provider_family="openai",
            planner_provider_family=None,
            planner_model="gpt-5.4-mini",
            patch_provider_family="anthropic",
            patch_model="claude-haiku-4-5",
            google_location=None,
            planner_google_location=None,
            patch_google_location=None,
            gcp_region="us-east1",
            vertex_model="gemini-2.5-flash",
        )
    )

    assert planner_spec.provider_family == "openai"
    assert planner_spec.model_name == "gpt-5.4-mini"
    assert patch_spec.provider_family == "anthropic"
    assert patch_spec.model_name == "claude-haiku-4-5"