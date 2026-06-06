from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.domains.auth.access import (
    CLINICAL_ACCESS_DENIED_DETAIL,
    require_clinical_access,
)


def test_require_clinical_access_allows_enabled_user() -> None:
    user = SimpleNamespace(clinical_access_enabled=True)
    require_clinical_access(user)


def test_require_clinical_access_blocks_disabled_user() -> None:
    user = SimpleNamespace(clinical_access_enabled=False)
    with pytest.raises(HTTPException) as exc_info:
        require_clinical_access(user)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == CLINICAL_ACCESS_DENIED_DETAIL
