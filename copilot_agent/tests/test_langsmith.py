from types import SimpleNamespace

from app.langsmith import langsmith_enabled


def test_langsmith_enabled_only_for_local_with_project_and_key():
    settings = SimpleNamespace(
        environment="local",
        langsmith_tracing=None,
        langsmith_api_key="ls-test",
        langsmith_project="copilot-agent-local",
    )

    assert langsmith_enabled(settings) is True


def test_langsmith_disabled_when_explicitly_turned_off():
    settings = SimpleNamespace(
        environment="local",
        langsmith_tracing=False,
        langsmith_api_key="ls-test",
        langsmith_project="copilot-agent-local",
    )

    assert langsmith_enabled(settings) is False


def test_langsmith_disabled_outside_local():
    settings = SimpleNamespace(
        environment="production",
        langsmith_tracing=True,
        langsmith_api_key="ls-test",
        langsmith_project="copilot-agent-prod",
    )

    assert langsmith_enabled(settings) is False