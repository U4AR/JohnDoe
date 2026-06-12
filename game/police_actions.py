from __future__ import annotations

from dataclasses import asdict

from .state import PoliceBlock


def create_edge_block(block_id: str, turn_number: int, from_junction: int, to_junction: int, mode: str | None, turns: int = 2) -> PoliceBlock:
    return PoliceBlock(
        block_id=block_id,
        turn_created=turn_number,
        block_type="edge_block",
        from_junction=from_junction,
        to_junction=to_junction,
        mode=mode,
        turns_remaining=turns,
    )


def create_mode_block(block_id: str, turn_number: int, mode: str, junction_id: int | None = None, turns: int = 1) -> PoliceBlock:
    return PoliceBlock(
        block_id=block_id,
        turn_created=turn_number,
        block_type="mode_block",
        mode=mode,
        junction_id=junction_id,
        turns_remaining=turns,
    )


def create_junction_block(block_id: str, turn_number: int, junction_id: int, turns: int = 1) -> PoliceBlock:
    return PoliceBlock(
        block_id=block_id,
        turn_created=turn_number,
        block_type="junction_block",
        junction_id=junction_id,
        turns_remaining=turns,
    )


def tick_blocks(blocks: list[PoliceBlock]) -> list[PoliceBlock]:
    updated: list[PoliceBlock] = []
    for block in blocks:
        block.turns_remaining -= 1
        if block.turns_remaining > 0:
            updated.append(block)
    return updated


def blocks_for_prompt(blocks: list[PoliceBlock]) -> list[dict]:
    return [asdict(block) for block in blocks if block.turns_remaining > 0]
