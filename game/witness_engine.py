from __future__ import annotations

from config import load_settings

from .rules import can_review_individual_witnesses
from .state import GameState, LookoutNotice, WitnessBatch, WitnessQuestion, WitnessRecord


PERSONALITIES = [
    {"style": "careful", "confidence": "measured", "quirk": "keeps correcting small details"},
    {"style": "talkative", "confidence": "overconfident", "quirk": "compares people to customers"},
    {"style": "nervous", "confidence": "uncertain", "quirk": "remembers colors better than faces"},
    {"style": "blunt", "confidence": "low", "quirk": "answers in short fragments"},
]


def generate_witness_batch(state: GameState, notice: LookoutNotice) -> WitnessBatch:
    witnesses: list[WitnessRecord] = []
    for plan in notice.response_plan:
        junction_id = int(plan["junction_id"])
        count = int(plan["estimated_witnesses"])
        relevance_bias = float(plan["relevance_bias"])
        for index in range(count):
            witness_index = len(witnesses) + 1
            relevance = _relevance_for_index(relevance_bias, index)
            reliability = _bounded(0.42 + ((junction_id + index) % 6) * 0.08)
            memory = _bounded(0.45 + ((junction_id * 3 + index) % 5) * 0.09)
            summary = _summary_for_witness(state, notice, junction_id, relevance, reliability)
            witnesses.append(
                WitnessRecord(
                    witness_id=f"w_t{state.turn_number:03d}_{notice.notice_id}_j{junction_id}_{witness_index:03d}",
                    notice_id=notice.notice_id,
                    turn_created=state.turn_number,
                    junction_id=junction_id,
                    personality=PERSONALITIES[witness_index % len(PERSONALITIES)],
                    reliability=reliability,
                    memory_strength=memory,
                    corruption_level=0.0,
                    relevance_score=relevance,
                    original_summary=summary,
                    current_summary=summary,
                    stable_facts=[f"witness was at Junction {junction_id}", f"witness responded to {notice.notice_id}"],
                    fragile_facts=_fragile_facts_from_notice(notice),
                )
            )

    total = len(witnesses)
    return WitnessBatch(
        batch_id=f"batch_{notice.notice_id}",
        notice_id=notice.notice_id,
        turn_number=state.turn_number,
        total_witnesses=total,
        individual_review_allowed=can_review_individual_witnesses(total),
        witnesses=witnesses,
    )


def answer_witness_question(witness: WitnessRecord, question: str, turn_number: int) -> str:
    lowered = question.lower()
    summary = witness.current_summary
    if any(word in lowered for word in ("carry", "holding", "object", "folder", "bag")):
        answer = _extract_answer(summary, ["folder", "red", "bag", "packet", "backpack"])
    elif any(word in lowered for word in ("where", "junction", "location")):
        answer = f"I was at Junction {witness.junction_id}. I can only speak to what I noticed there."
    elif any(word in lowered for word in ("direction", "went", "move", "route", "transport", "bus", "taxi", "subway")):
        answer = _extract_answer(summary, ["toward", "route", "bus", "taxi", "subway", "left", "moved"])
    elif any(word in lowered for word in ("clothes", "coat", "wearing", "disguise")):
        answer = _extract_answer(summary, ["coat", "raincoat", "grey", "gray", "tan", "helmet"])
    else:
        answer = f"I remember it like this: {summary}"

    witness.question_history.append(WitnessQuestion(question=question, answer=answer, turn_number=turn_number))
    return answer


def corrupt_witnesses_slightly(state: GameState) -> None:
    settings = load_settings()
    for batch in state.witness_batches:
        for witness in batch.witnesses:
            witness.corruption_level = _bounded(witness.corruption_level + settings.memory_corruption_per_turn)
            if witness.corruption_level < 0.2:
                witness.current_summary = witness.current_summary.replace("saw ", "remembers seeing ", 1)
            elif witness.corruption_level < 0.5:
                witness.current_summary = witness.current_summary.replace("red folder", "red item")
                witness.current_summary = witness.current_summary.replace("grey raincoat", "grey or dark coat")
            else:
                witness.current_summary = (
                    f"The witness is still sure they were at Junction {witness.junction_id}, "
                    "but clothing, timing, and direction details have become unreliable."
                )


def _relevance_for_index(relevance_bias: float, index: int) -> float:
    return _bounded(relevance_bias - (index % 4) * 0.11 + (0.05 if index == 0 else 0.0))


def _summary_for_witness(state: GameState, notice: LookoutNotice, junction_id: int, relevance: float, reliability: float) -> str:
    culprit_here = junction_id == state.culprit.current_junction or any(move.to_junction == junction_id for move in state.culprit.route_history[-3:])
    if culprit_here and relevance >= 0.55:
        return (
            f"A witness at Junction {junction_id} saw someone matching the notice: {state.culprit.current_disguise}. "
            "They seemed alert to police attention and moved near one of the transport routes."
        )
    if relevance >= 0.35:
        return (
            f"A witness at Junction {junction_id} reports a partial match to '{notice.parsed_description}'. "
            "They remember a nervous person and one visual detail, but the direction of travel is uncertain."
        )
    if reliability < 0.55:
        return (
            f"A witness at Junction {junction_id} confidently reports a sighting, but the account appears to combine "
            "two unrelated commuters and should be treated cautiously."
        )
    return (
        f"A witness at Junction {junction_id} saw someone ordinary who only loosely matches the notice. "
        "The report is probably a false positive."
    )


def _fragile_facts_from_notice(notice: LookoutNotice) -> list[str]:
    facts = []
    text = (notice.parsed_description or notice.text).lower()
    for candidate in ("grey raincoat", "red folder", "nervous", "bag", "bus route", "taxi", "subway"):
        if all(part in text for part in candidate.split()):
            facts.append(candidate)
    return facts or ["clothing detail", "object detail", "direction of travel"]


def _extract_answer(summary: str, keywords: list[str]) -> str:
    sentences = [sentence.strip() for sentence in summary.replace("\n", " ").split(".") if sentence.strip()]
    for sentence in sentences:
        lowered = sentence.lower()
        if any(keyword in lowered for keyword in keywords):
            return f"{sentence}. I would not swear every detail is perfect."
    return "I am not sure from what I remember. I do not want to add details I did not actually notice."


def _bounded(value: float) -> float:
    return round(min(max(value, 0.0), 1.0), 2)
