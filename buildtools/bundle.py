"""Legal-file assembly and verification for frozen SiliconDraft bundles.

This module is build tooling: it never runs inside the frozen application. The
functions are kept free of PyInstaller imports so they can be unit tested with
plain temporary directories.
"""

from __future__ import annotations

import shutil
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

RequiresFn = Callable[[str], Sequence[str] | None]

APP_NAME = "SiliconDraft"
LEGAL_FILES: tuple[str, ...] = ("LGPL-3.0.txt", "GPL-3.0.txt", "QT_NOTICE.txt")

#: Packages that must never appear in a runtime bundle. They are build/test
#: dependencies, and PySide6-Addons would break the PySide6-Essentials-only
#: distribution commitment in docs/design/v1-spec.md.
FORBIDDEN_COMPONENTS: tuple[str, ...] = (
    "hypothesis",
    "jsonschema",
    "mypy",
    "pkg_resources",
    "pydantic.mypy",
    "pyside6-addons",
    "pyside6_addons",
    "pyside6addons",
    "pystdf",
    "pytest",
    "ruff",
    "setuptools",
)

#: Top-level distributions the GUI bundle needs at run time. Transitive
#: dependencies come from :func:`distribution_closure`.
RUNTIME_ROOTS: tuple[str, ...] = (
    "numpy",
    "pydantic",
    "PyYAML",
    "pyqtgraph",
    "PySide6-Essentials",
)

REQUIRED_DATA_FILES: tuple[tuple[str, ...], ...] = (
    ("silicondraft", "gui", "translations", "silicondraft_zh_CN.qm"),
    ("silicondraft", "locale", "zh_CN", "LC_MESSAGES", "silicondraft.mo"),
    ("PySide6", "Qt", "translations", "qtbase_zh_CN.qm"),
)


@dataclass(frozen=True, slots=True)
class BundleLayout:
    """Where a built bundle keeps its executable and legal files."""

    root: Path
    executable: Path
    licenses: Path


@dataclass(frozen=True, slots=True)
class LicenseSource:
    """One installed distribution and the license files it ships."""

    name: str
    version: str
    license_expression: str
    files: tuple[Path, ...] = ()


def render_notices(
    sources: Sequence[LicenseSource],
    *,
    project_name: str,
    project_version: str,
) -> str:
    """Render ``THIRD_PARTY_NOTICES.txt`` for the bundled components.

    Components are sorted by name so repeated builds produce identical notices.
    """
    lines = [
        f"{project_name} {project_version}",
        "=" * (len(project_name) + len(project_version) + 1),
        "",
        f"{project_name} itself is licensed under the MIT License; see "
        f"{project_name}/LICENSE in this directory.",
        "",
        "Qt is included through PySide6-Essentials and is used under the GNU Lesser",
        "General Public License version 3 (LGPL-3.0-only). See QT_NOTICE.txt,",
        "LGPL-3.0.txt, and GPL-3.0.txt in this directory.",
        "",
        "Third-party components",
        "----------------------",
        "",
    ]
    for source in sorted(sources, key=lambda item: item.name.casefold()):
        lines.append(f"{source.name} {source.version}")
        lines.append(f"  License: {source.license_expression}")
        if source.files:
            destinations = license_filenames(source.files)
            listed = ", ".join(f"{source.name}/{name}" for name in destinations)
            lines.append(f"  License files: {listed}")
        else:
            lines.append("  License files: none shipped by the distribution")
        lines.append("")
    return "\n".join(lines)


def write_license_bundle(
    dest: Path,
    sources: Sequence[LicenseSource],
    *,
    legal_dir: Path,
    project_license: Path,
    project_name: str,
    project_version: str,
) -> tuple[Path, ...]:
    """Write the project license, LGPL/GPL texts, Qt notice, and component files.

    ``dest`` is the license directory itself (``licenses`` inside the bundle).
    Returns every file written, so the build report can list them.
    """
    dest.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name in LEGAL_FILES:
        source = legal_dir / name
        if not source.is_file():
            raise FileNotFoundError(f"required legal text is missing: {source}")
        written.append(_copy_file(source, dest / name))

    written.append(_copy_file(project_license, dest / project_name / "LICENSE"))
    for item in sorted(sources, key=lambda entry: entry.name.casefold()):
        destinations = license_filenames(item.files)
        for source_file, destination in zip(item.files, destinations, strict=True):
            written.append(_copy_file(source_file, dest / item.name / destination))

    notices = dest / "THIRD_PARTY_NOTICES.txt"
    notices.write_text(
        render_notices(sources, project_name=project_name, project_version=project_version),
        encoding="utf-8",
    )
    written.append(notices)
    return tuple(written)


def license_filenames(files: Sequence[Path]) -> tuple[str, ...]:
    """Destination file names, disambiguating files that share a basename.

    Distributions such as numpy vendor multiple dependencies whose licenses are
    all called ``LICENSE.txt``; keeping only the last one would drop required
    texts. Repeated names get a numeric suffix in source order.
    """
    counts: dict[str, int] = {}
    names: list[str] = []
    for path in files:
        count = counts.get(path.name, 0) + 1
        counts[path.name] = count
        if count == 1:
            names.append(path.name)
            continue
        suffix = "".join(path.suffixes)
        stem = path.name[: len(path.name) - len(suffix)] if suffix else path.name
        names.append(f"{stem}-{count}{suffix}")
    return tuple(names)


def _copy_file(source: Path, dest: Path) -> Path:
    """Copy ``source`` to ``dest``, creating parent directories."""
    if not source.is_file():
        raise FileNotFoundError(f"license file is missing: {source}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, dest)
    return dest


def verify_bundle(layout: BundleLayout) -> tuple[str, ...]:
    """Check a built bundle for required runtime files and forbidden packages.

    Returns human-readable issues; an empty tuple means the bundle passes.
    """
    issues: list[str] = []
    if not layout.executable.is_file():
        issues.append(f"executable is missing: {layout.executable}")

    required_legal = (
        "THIRD_PARTY_NOTICES.txt",
        *LEGAL_FILES,
        str(Path(APP_NAME) / "LICENSE"),
    )
    for name in required_legal:
        path = layout.licenses / name
        if not path.is_file():
            issues.append(f"legal file is missing: {path}")
        elif path.stat().st_size == 0:
            issues.append(f"legal file is empty: {path}")

    notices = layout.licenses / "THIRD_PARTY_NOTICES.txt"
    if notices.is_file():
        text = notices.read_text(encoding="utf-8", errors="replace")
        for token in ("LGPL-3.0", "Qt"):
            if token not in text:
                issues.append(f"{notices} does not mention {token!r}")

    if not layout.root.is_dir():
        issues.append(f"bundle root is missing: {layout.root}")
        return tuple(issues)

    paths = sorted(layout.root.rglob("*"))
    for suffix in REQUIRED_DATA_FILES:
        if not any(_ends_with(path, suffix) for path in paths):
            issues.append(f"runtime data file is missing: {'/'.join(suffix)}")

    platform_plugins = [
        path
        for path in paths
        if path.is_file() and "platforms" in path.parts and path.parent.name == "platforms"
    ]
    if not platform_plugins:
        issues.append("Qt platform plugins are missing from the bundle")

    forbidden = sorted(
        {part for path in paths for part in path.parts if part.casefold() in FORBIDDEN_COMPONENTS}
    )
    if forbidden:
        issues.append(f"forbidden components in bundle: {', '.join(forbidden)}")

    expected = {str(canonicalize_name(name)) for name in distribution_closure(RUNTIME_ROOTS)}
    expected.add(str(canonicalize_name(APP_NAME)))
    unexpected = sorted(_bundled_distribution_names(layout.root) - expected)
    if unexpected:
        issues.append(f"unexpected distributions in bundle: {', '.join(unexpected)}")
    return tuple(issues)


def _bundled_distribution_names(root: Path) -> set[str]:
    """Distribution names recorded by ``*.dist-info`` directories in a bundle."""
    names: set[str] = set()
    for metadata_file in root.rglob("METADATA"):
        if not metadata_file.parent.name.endswith(".dist-info"):
            continue
        text = metadata_file.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            if line.startswith("Name:"):
                names.add(str(canonicalize_name(line.partition(":")[2].strip())))
                break
    return names


def _ends_with(path: Path, suffix: Sequence[str]) -> bool:
    """Whether ``path``'s trailing components equal ``suffix``."""
    return path.parts[-len(suffix) :] == tuple(suffix)


def distribution_closure(
    roots: Sequence[str],
    *,
    requires: RequiresFn = metadata.requires,
) -> tuple[str, ...]:
    """Resolve the runtime dependency closure of ``roots``.

    Dependency extras are not bundled, so requirements guarded by an extra are
    skipped. Environment markers are evaluated for the current interpreter,
    which matches the platform the bundle is built on.
    """
    seen: set[str] = set()
    pending = list(roots)
    while pending:
        name = pending.pop()
        key = canonicalize_name(name)
        if key in seen:
            continue
        seen.add(key)
        for raw in requires(name) or ():
            requirement = Requirement(raw)
            if requirement.marker is not None and not requirement.marker.evaluate({"extra": ""}):
                continue
            pending.append(requirement.name)
    return tuple(sorted(seen, key=str.casefold))


def license_sources(names: Sequence[str]) -> tuple[LicenseSource, ...]:
    """Describe installed distributions and the license files each one ships."""
    sources: list[LicenseSource] = []
    for name in names:
        distribution = metadata.distribution(name)
        expression = (
            distribution.metadata.get("License-Expression")
            or distribution.metadata.get("License")
            or "UNKNOWN"
        )
        sources.append(
            LicenseSource(
                name=str(distribution.metadata.get("Name") or name),
                version=distribution.version,
                license_expression=" ".join(str(expression).split()),
                files=_license_files(distribution),
            )
        )
    return tuple(sorted(sources, key=lambda source: source.name.casefold()))


def _license_files(distribution: metadata.Distribution) -> tuple[Path, ...]:
    """Return the license-like files recorded in a distribution's metadata."""
    found: dict[Path, None] = {}
    for entry in distribution.files or ():
        if not _is_license_filename(entry.name):
            continue
        path = Path(str(distribution.locate_file(entry)))
        if path.is_file():
            found[path] = None
    return tuple(sorted(found, key=lambda path: str(path).casefold()))


def _is_license_filename(name: str) -> bool:
    """Whether a distribution file name looks like a license or notice."""
    return name.upper().startswith(("LICENSE", "LICENCE", "COPYING", "NOTICE"))


def default_bundle_layout(dist_dir: Path, *, platform: str = sys.platform) -> BundleLayout:
    """Locate the GUI bundle produced by the PyInstaller spec.

    macOS builds a ``.app`` wrapper, so the executable lives under
    ``Contents/MacOS`` and legal files belong in ``Contents/Resources`` (the
    standard location for an app's resources). Other platforms use the onedir
    root directly.
    """
    if platform == "darwin":
        root = dist_dir / f"{APP_NAME}.app"
        return BundleLayout(
            root=root,
            executable=root / "Contents" / "MacOS" / APP_NAME,
            licenses=root / "Contents" / "Resources" / "licenses",
        )
    root = dist_dir / APP_NAME
    return BundleLayout(
        root=root,
        executable=root / f"{APP_NAME}.exe",
        licenses=root / "licenses",
    )
