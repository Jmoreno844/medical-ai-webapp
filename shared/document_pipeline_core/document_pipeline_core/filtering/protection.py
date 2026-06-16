from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

FULL_TRANSCRIPT_TURN_THRESHOLD = 180
WINDOW_RADIUS = 2

_DOCTOR_SPEAKERS = frozenset({"doctor", "medico", "physician", "dr", "clinician"})
_PATIENT_SPEAKERS = frozenset({"patient", "paciente", "pt"})

_ADMIN_NOISE_RE = re.compile(
    r"\b(?:audio|microfono|micr[oó]fono|conexion|conexi[oó]n|internet|wifi|"
    r"pago|pag[oa]r|estacionamiento|sala de espera|factura|copago|"
    r"seguro administrativo|no se escucha|no te escucho|se cort[oó])\b",
    re.IGNORECASE,
)
_BACKCHANNEL_RE = re.compile(
    r"^(?:aj[aá]|ok|okay|mmm+|eh+|uh+|ja|s[ií]|vale|claro|entiendo)\.?$",
    re.IGNORECASE,
)
_GREETING_ONLY_RE = re.compile(
    r"^(?:buen(?:os|as)\s+(?:d[ií]as|tardes|noches)|hola|gracias|"
    r"hasta luego|chao|adi[oó]s|muchas gracias)[\s.!]*$",
    re.IGNORECASE,
)
_CLINICAL_SIGNAL_RE = re.compile(
    r"\b(?:dolor|fiebre|tos|fatiga|cansancio|mareo|n[aá]usea|v[oó]mito|"
    r"diarrea|sangr|presi[oó]n|diabetes|hipertensi[oó]n|alerg|medicament|"
    r"pastilla|mg\b|ml\b|dosis|laboratorio|an[aá]lisis|ecg|electro|"
    r"radiograf|tomograf|resonancia|diagn[oó]stic|s[ií]ntoma|antecedent|"
    r"cirug[ií]a|hospital|tratamiento|receta|plan|seguimiento|"
    r"embaraz|semana|mes|a[nñ]o|peso|imc|frecuencia|cardiac|pecho|"
    r"coraz[oó]n|pulm[oó]n|falta de aire|disnea|edema|inflam)\w*\b",
    re.IGNORECASE,
)
_PATIENT_CONCERN_RE = re.compile(
    r"\b(?:cree que|creo que|pens[eé] que|me preocupa|temor|miedo|exager|"
    r"ser[aá] grave|algo malo)\b",
    re.IGNORECASE,
)
_DOCTOR_PLAN_RE = re.compile(
    r"\b(?:voy a|vamos a|examin|explor|auscult|orden(ar|o)|solicit|"
    r"recet|indic|puede ser|impresi[oó]n|diagn[oó]stic|tratamiento|"
    r"seguimiento|control|ecg|electrocardiograma|laboratorio|radiograf|"
    r"tomograf|hospitaliz)\w*\b",
    re.IGNORECASE,
)
_IDENTITY_DEMOGRAPHIC_RE = re.compile(
    r"\b(?:edad|a[nñ]os?|nombre|fecha de nacimiento|nacim|embaraz|gestaci[oó]n|"
    r"g[eé]nero|sexo|ocupaci[oó]n|trabajo|estado civil)\b",
    re.IGNORECASE,
)
_SHORT_ANSWER_MAX_CHARS = 40


@dataclass(frozen=True, slots=True)
class TurnProtectionResult:
    drop_eligible_turn_ids: list[int]
    protected_keep_reasons: dict[int, str]
    all_turn_ids: list[int]

    @property
    def eligible_count(self) -> int:
        return len(self.drop_eligible_turn_ids)

    @property
    def protected_count(self) -> int:
        return len(self.protected_keep_reasons)


@dataclass(frozen=True, slots=True)
class FilteringRunDiagnostics:
    drop_eligible_turn_ids: list[int]
    protected_keep_reasons: dict[int, str]
    eligible_count: int
    protected_count: int
    filtering_payload_mode: str | None
    llm_skipped: bool = False

    @classmethod
    def from_protection(
        cls,
        protection: TurnProtectionResult,
        *,
        filtering_payload_mode: str | None,
        llm_skipped: bool = False,
    ) -> FilteringRunDiagnostics:
        return cls(
            drop_eligible_turn_ids=list(protection.drop_eligible_turn_ids),
            protected_keep_reasons=dict(protection.protected_keep_reasons),
            eligible_count=protection.eligible_count,
            protected_count=protection.protected_count,
            filtering_payload_mode=filtering_payload_mode,
            llm_skipped=llm_skipped,
        )


def normalize_speaker(raw: str) -> str:
    normalized = unicodedata.normalize("NFKD", raw.strip().lower())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    if normalized in _DOCTOR_SPEAKERS:
        return "doctor"
    if normalized in _PATIENT_SPEAKERS:
        return "patient"
    return normalized


def normalize_text(raw: str) -> str:
    normalized = unicodedata.normalize("NFKD", raw.strip().lower())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(normalized.split())


def is_doctor_speaker(speaker: str) -> bool:
    return normalize_speaker(speaker) == "doctor"


def is_patient_speaker(speaker: str) -> bool:
    return normalize_speaker(speaker) == "patient"


def has_clinical_signal(text: str) -> bool:
    return bool(_CLINICAL_SIGNAL_RE.search(normalize_text(text)))


def is_admin_noise(text: str) -> bool:
    normalized = normalize_text(text)
    if not _ADMIN_NOISE_RE.search(normalized):
        return False
    return not has_clinical_signal(text)


def is_pure_backchannel(text: str) -> bool:
    return bool(_BACKCHANNEL_RE.fullmatch(normalize_text(text)))


def is_short_answer(text: str) -> bool:
    normalized = normalize_text(text)
    if not normalized:
        return False
    return len(normalized) <= _SHORT_ANSWER_MAX_CHARS


def _neighbor_indices(catalog: list[dict[str, object]], index: int) -> list[int]:
    neighbors: list[int] = []
    if index > 0:
        neighbors.append(index - 1)
    if index + 1 < len(catalog):
        neighbors.append(index + 1)
    return neighbors


def _neighbor_is_doctor_clinical_question(
    catalog: list[dict[str, object]],
    index: int,
) -> bool:
    for neighbor_index in _neighbor_indices(catalog, index):
        turn = catalog[neighbor_index]
        speaker = str(turn.get("speaker", ""))
        text = str(turn.get("text", ""))
        if is_doctor_speaker(speaker) and "?" in text and not is_admin_noise(text):
            return True
    return False


def _has_clinical_neighborhood(
    catalog: list[dict[str, object]],
    index: int,
) -> bool:
    for neighbor_index in _neighbor_indices(catalog, index):
        neighbor_text = str(catalog[neighbor_index].get("text", ""))
        if has_clinical_signal(neighbor_text):
            return True
        if _neighbor_is_doctor_clinical_question(catalog, neighbor_index):
            return True
    return _neighbor_is_doctor_clinical_question(catalog, index)


def protection_reason_for_turn(
    catalog: list[dict[str, object]],
    index: int,
) -> str | None:
    turn = catalog[index]
    speaker = str(turn.get("speaker", ""))
    text = str(turn.get("text", ""))
    normalized = normalize_text(text)

    if not normalized:
        return None

    if is_admin_noise(text):
        return None

    if is_pure_backchannel(text):
        return None

    if _GREETING_ONLY_RE.fullmatch(normalized):
        return None

    if is_doctor_speaker(speaker) and "?" in text:
        return "doctor_clinical_question"

    if is_patient_speaker(speaker) and "?" in text:
        if has_clinical_signal(text) or _neighbor_is_doctor_clinical_question(
            catalog, index
        ):
            return "patient_clinical_question"

    if is_patient_speaker(speaker) and _PATIENT_CONCERN_RE.search(text):
        return "patient_concern_perception"

    if is_doctor_speaker(speaker) and _DOCTOR_PLAN_RE.search(text):
        return "doctor_explanation_or_plan"

    if is_short_answer(text) and _has_clinical_neighborhood(catalog, index):
        return "short_contextual_answer"

    if has_clinical_signal(text):
        return "clinical_signal"

    if _IDENTITY_DEMOGRAPHIC_RE.search(text):
        return "identity_demographic"

    return None


def compute_turn_protection(
    catalog: list[dict[str, object]],
) -> TurnProtectionResult:
    protected_keep_reasons: dict[int, str] = {}
    all_turn_ids: list[int] = []

    for index, turn in enumerate(catalog):
        turn_id = int(turn["turn_id"])
        all_turn_ids.append(turn_id)
        reason = protection_reason_for_turn(catalog, index)
        if reason is not None:
            protected_keep_reasons[turn_id] = reason

    drop_eligible_turn_ids = [
        turn_id for turn_id in all_turn_ids if turn_id not in protected_keep_reasons
    ]
    return TurnProtectionResult(
        drop_eligible_turn_ids=drop_eligible_turn_ids,
        protected_keep_reasons=protected_keep_reasons,
        all_turn_ids=all_turn_ids,
    )


def sanitize_filtering_drop_turn_ids(
    drop_turn_ids: list[int],
    *,
    drop_eligible_turn_ids: list[int],
) -> list[int]:
    eligible_set = set(drop_eligible_turn_ids)
    seen: set[int] = set()
    sanitized: list[int] = []
    for turn_id in drop_turn_ids:
        if turn_id not in eligible_set or turn_id in seen:
            continue
        seen.add(turn_id)
        sanitized.append(turn_id)
    return sanitized


def _windowed_turn_indices(
    catalog: list[dict[str, object]],
    eligible_turn_ids: list[int],
    *,
    window_radius: int,
) -> set[int]:
    id_to_index = {int(turn["turn_id"]): index for index, turn in enumerate(catalog)}
    indices: set[int] = set()
    for turn_id in eligible_turn_ids:
        center = id_to_index.get(turn_id)
        if center is None:
            continue
        start = max(0, center - window_radius)
        end = min(len(catalog), center + window_radius + 1)
        indices.update(range(start, end))
    return indices


def build_filtering_v002_payload(
    catalog: list[dict[str, object]],
    protection: TurnProtectionResult,
) -> tuple[dict[str, object], str]:
    eligible_set = set(protection.drop_eligible_turn_ids)
    if len(catalog) <= FULL_TRANSCRIPT_TURN_THRESHOLD:
        payload_mode = "full_transcript"
        selected_turns = catalog
    else:
        payload_mode = "windowed_context"
        indices = _windowed_turn_indices(
            catalog,
            protection.drop_eligible_turn_ids,
            window_radius=WINDOW_RADIUS,
        )
        selected_turns = [catalog[index] for index in sorted(indices)]

    turns_payload: list[dict[str, object]] = []
    for turn in selected_turns:
        turn_id = int(turn["turn_id"])
        turns_payload.append(
            {
                "turn_id": turn_id,
                "speaker": turn["speaker"],
                "text": turn["text"],
                "can_drop": turn_id in eligible_set,
            }
        )

    return (
        {
            "drop_eligible_turn_ids": list(protection.drop_eligible_turn_ids),
            "turns": turns_payload,
        },
        payload_mode,
    )


__all__ = [
    "FULL_TRANSCRIPT_TURN_THRESHOLD",
    "WINDOW_RADIUS",
    "FilteringRunDiagnostics",
    "TurnProtectionResult",
    "build_filtering_v002_payload",
    "compute_turn_protection",
    "has_clinical_signal",
    "is_admin_noise",
    "is_doctor_speaker",
    "is_patient_speaker",
    "is_pure_backchannel",
    "is_short_answer",
    "normalize_speaker",
    "normalize_text",
    "protection_reason_for_turn",
    "sanitize_filtering_drop_turn_ids",
]
