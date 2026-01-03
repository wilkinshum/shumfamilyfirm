"""Utility helpers."""
from __future__ import annotations

import pathlib
import yaml


def load_yaml(path: str | pathlib.Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
