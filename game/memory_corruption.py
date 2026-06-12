from __future__ import annotations

from pathlib import Path

from config import PROJECT_ROOT, load_settings
from .state import WitnessRecord


PROMPT_PATH = PROJECT_ROOT / "llm" / "prompts" / "memory_corruption.md"


def build_corruption_prompt(witness: WitnessRecord, turn_number: int) -> str:
    prompt_template = PROMPT_PATH.read_text(encoding="utf-8")
    settings = load_settings()
    next_level = min(1.0, witness.corruption_level + settings.memory_corruption_per_turn)
    return prompt_template.format(
        turn_number=turn_number,
        corruption_level=f"{next_level:.2f}",
        stable_facts="\n".join(f"- {fact}" for fact in witness.stable_facts) or "- None listed",
        fragile_facts="\n".join(f"- {fact}" for fact in witness.fragile_facts) or "- None listed",
        current_summary=witness.current_summary,
    )


def planned_corruption_output_path(game_dir: Path, witness_id: str, turn_number: int) -> Path:
    return game_dir / "witnesses" / "corruption" / f"turn_{turn_number:03d}_{witness_id}.json"

