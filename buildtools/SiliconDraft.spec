# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onedir spec for the SiliconDraft GUI (T15 packaging spike).

Only PySide6-Essentials is installed as a GUI dependency, so Addons cannot be
collected. The explicit ``excludes`` keep build and test dependencies out even
if an import slips in through a future hook.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(SPECPATH).parent
SRC = REPO_ROOT / "src"
for entry in (SRC, REPO_ROOT):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from buildtools.bundle import FORBIDDEN_COMPONENTS  # noqa: E402
from silicondraft import __version__  # noqa: E402

DATAS = [
    (
        str(SRC / "silicondraft" / "gui" / "translations" / "*.qm"),
        "silicondraft/gui/translations",
    ),
    (
        str(SRC / "silicondraft" / "locale" / "zh_CN" / "LC_MESSAGES" / "*.mo"),
        "silicondraft/locale/zh_CN/LC_MESSAGES",
    ),
]

# Keep the spec's excludes and verify_bundle()'s forbidden list in one place.
EXCLUDES = list(FORBIDDEN_COMPONENTS)

a = Analysis(
    [str(REPO_ROOT / "buildtools" / "entry_gui.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=DATAS,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SiliconDraft",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="SiliconDraft",
)
app = BUNDLE(
    coll,
    name="SiliconDraft.app",
    icon=None,
    bundle_identifier="io.github.kpshao.silicondraft",
    info_plist={
        "CFBundleName": "SiliconDraft",
        "CFBundleDisplayName": "SiliconDraft",
        "CFBundleShortVersionString": __version__,
        "CFBundleVersion": __version__,
        "NSHighResolutionCapable": True,
    },
)
