"""Build, verify, and smoke-test the frozen SiliconDraft GUI bundle.

The script is safe to re-run: PyInstaller replaces the previous output and the
license directory is rewritten from the current environment. Run it with the
project environment so PyInstaller and PySide6-Essentials resolve::

    uv run python scripts/package.py

On macOS this produces ``dist/SiliconDraft.app``; on Windows it produces
``dist/SiliconDraft/SiliconDraft.exe``. A ``package-report.json`` next to the
bundle records the size, timing, and component licenses.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from buildtools.bundle import (  # noqa: E402
    APP_NAME,
    RUNTIME_ROOTS,
    BundleLayout,
    LicenseSource,
    default_bundle_layout,
    distribution_closure,
    license_filenames,
    license_sources,
    verify_bundle,
    write_license_bundle,
)

SPEC = REPO_ROOT / "buildtools" / "SiliconDraft.spec"
LEGAL_DIR = REPO_ROOT / "buildtools" / "licenses"
PROJECT_LICENSE = REPO_ROOT / "LICENSE"
SMOKE_TIMEOUT_SECONDS = 600.0


class PackagingError(RuntimeError):
    """A packaging precondition, build, or verification step failed."""


@dataclass(frozen=True, slots=True)
class SmokeResult:
    """Timing and output of a frozen smoke run."""

    startup_seconds: float
    wall_seconds: float
    exported: tuple[str, ...]
    lots: int
    dies: int


def _installed_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def check_environment() -> str:
    """Refuse to build with PySide6-Addons and return the project version."""
    addons = _installed_version("PySide6-Addons")
    if addons is not None:
        raise PackagingError(
            f"PySide6-Addons {addons} is installed; the bundle must use PySide6-Essentials only"
        )
    for name in ("pyinstaller", "PySide6-Essentials"):
        if _installed_version(name) is None:
            raise PackagingError(f"{name} is not installed; run `uv sync` first")
    return _installed_version("silicondraft") or "0.0.0"


def build(dist_dir: Path, work_dir: Path) -> float:
    """Run PyInstaller and return the build duration in seconds."""
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        str(SPEC),
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(work_dir),
        "--noconfirm",
        "--clean",
    ]
    started = time.monotonic()
    try:
        subprocess.run(command, cwd=REPO_ROOT, check=True)
    except subprocess.CalledProcessError as exc:
        raise PackagingError(f"PyInstaller failed with exit code {exc.returncode}") from exc
    return time.monotonic() - started


def remove_intermediate_onedir(layout: BundleLayout, dist_dir: Path) -> None:
    """Drop PyInstaller's plain onedir when macOS also produced a ``.app``.

    BUNDLE copies the collected onedir into the ``.app``; keeping both would
    double the artifact size without adding anything the app needs.
    """
    plain = dist_dir / APP_NAME
    if plain != layout.root and plain.is_dir():
        shutil.rmtree(plain)


def sign_bundle(layout: BundleLayout) -> None:
    """Re-sign a macOS bundle after writing legal files into ``Resources``.

    PyInstaller signs the ``.app`` before this script adds ``licenses/``; that
    invalidates the resource seal. Ad-hoc signing is enough for the spike;
    release builds must repeat Developer ID signing and notarization last.
    """
    if sys.platform != "darwin":
        return
    codesign = shutil.which("codesign")
    if codesign is None:
        raise PackagingError("codesign is not available on this macOS host")
    subprocess.run(
        [codesign, "--force", "--sign", "-", str(layout.root)],
        check=True,
        capture_output=True,
        text=True,
    )
    verified = subprocess.run(
        [codesign, "--verify", "--strict", str(layout.root)],
        capture_output=True,
        text=True,
    )
    if verified.returncode != 0:
        detail = verified.stderr.strip() or verified.stdout.strip()
        raise PackagingError(f"codesign verification failed: {detail}")


def write_licenses(layout: BundleLayout, version: str) -> tuple[LicenseSource, ...]:
    """Rewrite the bundle's license directory and return the component list."""
    names = distribution_closure(RUNTIME_ROOTS)
    sources = license_sources(names)
    write_license_bundle(
        layout.licenses,
        sources,
        legal_dir=LEGAL_DIR,
        project_license=PROJECT_LICENSE,
        project_name=APP_NAME,
        project_version=version,
    )
    return sources


def run_smoke(layout: BundleLayout, scenario: Path, output: Path) -> SmokeResult:
    """Run the hidden GUI smoke test inside the frozen bundle."""
    if not scenario.is_file():
        raise PackagingError(f"smoke scenario does not exist: {scenario}")
    shutil.rmtree(output, ignore_errors=True)
    output.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment["QT_QPA_PLATFORM"] = "offscreen"
    command = [
        str(layout.executable),
        "--smoke-test",
        "--scenario",
        str(scenario.resolve()),
        "--output",
        str(output.resolve()),
    ]
    spawn_unix_ns = time.time_ns()
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=SMOKE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise PackagingError(f"smoke test timed out after {SMOKE_TIMEOUT_SECONDS:.0f}s") from exc
    wall_seconds = time.monotonic() - started
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, file=sys.stderr, end="")
    if completed.returncode != 0:
        raise PackagingError(f"smoke test failed with exit code {completed.returncode}")

    report_path = output / "smoke-report.json"
    if not report_path.is_file():
        raise PackagingError(f"smoke report is missing: {report_path}")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    shown_unix_ns = report.get("window_shown_unix_ns")
    if not isinstance(shown_unix_ns, int):
        raise PackagingError("smoke report is missing window_shown_unix_ns")
    startup_seconds = (shown_unix_ns - spawn_unix_ns) / 1e9

    exported = tuple(str(path) for path in report.get("exported", []))
    if not exported or any(not Path(path).is_file() for path in exported):
        raise PackagingError("smoke export produced no files or missing files")
    suffixes = {Path(path).suffix.lower() for path in exported}
    if ".stdf" not in suffixes or ".csv" not in suffixes:
        raise PackagingError(f"smoke export did not produce STDF and CSV files: {sorted(suffixes)}")
    lots = report.get("lots")
    dies = report.get("dies")
    if not isinstance(lots, int) or not isinstance(dies, int):
        raise PackagingError("smoke report is missing lots/dies")
    return SmokeResult(
        startup_seconds=startup_seconds,
        wall_seconds=wall_seconds,
        exported=exported,
        lots=lots,
        dies=dies,
    )


def directory_stats(root: Path) -> tuple[int, int]:
    """Return ``(size_bytes, file_count)`` for a bundle directory.

    Symbolic links are skipped so macOS framework ``Versions/Current`` links do
    not count the same binary multiple times.
    """
    size = 0
    count = 0
    for path in root.rglob("*"):
        if path.is_file() and not path.is_symlink():
            size += path.stat().st_size
            count += 1
    return size, count


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _report_payload(
    layout: BundleLayout,
    *,
    version: str,
    sources: Sequence[LicenseSource],
    build_seconds: float,
    smoke: SmokeResult | None,
) -> dict[str, object]:
    size, count = directory_stats(layout.root)
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "platform": sys.platform,
        "machine": platform.machine(),
        "python": platform.python_version(),
        "silicondraft": version,
        "pyside6_essentials": _installed_version("PySide6-Essentials"),
        "pyinstaller": _installed_version("pyinstaller"),
        "bundle": _display_path(layout.root),
        "bundle_size_bytes": size,
        "bundle_file_count": count,
        "build_seconds": round(build_seconds, 3),
        "distributions": [
            {
                "name": source.name,
                "version": source.version,
                "license": source.license_expression,
                "license_files": list(license_filenames(source.files)),
            }
            for source in sources
        ],
        "smoke": (
            None
            if smoke is None
            else {
                "startup_seconds": round(smoke.startup_seconds, 3),
                "wall_seconds": round(smoke.wall_seconds, 3),
                "lots": smoke.lots,
                "dies": smoke.dies,
                "exported": list(smoke.exported),
            }
        ),
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Build the bundle, verify it, smoke-test it, and write the report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=REPO_ROOT / "dist")
    parser.add_argument("--work", type=Path, default=REPO_ROOT / "build" / "pyinstaller")
    parser.add_argument(
        "--smoke-scenario",
        type=Path,
        default=REPO_ROOT / "examples" / "tiny.yaml",
        help="scenario used by the frozen generate/export smoke test",
    )
    parser.add_argument("--no-smoke", action="store_true", help="skip the frozen smoke test")
    args = parser.parse_args(argv)

    try:
        version = check_environment()
        print(f"package: building {APP_NAME} {version} with PyInstaller")
        build_seconds = build(args.dist, args.work)
        layout = default_bundle_layout(args.dist)
        if not layout.executable.is_file():
            raise PackagingError(f"bundle executable is missing: {layout.executable}")
        remove_intermediate_onedir(layout, args.dist)
        sources = write_licenses(layout, version)
        issues = verify_bundle(layout)
        if issues:
            raise PackagingError("; ".join(issues))
        sign_bundle(layout)
        print(f"package: verified licenses for {len(sources)} distributions")

        smoke = None
        if not args.no_smoke:
            smoke_output = args.work.parent / "smoke"
            smoke = run_smoke(layout, args.smoke_scenario, smoke_output)
            print(
                f"package: smoke ok (lots={smoke.lots}, dies={smoke.dies}, "
                f"startup={smoke.startup_seconds:.2f}s)"
            )
    except PackagingError as exc:
        print(f"package: error: {exc}", file=sys.stderr)
        return 1

    report_path = args.dist / "package-report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(
            _report_payload(
                layout,
                version=version,
                sources=sources,
                build_seconds=build_seconds,
                smoke=smoke,
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    size, count = directory_stats(layout.root)
    print(f"package: bundle {_display_path(layout.root)} ({count} files, {size / 2**20:.1f} MiB)")
    print(f"package: report {_display_path(report_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
