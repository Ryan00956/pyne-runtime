from __future__ import annotations

import pyne_runtime as pn
import pyne_runtime.cache as cache_module
from pyne_runtime.cache import PyneCache


def _bars() -> list[dict[str, float]]:
    return [
        {"time": 1, "open": 1, "high": 2, "low": 1, "close": 1, "volume": 10},
        {"time": 2, "open": 1, "high": 3, "low": 1, "close": 2, "volume": 20},
    ]


def test_cache_reuses_loader_value() -> None:
    pn.pyne_cache.clear()
    calls = {"count": 0}

    def loader() -> dict[str, int]:
        calls["count"] += 1
        return {"value": calls["count"]}

    first = pn.pyne_cache.get_or_load("x", loader)
    second = pn.pyne_cache.get_or_load("x", loader)

    assert first is second
    assert calls["count"] == 1
    pn.pyne_cache.clear()


def test_cache_ttl_starts_after_loader_completes(monkeypatch) -> None:
    now = {"value": 100.0}
    monkeypatch.setattr(cache_module.time, "time", lambda: now["value"])
    cache = PyneCache()
    calls = {"count": 0}

    def loader() -> dict[str, int]:
        calls["count"] += 1
        now["value"] += 5.0
        return {"value": calls["count"]}

    first = cache.get_or_load("slow", loader, ttl=10)

    now["value"] = 110.1
    assert cache.get_or_load("slow", lambda: {"value": 99}, ttl=10) is first
    assert calls["count"] == 1

    now["value"] = 115.1
    second = cache.get_or_load("slow", loader, ttl=10)

    assert second == {"value": 2}
    assert calls["count"] == 2


def test_cache_respects_configured_limit() -> None:
    pn.pyne_cache.clear()
    pn.pyne_cache.configure(max_items=1)
    pn.pyne_cache.get_or_load("a", lambda: 1)
    pn.pyne_cache.get_or_load("b", lambda: 2)

    assert pn.pyne_cache.stats()["size"] == 1
    assert pn.pyne_cache.stats()["maxItems"] == 1
    pn.pyne_cache.configure(max_items=32)
    pn.pyne_cache.clear()


def test_batch_script_cache_is_isolated_between_executions() -> None:
    first = pn.run(
        'indicator(cache("shared-key", lambda: "first"))',
        _bars(),
        executor_mode="inline",
    )
    second = pn.run(
        'indicator(cache("shared-key", lambda: "second"))',
        _bars(),
        executor_mode="inline",
    )

    assert first.ok and first.meta["title"] == "first"
    assert second.ok and second.meta["title"] == "second"


def test_explicit_execution_scope_can_share_cache_intentionally() -> None:
    scope = pn.PyneExecutionScope.fresh(max_items=4)
    runtime = pn.PyneRuntime(execution_scope=scope)

    first = runtime.execute('indicator(cache("shared-key", lambda: "first"))', _bars())
    second = runtime.execute('indicator(cache("shared-key", lambda: "second"))', _bars())

    assert first.ok and first.meta["title"] == "first"
    assert second.ok and second.meta["title"] == "first"
    assert scope.cache.stats()["keys"] == ["shared-key"]


def test_runtime_cache_limit_does_not_reconfigure_explicit_host_cache() -> None:
    pn.pyne_cache.clear()
    pn.pyne_cache.configure(max_items=7)

    result = pn.PyneRuntime(pn.PyneSettings(cache_max_items=1)).execute(
        'indicator(str(cache_stats()["maxItems"]))',
        _bars(),
    )

    assert result.ok and result.meta["title"] == "1"
    assert pn.pyne_cache.stats()["maxItems"] == 7
    pn.pyne_cache.configure(max_items=32)


def test_incremental_script_cache_is_scoped_to_one_session() -> None:
    script = """
indicator("Scoped cache", mode="incremental")
values = cache("values", lambda: [])

def on_bar(ctx, bar):
    values.append(bar.close)
    ctx.plot("Cache size", len(values))
"""

    first = pn.PyneIncrementalSession(script=script).seed(_bars())
    second = pn.PyneIncrementalSession(script=script).seed(_bars())

    first_values = [point["value"] for point in first.lines[0]["data"]]
    second_values = [point["value"] for point in second.lines[0]["data"]]
    assert first.ok and first_values == [1.0, 2.0]
    assert second.ok and second_values == [1.0, 2.0]

