# Mirrors .github/workflows/ci.yml so local checks catch the same failures.
.PHONY: check

check:
	uv run ruff format --check
	uv run ruff check
	uv run mypy
	uv run pytest
