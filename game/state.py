from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class CulpritMove:
    turn_number: int
    from_junction: int
    to_junction: int
    mode: str
    route: list[int]
    changed_disguise: bool = False
    risk_level: str = "unknown"


@dataclass
class CulpritState:
    current_junction: int
    current_disguise: str
    remaining_disguise_changes: int
    route_history: list[CulpritMove] = field(default_factory=list)


@dataclass
class LookoutNotice:
    notice_id: str
    turn_number: int
    text: str
    parsed_location: str | None = None
    parsed_description: str | None = None
    genericness_score: float = 0.0
    false_positive_likelihood: float = 0.0
    response_plan: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class WitnessQuestion:
    question: str
    answer: str
    turn_number: int


@dataclass
class WitnessRecord:
    witness_id: str
    notice_id: str
    turn_created: int
    junction_id: int
    personality: dict[str, Any]
    reliability: float
    memory_strength: float
    corruption_level: float
    relevance_score: float
    original_summary: str
    current_summary: str
    stable_facts: list[str] = field(default_factory=list)
    fragile_facts: list[str] = field(default_factory=list)
    question_history: list[WitnessQuestion] = field(default_factory=list)


@dataclass
class WitnessBatch:
    batch_id: str
    notice_id: str
    turn_number: int
    total_witnesses: int
    individual_review_allowed: bool
    witnesses: list[WitnessRecord] = field(default_factory=list)


@dataclass
class PoliceBlock:
    block_id: str
    turn_created: int
    block_type: str
    turns_remaining: int
    mode: str | None = None
    from_junction: int | None = None
    to_junction: int | None = None
    junction_id: int | None = None
    district: str | None = None


@dataclass
class JunctionCheck:
    check_id: str
    turn_number: int
    junction_id: int
    result: str


@dataclass
class GameState:
    game_id: str
    turn_number: int
    max_turns: int
    phase: str
    initial_description: str
    culprit: CulpritState
    notices: list[LookoutNotice] = field(default_factory=list)
    witness_batches: list[WitnessBatch] = field(default_factory=list)
    active_blocks: list[PoliceBlock] = field(default_factory=list)
    junction_checks: list[JunctionCheck] = field(default_factory=list)
    game_log: list[dict[str, Any]] = field(default_factory=list)
    result: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GameState":
        culprit_data = data["culprit"]
        route_history = [CulpritMove(**move) for move in culprit_data.get("route_history", [])]
        culprit = CulpritState(
            current_junction=culprit_data["current_junction"],
            current_disguise=culprit_data["current_disguise"],
            remaining_disguise_changes=culprit_data["remaining_disguise_changes"],
            route_history=route_history,
        )

        notices = [LookoutNotice(**notice) for notice in data.get("notices", [])]
        batches = [_witness_batch_from_dict(batch) for batch in data.get("witness_batches", [])]
        blocks = [PoliceBlock(**block) for block in data.get("active_blocks", [])]
        checks = [JunctionCheck(**check) for check in data.get("junction_checks", [])]
        return cls(
            game_id=data["game_id"],
            turn_number=data["turn_number"],
            max_turns=data["max_turns"],
            phase=data["phase"],
            initial_description=data["initial_description"],
            culprit=culprit,
            notices=notices,
            witness_batches=batches,
            active_blocks=blocks,
            junction_checks=checks,
            game_log=data.get("game_log", []),
            result=data.get("result"),
        )


def _witness_batch_from_dict(data: dict[str, Any]) -> WitnessBatch:
    witnesses: list[WitnessRecord] = []
    for witness in data.get("witnesses", []):
        questions = [WitnessQuestion(**question) for question in witness.get("question_history", [])]
        witness = {**witness, "question_history": questions}
        witnesses.append(WitnessRecord(**witness))
    return WitnessBatch(
        batch_id=data["batch_id"],
        notice_id=data["notice_id"],
        turn_number=data["turn_number"],
        total_witnesses=data["total_witnesses"],
        individual_review_allowed=data["individual_review_allowed"],
        witnesses=witnesses,
    )
