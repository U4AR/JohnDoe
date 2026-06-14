"""Test witness path with (a) JSON-encoded prompt vs (b) plain English prompt."""
import json, sys, time, urllib.request
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from config import load_settings

settings = load_settings()
out = REPO / "runtime" / "tmp" / "witness_prompt_test.txt"
out.parent.mkdir(parents=True, exist_ok=True)

SYSTEM_OLD = (
    "You are this fictional witness. Answer only from allowed knowledge. "
    "Never invent or reveal hidden game state. Keep the reply natural, "
    "concise, and in English."
)
SYSTEM_NEW = (
    "You are roleplaying a witness in an English detective game. Reply in ONE "
    "short English sentence based only on the facts the user gives you. "
    "Output English only. Do not output Chinese."
)
SUMMARY = "A passer-by near Junction 74 saw an ordinary commuter who only loosely matched the notice."
QUESTIONS = ["what did you see", "where was he", "what was he carrying"]


def call(messages, label, lines):
    payload = {
        "model": settings.minicpm_quantization or settings.llm_model,
        "messages": messages,
        "temperature": 0.55,
        "max_tokens": 120,
        "stream": False,
    }
    req = urllib.request.Request(
        "http://127.0.0.1:19060/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    start = time.perf_counter()
    with urllib.request.urlopen(req, timeout=90) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    elapsed = time.perf_counter() - start
    text = data["choices"][0]["message"]["content"].strip()
    lines.append(f"  Q: {label}  ({elapsed:.2f}s)")
    lines.append(f"  A: {text}")
    lines.append("")


lines: list[str] = []

lines.append("===== CONFIG A: current code — JSON-encoded user message")
for q in QUESTIONS:
    user = json.dumps({
        "profile": {"name": "Harriet Moss", "occupation": "passer-by", "style": "nervous"},
        "allowed_knowledge": SUMMARY,
        "stable_facts": ["witness was at Junction 74"],
        "recent_conversation": [],
        "question": q,
    })
    call([{"role": "system", "content": SYSTEM_OLD}, {"role": "user", "content": user}], q, lines)

lines.append("===== CONFIG B: plain English prompt, same data")
for q in QUESTIONS:
    user = (
        f"You are Harriet Moss, a nervous passer-by who only saw this:\n"
        f"\"{SUMMARY}\"\n"
        f"The detective asks you: {q!r}.\n"
        f"Reply in one short English sentence, based only on what you saw."
    )
    call([{"role": "system", "content": SYSTEM_NEW}, {"role": "user", "content": user}], q, lines)

out.write_text("\n".join(lines), encoding="utf-8")
print(f"wrote: {out}")
