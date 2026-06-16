#!/usr/bin/env python3
"""Offline comparison of two document pipeline generation strategies."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKER_ROOT = REPO_ROOT / "document_pipeline_worker"
sys.path.insert(0, str(WORKER_ROOT))

from app.pipeline.config import PipelineConfig  # noqa: E402
from app.pipeline.orchestrator import parse_context_inputs, run_document_pipeline  # noqa: E402
from document_pipeline_core.common.templates import ClinicalTemplate, TemplateSection  # noqa: E402
from document_pipeline_core.common.transcripts import TranscriptCase  # noqa: E402


def _parse_markdown_template(*, template_content: str, template_id: str) -> ClinicalTemplate:
    sections: list[TemplateSection] = []
    for line in template_content.splitlines():
        if line.startswith("## "):
            heading = line.removeprefix("## ").strip()
            section_id = heading.lower().replace(" ", "_")
            sections.append(
                TemplateSection(section_id=section_id, heading=heading, description="")
            )
    if not sections:
        sections.append(TemplateSection(section_id="motivo", heading="Motivo", description=""))
    return ClinicalTemplate(id=template_id, name=template_id, sections=sections)


def _load_case(path: Path, case_id: str) -> tuple[TranscriptCase, str]:
    cases = json.loads(path.read_text(encoding="utf-8"))
    for item in cases:
        if item.get("id") == case_id:
            transcript = item.get("transcript_json")
            if not isinstance(transcript, dict):
                raise ValueError(f"case {case_id} missing transcript_json")
            return TranscriptCase(id=case_id, transcript_json=transcript), str(
                item.get("template_markdown") or "## Motivo\n\n## Examen\n"
            )
    raise ValueError(f"case_not_found: {case_id}")


def _run_once(
    *,
    case: TranscriptCase,
    template_markdown: str,
    config: PipelineConfig,
) -> dict[str, object]:
    template = _parse_markdown_template(
        template_content=template_markdown,
        template_id=f"eval_{case.id}",
    )
    started = time.perf_counter()
    result = run_document_pipeline(
        session_id=case.id,
        template=template,
        transcript_json=case.transcript_json,
        context_inputs=parse_context_inputs(
            {
                "context_inputs": {
                    "doctor_note_markdown": "No se agregó contexto.",
                    "external_documents": [],
                }
            }
        ),
        pipeline_config=config,
    )
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return {
        "document_length": len(result.document_markdown),
        "elapsed_ms": elapsed_ms,
        "steps": [step.step for step in result.step_results],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--case-id", type=str, required=True)
    parser.add_argument("--config-a", action="append", default=[])
    parser.add_argument("--config-b", action="append", default=[])
    args = parser.parse_args()

    case, template_markdown = _load_case(args.cases, args.case_id)
    config_a = PipelineConfig()
    config_b = PipelineConfig()
    for override in args.config_a:
        key, _, value = override.partition("=")
        setattr(config_a, key, value)
    for override in args.config_b:
        key, _, value = override.partition("=")
        setattr(config_b, key, value)

    out_a = _run_once(case=case, template_markdown=template_markdown, config=config_a)
    out_b = _run_once(case=case, template_markdown=template_markdown, config=config_b)
    print(json.dumps({"config_a": out_a, "config_b": out_b}, indent=2))


if __name__ == "__main__":
    main()
