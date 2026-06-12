from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Junction:
    junction_id: int
    x: int
    y: int
    radius: int
    modes_present: tuple[str, ...]


@dataclass(frozen=True)
class TransportEdge:
    source: int
    target: int
    modes: tuple[str, ...]


@dataclass(frozen=True)
class LegalMove:
    destination: int
    via: tuple[int, int]
    mode: str
    blocked: bool = False

