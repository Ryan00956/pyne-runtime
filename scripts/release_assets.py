"""Validate and prepare deterministic GitHub Release assets."""
from __future__ import annotations

import argparse
import hashlib
import re
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKSUMS_NAME = "SHA256SUMS"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True, help="Release tag, for example v0.2.0rc1.")
    parser.add_argument(
        "--dist-dir",
        required=True,
        type=Path,
        help="Directory containing exactly the wheel and source distribution.",
    )
    parser.add_argument(
        "--project-file",
        default=ROOT / "pyproject.toml",
        type=Path,
        help="Project metadata used to validate the tag and artifact names.",
    )
    parser.add_argument(
        "--changelog",
        default=ROOT / "CHANGELOG.md",
        type=Path,
        help="Changelog containing the release section.",
    )
    parser.add_argument(
        "--notes-file",
        type=Path,
        help="Optional destination for release notes extracted from the changelog.",
    )
    args = parser.parse_args(argv)

    version = _project_version(args.project_file)
    _validate_tag(args.tag, version)
    artifacts = _validate_artifacts(args.dist_dir, version)
    checksums = _write_checksums(args.dist_dir, artifacts)

    if args.notes_file is not None:
        notes = _release_notes(args.changelog, version)
        args.notes_file.write_text(notes, encoding="utf-8", newline="\n")

    print(f"validated release tag {args.tag}")
    for artifact in artifacts:
        print(f"validated release asset {artifact.name}")
    print(f"wrote {checksums}")
    if args.notes_file is not None:
        print(f"wrote {args.notes_file}")
    return 0


def _project_version(project_file: Path) -> str:
    project = tomllib.loads(project_file.read_text(encoding="utf-8"))
    version = project.get("project", {}).get("version")
    if not isinstance(version, str) or not version:
        raise RuntimeError(f"missing project.version in {project_file}")
    return version


def _validate_tag(tag: str, version: str) -> None:
    expected = f"v{version}"
    if tag != expected:
        raise RuntimeError(f"release tag {tag!r} does not match package version {expected!r}")


def _expected_asset_names(version: str) -> tuple[str, str]:
    return (
        f"pyne_runtime-{version}-py3-none-any.whl",
        f"pyne_runtime-{version}.tar.gz",
    )


def _validate_artifacts(dist_dir: Path, version: str) -> tuple[Path, Path]:
    resolved = dist_dir.resolve()
    if not resolved.is_dir():
        raise RuntimeError(f"distribution directory does not exist: {resolved}")

    expected_names = _expected_asset_names(version)
    actual = {
        path.name: path
        for path in resolved.iterdir()
        if path.is_file() and path.name != CHECKSUMS_NAME
    }
    missing = sorted(set(expected_names) - set(actual))
    unexpected = sorted(set(actual) - set(expected_names))
    if missing or unexpected:
        details: list[str] = []
        if missing:
            details.append(f"missing: {', '.join(missing)}")
        if unexpected:
            details.append(f"unexpected: {', '.join(unexpected)}")
        raise RuntimeError("invalid release assets (" + "; ".join(details) + ")")

    artifacts = tuple(actual[name] for name in expected_names)
    empty = [path.name for path in artifacts if path.stat().st_size == 0]
    if empty:
        raise RuntimeError(f"release assets must not be empty: {', '.join(empty)}")
    return artifacts


def _write_checksums(dist_dir: Path, artifacts: tuple[Path, ...]) -> Path:
    output = dist_dir.resolve() / CHECKSUMS_NAME
    lines = [f"{_sha256(path)}  {path.name}" for path in sorted(artifacts)]
    output.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return output


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _release_notes(changelog: Path, version: str) -> str:
    body = changelog.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"^## {re.escape(version)} - \d{{4}}-\d{{2}}-\d{{2}}\s*$\n"
        r"(?P<notes>.*?)(?=^## |\Z)",
        flags=re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(body)
    if match is None:
        raise RuntimeError(f"missing dated changelog section for {version}")
    notes = match.group("notes").strip()
    if not notes:
        raise RuntimeError(f"empty changelog section for {version}")
    return notes + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
