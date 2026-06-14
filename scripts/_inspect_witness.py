import json, sys, glob
from pathlib import Path

games = sorted(Path("data/games").glob("game_*"), key=lambda p: p.stat().st_mtime, reverse=True)
if not games:
    print("no games")
    sys.exit(0)
g = games[0]
print(f"game: {g.name}\n")
for batch_file in sorted((g / "witnesses").glob("*.json")):
    data = json.loads(batch_file.read_text(encoding="utf-8"))
    print(f"batch {batch_file.name}: {len(data.get('witnesses', []))} witnesses")
    for w in data.get("witnesses", []):
        print(f"  --- {w['witness_id']} | {w.get('name')} | junction={w.get('junction_id')}")
        print(f"      summary: {w['current_summary'][:160]}")
        history = w.get("question_history", [])
        print(f"      Q/A history ({len(history)} turns):")
        for h in history:
            print(f"        Q: {h['question']!r}")
            print(f"        A: {h['answer']!r}")
