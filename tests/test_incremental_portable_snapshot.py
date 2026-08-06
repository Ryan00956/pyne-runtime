from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pyne_runtime as pn
import pytest


SCRIPT = """
indicator("Portable", mode="incremental", overlay=True)

def init(ctx):
    ctx.ta.sma("ma", period=2)

def on_bar(ctx, bar):
    total = ctx.state("total", 0)
    total.value += bar.close
    ctx.plot("Total", total.value)
    ctx.plot("MA", ctx.ta.sma("ma").update(bar.close))
    ctx.plotcandle(bar.open, bar.high, bar.low, bar.close, "Bars")
"""


def _bar(time: int, close: float) -> dict[str, float]:
    return {
        "time": time,
        "open": close - 0.5,
        "high": close + 1,
        "low": close - 1,
        "close": close,
        "volume": 10,
    }


def _settings(**overrides: object) -> pn.PyneSettings:
    values = {"executor_mode": "inline", "timeframe": "1S", **overrides}
    return pn.PyneSettings(**values)


def test_portable_snapshot_is_deterministic_and_restores_exact_execution() -> None:
    original = pn.PyneIncrementalSession(script=SCRIPT, settings=_settings())
    original.seed([_bar(1, 1), _bar(2, 2)])
    original.on_bar_closed(_bar(3, 3))

    first = original.snapshot_portable()
    second = original.snapshot_portable()
    restored = pn.PyneIncrementalSession.from_portable_snapshot(first, script=SCRIPT)

    assert first == second
    assert restored.snapshot_result() == original.snapshot_result()
    expected = original.on_bar_closed(_bar(4, 4))
    actual = restored.on_bar_closed(_bar(4, 4))
    assert actual == expected


def test_portable_snapshot_restores_in_a_fresh_python_process(tmp_path: Path) -> None:
    session = pn.PyneIncrementalSession(script=SCRIPT, settings=_settings())
    session.seed([_bar(1, 1), _bar(2, 2)])
    snapshot_path = tmp_path / "session.pyne-snapshot.json"
    script_path = tmp_path / "indicator.py"
    snapshot_path.write_bytes(session.snapshot_portable())
    script_path.write_text(SCRIPT, encoding="utf-8")
    probe = """
import json
import sys
import pyne_runtime as pn
payload = open(sys.argv[1], "rb").read()
script = open(sys.argv[2], encoding="utf-8").read()
session = pn.PyneIncrementalSession.from_portable_snapshot(payload, script=script)
result = session.on_bar_closed({"time": 3, "open": 2.5, "high": 4, "low": 2, "close": 3, "volume": 10})
print(json.dumps(result.output, sort_keys=True, separators=(",", ":")))
"""
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")

    completed = subprocess.run(
        [sys.executable, "-c", probe, str(snapshot_path), str(script_path)],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    expected = session.on_bar_closed(_bar(3, 3))

    assert json.loads(completed.stdout) == expected.output


def test_portable_snapshot_detects_corruption_and_script_mismatch() -> None:
    session = pn.PyneIncrementalSession(script=SCRIPT, settings=_settings())
    session.seed([_bar(1, 1)])
    payload = session.snapshot_portable()
    corrupted = json.loads(payload)
    corrupted["payload"]["bars"][0]["close"] = 999

    with pytest.raises(pn.PynePortableSnapshotError, match="checksum"):
        pn.PyneIncrementalSession.from_portable_snapshot(
            json.dumps(corrupted),
            script=SCRIPT,
        )
    with pytest.raises(pn.PynePortableSnapshotError, match="script does not match"):
        pn.PyneIncrementalSession.from_portable_snapshot(payload, script=SCRIPT + "\n# changed")


def test_portable_snapshot_enforces_size_and_json_value_boundaries() -> None:
    session = pn.PyneIncrementalSession(script=SCRIPT, settings=_settings())
    session.seed([_bar(1, 1)])

    with pytest.raises(pn.PynePortableSnapshotError, match="exceeds 32 bytes"):
        session.snapshot_portable(max_bytes=32)

    invalid_params = pn.PyneIncrementalSession(
        script=SCRIPT,
        params={"notPortable": float("nan")},
        settings=_settings(),
    )
    invalid_params.seed([_bar(1, 1)])
    with pytest.raises(pn.PynePortableSnapshotError, match="NaN or infinity"):
        invalid_params.snapshot_portable()


def test_portable_snapshot_fails_after_exact_replay_history_exceeds_max_bars() -> None:
    settings = _settings(max_bars=2)
    session = pn.PyneIncrementalSession(script=SCRIPT, settings=settings)
    session.seed([_bar(1, 1), _bar(2, 2)])
    session.on_bar_closed(_bar(3, 3))

    with pytest.raises(pn.PynePortableSnapshotError, match="history exceeded max_bars"):
        session.snapshot_portable()


class _Provider:
    capabilities = {"request.security": True}

    def get_ohlcv(self, symbol: str, timeframe: str, start: int, end: int):
        return [
            _bar(timestamp, float(timestamp))
            for timestamp in range(0, 6)
            if start <= timestamp <= end
        ]


REQUEST_SCRIPT = """
indicator("Portable Request", mode="incremental")
def on_bar(ctx, bar):
    ctx.plot("Requested", request.security("TEST", "2S", "close"))
"""


def test_portable_request_snapshot_requires_matching_provider_settings() -> None:
    settings = _settings(
        data_provider=_Provider(),
        syminfo={"tickerid": "TEST"},
    )
    session = pn.PyneIncrementalSession(script=REQUEST_SCRIPT, settings=settings)
    session.seed([_bar(1, 1), _bar(2, 2)])
    payload = session.snapshot_portable()

    with pytest.raises(pn.PynePortableSnapshotError, match="requires matching settings"):
        pn.PyneIncrementalSession.from_portable_snapshot(payload, script=REQUEST_SCRIPT)
    restored = pn.PyneIncrementalSession.from_portable_snapshot(
        payload,
        script=REQUEST_SCRIPT,
        settings=settings,
    )
    assert restored.snapshot_result() == session.snapshot_result()

    restored_with_provider = pn.PyneIncrementalSession.from_portable_snapshot(
        payload,
        script=REQUEST_SCRIPT,
        data_provider=_Provider(),
    )
    assert restored_with_provider.snapshot_result() == session.snapshot_result()
