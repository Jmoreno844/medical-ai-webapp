from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, TypeAdapter, ValidationError

from common.context_spans import Span, SpanCluster, audit_span_clusters
from common.json_utils import extract_json_object
from common.llm_response import LlmResponse
from common.prompt_registry import is_py_prompt_version, load_py_prompt_module, py_system_prompt
from common.prompts import load_prompt as load_prompt_from_file
from common.prompts import prompt_file_path as resolve_prompt_file_path

MODULE_ROOT = Path(__file__).resolve().parent
PROMPTS_DIR = MODULE_ROOT / "prompts"
PROMPT_FILENAME_STEM = "cluster_spans"
PY_CLUSTER_SPANS_STEP = "context_cluster_spans"
PY_CLUSTER_SPANS_PROMPT_VERSIONS = frozenset({"v002"})
_CLUSTER_ADAPTER = TypeAdapter(list[SpanCluster])


class ClusterSpansResult(BaseModel):
    clusters: list[SpanCluster]


def cluster_spans_uses_py_prompt(prompt_version: str) -> bool:
    return is_py_prompt_version(PY_CLUSTER_SPANS_STEP, prompt_version)


def cluster_spans_structured_output_enabled(prompt_version: str) -> bool:
    return prompt_version.strip().lower() in PY_CLUSTER_SPANS_PROMPT_VERSIONS


def cluster_spans_output_schema(
    spans: list[Span],
    *,
    prompt_version: str,
) -> dict[str, object] | None:
    if not cluster_spans_structured_output_enabled(prompt_version):
        return None
    module = load_py_prompt_module(PY_CLUSTER_SPANS_STEP, prompt_version)
    output_schema_fn = getattr(module, "output_schema", None)
    if not callable(output_schema_fn):
        raise ValueError(
            f"cluster_spans_py_prompt_missing_output_schema: {prompt_version}"
        )
    schema = output_schema_fn(span_ids=[span.id for span in spans])
    if not isinstance(schema, dict):
        raise ValueError(
            f"cluster_spans_py_prompt_invalid_output_schema: {prompt_version}"
        )
    return schema


def cluster_spans_prompt_file_path(version: str) -> Path:
    return resolve_prompt_file_path(
        prompts_dir=PROMPTS_DIR,
        filename_stem=PROMPT_FILENAME_STEM,
        version=version,
    )


def load_cluster_spans_prompt(version: str) -> str:
    if cluster_spans_uses_py_prompt(version):
        return py_system_prompt(PY_CLUSTER_SPANS_STEP, version)
    return load_prompt_from_file(
        prompts_dir=PROMPTS_DIR,
        filename_stem=PROMPT_FILENAME_STEM,
        version=version,
    )


def cluster_spans_prompt_reference(version: str) -> str:
    if cluster_spans_uses_py_prompt(version):
        module_path = load_py_prompt_module(PY_CLUSTER_SPANS_STEP, version).__name__
        return f"{module_path.replace('.', '/')}.py"
    return str(cluster_spans_prompt_file_path(version).relative_to(MODULE_ROOT))


def prompt_file_path(version: str) -> Path:
    return cluster_spans_prompt_file_path(version)


def load_prompt(version: str) -> str:
    return load_cluster_spans_prompt(version)


def _cluster_spans_span_payload(span: Span) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": span.id,
        "text": span.text,
    }
    if span.date_hint:
        payload["date_hint"] = span.date_hint
    return payload


def render_cluster_spans_payload(
    *,
    spans: list[Span],
    prompt_version: str = "v001",
) -> str:
    if not spans:
        raise ValueError("cluster_spans_payload_requires_at_least_one_span")
    if cluster_spans_uses_py_prompt(prompt_version):
        module = load_py_prompt_module(PY_CLUSTER_SPANS_STEP, prompt_version)
        spans_payload = [_cluster_spans_span_payload(span) for span in spans]
        return module.render_user_payload(spans=spans_payload)
    payload = {
        "spans": [{"id": span.id, "text": span.text} for span in spans],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def parse_cluster_spans_result(raw: str) -> list[SpanCluster]:
    payload = extract_json_object(raw)
    if isinstance(payload, dict) and "clusters" in payload:
        clusters_raw = payload["clusters"]
    else:
        clusters_raw = payload
    try:
        if isinstance(clusters_raw, list):
            return _CLUSTER_ADAPTER.validate_python(clusters_raw)
        raise ValueError("cluster_spans_result_must_be_list_or_clusters_key")
    except ValidationError as exc:
        raise ValueError(f"cluster_spans_invalid_result: {exc}") from exc


def enrich_cluster_spans_result_for_export(
    clusters: list[SpanCluster],
) -> dict[str, object]:
    return {
        "clusters": [cluster.model_dump(mode="json") for cluster in clusters],
        "cluster_count": len(clusters),
    }


class ClusterSpansValidationError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        raw_response: str | None = None,
        llm_response: LlmResponse | None = None,
        clusters: list[SpanCluster] | None = None,
        missing_span_ids: list[str] | None = None,
        missing_spans: list[dict[str, object]] | None = None,
    ) -> None:
        super().__init__(message)
        self.raw_response = raw_response
        self.llm_response = llm_response
        self.clusters = list(clusters or [])
        self.missing_span_ids = list(missing_span_ids or [])
        self.missing_spans = list(missing_spans or [])

    def diagnostics(self) -> dict[str, object]:
        payload: dict[str, object] = {}
        if self.raw_response is not None:
            payload["raw_response"] = self.raw_response
        if self.clusters:
            payload["cluster_spans_result"] = enrich_cluster_spans_result_for_export(
                self.clusters
            )
        if self.missing_span_ids:
            payload["missing_span_ids"] = self.missing_span_ids
        if self.missing_spans:
            payload["missing_spans"] = self.missing_spans
        return payload


def missing_span_ids_from_clusters(
    spans: list[Span],
    clusters: list[SpanCluster],
) -> list[str]:
    span_ids = {span.id for span in spans}
    assigned_span_ids = {
        span_id for cluster in clusters for span_id in cluster.span_ids
    }
    return sorted(span_ids - assigned_span_ids)


__all__ = [
    "MODULE_ROOT",
    "ClusterSpansResult",
    "ClusterSpansValidationError",
    "audit_span_clusters",
    "cluster_spans_output_schema",
    "cluster_spans_prompt_file_path",
    "cluster_spans_prompt_reference",
    "cluster_spans_structured_output_enabled",
    "cluster_spans_uses_py_prompt",
    "enrich_cluster_spans_result_for_export",
    "load_cluster_spans_prompt",
    "load_prompt",
    "missing_span_ids_from_clusters",
    "parse_cluster_spans_result",
    "prompt_file_path",
    "render_cluster_spans_payload",
]
