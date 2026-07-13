"""Resolve the application version in source and installed environments."""

from importlib import metadata
from pathlib import Path


FALLBACK_VERSION = "1.4.0"
PACKAGE_NAME = "vinote"


def resolve_version() -> str:
    package_dir = Path(__file__).resolve().parent
    source_root = package_dir.parent
    if (source_root / "pyproject.toml").is_file():
        try:
            return (source_root / "VERSION").read_text(encoding="utf-8").strip() or FALLBACK_VERSION
        except (OSError, UnicodeError):
            return FALLBACK_VERSION

    try:
        return metadata.version(PACKAGE_NAME).strip() or FALLBACK_VERSION
    except (metadata.PackageNotFoundError, OSError, ValueError):
        return FALLBACK_VERSION


VERSION = resolve_version()
