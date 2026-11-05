"""Tests for the packaging helpers that assemble a bundle's legal files."""

from pathlib import Path

from buildtools.bundle import (
    RUNTIME_ROOTS,
    BundleLayout,
    LicenseSource,
    default_bundle_layout,
    distribution_closure,
    license_sources,
    render_notices,
    verify_bundle,
    write_license_bundle,
)
from packaging.utils import canonicalize_name


def test_darwin_layout_uses_the_app_bundle_resources() -> None:
    layout = default_bundle_layout(Path("/tmp/dist"), platform="darwin")

    assert layout.root == Path("/tmp/dist/SiliconDraft.app")
    assert layout.executable == layout.root / "Contents/MacOS/SiliconDraft"
    assert layout.licenses == layout.root / "Contents/Resources/licenses"


def test_windows_layout_uses_the_onedir_root() -> None:
    layout = default_bundle_layout(Path("/tmp/dist"), platform="win32")

    assert layout.root == Path("/tmp/dist/SiliconDraft")
    assert layout.executable == layout.root / "SiliconDraft.exe"
    assert layout.licenses == layout.root / "licenses"


def test_notices_list_every_component_with_version_license_and_file() -> None:
    sources = (
        LicenseSource(
            name="PySide6-Essentials",
            version="6.12.0",
            license_expression="LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only",
        ),
        LicenseSource(
            name="numpy",
            version="2.5.4",
            license_expression="BSD-3-Clause",
            files=(Path("/site-packages/numpy-2.5.4.dist-info/licenses/LICENSE.txt"),),
        ),
    )

    notices = render_notices(sources, project_name="SiliconDraft", project_version="0.1.0")

    assert "SiliconDraft 0.1.0" in notices
    assert "MIT License" in notices
    assert "LGPL-3.0-only" in notices
    assert "QT_NOTICE.txt" in notices
    assert "PySide6-Essentials 6.12.0" in notices
    assert "numpy 2.5.4" in notices
    assert "BSD-3-Clause" in notices
    assert "numpy/LICENSE.txt" in notices
    assert notices.index("numpy 2.5.4") < notices.index("PySide6-Essentials 6.12.0")


def test_write_license_bundle_copies_every_legal_file(tmp_path: Path) -> None:
    legal_dir = tmp_path / "legal"
    legal_dir.mkdir()
    (legal_dir / "LGPL-3.0.txt").write_text("LGPL text", encoding="utf-8")
    (legal_dir / "GPL-3.0.txt").write_text("GPL text", encoding="utf-8")
    (legal_dir / "QT_NOTICE.txt").write_text("Qt notice", encoding="utf-8")
    project_license = tmp_path / "LICENSE"
    project_license.write_text("MIT text", encoding="utf-8")
    numpy_license = tmp_path / "site-packages" / "LICENSE.txt"
    numpy_license.parent.mkdir()
    numpy_license.write_text("BSD text", encoding="utf-8")

    dest = tmp_path / "bundle" / "licenses"
    written = write_license_bundle(
        dest,
        (
            LicenseSource(
                name="numpy",
                version="2.5.4",
                license_expression="BSD-3-Clause",
                files=(numpy_license,),
            ),
        ),
        legal_dir=legal_dir,
        project_license=project_license,
        project_name="SiliconDraft",
        project_version="0.1.0",
    )

    assert (dest / "LGPL-3.0.txt").read_text(encoding="utf-8") == "LGPL text"
    assert (dest / "GPL-3.0.txt").read_text(encoding="utf-8") == "GPL text"
    assert (dest / "QT_NOTICE.txt").read_text(encoding="utf-8") == "Qt notice"
    assert (dest / "SiliconDraft" / "LICENSE").read_text(encoding="utf-8") == "MIT text"
    assert (dest / "numpy" / "LICENSE.txt").read_text(encoding="utf-8") == "BSD text"
    assert "numpy 2.5.4" in (dest / "THIRD_PARTY_NOTICES.txt").read_text(encoding="utf-8")
    assert set(written) == {
        dest / "LGPL-3.0.txt",
        dest / "GPL-3.0.txt",
        dest / "QT_NOTICE.txt",
        dest / "SiliconDraft" / "LICENSE",
        dest / "numpy" / "LICENSE.txt",
        dest / "THIRD_PARTY_NOTICES.txt",
    }


def test_write_license_bundle_keeps_colliding_license_names(tmp_path: Path) -> None:
    legal_dir = tmp_path / "legal"
    legal_dir.mkdir()
    (legal_dir / "LGPL-3.0.txt").write_text("LGPL text", encoding="utf-8")
    (legal_dir / "GPL-3.0.txt").write_text("GPL text", encoding="utf-8")
    (legal_dir / "QT_NOTICE.txt").write_text("Qt notice", encoding="utf-8")
    project_license = tmp_path / "LICENSE"
    project_license.write_text("MIT text", encoding="utf-8")
    first = tmp_path / "numpy" / "LICENSE.txt"
    first.parent.mkdir()
    first.write_text("first license", encoding="utf-8")
    second = tmp_path / "numpy" / "vendored" / "LICENSE.txt"
    second.parent.mkdir()
    second.write_text("second license", encoding="utf-8")

    dest = tmp_path / "bundle" / "licenses"
    write_license_bundle(
        dest,
        (
            LicenseSource(
                name="numpy",
                version="2.5.4",
                license_expression="BSD-3-Clause",
                files=(first, second),
            ),
        ),
        legal_dir=legal_dir,
        project_license=project_license,
        project_name="SiliconDraft",
        project_version="0.1.0",
    )

    assert (dest / "numpy" / "LICENSE.txt").read_text(encoding="utf-8") == "first license"
    assert (dest / "numpy" / "LICENSE-2.txt").read_text(encoding="utf-8") == "second license"
    notices = (dest / "THIRD_PARTY_NOTICES.txt").read_text(encoding="utf-8")
    assert "numpy/LICENSE.txt" in notices
    assert "numpy/LICENSE-2.txt" in notices


def _write_legal_files(license_dir: Path) -> None:
    (license_dir / "SiliconDraft").mkdir(parents=True)
    (license_dir / "SiliconDraft" / "LICENSE").write_text("MIT text", encoding="utf-8")
    (license_dir / "LGPL-3.0.txt").write_text("LGPL text", encoding="utf-8")
    (license_dir / "GPL-3.0.txt").write_text("GPL text", encoding="utf-8")
    (license_dir / "QT_NOTICE.txt").write_text("Qt notice", encoding="utf-8")
    (license_dir / "THIRD_PARTY_NOTICES.txt").write_text(
        "Qt is used under LGPL-3.0-only.\n", encoding="utf-8"
    )


def _make_complete_bundle(tmp_path: Path) -> BundleLayout:
    layout = default_bundle_layout(tmp_path / "dist", platform="win32")
    layout.executable.parent.mkdir(parents=True)
    layout.executable.write_text("", encoding="utf-8")
    _write_legal_files(layout.licenses)
    internal = layout.root / "_internal"
    translations = internal / "silicondraft" / "gui" / "translations"
    translations.mkdir(parents=True)
    (translations / "silicondraft_zh_CN.qm").write_text("", encoding="utf-8")
    messages = internal / "silicondraft" / "locale" / "zh_CN" / "LC_MESSAGES"
    messages.mkdir(parents=True)
    (messages / "silicondraft.mo").write_text("", encoding="utf-8")
    platforms = internal / "PySide6" / "Qt" / "plugins" / "platforms"
    platforms.mkdir(parents=True)
    (platforms / "qoffscreen.dll").write_text("", encoding="utf-8")
    qt_translations = internal / "PySide6" / "translations"
    qt_translations.mkdir(parents=True)
    (qt_translations / "qtbase_zh_CN.qm").write_text("", encoding="utf-8")
    return layout


def test_verify_bundle_accepts_a_complete_bundle(tmp_path: Path) -> None:
    layout = _make_complete_bundle(tmp_path)

    assert verify_bundle(layout) == ()


def test_verify_bundle_reports_a_missing_executable(tmp_path: Path) -> None:
    layout = _make_complete_bundle(tmp_path)
    layout.executable.unlink()

    issues = verify_bundle(layout)

    assert any("executable" in issue for issue in issues)


def test_verify_bundle_reports_forbidden_test_packages(tmp_path: Path) -> None:
    layout = _make_complete_bundle(tmp_path)
    (layout.root / "pytest").mkdir()

    issues = verify_bundle(layout)

    assert any("forbidden" in issue and "pytest" in issue for issue in issues)


def test_verify_bundle_reports_unexpected_distributions(tmp_path: Path) -> None:
    layout = _make_complete_bundle(tmp_path)
    rogue = layout.root / "rogue_package-1.0.dist-info"
    rogue.mkdir()
    (rogue / "METADATA").write_text(
        "Metadata-Version: 2.4\nName: rogue-package\nVersion: 1.0\n",
        encoding="utf-8",
    )

    issues = verify_bundle(layout)

    assert any("unexpected distributions" in issue and "rogue-package" in issue for issue in issues)


def test_verify_bundle_reports_a_missing_translation_catalog(tmp_path: Path) -> None:
    layout = _make_complete_bundle(tmp_path)
    messages = layout.root / "_internal" / "silicondraft" / "locale" / "zh_CN" / "LC_MESSAGES"
    (messages / "silicondraft.mo").unlink()

    issues = verify_bundle(layout)

    assert any("silicondraft.mo" in issue for issue in issues)


def test_distribution_closure_follows_dependencies_but_skips_extras() -> None:
    graph = {
        "root": (
            "dep-a>=1",
            "dep-docs; extra == 'docs'",
            "dep-old; python_version < '3'",
        ),
        "dep-a": ("dep-b", "root"),
        "dep-b": (),
        "dep-docs": (),
        "dep-old": (),
    }

    closure = distribution_closure(("root",), requires=graph.get)

    assert closure == ("dep-a", "dep-b", "root")


def test_license_sources_describe_the_installed_runtime_distributions() -> None:
    sources = license_sources(distribution_closure(RUNTIME_ROOTS))

    by_name = {str(canonicalize_name(source.name)): source for source in sources}
    assert {"numpy", "pydantic", "pyqtgraph", "pyside6-essentials", "pyyaml"} <= by_name.keys()
    assert "LGPL-3.0" in by_name["pyside6-essentials"].license_expression
    assert any(path.name == "LICENSE.txt" for path in by_name["pyqtgraph"].files)
