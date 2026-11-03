"""Shared pytest configuration."""

import os

# Qt needs a platform plugin in headless CI; offscreen works on every OS.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
