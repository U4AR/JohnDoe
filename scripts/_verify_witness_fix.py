"""Run the new plain-English witness prompt directly against the live LLM
(stateless /v1/chat/completions) so we can verify the fix produces distinct
sensible English answers before restarting the FastAPI server."""
import json, sys, time, urllib.request
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from config import load_settings

settings = load_settings()
out = REPO / "runtime" / "tmp" / "witness_fix_verify.txt"
out.parent.mkdir(parents=True, exist_ok=True)

WITNESS = {
    "name": "Harriet Moss",
    "occupation": "passer-by",
    "personality": {"style": "nervous", "confidence": "uncertain", "quirk": "remembers colors better than faces"},
    "current_summary": "A passer-by near Junction 74 saw an ordinary commuter who only loosely matched the notice.",
    "stable_facts": ["witness was at Junction 74"],
}

SYSTEM = (
    "You are roleplaying a witness in an English-language detective game. "
    "Speak only English. Reply in one or two short sentences. Use only the "
    "facts the user gives you. Never invent details. If you don't know, "
    "say you don't know."
)


def build_user(question, history):
    history_block = (
        "\n".join(f"  Detective: {q}\n  You: {a}" for q, a in history)
        if history else "  (no prior questions)"
    )
    stable_block = ", ".join(WITNESS["stable_facts"])
    personality_block = ", ".join(f"{k}: {v}" for k, v in WITNESS["personality"].items())
    return (
        f"You are {WITNESS['name']}, a {WITNESS['occupation']} ({personality_block}).\n"
        f"What you saw / know: {WITNESS['current_summary']}\n"
        f"Stable facts: {stable_block}\n"
        f"Conversation so far:\n{history_block}\n"
        f"The detective now asks: {question!r}\n"
        f"Reply in character, in English, in one or two short sentences."
    )


def call(messages):
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
    return data["choices"][0]["message"]["content"].strip(), time.perf_counter() - start


history = []
lines = []
for q in ["what did you see", "where was he", "what was he carrying", "what time was this"]:
    user = build_user(q, history)
    answer, elapsed = call([{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}])
    lines.append(f"Q ({elapsed:.2f}s): {q}")
    lines.append(f"A: {answer}")
    lines.append("")
    history.append((q, answer))

out.write_text("\n".join(lines), encoding="utf-8")
print(f"wrote: {out}")
