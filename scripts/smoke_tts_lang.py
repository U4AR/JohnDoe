"""Compare TTS output language across three reference-audio configurations.

The upstream MiniCPM-o docs say there is no `language` parameter; output language
is steered by (a) the system-prompt template (we already pass lang=en) and (b)
the *reference audio* used for voice cloning. This script runs the same English
prompt under three configurations and scans the worker log for CJK code points
so we can see which reference, if any, actually produces English TTS.

Configs:
  1. No ref_audio_path                                — baseline (previous test)
  2. data/voices/voice_01.wav                          — locally-generated
                                                         Windows-TTS English voice
  3. runtime/MiniCPM-o-Demo/assets/ref_audio/
       ref_en_dlc_1.wav                                — upstream-shipped English
                                                         reference clip
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from llm.omni_client import OmniClient  # noqa: E402

WORKER_LOG = REPO / "runtime" / "MiniCPM-o-Demo" / "tmp" / "phantom_grid_worker.log"
LLM_TTS_LINE = re.compile(r"LLM->TTS:\s+text='([^']*)'")
CJK_RANGE = re.compile(r"[一-鿿㐀-䶿]")
CJK_ESCAPE = re.compile(r"\\u(?:[4-9][0-9a-fA-F]{3}|[a-fA-F][0-9a-fA-F]{3})")

CONFIGS = [
    ("no reference",      None),
    ("local voice_01.wav", REPO / "data" / "voices" / "voice_01.wav"),
    ("upstream ref_en_dlc_1.wav",
        REPO / "runtime" / "MiniCPM-o-Demo" / "assets" / "ref_audio" / "ref_en_dlc_1.wav"),
]

SYSTEM = (
    "You are a witness in a noir detective game. Reply in one short English "
    "sentence. Speak only English."
)
USER = "Did you see anything unusual at the canal last night?"


def tts_chunks_since(offset: int) -> tuple[list[str], int]:
    if not WORKER_LOG.exists():
        return [], offset
    with WORKER_LOG.open("rb") as fh:
        fh.seek(offset)
        chunk = fh.read()
        new_offset = fh.tell()
    texts: list[str] = []
    for line in chunk.decode("utf-8", errors="replace").splitlines():
        match = LLM_TTS_LINE.search(line)
        if match:
            texts.append(match.group(1))
    return texts, new_offset


def main() -> int:
    client = OmniClient.from_settings()
    if not client.health(timeout=5.0).get("ready"):
        print("gateway not ready"); return 1

    print(f"{'config':32s} {'elapsed':>9s} {'chunks':>7s} {'CJK':>5s}  example")
    print("-" * 110)
    results = []
    for label, ref_path in CONFIGS:
        if ref_path is not None and not ref_path.exists():
            print(f"{label:32s} SKIP (ref not found: {ref_path})")
            continue
        log_offset = WORKER_LOG.stat().st_size if WORKER_LOG.exists() else 0
        start = time.perf_counter()
        resp = client.chat(
            SYSTEM, USER,
            task="witness",
            tts=True,
            temperature=0.4,
            ref_audio_path=str(ref_path) if ref_path else None,
        )
        elapsed = time.perf_counter() - start
        chunks, _ = tts_chunks_since(log_offset)
        cjk_chunks = [c for c in chunks if CJK_RANGE.search(c) or CJK_ESCAPE.search(c)]
        example = (cjk_chunks[0] if cjk_chunks else (chunks[0] if chunks else ""))[:60]
        print(f"{label:32s} {elapsed:8.2f}s {len(chunks):7d} {len(cjk_chunks):5d}  {example}")
        results.append((label, len(chunks), len(cjk_chunks)))

    print()
    print("verdict:")
    for label, total, cjk in results:
        if total == 0:
            print(f"  {label}: no TTS chunks produced — ambiguous")
        elif cjk == 0:
            print(f"  {label}: PASS — English TTS")
        else:
            print(f"  {label}: FAIL — {cjk}/{total} chunks contained CJK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
