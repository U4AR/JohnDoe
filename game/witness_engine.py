from __future__ import annotations

from config import load_settings
from llm.omni_client import OmniClient
from game.context_budget import ContextBudget, trim_text_to_tokens
from grid_map.graph_loader import adjacent_junctions

from .rules import can_review_individual_witnesses
from .state import GameState, LookoutNotice, WitnessBatch, WitnessQuestion, WitnessRecord


PERSONALITIES = [
    {"style": "careful", "confidence": "measured", "quirk": "keeps correcting small details"},
    {"style": "talkative", "confidence": "overconfident", "quirk": "compares people to customers"},
    {"style": "nervous", "confidence": "uncertain", "quirk": "remembers colors better than faces"},
    {"style": "blunt", "confidence": "low", "quirk": "answers in short fragments"},
]

FALSE_WITNESS_PROFILES = [
    ("Harriet Moss", "passer-by", {"style": "nervous", "confidence": "uncertain", "quirk": "remembers colors better than faces"}),
    ("Leonard Pike", "delivery clerk", {"style": "blunt", "confidence": "measured", "quirk": "describes routes before appearances"}),
    ("Nora Wren", "market customer", {"style": "talkative", "confidence": "overconfident", "quirk": "compares strangers to regular shoppers"}),
    ("Samuel Croft", "retired conductor", {"style": "careful", "confidence": "measured", "quirk": "corrects himself when timing is uncertain"}),
]

FALSE_ACCOUNT_TEMPLATES = [
    "At Junction {junction}, {name} saw a delivery cyclist in a navy waterproof coat carrying a flat brown parcel toward the bus stops. The coat looked dark rather than grey, and {name} never saw a red folder.",
    "At Junction {junction}, {name} noticed a hurried shopper in a tan coat holding a red shopping bag near the taxi queue. The person did not wear a raincoat and remained in the area.",
    "At Junction {junction}, {name} saw a station worker in a grey work jacket carrying newspapers in a red sleeve. The worker walked toward the subway entrance but did not match the nervous behavior in the notice.",
    "At Junction {junction}, {name} remembers a commuter with a black umbrella and a burgundy document case. The commuter boarded a bus, but the clothing and carried item only partly resembled the notice.",
]

STYLE_QUIRKS = {
    "careful": "keeps correcting small details",
    "talkative": "adds comparisons from daily work",
    "nervous": "remembers colors better than faces",
    "blunt": "answers in short fragments",
    "observant": "focuses on one concrete visual detail",
    "skeptical": "avoids claiming more than was actually seen",
}


def generate_witness_batch(state: GameState, notice: LookoutNotice) -> WitnessBatch:
    witnesses = _surface_matching_witnesses(state, notice)
    witnesses.extend(_false_positive_witnesses(state, notice, len(witnesses)))

    total = len(witnesses)
    return WitnessBatch(
        batch_id=f"batch_{notice.notice_id}",
        notice_id=notice.notice_id,
        turn_number=state.turn_number,
        total_witnesses=total,
        individual_review_allowed=can_review_individual_witnesses(total),
        witnesses=witnesses,
    )


def answer_witness_question(witness: WitnessRecord, question: str, turn_number: int, use_model: bool = False) -> str:
    if use_model:
        answer = _model_witness_answer(witness, question)
        if not answer:
            answer = deterministic_witness_answer(witness, question)
        witness.question_history.append(WitnessQuestion(question=question, answer=answer, turn_number=turn_number))
        return answer
    answer = deterministic_witness_answer(witness, question)
    witness.question_history.append(WitnessQuestion(question=question, answer=answer, turn_number=turn_number))
    return answer


def deterministic_witness_answer(witness: WitnessRecord, question: str) -> str:
    lowered = question.lower()
    summary = witness.current_summary
    if any(word in lowered for word in ("carry", "holding", "object", "folder", "bag")):
        answer = _extract_answer(
            summary,
            ["carrying", "holding", "parcel", "folder", "bag", "packet", "backpack", "document case", "newspapers"],
        )
    elif any(word in lowered for word in ("where", "junction", "location")):
        answer = f"I was at Junction {witness.junction_id}. I can only speak to what I noticed there."
    elif any(word in lowered for word in ("direction", "went", "move", "route", "transport", "bus", "taxi", "subway")):
        answer = _extract_answer(summary, ["toward", "route", "bus", "taxi", "subway", "left", "moved"])
    elif any(word in lowered for word in ("clothes", "coat", "wearing", "disguise")):
        answer = _extract_answer(summary, ["coat", "raincoat", "grey", "gray", "tan", "helmet"])
    else:
        answer = f"I remember it like this: {summary}"
    return _apply_personality(witness, answer)


def witness_by_id(state: GameState, witness_id: str) -> WitnessRecord | None:
    for batch in state.witness_batches:
        for witness in batch.witnesses:
            if witness.witness_id == witness_id:
                return witness
    return None


def _surface_matching_witnesses(state: GameState, notice: LookoutNotice) -> list[WitnessRecord]:
    text_words = set(_distinctive_words(notice.text))
    planned = [int(item["junction_id"]) for item in notice.response_plan]
    candidates = []
    for potential in state.potential_witnesses:
        if potential.surfaced_notice_id:
            continue
        tag_words = set(_distinctive_words(" ".join(potential.search_tags) + " " + potential.summary))
        overlap = len(text_words & tag_words)
        if overlap == 0:
            continue
        distance = _distance_from_plan(potential.junction_id, planned)
        if distance is None or distance > 1:
            continue
        description_score = min(overlap / max(min(len(text_words), 6), 1), 1.0) * 0.58
        location_score = 0.30 if distance == 0 else 0.16
        reliability_score = potential.reliability * 0.12
        score = description_score + location_score + reliability_score
        if score >= 0.42:
            candidates.append((score, potential))
    candidates.sort(key=lambda item: (-item[0], item[1].potential_id))
    witnesses: list[WitnessRecord] = []
    for index, (score, potential) in enumerate(candidates[:18], start=1):
        potential.surfaced_notice_id = notice.notice_id
        profile = potential.profile
        personality = _complete_personality(profile)
        witnesses.append(WitnessRecord(
            witness_id=f"w_{potential.potential_id}", notice_id=notice.notice_id,
            turn_created=state.turn_number, junction_id=potential.junction_id,
            personality=personality, reliability=potential.reliability,
            memory_strength=potential.memory_strength, corruption_level=0.0,
            relevance_score=_bounded(score), original_summary=potential.summary,
            current_summary=potential.summary,
            stable_facts=[f"witness was at Junction {potential.junction_id}", *potential.observed_fact_ids],
            fragile_facts=_fragile_facts_from_notice(notice), name=profile.get("name", f"Witness {index}"),
            occupation=profile.get("occupation", "local resident"), voice_id=potential.voice_id,
            observed_fact_ids=potential.observed_fact_ids, is_false_positive=False,
        ))
    return witnesses


def _false_positive_witnesses(state: GameState, notice: LookoutNotice, real_count: int) -> list[WitnessRecord]:
    planned = [int(item["junction_id"]) for item in notice.response_plan]
    junctions = planned or [state.culprit.current_junction]
    desired = 1 + int(notice.false_positive_likelihood >= 0.45) + int(notice.false_positive_likelihood >= 0.7)
    if real_count >= 3:
        desired = 1
    witnesses: list[WitnessRecord] = []
    notice_index = max(len(state.notices), 1)
    for offset in range(desired):
        profile_index = (notice_index + offset - 1) % len(FALSE_WITNESS_PROFILES)
        name, occupation, personality = FALSE_WITNESS_PROFILES[profile_index]
        junction_id = junctions[offset % len(junctions)]
        template = FALSE_ACCOUNT_TEMPLATES[profile_index]
        summary = template.format(junction=junction_id, name=name)
        witnesses.append(WitnessRecord(
            witness_id=f"w_false_{notice.notice_id}_{junction_id}_{offset + 1:02d}",
            notice_id=notice.notice_id, turn_created=state.turn_number, junction_id=junction_id,
            personality=dict(personality), reliability=round(0.42 + profile_index * 0.05, 2),
            memory_strength=round(0.50 + (profile_index % 3) * 0.07, 2), corruption_level=0.0,
            relevance_score=round(0.12 + notice.false_positive_likelihood * 0.18, 2),
            original_summary=summary, current_summary=summary,
            stable_facts=[f"witness was at Junction {junction_id}", f"account originated from {notice.notice_id}"],
            fragile_facts=_fragile_facts_from_notice(notice), name=name, occupation=occupation,
            voice_id=f"voice_{profile_index + 1:02d}", observed_fact_ids=[], is_false_positive=True,
        ))
    return witnesses


def _model_witness_answer(witness: WitnessRecord, question: str) -> str:
    settings = load_settings()
    budget = ContextBudget.for_context(settings.llamacpp_context_length)
    # Build a plain English prompt. JSON-encoded prompts degrade to Chinese
    # filler on Q4_K_M MiniCPM-o-4.5 — see app.api_witness_message for the
    # same workaround.
    history = witness.question_history[-budget.recent_interview_turns :]
    history_block = (
        "\n".join(f"  Detective: {item.question}\n  You: {item.answer}" for item in history)
        if history else "  (no prior questions)"
    )
    stable_block = ", ".join(witness.stable_facts) if witness.stable_facts else "(none recorded)"
    personality_block = ", ".join(f"{k}: {v}" for k, v in witness.personality.items()) or "ordinary"
    synopsis = trim_text_to_tokens(witness.conversation_summary, budget.synopsis_tokens)
    synopsis_block = f"Earlier summary: {synopsis}\n" if synopsis else ""
    user = (
        f"You are {witness.name}, a {witness.occupation} ({personality_block}).\n"
        f"What you saw / know: {witness.current_summary}\n"
        f"Stable facts: {stable_block}\n"
        f"{synopsis_block}"
        f"Conversation so far:\n{history_block}\n"
        f"The detective now asks: {question!r}\n"
        f"Reply in character, in English, in one or two short sentences. "
        f"Express uncertainty naturally if you are not sure."
    )
    system = (
        "You are roleplaying a witness in an English-language detective game. "
        "Speak only English. Reply briefly. Use only the facts the user gives "
        "you. Let the supplied personality shape wording and confidence. Never "
        "invent details or reveal hidden game state."
    )
    return OmniClient.from_settings().chat(system, user, task="interview", temperature=0.55).text.strip()


def _words(text: str) -> list[str]:
    import re
    return re.findall(r"[a-z0-9]+", text.lower())


def _distinctive_words(text: str) -> list[str]:
    ignored = {
        "a", "an", "and", "at", "by", "for", "from", "high", "in", "junction", "matching",
        "near", "of", "on", "person", "reports", "request", "seen", "someone", "the", "to",
        "was", "with",
    }
    return [word for word in _words(text) if word not in ignored and not word.isdigit()]


def _distance_from_plan(junction_id: int, planned: list[int]) -> int | None:
    if junction_id in planned:
        return 0
    if any(junction_id in adjacent_junctions(item) for item in planned):
        return 1
    return None


def _apply_personality(witness: WitnessRecord, answer: str) -> str:
    style = str(witness.personality.get("style", "careful"))
    if style == "blunt":
        return answer.split(". ", 1)[0].rstrip(".") + "."
    if style == "nervous":
        return f"I think so, but I may be mixing up a detail. {answer}"
    if style == "talkative":
        return f"What stayed with me was this: {answer}"
    if style == "skeptical":
        return f"I would not make more of it than this: {answer}"
    if style == "observant":
        return f"The detail I noted was this: {answer}"
    return f"As carefully as I can put it: {answer}"


def _complete_personality(profile: dict) -> dict:
    style = str(profile.get("style") or "careful")
    return {
        "style": style,
        "confidence": str(profile.get("confidence") or "measured"),
        "quirk": str(profile.get("quirk") or STYLE_QUIRKS.get(style, "sticks to concrete details")),
    }


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
