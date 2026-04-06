from __future__ import annotations

import functools
import logging
import os
from functools import lru_cache
from typing import Any, Callable, TypeVar, cast

try:
    from langsmith import Client, trace
except ImportError:  # pragma: no cover - dependency comes from requirements.txt
    Client = None
    trace = None

from config import get_environment, is_local

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def _tracing_enabled_flag() -> bool:
    value = (os.environ.get("LANGSMITH_TRACING") or "").strip().lower()
    return value not in {"0", "false", "no", "off"}


def _api_key() -> str | None:
    return (os.environ.get("LANGSMITH_API_KEY") or "").strip() or None


def _project_name() -> str | None:
    return (os.environ.get("LANGSMITH_PROJECT") or "").strip() or None


def _endpoint() -> str | None:
    return (os.environ.get("LANGSMITH_ENDPOINT") or "").strip() or None


def langsmith_enabled() -> bool:
    return (
        is_local()
        and _tracing_enabled_flag()
        and bool(_api_key())
        and bool(_project_name())
        and Client is not None
        and trace is not None
    )


@lru_cache(maxsize=2)
def _build_client(api_key: str, endpoint: str | None) -> Any:
    if Client is None:
        return None
    kwargs: dict[str, Any] = {"api_key": api_key}
    if endpoint:
        kwargs["api_url"] = endpoint
    return Client(**kwargs)


def _client() -> Any:
    api_key = _api_key()
    if not api_key:
        return None
    return _build_client(api_key, _endpoint())


def configure_langsmith() -> bool:
    enabled = langsmith_enabled()
    if enabled:
        logger.info(
            "LangSmith tracing enabled for local Cloud Functions runtime",
            extra={"langsmith_project": _project_name()},
        )
    return enabled


def trace_operation(
    *,
    name: str,
    run_type: str = "chain",
    process_inputs: Callable[..., dict[str, Any]] | None = None,
    process_outputs: Callable[[Any], dict[str, Any]] | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not langsmith_enabled() or trace is None:
                return func(*args, **kwargs)

            client = _client()
            if client is None:
                return func(*args, **kwargs)

            inputs = process_inputs(*args, **kwargs) if process_inputs else {}
            merged_metadata = {
                "component": "cloud_functions",
                "environment": get_environment(),
                **(metadata or {}),
            }
            merged_tags = sorted(
                set(tags or []) | {"cloud_functions", get_environment()}
            )

            with trace(
                name,
                run_type=run_type,
                inputs=inputs,
                project_name=_project_name(),
                client=client,
                metadata=merged_metadata,
                tags=merged_tags,
            ) as run:
                result = func(*args, **kwargs)
                run.end(
                    outputs=(
                        process_outputs(result)
                        if process_outputs
                        else {"result_type": type(result).__name__}
                    )
                )
                return result

        return cast(F, wrapper)

    return decorator