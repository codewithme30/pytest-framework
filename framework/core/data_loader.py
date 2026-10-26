"""
Module  : framework.core.data_loader
Author  : Anil Kalisetti
Purpose : Load static test data (JSON / YAML) once and share it safely.

Files are cached, so 500 parametrized tests reading ``users.json`` hit the disk once.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from framework.core.yaml_loader import load_yaml


@lru_cache(maxsize=64)
def _load(path_str: str) -> Any:
    path = Path(path_str)
    with path.open(encoding="utf-8") as handle:
        if path.suffix.lower() in {".yaml", ".yml"}:
            return load_yaml(handle)
        if path.suffix.lower() == ".json":
            return json.load(handle)
    raise ValueError(f"Unsupported test-data format: {path.suffix} ({path})")


def load_data(path: str | Path) -> Any:
    """Return parsed JSON/YAML content. Treat the result as read-only."""
    return _load(str(Path(path).resolve()))
