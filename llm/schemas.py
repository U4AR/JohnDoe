from __future__ import annotations

from typing import Literal, TypedDict


class CulpritMoveOutput(TypedDict):
    chosen_destination: int
    transport_mode: str
    route: list[int]
    change_disguise: bool
    new_disguise: str | None
    reasoning_summary: str
    risk_level: Literal["low", "medium", "high"]


class CorruptedWitnessOutput(TypedDict):
    corruption_level: float
    corrupted_summary: str
    changed_fragile_facts: list[str]
    preserved_stable_facts: list[str]

