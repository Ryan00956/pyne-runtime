from __future__ import annotations

from pathlib import Path
from typing import Any

import pyne_runtime as pn


EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples"
EXAMPLES_README = EXAMPLES_DIR / "README.md"


def test_all_packaged_examples_run() -> None:
    data = pn.read_ohlcv(EXAMPLES_DIR / "sample_ohlcv.csv")

    for script in sorted(EXAMPLES_DIR.glob("*.py")):
        result = pn.run(script, data)

        assert result.ok, f"{script.name} failed: {result.error}"
        assert result.meta.get("title")
        assert result.lines or result.output


def test_examples_readme_covers_packaged_scripts_and_data_fixture() -> None:
    body = EXAMPLES_README.read_text(encoding="utf-8")

    for script in sorted(EXAMPLES_DIR.glob("*.py")):
        assert f"`{script.name}`" in body

    assert "`sample_ohlcv.csv`" in body
    assert "pyne run examples/ma_cross.py" in body
    assert "pyne validate examples/ma_cross.py" in body


def test_host_output_contract_example_matches_schema() -> None:
    data = pn.read_ohlcv(EXAMPLES_DIR / "sample_ohlcv.csv")
    result = pn.run(EXAMPLES_DIR / "host_output_contract.py", data)
    schema = pn.schema()["output"]

    assert result.ok, result.error
    assert result.schema_version == schema["schemaVersion"]

    for key, contract in schema["renderables"].items():
        assert key in result.output
        _assert_required_fields(result.output[key][0], contract["required"])

        point_required = contract.get("pointRequired")
        if point_required:
            _assert_required_fields(result.output[key][0]["data"][0], point_required)

        region_required = contract.get("regionRequired")
        if region_required:
            _assert_required_fields(result.output[key][0]["regions"][0], region_required)

    objects = result.output["objects"]
    object_contract = schema["objects"]
    assert set(objects) == set(object_contract["groups"])
    for group in object_contract["groups"]:
        _assert_required_fields(objects[group][0], object_contract[group]["required"])

    table_cell = objects["tables"][0]["cells"][0]
    _assert_required_fields(table_cell, object_contract["tables"]["cellRequired"])


def _assert_required_fields(payload: dict[str, Any], fields: list[str]) -> None:
    for field in fields:
        assert field in payload
