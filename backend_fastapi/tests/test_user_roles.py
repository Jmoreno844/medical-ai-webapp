from app.domains.auth.roles import ADMIN_ROLE, DOCTOR_ROLE, is_admin_role, normalize_user_role


def test_normalize_user_role_maps_legacy_values() -> None:
    assert normalize_user_role("doctor") == DOCTOR_ROLE
    assert normalize_user_role("medico") == DOCTOR_ROLE
    assert normalize_user_role("Médico") == DOCTOR_ROLE
    assert normalize_user_role("administrador") == ADMIN_ROLE
    assert normalize_user_role(" admin ") == ADMIN_ROLE


def test_is_admin_role_uses_canonical_and_legacy_values() -> None:
    assert is_admin_role("admin") is True
    assert is_admin_role("administrador") is True
    assert is_admin_role("doctor") is False
