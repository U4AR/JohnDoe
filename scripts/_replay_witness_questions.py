"""Replay the user's two witness questions to the live model with the *exact*
prompt structure app.api_witness_message builds, so we can see whether:

  (a) the model is being called and is returning the same paraphrase both times
      (because the fallback witness's summary genuinely contains almost no info), or
  (b) something is short-circuiting / caching / falling back without calling the
      model at all.

Pulls the persisted witness record from the most recent game directory so the
prompt matches what the live UI sent. Calls OmniClient.chat() directly.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from llm.omni_client import OmniClient  # noqa: E402

def main() -> int:
    games = sorted((REPO / "data" / "games").glob("game_*"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not games:
        print("no games"); return 1
    g = games[0]
    print(f"using game: {g.name}")
    batch = json.loads(next((g / "witnesses").glob("*.json")).read_text(encoding="utf-8"))
    witness = batch["witnesses"][0]
    print(f"witness: {witness['witness_id']} | summary: {witness['current_summary']}\n")

    client = OmniClient.from_settings()
    if not client.health(timeout=5.0).get("ready"):
        print("gateway not ready"); return 1

    SYSTEM = (
        "You are this fictional witness. Answer only from allowed knowledge. "
        "Never invent or reveal hidden game state. Keep the reply natural, "
        "concise, and in English."
    )
    base_prompt = {
        "profile": {"name": witness["name"], "occupation": witness["occupation"], **witness["personality"]},
        "allowed_knowledge": witness["current_summary"],
        "stable_facts": witness["stable_facts"],
        "recent_conversation": [],
        "question": "",
    }

    questions = ["what did you see", "where was he", "what was he carrying"]
    out = REPO / "runtime" / "tmp" / "witness_replay.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for q in questions:
        prompt = dict(base_prompt)
        prompt["question"] = q
        start = time.perf_counter()
        resp = client.chat(SYSTEM, json.dumps(prompt), task="interview", temperature=0.55, tts=False)
        elapsed = time.perf_counter() - start
        lines.append(f"Q ({elapsed:.2f}s): {q!r}")
        lines.append(f"A repr: {resp.text.strip()!r}")
        lines.append(f"A raw : {resp.text.strip()}")
        lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote: {out}")
    print(f"\n{out.read_text(encoding='utf-8')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
