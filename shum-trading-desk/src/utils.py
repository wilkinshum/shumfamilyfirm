"""Utility helpers."""
from __future__ import annotations

import json
import pathlib
from typing import Any, Dict

import yaml
from jsonschema import validate


def load_yaml(path: str | pathlib.Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_json_schema(path: str | pathlib.Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_json(data: Dict[str, Any], schema: Dict[str, Any]) -> None:
    validate(instance=data, schema=schema)
