"""Hit the LIVE /api/witness/.../message endpoint twice with different
questions on the same Harriet Moss witness and confirm we get distinct
English answers."""
import json, sys, time, urllib.request
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent

GAME = "game_20260614_075442_190041"
WIT = "w_false_notice_001_74"

questions = ["what did you see", "where was he", "what was he carrying"]
out = REPO / "runtime" / "tmp" / "witness_api_test.txt"
out.parent.mkdir(parents=True, exist_ok=True)
lines = []
for q in questions:
    payload = json.dumps({"message": q}).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:7860/api/witness/{GAME}/{WIT}/message",
        data=payload, headers={"Content-Type": "application/json"}, method="POST",
    )
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        lines.append(f"Q: {q}  HTTP {e.code}: {e.read().decode('utf-8', errors='replace')}")
        continue
    elapsed = time.perf_counter() - start
    lines.append(f"Q ({elapsed:.2f}s): {q}")
    lines.append(f"A: {data.get('answer')}")
    lines.append("")
out.write_text("\n".join(lines), encoding="utf-8")
print(f"wrote: {out}")
