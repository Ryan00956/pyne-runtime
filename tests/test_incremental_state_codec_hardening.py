from __future__ import annotations

import math
import random

import numpy as np
import pyne_runtime as pn
import pytest

from pyne_runtime.incremental.state_codec import (
    decode_typed_state_graph,
    encode_typed_state_graph,
)


def _decode(graph: object, *, max_nodes: int = 10_000, max_depth: int = 32) -> object:
    return decode_typed_state_graph(graph, max_nodes=max_nodes, max_depth=max_depth)


def test_typed_state_graph_preserves_aliases_cycles_and_ndarray_dtypes() -> None:
    shared = {"values": [1, 2, 3]}
    cycle: list[object] = [shared, shared]
    cycle.append(cycle)
    value = {
        "cycle": cycle,
        "float32": np.asarray([[1.25, math.nan]], dtype=np.float32),
        "unicode": np.asarray(["甲", "乙"], dtype="U1"),
    }

    restored = _decode(encode_typed_state_graph(value, max_nodes=10_000, max_depth=32))

    assert restored["cycle"][0] is restored["cycle"][1]
    assert restored["cycle"][2] is restored["cycle"]
    assert restored["float32"].dtype == np.dtype("float32")
    assert math.isnan(float(restored["float32"][0, 1]))
    assert restored["unicode"].tolist() == ["甲", "乙"]


def test_typed_state_graph_seeded_scalar_collections_round_trip() -> None:
    generator = random.Random(20260806)
    for _ in range(100):
        value = {
            "numbers": [generator.randint(-10_000, 10_000) for _ in range(20)],
            "flags": {generator.choice([True, False]) for _ in range(5)},
            "tuple": tuple(round(generator.random(), 8) for _ in range(8)),
        }
        graph = encode_typed_state_graph(value, max_nodes=10_000, max_depth=32)
        assert _decode(graph) == value


@pytest.mark.parametrize(
    ("graph", "message"),
    [
        (
            {
                "schemaVersion": 1,
                "root": {"$ref": 0},
                "nodes": [{"kind": "list", "items": [], "extra": True}],
            },
            "node fields",
        ),
        (
            {
                "schemaVersion": 1,
                "root": {"$ref": 0},
                "nodes": [{"kind": "tuple", "items": [{"$ref": 0}]}],
            },
            "immutable cycle",
        ),
        (
            {
                "schemaVersion": 1,
                "root": {"$ref": 0},
                "nodes": [
                    {
                        "kind": "ndarray",
                        "dtype": "|S999999999",
                        "shape": [1],
                        "items": {"$ref": 1},
                    },
                    {"kind": "list", "items": ["x"]},
                ],
            },
            "byte budget",
        ),
        (
            {
                "schemaVersion": 1,
                "root": {"$ref": 0},
                "nodes": [
                    {
                        "kind": "object",
                        "type": "pyne_runtime.trace:PyneTraceRecorder",
                        "attributes": [["emit", "shadowed"]],
                    }
                ],
            },
            "shadow runtime attribute",
        ),
    ],
)
def test_typed_state_graph_rejects_adversarial_contracts(
    graph: object,
    message: str,
) -> None:
    with pytest.raises(pn.PynePortableSnapshotError, match=message):
        _decode(graph)


def test_typed_state_graph_restores_pre_span_events_trace_state() -> None:
    trace = pn.PyneTraceRecorder(enabled=True)
    graph = encode_typed_state_graph(trace, max_nodes=1_000, max_depth=16)
    trace_node = next(node for node in graph["nodes"] if node.get("kind") == "object")
    trace_node["attributes"] = [
        pair for pair in trace_node["attributes"] if pair[0] != "span_events"
    ]

    restored = _decode(graph, max_nodes=1_000, max_depth=16)

    assert restored.span_events is False
    with restored.span("compat"):
        restored.emit("inside")
    assert restored.snapshot()["timings"]["spans"][0]["name"] == "compat"


def test_typed_state_snapshot_survives_chained_long_running_restores() -> None:
    script = """
indicator("Long State", mode="incremental")
def init(ctx):
    ctx.ta.change("change", 7)
def on_bar(ctx, bar):
    total = ctx.state("total", 0.0)
    total.value += bar.close
    ctx.plot("Total", total.value)
    ctx.plot("Change", ctx.ta.change("change").update(bar.close))
"""
    settings = pn.PyneSettings(
        executor_mode="inline",
        timeframe="1S",
        incremental_retention_bars=128,
    )
    reference = pn.PyneIncrementalSession(script=script, settings=settings)
    restored = pn.PyneIncrementalSession(script=script, settings=settings)
    bars = [
        {
            "time": index + 1,
            "open": 100.0,
            "high": 102.0,
            "low": 99.0,
            "close": 100.0 + (index % 17) * 0.1,
            "volume": 1.0,
        }
        for index in range(1_000)
    ]
    for index, bar in enumerate(bars):
        expected = reference.on_bar_closed(bar)
        actual = restored.on_bar_closed(bar)
        assert actual == expected
        if index and index % 100 == 0:
            restored = pn.PyneIncrementalSession.from_portable_snapshot(
                restored.snapshot_portable(mode="state"),
                script=script,
                settings=settings,
            )
