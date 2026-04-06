from evals.shared.live_eval_support import all_promptfoo_provider_specs


def test_promptfoo_provider_specs_match_requested_matrix() -> None:
    specs = all_promptfoo_provider_specs()

    assert [spec.provider_id for spec in specs] == [
        "openai-gpt-5.4-mini",
        "openai-gpt-5.4-nano",
        "google-gemini-2.5-flash",
        "google-gemini-2.5-flash-lite",
        "google-gemini-3-flash-preview",
        "google-gemini-3.1-flash-lite-preview",
        "anthropic-claude-haiku-4-5",
    ]
    assert [spec.planner_model for spec in specs] == [
        "gpt-5.4-mini",
        "gpt-5.4-nano",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-3-flash-preview",
        "gemini-3.1-flash-lite-preview",
        "claude-haiku-4-5",
    ]