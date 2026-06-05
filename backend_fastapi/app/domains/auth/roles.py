from __future__ import annotations

DOCTOR_ROLE = "doctor"
ADMIN_ROLE = "admin"

LEGACY_ROLE_ALIASES = {
    "medico": DOCTOR_ROLE,
    "médico": DOCTOR_ROLE,
    "administrador": ADMIN_ROLE,
}

CANONICAL_USER_ROLES = frozenset({DOCTOR_ROLE, ADMIN_ROLE})


def normalize_user_role(role: str | None) -> str:
    normalized = (role or "").strip().lower()
    if not normalized:
        return ""
    return LEGACY_ROLE_ALIASES.get(normalized, normalized)


def is_admin_role(role: str | None) -> bool:
    return normalize_user_role(role) == ADMIN_ROLE
