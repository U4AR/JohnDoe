"""Hit the underlying llama-server endpoint with a trivial English prompt to
see if the LLM itself is broken or only the witness path is."""
import json, sys, time, urllib.request
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from config import load_settings

settings = load_settings()
out = REPO / "runtime" / "tmp" / "llm_probe.txt"
out.parent.mkdir(parents=True, exist_ok=True)

prompts = [
    ("system: You are a helpful assistant. Respond ONLY in English.\nuser: What is 2 + 2? Reply with the digit.",
     [{"role": "system", "content": "You are a helpful assistant. Respond ONLY in English."},
      {"role": "user", "content": "What is 2 + 2? Reply with the digit."}]),
    ("system: Reply in English.\nuser: Name a single fruit.",
     [{"role": "system", "content": "Reply in English."},
      {"role": "user", "content": "Name a single fruit."}]),
    ("system: -\nuser: Hello, how are you?",
     [{"role": "user", "content": "Hello, how are you?"}]),
]

lines: list[str] = []
for label, msgs in prompts:
    payload = {
        "model": settings.minicpm_quantization or settings.llm_model,
        "messages": msgs,
        "temperature": 0.3,
        "max_tokens": 80,
        "stream": False,
    }
    req = urllib.request.Request(
        "http://127.0.0.1:19060/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    start = time.perf_counter()
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    elapsed = time.perf_counter() - start
    text = data["choices"][0]["message"]["content"].strip()
    lines.append(f"=== {label}")
    lines.append(f"elapsed: {elapsed:.2f}s")
    lines.append(f"reply: {text!r}")
    lines.append(f"raw  : {text}")
    lines.append("")
out.write_text("\n".join(lines), encoding="utf-8")
print(f"wrote: {out}")
