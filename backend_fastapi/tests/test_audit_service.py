from __future__ import annotations

from app.core.config import Settings
from app.domains.audit.service import (
    encrypt_ip,
    network_prefix_for_ip,
    pseudonymize_ip,
    summarize_user_agent,
)


def test_pseudonymize_ip_is_stable_for_equivalent_values() -> None:
    settings = Settings(
        JWT_SECRET_KEY="test-secret-at-least-32-bytes-long",
        AUDIT_IP_HMAC_SECRET="test-audit-ip-hmac-secret",
        AUDIT_IP_ENCRYPTION_KEY="Zb5QQ8mVdPPKZkhq0dQECjSlxMdkh2c8WqY2d9I4I1o=",
    )

    assert pseudonymize_ip("181.52.34.9", settings.audit_ip_hmac_secret) == pseudonymize_ip(
        "181.52.34.9",
        settings.audit_ip_hmac_secret,
    )


def test_network_prefix_uses_ipv4_and_ipv6_safe_ranges() -> None:
    assert network_prefix_for_ip("181.52.34.9") == "181.52.34.0/24"
    assert network_prefix_for_ip("2001:db8::1234") == "2001:db8::/64"


def test_encrypt_ip_returns_opaque_token() -> None:
    encrypted = encrypt_ip(
        "181.52.34.9",
        "Zb5QQ8mVdPPKZkhq0dQECjSlxMdkh2c8WqY2d9I4I1o=",
    )

    assert encrypted != "181.52.34.9"
    assert len(encrypted) > 20


def test_user_agent_summary_truncates_and_compacts() -> None:
    summary = summarize_user_agent("Mozilla/5.0   Example   Browser" * 20)

    assert summary is not None
    assert "  " not in summary
    assert len(summary) == 150
