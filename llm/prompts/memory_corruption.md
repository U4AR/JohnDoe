You slightly corrupt witness information for a detective board game.

Current turn: {turn_number}
New corruption level: {corruption_level}

Stable facts, which should stay intact:
{stable_facts}

Fragile facts, which may become blurrier:
{fragile_facts}

Current witness summary:
{current_summary}

Rules:
- Slightly corrupt the information only.
- Preserve stable facts.
- Do not completely rewrite the statement.
- Blur confidence, timing, direction, or small visual details.
- Do not add new hard facts.
- Keep the witness voice natural and uncertain.
- Return JSON only.

Return:
{{
  "corruption_level": {corruption_level},
  "corrupted_summary": "...",
  "changed_fragile_facts": ["..."],
  "preserved_stable_facts": ["..."]
}}

