from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

AI_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(AI_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(AI_PIPELINE_ROOT))

from common.context_claims import merge_claim_lists  # noqa: E402
from common.output_detail import normalize_output_detail  # noqa: E402
from common.prompts import normalize_prompt_version  # noqa: E402
from common.providers import (  # noqa: E402
    ModelSpec,
    default_model_for_provider,
    normalize_provider_name,
)
from common.templates import DEFAULT_TEMPLATES_DIR, load_template  # noqa: E402
from context_pipeline.classify_claims.classify_claims import (  # noqa: E402
    run_classify_claims_session,
)
from context_pipeline.classify_claims.lib import (  # noqa: E402
    DEFAULT_OUTPUT_DETAIL,
    DEFAULT_PROMPT_VERSION,
    MODULE_ROOT,
    audit_claim_assignments,
    enrich_claim_classification_session_result_for_export,
    format_claim_classification_debug_output,
    load_prompt,
    prompt_file_path,
)
from context_pipeline.decompose.lib import (  # noqa: E402
    DEFAULT_CASES_INDEX,
    load_context_case,
    load_context_cases,
    normalize_decompose_claims,
    parse_decompose_result,
    select_context_case,
)
from context_pipeline.extract.lib import (  # noqa: E402
    normalize_extract_claims,
    parse_extract_result,
)

DEFAULT_RESULTS_DIR = MODULE_ROOT / "results"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Debug claim classification for a context session."
    )
    parser.add_argument("--cases", default=str(DEFAULT_CASES_INDEX))
    parser.add_argument("--case-id", required=True)
    parser.add_argument(
        "--claims-json",
        default=None,
        help=(
            "Optional JSON file with claims[] to classify "
            "instead of running upstream steps."
        ),
    )
    parser.add_argument(
        "--decompose-result",
        default=None,
        help="Optional decompose result JSON to merge with extract results.",
    )
    parser.add_argument(
        "--extract-result",
        default=None,
        help="Optional extract result JSON to merge with decompose results.",
    )
    parser.add_argument(
        "--template-id",
        default=None,
        help="Defaults to template_id from context case.",
    )
    parser.add_argument(
        "--templates-dir",
        default=str(DEFAULT_TEMPLATES_DIR),
    )
    parser.add_argument("--provider", default=os.environ.get("PROVIDER", "openai"))
    parser.add_argument("--model", default=None)
    parser.add_argument(
        "--prompt-version",
        default=os.environ.get("PROMPT_VERSION", DEFAULT_PROMPT_VERSION),
    )
    parser.add_argument(
        "--results-dir",
        default=os.environ.get("RESULTS_DIR", str(DEFAULT_RESULTS_DIR)),
    )
    parser.add_argument(
        "--output-detail",
        default=os.environ.get("OUTPUT_DETAIL", DEFAULT_OUTPUT_DETAIL),
    )
    return parser.parse_args()


def _load_claims_from_args(args: argparse.Namespace, case_meta: object) -> list:
    from common.context_claims import ClinicalClaim

    if args.claims_json:
        payload = json.loads(Path(args.claims_json).read_text(encoding="utf-8"))
        claims_raw = payload.get("claims", payload)
        if not isinstance(claims_raw, list):
            raise ValueError("claims_json_must_contain_claims_list")
        return [ClinicalClaim.model_validate(item) for item in claims_raw]

    claim_lists: list[list[ClinicalClaim]] = []
    if args.decompose_result:
        record = json.loads(Path(args.decompose_result).read_text(encoding="utf-8"))
        decompose_payload = record.get("decompose_result", record)
        if isinstance(decompose_payload, dict):
            claims_raw = decompose_payload.get("claims", [])
            parsed = parse_decompose_result(
                json.dumps({"claims": claims_raw}, ensure_ascii=False)
            )
            session_id = str(record.get("session_id", case_meta.session_id))
            claim_lists.append(
                normalize_decompose_claims(parsed, session_id=session_id)
            )
    if args.extract_result:
        record = json.loads(Path(args.extract_result).read_text(encoding="utf-8"))
        extract_payload = record.get("extract_result", record)
        if isinstance(extract_payload, dict):
            parsed = parse_extract_result(
                json.dumps(extract_payload, ensure_ascii=False)
            )
            session_id = str(record.get("session_id", case_meta.session_id))
            claim_lists.append(
                normalize_extract_claims(parsed, session_id=session_id)
            )
    if claim_lists:
        return merge_claim_lists(*claim_lists)

    raise ValueError(
        "classify_claims_requires --claims-json or --decompose-result/--extract-result"
    )


def main() -> int:
    load_dotenv(AI_PIPELINE_ROOT / ".env.local", override=False)
    load_dotenv(MODULE_ROOT / ".env.local", override=True)
    args = parse_args()
    output_detail = normalize_output_detail(args.output_detail)
    prompt_version = normalize_prompt_version(args.prompt_version)
    provider = normalize_provider_name(args.provider)
    model = (args.model or default_model_for_provider(provider)).strip()
    model_spec = ModelSpec(alias=provider, provider=provider, model=model)
    prompt_path = prompt_file_path(prompt_version)
    results_dir = Path(args.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)

    cases_index = Path(args.cases)
    case_meta = select_context_case(
        load_context_cases(cases_index),
        case_id=args.case_id,
    )
    _ = load_context_case(case_meta, cases_dir=cases_index.parent)
    template_id = (args.template_id or case_meta.template_id).strip()
    templates_dir = Path(args.templates_dir)
    if not templates_dir.is_absolute():
        templates_dir = templates_dir.resolve()
    template = load_template(template_id, templates_dir=templates_dir)
    system_prompt = load_prompt(prompt_version)

    try:
        claims = _load_claims_from_args(args, case_meta)
    except Exception as exc:
        print(f"error: {exc}")
        return 1

    claims_by_id = {claim.claim_id: claim for claim in claims}
    run_started_at = datetime.now(UTC)
    output_path = results_dir / (
        f"{run_started_at.strftime('%Y%m%dT%H%M%SZ')}_session_{case_meta.session_id}_{provider}.json"
    )

    print(
        f"case={case_meta.id} session={case_meta.session_id} claims={len(claims)} "
        f"template={template_id} provider={provider} model={model}"
    )
    try:
        session_result, llm_response = run_classify_claims_session(
            claims=claims,
            template=template,
            model_spec=model_spec,
            system_prompt=system_prompt,
        )
    except Exception as exc:
        print(f"\nerror: {exc}")
        return 1

    audit = audit_claim_assignments(
        session_result,
        [claim.claim_id for claim in claims],
        template,
    )
    session_export = enrich_claim_classification_session_result_for_export(
        session_result,
        template,
        claims_by_id=claims_by_id,
    )
    output_payload: dict[str, object] = {
        "provider": provider,
        "model": model,
        "claim_classification_session_result": session_export,
        "claim_assignment_audit": audit.to_dict(),
    }
    if output_detail == "full":
        output_payload["raw_response"] = llm_response.content

    result_record: dict[str, object] = {
        "run_mode": "debug_session",
        "run_started_at": run_started_at.isoformat(),
        "run_finished_at": datetime.now(UTC).isoformat(),
        "output_path": str(output_path),
        "case_id": case_meta.id,
        "session_id": case_meta.session_id,
        "template_id": template_id,
        "claim_count": len(claims),
        "claims": [claim.model_dump(mode="json") for claim in claims],
        "provider": provider,
        "model": model,
        "prompt_version": prompt_version,
        "prompt_file": str(prompt_path.relative_to(MODULE_ROOT)),
        "output_detail": output_detail,
        **output_payload,
    }
    output_path.write_text(
        json.dumps(result_record, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("\n" + format_claim_classification_debug_output(
        session_result,
        claims_by_id=claims_by_id,
        template=template,
    ))
    print("\n" + json.dumps(audit.to_dict(), indent=2))
    print(f"\nWrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
