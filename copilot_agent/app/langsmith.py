from __future__ import annotations

import logging
from contextlib import contextmanager
from functools import lru_cache
from typing import Any, Iterator

try:
    from langsmith import Client, trace
except ImportError:  # pragma: no cover - runtime dependency in deployed service
    Client = None
    trace = None

from app.config import Settings

logger = logging.getLogger(__name__)


def langsmith_enabled(settings: Settings) -> bool:
    environment = getattr(settings, "environment", "local")
    tracing_flag = getattr(settings, "langsmith_tracing", None)
    api_key = getattr(settings, "langsmith_api_key", None)
    project = getattr(settings, "langsmith_project", None)
    return (
        environment == "local"
        and tracing_flag is not False
        and bool(api_key)
        and bool(project)
        and Client is not None
        and trace is not None
    )


@lru_cache(maxsize=4)
def _build_client(api_key: str, endpoint: str | None) -> Any:
    if Client is None:
        return None
    kwargs: dict[str, Any] = {"api_key": api_key}
    if endpoint:
        kwargs["api_url"] = endpoint
    return Client(**kwargs)


def _client_for_settings(settings: Settings) -> Any:
    api_key = getattr(settings, "langsmith_api_key", None)
    endpoint = getattr(settings, "langsmith_endpoint", None)
    if not api_key:
        return None
    return _build_client(api_key, endpoint)


def configure_langsmith(settings: Settings) -> bool:
    enabled = langsmith_enabled(settings)
    if enabled:
        logger.info(
            "LangSmith tracing enabled for copilot agent local runtime",
            extra={"langsmith_project": getattr(settings, "langsmith_project", None)},
        )
    return enabled


@contextmanager
def traced_operation(
    settings: Settings,
    *,
    name: str,
    inputs: dict[str, Any],
    metadata: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    run_type: str = "chain",
) -> Iterator[Any]:
    if not langsmith_enabled(settings) or trace is None:
        yield None
        return

    client = _client_for_settings(settings)
    if client is None:
        yield None
        return

    environment = getattr(settings, "environment", "local")
    project = getattr(settings, "langsmith_project", None)

    merged_metadata = {
        "component": "copilot_agent",
        "environment": environment,
        **(metadata or {}),
    }
    merged_tags = sorted(
        set(tags or []) | {"copilot_agent", "runtime", environment}
    )

    with trace(
        name,
        run_type=run_type,
        inputs=inputs,
        project_name=project,
        client=client,
        metadata=merged_metadata,
        tags=merged_tags,
    ) as run:
        yield run


def finish_traced_operation(
    run: Any,
    *,
    outputs: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> None:
    if run is None:
        return
    if metadata:
        run.metadata.update(metadata)
    run.end(outputs=outputs)