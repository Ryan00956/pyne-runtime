from __future__ import annotations

import pytest

from pyne_runtime import PyneSettings


def test_settings_reject_invalid_security_mode() -> None:
    with pytest.raises(ValueError, match="security_mode"):
        PyneSettings(security_mode="surprise")


def test_with_security_mode_preserves_all_existing_fields() -> None:
    provider = object()
    settings = PyneSettings(
        security_mode="safe",
        cache_max_items=7,
        data_provider=provider,
        syminfo={"tickerid": "NASDAQ:AAPL", "mintick": 0.25},
        timeframe="1h",
        session={"ismarket": False},
    )

    updated = settings.with_security_mode("research")

    assert updated.security_mode == "research"
    assert updated.cache_max_items == 7
    assert updated.data_provider is provider
    assert updated.syminfo.mintick == 0.25
    assert updated.timeframe.period == "1h"
    assert updated.session.ismarket is False
