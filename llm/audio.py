from __future__ import annotations

import audioop
import base64
import wave
from array import array
from pathlib import Path


def wav_to_float32_base64(path: Path, target_rate: int = 16000) -> tuple[str, float]:
    """Return mono float32 PCM expected by the MiniCPM-o Comni APIs."""
    with wave.open(str(path), "rb") as source:
        channels = source.getnchannels()
        sample_width = source.getsampwidth()
        source_rate = source.getframerate()
        pcm = source.readframes(source.getnframes())

    if channels > 1:
        pcm = audioop.tomono(pcm, sample_width, 0.5, 0.5)
    if sample_width != 2:
        pcm = audioop.lin2lin(pcm, sample_width, 2)
    if source_rate != target_rate:
        pcm, _ = audioop.ratecv(pcm, 2, 1, source_rate, target_rate, None)

    int_samples = array("h")
    int_samples.frombytes(pcm)
    float_samples = array("f", (sample / 32768.0 for sample in int_samples))
    duration = len(float_samples) / target_rate
    return base64.b64encode(float_samples.tobytes()).decode("ascii"), duration
