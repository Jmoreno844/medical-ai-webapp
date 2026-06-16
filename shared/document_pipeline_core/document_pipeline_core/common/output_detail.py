from __future__ import annotations

DEFAULT_OUTPUT_DETAIL = "compact"
ALLOWED_OUTPUT_DETAILS = ("compact", "full")


def normalize_output_detail(raw: str) -> str:
    normalized = raw.strip().lower()
    if normalized in ALLOWED_OUTPUT_DETAILS:
        return normalized
    raise ValueError(
        f"ai_pipeline_output_detail_invalid: {raw!r} "
        f"(expected one of {', '.join(ALLOWED_OUTPUT_DETAILS)})"
    )
