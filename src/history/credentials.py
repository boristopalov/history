"""Tokens from `hist spotify-login` and `hist simplefin-link`, as owner-only JSON files."""

import json
import os
from pathlib import Path
from typing import Any


def load(directory: Path, name: str) -> dict[str, Any] | None:
    path = directory / f"{name}.json"
    return json.loads(path.read_text()) if path.exists() else None


def save(directory: Path, name: str, values: dict[str, Any]) -> None:
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / f"{name}.json"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as file:
        json.dump(values, file)
