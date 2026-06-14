from __future__ import annotations

from dataclasses import dataclass


MIN_CONTEXT = 4096
MAX_CONTEXT = 32768


@dataclass(frozen=True)
class ContextBudget:
    context_length: int
    output_tokens: int
    prompt_tokens: int
    recent_story_segments: int
    recent_interview_turns: int
    synopsis_tokens: int

    @classmethod
    def for_context(cls, context_length: int) -> "ContextBudget":
        clean = normalize_context_length(context_length)
        output = min(max(round(clean * 0.15), 512), 2048)
        prompt = clean - output
        scale = clean / MIN_CONTEXT
        return cls(
            context_length=clean,
            output_tokens=output,
            prompt_tokens=prompt,
            recent_story_segments=min(max(int(scale * 2), 2), 12),
            recent_interview_turns=min(max(int(scale * 3), 3), 24),
            synopsis_tokens=min(max(int(prompt * 0.18), 384), 1800),
        )

    def task_prompt_limit(self, task: str) -> int:
        shares = {
            "decision": 0.48,
            "story": 0.78,
            "witness": 0.58,
            "interview": 0.72,
            "summary": 0.48,
        }
        return max(1024, int(self.prompt_tokens * shares.get(task, 0.60)))


def normalize_context_length(value: int | str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Context length must be an integer.") from exc
    if parsed < MIN_CONTEXT or parsed > MAX_CONTEXT:
        raise ValueError(f"Context length must be between {MIN_CONTEXT} and {MAX_CONTEXT}.")
    return max(MIN_CONTEXT, min(MAX_CONTEXT, round(parsed / 1024) * 1024))


def trim_text_to_tokens(text: str, max_tokens: int) -> str:
    # A conservative local approximation keeps budgeting independent of a tokenizer.
    max_chars = max_tokens * 3
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]
