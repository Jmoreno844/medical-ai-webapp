from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, TypeAdapter, ValidationError

from common.context_spans import Span, SpanCluster, audit_span_clusters
from common.json_utils import extract_json_object
from common.prompts import load_prompt as load_prompt_from_file
from common.prompts import prompt_file_path as resolve_prompt_file_path

MODULE_ROOT = Path(__file__).resolve().parent
PROMPTS_DIR = MODULE_ROOT / "prompts"
PROMPT_FILENAME_STEM = "cluster_spans"
_CLUSTER_ADAPTER = TypeAdapter(list[SpanCluster])


class ClusterSpansResult(BaseModel):
    clusters: list[SpanCluster]


def cluster_spans_prompt_file_path(version: str) -> Path:
    return resolve_prompt_file_path(
        prompts_dir=PROMPTS_DIR,
        filename_stem=PROMPT_FILENAME_STEM,
        version=version,
    )


def load_cluster_spans_prompt(version: str) -> str:
    return load_prompt_from_file(
        prompts_dir=PROMPTS_DIR,
        filename_stem=PROMPT_FILENAME_STEM,
        version=version,
    )


def prompt_file_path(version: str) -> Path:
    return cluster_spans_prompt_file_path(version)


def load_prompt(version: str) -> str:
    return load_cluster_spans_prompt(version)


def render_cluster_spans_payload(*, spans: list[Span]) -> str:
    if not spans:
        raise ValueError("cluster_spans_payload_requires_at_least_one_span")
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


__all__ = [
    "MODULE_ROOT",
    "ClusterSpansResult",
    "audit_span_clusters",
    "enrich_cluster_spans_result_for_export",
    "load_cluster_spans_prompt",
    "load_prompt",
    "parse_cluster_spans_result",
    "prompt_file_path",
    "render_cluster_spans_payload",
]
