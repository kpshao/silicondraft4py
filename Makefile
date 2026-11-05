# Mirrors .github/workflows/ci.yml so local checks catch the same failures.
.PHONY: check package translations

check:
	uv run ruff format --check
	uv run ruff check
	uv run mypy
	uv run pytest

# Build the PyInstaller onedir bundle, verify licenses, and run the frozen
# generate/export smoke test (see docs/design/packaging-spike.md).
package:
	uv run python scripts/package.py

# Regenerate the Qt and gettext catalogs after changing user-visible strings.
# The .ts file keeps its existing translations; fill new ones before committing.
translations:
	uv run pyside6-lupdate -no-obsolete src/silicondraft/gui/*.py -ts src/silicondraft/gui/translations/silicondraft_zh_CN.ts
	uv run pyside6-lrelease src/silicondraft/gui/translations/silicondraft_zh_CN.ts -qm src/silicondraft/gui/translations/silicondraft_zh_CN.qm
	uv run python scripts/compile_gettext.py src/silicondraft/locale/zh_CN/LC_MESSAGES/silicondraft.po
