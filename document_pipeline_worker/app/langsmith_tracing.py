from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from app.settings import Settings

try:
    from langsmith import Client, trace
except ImportError:  # pragma: no cover
    Client = None
    trace = None

logger = logging.getLogger(__name__)


@lru_cache(maxsize=4)
def _client(api_key: str, endpoint: str | None) -> Any:
    if Client is None:
        return None
    kwargs: dict[str, Any] = {"api_key": api_key}
    if endpoint:
        kwargs["api_url"] = endpoint
    return Client(**kwargs)


def configure_langsmith(settings: Settings) -> bool:
    enabled = settings.langsmith_enabled and Client is not None and trace is not None
    if enabled:
        logger.info(
            "LangSmith tracing enabled for document pipeline worker environment=%s",
            settings.environment_name,
        )
    return enabled


class LangSmithRun:
    def __init__(
        self,
        settings: Settings,
        *,
        name: str,
        inputs: dict[str, Any],
        tags: list[str],
    ) -> None:
        self._settings = settings
        self._name = name
        self._inputs = inputs
        self._tags = tags
        self._ctx = None
        self._run = None

    def __enter__(self) -> "LangSmithRun":
        if not self._settings.langsmith_enabled or trace is None:
            return self
        client = _client(
            str(self._settings.langsmith_api_key),
            self._settings.langsmith_endpoint,
        )
        if client is None:
            return self
        self._ctx = trace(
            self._name,
            run_type="chain",
            inputs=self._inputs,
            project_name=self._settings.langsmith_project,
            client=client,
            metadata={
                "component": "document_pipeline_worker",
                "environment": self._settings.environment_name,
            },
            tags=sorted(set(self._tags) | {self._settings.environment_name}),
        )
        self._run = self._ctx.__enter__()
        return self

    def end(self, outputs: dict[str, Any]) -> None:
        if self._run is not None:
            self._run.end(outputs=outputs)

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._ctx is not None:
            self._ctx.__exit__(exc_type, exc, tb)
