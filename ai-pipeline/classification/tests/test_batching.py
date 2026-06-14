from __future__ import annotations

from classification.batching import plan_balanced_batches, weigh_cluster
from classification.lib import ClusterCase
from classification.templates import load_template


def _cluster(case_id: str, text: str) -> ClusterCase:
    return ClusterCase(
        id=case_id,
        template_id="minimal_outpatient_v001",
        cluster_json={
            "session_id": "mock",
            "topic_label": case_id,
            "turns": [
                {"turn_id": 0, "speaker": "PACIENTE", "text": text},
            ],
        },
    )


def test_plan_balanced_batches_splits_when_over_budget() -> None:
    template = load_template("minimal_outpatient_v001")
    clusters = [
        _cluster(f"case1_cluster_{index}", f"tema {index} " + ("detalle " * 80))
        for index in range(12)
    ]
    plan = plan_balanced_batches(clusters, template, budget=1200)
    assert plan.batch_count >= 2
    assigned_ids = [
        cluster.id for batch in plan.batches for cluster in batch.clusters
    ]
    assert set(assigned_ids) == {cluster.id for cluster in clusters}
    assert len(assigned_ids) == len(clusters)


def test_plan_balanced_batches_keeps_batch_token_loads_balanced() -> None:
    template = load_template("minimal_outpatient_v001")
    clusters = [
        _cluster("heavy_a", "x " * 500),
        _cluster("heavy_b", "y " * 500),
        _cluster("light_c", "z " * 50),
        _cluster("light_d", "w " * 50),
    ]
    plan = plan_balanced_batches(clusters, template, budget=1200)
    assert plan.batch_count >= 2
    cluster_loads = [
        sum(weigh_cluster(cluster) for cluster in batch.clusters)
        for batch in plan.batches
    ]
    assert max(cluster_loads) - min(cluster_loads) <= 400


def test_plan_balanced_batches_oversize_cluster_gets_warning_flag() -> None:
    template = load_template("minimal_outpatient_v001")
    clusters = [
        _cluster("tiny", "hola"),
        _cluster("huge", "palabra " * 5000),
    ]
    plan = plan_balanced_batches(clusters, template, budget=4000)
    assert plan.oversize_cluster_ids == ("huge",)
    assert any(batch.oversize_cluster_ids for batch in plan.batches)


def test_effective_budget_subtracts_template_tokens() -> None:
    template = load_template("minimal_outpatient_v001")
    clusters = [_cluster("only", "hola")]
    plan = plan_balanced_batches(clusters, template, budget=4000)
    assert plan.template_token_count > 0
    assert plan.effective_cluster_budget == 4000 - plan.template_token_count


def test_estimate_batch_input_tokens_v003_does_not_raise() -> None:
    from classification.batching import estimate_batch_input_tokens
    from classification.lib import load_classification_prompt

    template = load_template("consulta_estructurada_v001")
    clusters = [_cluster("case1_a", "texto " * 20)]
    tokens = estimate_batch_input_tokens(
        clusters,
        template,
        prompt_version="v003",
        base_system_prompt=load_classification_prompt("v003"),
    )
    assert tokens > 0
