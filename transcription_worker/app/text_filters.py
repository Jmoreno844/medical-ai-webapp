from __future__ import annotations

import re


REMOVABLE_INLINE_TAGS = {
    "tos",
    "ruido",
    "silencio",
    "carraspeo",
    "respiracion",
    "respiración",
}


def normalize_transcript(transcript: str | None) -> str:
    if not transcript:
        return ""

    def replace_tag(match: re.Match[str]) -> str:
        tag = match.group(1).strip().lower()
        if tag in REMOVABLE_INLINE_TAGS:
            return " "
        return match.group(0)

    normalized = re.sub(r"\[\s*([^\[\]]+?)\s*\]", replace_tag, transcript)
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"\s+([,.;:!?])", r"\1", normalized)
    normalized = normalized.strip()

    if re.fullmatch(r"(?:\[[^\[\]]+\]\s*)+", normalized):
        return ""

    return normalized
