from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import lru_cache

import tiktoken

from classification.lib import ClusterCase, cluster_to_payload_item
from classification.templates import ClassificationTemplate

DEFAULT_INPUT_TOKEN_BUDGET = 4000
DEFAULT_TOKEN_ENCODING = "cl100k_base"
DEFAULT_BATCH_CONCURRENCY = 0


@dataclass(frozen=True, slots=True)
class ClusterWeight:
    cluster_id: str
    cluster_case: ClusterCase
    token_count: int


@dataclass(frozen=True, slots=True)
class ClassificationBatch:
    batch_index: int
    clusters: list[ClusterCase]
    estimated_input_tokens: int
    oversize_cluster_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BatchPlan:
    input_token_budget: int
    template_token_count: int
    effective_cluster_budget: int
    encoding_name: str
    batches: list[ClassificationBatch]
    oversize_cluster_ids: tuple[str, ...]

    @property
    def batch_count(self) -> int:
        return len(self.batches)

    def to_dict(self) -> dict[str, object]:
        return {
            "input_token_budget": self.input_token_budget,
            "template_token_count": self.template_token_count,
            "effective_cluster_budget": self.effective_cluster_budget,
            "encoding_name": self.encoding_name,
            "batch_count": self.batch_count,
            "oversize_cluster_ids": list(self.oversize_cluster_ids),
            "batches": [
                {
                    "batch_index": batch.batch_index,
                    "cluster_ids": [cluster.id for cluster in batch.clusters],
                    "estimated_input_tokens": batch.estimated_input_tokens,
                    "oversize_cluster_ids": list(batch.oversize_cluster_ids),
                }
                for batch in self.batches
            ],
        }


@lru_cache(maxsize=8)
def _get_encoding(encoding_name: str) -> tiktoken.Encoding:
    return tiktoken.get_encoding(encoding_name)


def count_text_tokens(text: str, *, encoding_name: str = DEFAULT_TOKEN_ENCODING) -> int:
    encoding = _get_encoding(encoding_name)
    return len(encoding.encode(text))


def weigh_cluster(
    cluster_case: ClusterCase,
    *,
    encoding_name: str = DEFAULT_TOKEN_ENCODING,
) -> int:
    payload_text = json.dumps(
        cluster_to_payload_item(cluster_case),
        ensure_ascii=False,
        indent=2,
    )
    return count_text_tokens(payload_text, encoding_name=encoding_name)


def weigh_template(
    template: ClassificationTemplate,
    *,
    encoding_name: str = DEFAULT_TOKEN_ENCODING,
) -> int:
    payload_text = json.dumps(
        template.to_prompt_payload(),
        ensure_ascii=False,
        indent=2,
    )
    return count_text_tokens(payload_text, encoding_name=encoding_name)


def weigh_classification_request_context(
    template: ClassificationTemplate,
    *,
    base_system_prompt: str,
    prompt_version: str,
    encoding_name: str = DEFAULT_TOKEN_ENCODING,
) -> int:
    from classification.lib import (
        classification_uses_enriched_system_prompt,
        prepare_classification_prompts,
        template_ref_for_classification_user,
    )

    if not classification_uses_enriched_system_prompt(prompt_version):
        return weigh_template(template, encoding_name=encoding_name)

    resolved_system_prompt, _ = prepare_classification_prompts(
        base_system_prompt,
        template,
        prompt_version=prompt_version,
    )
    ref_payload = {
        "template_ref": template_ref_for_classification_user(template),
    }
    return count_text_tokens(
        resolved_system_prompt,
        encoding_name=encoding_name,
    ) + count_text_tokens(
        json.dumps(ref_payload, ensure_ascii=False, indent=2),
        encoding_name=encoding_name,
    )


def estimate_batch_input_tokens(
    clusters: list[ClusterCase],
    template: ClassificationTemplate,
    *,
    encoding_name: str = DEFAULT_TOKEN_ENCODING,
    prompt_version: str = "v002",
    base_system_prompt: str = "",
) -> int:
    from classification.lib import (
        classification_uses_enriched_system_prompt,
        prepare_classification_prompts,
        template_ref_for_classification_user,
    )

    cluster_items = [cluster_to_payload_item(cluster) for cluster in clusters]
    if classification_uses_enriched_system_prompt(prompt_version):
        payload = {
            "clusters": cluster_items,
            "template_ref": template_ref_for_classification_user(template),
        }
        user_tokens = count_text_tokens(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding_name=encoding_name,
        )
        return user_tokens + count_text_tokens(
            prepare_classification_prompts(
                base_system_prompt,
                template,
                prompt_version=prompt_version,
            )[0],
            encoding_name=encoding_name,
        )
    payload = {
        "clusters": cluster_items,
        "template": template.to_prompt_payload(),
    }
    return count_text_tokens(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding_name=encoding_name,
    )


def _partition_lpt(
    weighted_clusters: list[ClusterWeight],
    *,
    batch_count: int,
    effective_budget: int,
) -> tuple[list[list[ClusterCase]], list[int], list[str]]:
    bins: list[list[ClusterCase]] = [[] for _ in range(batch_count)]
    bin_weights = [0] * batch_count
    oversize_cluster_ids: list[str] = []

    ordered_clusters = sorted(
        weighted_clusters,
        key=lambda entry: entry.token_count,
        reverse=True,
    )
    for item in ordered_clusters:
        if item.token_count > effective_budget:
            oversize_cluster_ids.append(item.cluster_id)
        lightest_bin = min(range(batch_count), key=lambda index: bin_weights[index])
        bins[lightest_bin].append(item.cluster_case)
        bin_weights[lightest_bin] += item.token_count

    return bins, bin_weights, oversize_cluster_ids


def plan_balanced_batches(
    clusters: list[ClusterCase],
    template: ClassificationTemplate,
    *,
    budget: int = DEFAULT_INPUT_TOKEN_BUDGET,
    encoding_name: str = DEFAULT_TOKEN_ENCODING,
    prompt_version: str = "v002",
    base_system_prompt: str = "",
) -> BatchPlan:
    if not clusters:
        raise ValueError("classification_batching_requires_at_least_one_cluster")
    if budget <= 0:
        raise ValueError("classification_input_token_budget_must_be_positive")

    template_token_count = weigh_classification_request_context(
        template,
        base_system_prompt=base_system_prompt,
        prompt_version=prompt_version,
        encoding_name=encoding_name,
    )
    effective_cluster_budget = budget - template_token_count
    if effective_cluster_budget <= 0:
        raise ValueError(
            "classification_input_token_budget_too_small_for_template: "
            f"budget={budget} template_tokens={template_token_count}"
        )

    weighted_clusters = [
        ClusterWeight(
            cluster_id=cluster.id,
            cluster_case=cluster,
            token_count=weigh_cluster(cluster, encoding_name=encoding_name),
        )
        for cluster in clusters
    ]
    total_cluster_tokens = sum(item.token_count for item in weighted_clusters)
    batch_count = max(
        1,
        min(
            len(weighted_clusters),
            math.ceil(total_cluster_tokens / effective_cluster_budget),
        ),
    )

    all_oversize_cluster_ids: list[str] = []
    while batch_count <= len(weighted_clusters):
        bins, bin_weights, oversize_cluster_ids = _partition_lpt(
            weighted_clusters,
            batch_count=batch_count,
            effective_budget=effective_cluster_budget,
        )
        all_oversize_cluster_ids = oversize_cluster_ids
        if all(weight <= effective_cluster_budget for weight in bin_weights):
            break
        batch_count += 1
    else:
        bins = [[item.cluster_case] for item in weighted_clusters]
        all_oversize_cluster_ids = [
            item.cluster_id
            for item in weighted_clusters
            if item.token_count > effective_cluster_budget
        ]

    batches: list[ClassificationBatch] = []
    for index, batch_clusters in enumerate(bins):
        if not batch_clusters:
            continue
        batch_oversize = tuple(
            cluster.id
            for cluster in batch_clusters
            if weigh_cluster(cluster, encoding_name=encoding_name)
            > effective_cluster_budget
        )
        batches.append(
            ClassificationBatch(
                batch_index=len(batches),
                clusters=batch_clusters,
                estimated_input_tokens=estimate_batch_input_tokens(
                    batch_clusters,
                    template,
                    encoding_name=encoding_name,
                    prompt_version=prompt_version,
                    base_system_prompt=base_system_prompt,
                ),
                oversize_cluster_ids=batch_oversize,
            )
        )

    return BatchPlan(
        input_token_budget=budget,
        template_token_count=template_token_count,
        effective_cluster_budget=effective_cluster_budget,
        encoding_name=encoding_name,
        batches=batches,
        oversize_cluster_ids=tuple(dict.fromkeys(all_oversize_cluster_ids)),
    )


__all__ = [
    "BatchPlan",
    "ClassificationBatch",
    "ClusterWeight",
    "DEFAULT_BATCH_CONCURRENCY",
    "DEFAULT_INPUT_TOKEN_BUDGET",
    "DEFAULT_TOKEN_ENCODING",
    "count_text_tokens",
    "estimate_batch_input_tokens",
    "plan_balanced_batches",
    "weigh_cluster",
    "weigh_classification_request_context",
    "weigh_template",
]
