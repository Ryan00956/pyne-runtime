"""Inventory Pine sources as compatibility evidence without executing or copying them.

The audit intentionally stops at feature discovery.  Pyne is a Pine-like Python
runtime, so a positive result means that a Pine concept has a Pyne API analogue;
it never means that the original Pine source can be executed as Python.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pyne_runtime.context import PyneContext  # noqa: E402
from pyne_runtime.namespace import RuntimeServices, build_script_namespace  # noqa: E402
from pyne_runtime.security import PyneSecurityPolicy  # noqa: E402
from pyne_runtime.settings import PyneSettings  # noqa: E402


SCHEMA_VERSION = 1
STANDARD_NAMESPACES = frozenset(
    {
        "alert",
        "array",
        "barstate",
        "box",
        "chart",
        "color",
        "dayofweek",
        "display",
        "extend",
        "format",
        "hline",
        "input",
        "label",
        "line",
        "linefill",
        "location",
        "math",
        "polyline",
        "position",
        "request",
        "runtime",
        "scale",
        "session",
        "shape",
        "size",
        "str",
        "syminfo",
        "ta",
        "table",
        "text",
        "ticker",
        "timeframe",
        "xloc",
        "yloc",
    }
)
HOST_OWNED_NAMESPACES = frozenset()
HOST_OWNED_FEATURES = frozenset(
    {
        "chart.bg_color",
        "chart.fg_color",
        "chart.left_visible_bar_time",
        "chart.right_visible_bar_time",
        "request.currency_rate",
        "request.dividends",
        "request.earnings",
        "request.splits",
        "syminfo.timezone",
        "syminfo.volumetype",
    }
)
RENDER_CONTRACT_GAPS = frozenset(
    {
        "linefill.new",
        "linefill.delete",
        "polyline.new",
        "plotcandle",
        "table.merge_cells",
    }
)
PYTHON_SPELLING_REWRITES = {
    "array.from": "Use array.from_values(...) because `from` is a Python keyword.",
}
LEGACY_TO_PYNE = {
    "abs": "math.abs",
    "study": "indicator",
    "security": "request.security",
    "alma": "ta.alma",
    "avg": "math.avg",
    "atr": "ta.atr",
    "barssince": "ta.barssince",
    "bb": "ta.bb",
    "cci": "ta.cci",
    "ceil": "math.ceil",
    "change": "ta.change",
    "correlation": "ta.correlation",
    "cos": "math.cos",
    "cross": "ta.cross",
    "crossover": "ta.crossover",
    "crossunder": "ta.crossunder",
    "cum": "ta.cum",
    "dev": "ta.dev",
    "ema": "ta.ema",
    "exp": "math.exp",
    "falling": "ta.falling",
    "fixnan": "fixnan",
    "floor": "math.floor",
    "highest": "ta.highest",
    "highestbars": "ta.highestbars",
    "hma": "ta.hma",
    "hour": "time.hour",
    "linreg": "ta.linreg",
    "log": "math.log",
    "log10": "math.log10",
    "lowest": "ta.lowest",
    "lowestbars": "ta.lowestbars",
    "macd": "ta.macd",
    "max": "math.max",
    "mfi": "ta.mfi",
    "min": "math.min",
    "minute": "time.minute",
    "mom": "ta.mom",
    "month": "time.month",
    "pivothigh": "ta.pivothigh",
    "pivotlow": "ta.pivotlow",
    "pow": "math.pow",
    "rising": "ta.rising",
    "rma": "ta.rma",
    "roc": "ta.roc",
    "round": "math.round",
    "rsi": "ta.rsi",
    "sar": "ta.sar",
    "second": "time.second",
    "sign": "math.sign",
    "sin": "math.sin",
    "sma": "ta.sma",
    "stdev": "ta.stdev",
    "stoch": "ta.stoch",
    "sqrt": "math.sqrt",
    "sum": "math.sum",
    "supertrend": "ta.supertrend",
    "swma": "ta.swma",
    "tan": "math.tan",
    "time": "time",
    "timestamp": "time.timestamp",
    "tsi": "ta.tsi",
    "heikinashi": "ticker.heikinashi",
    "tostring": "str.tostring",
    "valuewhen": "ta.valuewhen",
    "vwap": "ta.vwap",
    "vwma": "ta.vwma",
    "wma": "ta.wma",
    "wpr": "ta.wpr",
    "year": "time.year",
    "dayofmonth": "time.dayofmonth",
    "dayofweek": "time.dayofweek",
}
TRACKED_TOP_LEVEL_CALLS = frozenset(
    {
        *LEGACY_TO_PYNE,
        "alert",
        "alertcondition",
        "barcolor",
        "bgcolor",
        "box",
        "color",
        "fill",
        "hline",
        "indicator",
        "input",
        "label",
        "line",
        "plot",
        "plotarrow",
        "plotcandle",
        "plotchar",
        "plotshape",
        "strategy",
        "table",
        "time",
    }
)
TOP_LEVEL_SYNTAX_REWRITES = {
    "alert": (
        "emit_signal",
        "Rewrite imperative alert(...) calls as an explicit vector condition passed to "
        "emit_signal(...).",
    ),
    "box": ("None / box.new(...)", "Replace Pine object type casts with Python None or handles."),
    "color": ("na / color.*", "Replace Pine color type casts with na or color values."),
    "label": (
        "None / label.new(...)",
        "Replace Pine object type casts with Python None or handles.",
    ),
    "line": ("None / line.new(...)", "Replace Pine object type casts with Python None or handles."),
    "table": (
        "None / table.new(...)",
        "Replace Pine object type casts with Python None or handles.",
    ),
}
FEATURE_SYNTAX_REWRITES = {
    "alert.freq_all": (
        "emit_signal(...) + host alert policy",
        "This constant configures TradingView realtime alert scheduling. Rewrite the "
        "alert event as emit_signal(...) and configure repeated intrabar delivery in the host.",
    ),
    "alert.freq_once_per_bar": (
        "emit_signal(...) + host alert policy",
        "This constant configures TradingView realtime alert scheduling. Rewrite the "
        "alert event as emit_signal(...) and configure per-bar deduplication in the host.",
    ),
    "alert.freq_once_per_bar_close": (
        "emit_signal(...) + host alert policy",
        "This constant configures TradingView realtime alert scheduling. Rewrite the "
        "alert event as emit_signal(...) and configure closed-bar delivery in the host.",
    ),
}
IGNORED_CALL_NAMES = frozenset(
    {
        "and",
        "bool",
        "color",
        "else",
        "float",
        "for",
        "if",
        "int",
        "line",
        "not",
        "or",
        "string",
        "switch",
        "to",
        "while",
    }
)
SOURCE_FEATURE_PATTERNS = {
    "pine.reassignment": re.compile(r":="),
    "pine.ternary": re.compile(r"\?"),
    "pine.function_declaration": re.compile(
        r"(?m)^[ \t]*(?:[A-Za-z_][A-Za-z0-9_<>\[\]]*[ \t]+)*"
        r"[A-Za-z_][A-Za-z0-9_]*[ \t]*\([^=\n]*\)[ \t]*=>"
    ),
    "pine.type_declaration": re.compile(r"(?m)^[ \t]*type[ \t]+[A-Za-z_]"),
    "pine.method_declaration": re.compile(r"(?m)^[ \t]*(?:export[ \t]+)?method[ \t]+"),
    "pine.import": re.compile(r"(?m)^[ \t]*import[ \t]+"),
    "pine.loop": re.compile(r"(?m)^[ \t]*(?:for|while)[ \t]+"),
}
VERSION_PATTERN = re.compile(r"(?m)^[ \t]*//@version[ \t]*=[ \t]*(\d+)")
DECLARATION_PATTERNS = (
    ("indicator", re.compile(r"(?m)^[ \t]*indicator[ \t]*\(")),
    ("strategy", re.compile(r"(?m)^[ \t]*strategy[ \t]*\(")),
    ("study", re.compile(r"(?m)^[ \t]*study[ \t]*\(")),
    ("library", re.compile(r"(?m)^[ \t]*library[ \t]*\(")),
)
NAMESPACE_PATTERN = re.compile(
    rf"\b({'|'.join(sorted(STANDARD_NAMESPACES))})\.([A-Za-z_][A-Za-z0-9_]*)"
)
IMPORT_PATTERN = re.compile(
    r"(?m)^[ \t]*import[ \t]+"
    r"(?P<owner>[A-Za-z_][A-Za-z0-9_]*)/"
    r"(?P<library>[A-Za-z_][A-Za-z0-9_]*)/"
    r"(?P<version>[0-9]+)"
    r"(?:[ \t]+as[ \t]+(?P<alias>[A-Za-z_][A-Za-z0-9_]*))?[ \t]*$"
)
CALL_PATTERN = re.compile(r"(?<![\w.])([A-Za-z_][A-Za-z0-9_]*)[ \t]*\(")
LINE_COMMENT_PATTERN = re.compile(r"(?m)//.*$")
PINE_LIBRARY_FEATURE_PREFIX = "pine-library:"
PINE_LIBRARY_MEMBER_SEPARATOR = "#"


@dataclass
class FeatureUsage:
    occurrences: int = 0
    files: set[str] | None = None

    def add(self, filename: str, occurrences: int) -> None:
        self.occurrences += occurrences
        if self.files is None:
            self.files = set()
        self.files.add(filename)


@dataclass(frozen=True)
class RuntimeSurface:
    top_level_names: frozenset[str]
    callable_top_level_names: frozenset[str]
    namespace_members: dict[str, frozenset[str]]


def build_runtime_surface() -> RuntimeSurface:
    """Inspect the real runtime namespace instead of maintaining a second API list."""
    settings = PyneSettings(executor_mode="inline")
    context = PyneContext.from_ohlcv(
        [
            {
                "time": 1,
                "open": 1,
                "high": 1,
                "low": 1,
                "close": 1,
                "volume": 1,
            },
        ]
    )
    services = RuntimeServices(
        ctx=context,
        settings=settings,
        params={},
        policy=PyneSecurityPolicy.from_settings(settings),
    )
    namespace = build_script_namespace(services)
    top_level = frozenset(namespace) - {"__builtins__"}
    callable_top_level = frozenset(name for name in top_level if callable(namespace[name]))
    namespace_members: dict[str, frozenset[str]] = {}
    for name in STANDARD_NAMESPACES:
        value = namespace.get(name)
        if value is None:
            continue
        namespace_members[name] = frozenset(
            member for member in dir(value) if not member.startswith("_")
        )
    return RuntimeSurface(top_level, callable_top_level, namespace_members)


def build_report(corpus: Path) -> dict[str, Any]:
    files = sorted(path for path in corpus.iterdir() if path.is_file())
    if not files:
        raise ValueError(f"no Pine source files found in {corpus}")

    versions: Counter[str] = Counter()
    declarations: Counter[str] = Counter()
    feature_usage: dict[str, FeatureUsage] = defaultdict(FeatureUsage)
    source_features: dict[str, FeatureUsage] = defaultdict(FeatureUsage)
    total_bytes = 0
    surface = build_runtime_surface()

    for path in files:
        raw = path.read_text(encoding="utf-8-sig", errors="replace")
        total_bytes += path.stat().st_size
        version_match = VERSION_PATTERN.search(raw)
        versions[version_match.group(1) if version_match else "none"] += 1
        declarations[_declaration(raw)] += 1
        code = LINE_COMMENT_PATTERN.sub("", raw)
        imported_aliases = _import_aliases(code)

        per_file: Counter[str] = Counter()
        for match in NAMESPACE_PATTERN.finditer(code):
            namespace, member = match.groups()
            library = imported_aliases.get(namespace)
            if library is not None and member not in surface.namespace_members.get(
                namespace, frozenset()
            ):
                per_file[_pine_library_feature(library, member)] += 1
            else:
                per_file[f"{namespace}.{member}"] += 1

        for alias, library in imported_aliases.items():
            if alias in STANDARD_NAMESPACES:
                continue
            alias_pattern = re.compile(
                rf"\b{re.escape(alias)}\.([A-Za-z_][A-Za-z0-9_]*)"
            )
            for match in alias_pattern.finditer(code):
                per_file[_pine_library_feature(library, match.group(1))] += 1

        for match in CALL_PATTERN.finditer(code):
            name = match.group(1)
            if name in TRACKED_TOP_LEVEL_CALLS:
                per_file[name] += 1
        for feature, occurrences in per_file.items():
            feature_usage[feature].add(path.name, occurrences)

        for feature, pattern in SOURCE_FEATURE_PATTERNS.items():
            occurrences = len(pattern.findall(code))
            if occurrences:
                source_features[feature].add(path.name, occurrences)

    feature_rows = [
        _feature_row(feature, usage, surface) for feature, usage in feature_usage.items()
    ]
    feature_rows.sort(
        key=lambda item: (
            -item["fileCount"],
            -item["occurrenceCount"],
            item["feature"],
        )
    )
    source_rows = [
        _source_feature_row(feature, usage) for feature, usage in source_features.items()
    ]
    source_rows.sort(key=lambda item: (-item["fileCount"], item["feature"]))

    status_files: dict[str, set[str]] = defaultdict(set)
    status_features: Counter[str] = Counter()
    for row in feature_rows:
        status = row["status"]
        status_features[status] += 1
        status_files[status].update(row["examples"])
        # examples are capped, so use the full internal set for exact file totals.
        usage = feature_usage[row["feature"]]
        status_files[status].update(usage.files or ())

    return {
        "schemaVersion": SCHEMA_VERSION,
        "sourcePolicy": {
            "executesPine": False,
            "copiesSource": False,
            "claim": (
                "Feature coverage means a Pyne API analogue exists after a Python rewrite; "
                "it does not mean the Pine source is directly executable."
            ),
        },
        "summary": {
            "fileCount": len(files),
            "byteCount": total_bytes,
            "versions": dict(sorted(versions.items())),
            "declarations": dict(sorted(declarations.items())),
        },
        "compatibility": {
            status: {
                "featureCount": status_features[status],
                "fileCount": len(status_files[status]),
            }
            for status in sorted(status_features)
        },
        "features": feature_rows,
        "sourceFeatures": source_rows,
    }


def _declaration(source: str) -> str:
    for name, pattern in DECLARATION_PATTERNS:
        if pattern.search(source):
            return name
    return "unknown"


def _import_aliases(source: str) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for match in IMPORT_PATTERN.finditer(source):
        library_name = match.group("library")
        alias = match.group("alias") or library_name
        aliases[alias] = (
            f"{match.group('owner')}/{library_name}/{match.group('version')}"
        )
    return aliases


def _pine_library_feature(library: str, member: str) -> str:
    return (
        f"{PINE_LIBRARY_FEATURE_PREFIX}{library}"
        f"{PINE_LIBRARY_MEMBER_SEPARATOR}{member}"
    )


def _feature_row(
    feature: str,
    usage: FeatureUsage,
    surface: RuntimeSurface,
) -> dict[str, Any]:
    status, target, note = classify_feature(feature, surface)
    files = sorted(usage.files or ())
    return {
        "feature": feature,
        "status": status,
        "pyneTarget": target,
        "note": note,
        "fileCount": len(files),
        "occurrenceCount": usage.occurrences,
        "examples": files[:5],
    }


def _source_feature_row(feature: str, usage: FeatureUsage) -> dict[str, Any]:
    files = sorted(usage.files or ())
    return {
        "feature": feature,
        "status": "syntax-rewrite",
        "fileCount": len(files),
        "occurrenceCount": usage.occurrences,
        "examples": files[:5],
    }


def classify_feature(
    feature: str,
    surface: RuntimeSurface,
) -> tuple[str, str | None, str]:
    if feature.startswith(PINE_LIBRARY_FEATURE_PREFIX):
        library_and_member = feature.removeprefix(PINE_LIBRARY_FEATURE_PREFIX)
        library, _, member = library_and_member.partition(PINE_LIBRARY_MEMBER_SEPARATOR)
        return (
            "library-rewrite",
            None,
            f"{member} is supplied by the imported Pine library {library}, not by the "
            "core Pine namespace. Port or replace that pinned library dependency explicitly.",
        )
    if feature in PYTHON_SPELLING_REWRITES:
        return "syntax-rewrite", "array.from_values", PYTHON_SPELLING_REWRITES[feature]
    if feature in FEATURE_SYNTAX_REWRITES:
        target, note = FEATURE_SYNTAX_REWRITES[feature]
        return "syntax-rewrite", target, note
    if feature in TOP_LEVEL_SYNTAX_REWRITES:
        target, note = TOP_LEVEL_SYNTAX_REWRITES[feature]
        return "syntax-rewrite", target, note
    if feature in HOST_OWNED_FEATURES or feature.split(".", 1)[0] in HOST_OWNED_NAMESPACES:
        return "host-gap", None, "Requires data or state owned by the embedding host."
    if feature in RENDER_CONTRACT_GAPS:
        return "render-gap", None, "Requires an explicit Pyne output and host Render IR contract."

    if "." in feature:
        namespace, member = feature.split(".", 1)
        if member in surface.namespace_members.get(namespace, frozenset()):
            return "api-covered", feature, "Available after rewriting the indicator as Pyne Python."
        return "runtime-gap", None, "No matching member exists in the current Pyne namespace."

    if feature == "input":
        if feature in surface.callable_top_level_names:
            return "api-covered", feature, "Legacy inferred input is callable in Pyne."
        return "runtime-gap", None, "The current input namespace is not callable."

    if feature == "plotcandle":
        return "render-gap", None, "Requires an explicit candle-series Render IR contract."

    target = LEGACY_TO_PYNE.get(feature)
    if target is not None:
        if feature in surface.callable_top_level_names:
            return "api-covered", feature, "Legacy alias is available after a Python rewrite."
        if _target_exists(target, surface):
            return "syntax-rewrite", target, f"Rewrite legacy {feature}(...) as {target}(...)."
        return "runtime-gap", target, f"Neither {feature}(...) nor {target}(...) is available."

    if feature in IGNORED_CALL_NAMES:
        return "manual-review", None, "Language token or user-defined symbol."
    if feature in surface.callable_top_level_names:
        return "api-covered", feature, "Available after rewriting the indicator as Pyne Python."
    return "manual-review", None, "User-defined call or unclassified Pine feature."


def _target_exists(target: str, surface: RuntimeSurface) -> bool:
    if "." not in target:
        return target in surface.callable_top_level_names
    namespace, member = target.split(".", 1)
    return member in surface.namespace_members.get(namespace, frozenset())


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Pine Corpus Compatibility Audit",
        "",
        "> This report inventories APIs only. It never executes Pine source and does not "
        "claim source-level compatibility.",
        "",
        f"- Files: {summary['fileCount']}",
        f"- Bytes: {summary['byteCount']}",
        f"- Versions: {_mapping_text(summary['versions'])}",
        f"- Declarations: {_mapping_text(summary['declarations'])}",
        "",
        "## Compatibility buckets",
        "",
        "| Status | Features | Files touched |",
        "| --- | ---: | ---: |",
    ]
    for status, values in report["compatibility"].items():
        lines.append(f"| {status} | {values['featureCount']} | {values['fileCount']} |")
    lines.extend(
        [
            "",
            "## Standard-library, imported-library, and host features",
            "",
            "| Feature | Status | Files | Uses | Pyne target |",
            "| --- | --- | ---: | ---: | --- |",
        ]
    )
    for item in report["features"]:
        lines.append(
            f"| `{item['feature']}` | {item['status']} | {item['fileCount']} | "
            f"{item['occurrenceCount']} | `{item['pyneTarget'] or ''}` |"
        )
    lines.extend(
        [
            "",
            "## Pine syntax requiring a Python rewrite",
            "",
            "| Feature | Files | Uses |",
            "| --- | ---: | ---: |",
        ]
    )
    for item in report["sourceFeatures"]:
        lines.append(f"| `{item['feature']}` | {item['fileCount']} | {item['occurrenceCount']} |")
    return "\n".join(lines) + "\n"


def _mapping_text(values: dict[str, Any]) -> str:
    return ", ".join(f"{key}={value}" for key, value in values.items())


def _write_output(path: Path | None, text: str) -> None:
    if path is None:
        print(text, end="")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    print(f"Wrote Pine compatibility audit: {path}")


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inventory Pine source features without executing or copying source code.",
    )
    parser.add_argument("corpus", type=Path, help="Directory containing Pine source files.")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        report = build_report(args.corpus)
    except (OSError, ValueError) as exc:
        print(f"Pine corpus audit failed: {exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    else:
        rendered = render_markdown(report)
    _write_output(args.output, rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
