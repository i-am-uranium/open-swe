"""Service catalog loading for repo inference."""

from __future__ import annotations

import json
import logging
import os
import tomllib
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_SERVICE_CATALOG_PATHS = (
    Path("/app/config/service-catalog.json"),
    Path("/app/config/service-catalog.toml"),
    Path("/workspace/open-swe/config/service-catalog.json"),
    Path("/workspace/open-swe/config/service-catalog.toml"),
    Path("config/service-catalog.json"),
    Path("config/service-catalog.toml"),
)


def load_service_catalog(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """Load repo/service metadata from a JSON or TOML catalog file.

    The catalog is intentionally file-backed instead of label-env-backed so it can
    be reviewed and versioned like any other production configuration.
    """
    configured_path = path or os.environ.get("OPEN_SWE_SERVICE_CATALOG_PATH")
    candidates = (Path(configured_path),) if configured_path else _DEFAULT_SERVICE_CATALOG_PATHS

    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            return _load_catalog_file(candidate)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to load service catalog from %s", candidate)
            return {}

    return {}


def _load_catalog_file(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        loaded = json.loads(path.read_text())
    elif suffix == ".toml":
        loaded = tomllib.loads(path.read_text())
    elif suffix in {".yaml", ".yml"}:
        loaded = _load_yaml(path)
    else:
        logger.warning("Unsupported service catalog file extension: %s", path)
        return {}

    if not isinstance(loaded, dict):
        logger.warning("Service catalog root must be an object: %s", path)
        return {}
    return loaded


def _load_yaml(path: Path) -> Any:
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("PyYAML is not installed; cannot load YAML service catalog %s", path)
        return {}
    return yaml.safe_load(path.read_text()) or {}
