from __future__ import annotations

from typing import Any


def require_keys(data: dict[str, Any], keys: list[str]) -> None:
    missing = [key for key in keys if key not in data]
    if missing:
        raise ValueError(f"Structured LLM output missing keys: {', '.join(missing)}")

