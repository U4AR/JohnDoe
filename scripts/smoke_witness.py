"""End-to-end smoke test for the witness chat path.

Bypasses the game state machine and hits the same OmniClient.chat() entrypoint
the witness UI uses so we can:

  (1) confirm the *default* witness path (TTS off) is fast on the GPU,
  (2) document the *opt-in* TTS path's current behaviour by scanning the worker
      log for Mandarin characters that the LLM->TTS pipeline emits (those bytes
      never reach the websocket "text" field, so we have to read the log).

Writes the resulting wav to runtime/tmp/smoke_witness.wav for manual playback.
"""

from __future__ import annotations

import base64
import re
import struct
import sys
import time
import wave
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from llm.omni_client import OmniClient  # noqa: E402


WORKER_LOG = REPO / "runtime" / "MiniCPM-o-Demo" / "tmp" / "phantom_grid_worker.log"
LLM_TTS_LINE = re.compile(r"LLM->TTS:\s+text='([^']*)'")
# Worker log stores non-ASCII as Python-style \uXXXX escapes, so we have to
# match both literal CJK code points and the escape form.
CJK_RANGE = re.compile(r"[一-鿿㐀-䶿]")
CJK_ESCAPE = re.compile(r"\\u(?:[4-9][0-9a-fA-F]{3}|[a-fA-F][0-9a-fA-F]{3})")


def time_call(label, fn):
    print(f"== {label}")
    start = time.perf_counter()
    out = fn()
    elapsed = time.perf_counter() - start
    print(f"   elapsed: {elapsed:.2f}s")
    return out, elapsed


def tail_llm_tts_text(since_offset: int) -> tuple[list[str], int]:
    if not WORKER_LOG.exists():
        return [], since_offset
    with WORKER_LOG.open("rb") as fh:
        fh.seek(since_offset)
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
    health = client.health(timeout=5.0)
    print("gateway reachable:", health.get("reachable"), "ready:", health.get("ready"))
    if not health.get("ready"):
        print("gateway not ready; aborting")
        return 1

    system_text = (
        "You are a witness in a noir detective game. Reply in one short English "
        "sentence. Do not use Chinese characters."
    )
    user_text = "Did you see anything unusual at the canal last night?"

    log_offset = WORKER_LOG.stat().st_size if WORKER_LOG.exists() else 0

    text_resp, text_elapsed = time_call(
        "text-only chat (default app path, TTS off)",
        lambda: client.chat(system_text, user_text, task="witness", tts=False, temperature=0.4),
    )
    print("   text:", text_resp.text[:240])

    short_user = "Reply in one short English sentence and nothing else."
    tts_resp, tts_elapsed = time_call(
        "chat + TTS (opt-in, audio_assistant mode)",
        lambda: client.chat(system_text, short_user, task="witness", tts=True, temperature=0.4),
    )
    print("   text:", tts_resp.text[:240])
    print("   audio sample rate:", tts_resp.audio_sample_rate)
    print("   audio b64 length:", len(tts_resp.audio_data or ""))

    if tts_resp.audio_data:
        pcm = base64.b64decode(tts_resp.audio_data)
        wav_path = REPO / "runtime" / "tmp" / "smoke_witness.wav"
        wav_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(tts_resp.audio_sample_rate or 24000)
            if len(pcm) % 4 == 0 and pcm[:4] != b"RIFF":
                floats = struct.unpack(f"<{len(pcm) // 4}f", pcm)
                pcm = b"".join(struct.pack("<h", max(-32768, min(32767, int(f * 32767)))) for f in floats)
            wf.writeframes(pcm)
        print("   wrote:", wav_path)

    # Real language check: pull the LLM->TTS lines the worker emitted during
    # this run and look for CJK code points in the text the model produced.
    tts_texts, _ = tail_llm_tts_text(log_offset)
    cjk_lines = [t for t in tts_texts if CJK_RANGE.search(t) or CJK_ESCAPE.search(t)]
    print("=" * 60)
    print(f"text-only elapsed   : {text_elapsed:6.2f}s   (the *default* app path)")
    print(f"chat+TTS elapsed    : {tts_elapsed:6.2f}s   (opt-in only)")
    print(f"LLM->TTS chunks seen: {len(tts_texts)}")
    print(f"  chunks w/ CJK     : {len(cjk_lines)}")
    if cjk_lines:
        print(f"  example CJK chunk : {cjk_lines[0][:120]}")
    print()
    fast_default = text_elapsed < 15
    print("default path fast?  :", "PASS" if fast_default else "FAIL")
    print("opt-in TTS English? :", "PASS" if not cjk_lines else "EXPECTED-FAIL (audio_assistant model is Chinese-prior)")
    return 0 if fast_default else 2


if __name__ == "__main__":
    raise SystemExit(main())
