"""Persistent GUI settings keys and small read/write helpers."""

from pathlib import Path

from PySide6.QtCore import QByteArray, QSettings

WINDOW_GEOMETRY_KEY = "window/geometry"
WINDOW_STATE_KEY = "window/state"
SPLITTER_STATE_KEY = "window/splitter"
OPEN_DIRECTORY_KEY = "paths/open_dir"
SAVE_DIRECTORY_KEY = "paths/save_dir"
EXPORT_DIRECTORY_KEY = "paths/export_dir"


def read_path(settings: QSettings, key: str) -> Path | None:
    """Read a stored directory, ignoring empty or non-string values."""
    value = settings.value(key)
    if isinstance(value, str) and value:
        return Path(value)
    return None


def write_path(settings: QSettings, key: str, path: Path | None) -> None:
    """Store a directory, or remove the key when there is none."""
    if path is None:
        settings.remove(key)
    else:
        settings.setValue(key, str(path))


def read_byte_array(settings: QSettings, key: str) -> QByteArray | None:
    """Read a stored window or splitter state."""
    value = settings.value(key)
    if isinstance(value, QByteArray):
        return value
    if isinstance(value, (bytes, bytearray)):
        return QByteArray(bytes(value))
    return None
