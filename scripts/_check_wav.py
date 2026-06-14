import contextlib
import wave
from pathlib import Path

for p in [
    Path(r"C:\temp\shadow_commission_london_maps_backup_20260611_183156\runtime\MiniCPM-o-Demo\assets\ref_audio\ref_en_dlc_1.wav"),
    Path(r"C:\temp\shadow_commission_london_maps_backup_20260611_183156\runtime\MiniCPM-o-Demo\assets\ref_audio\ref_minicpm_signature.wav"),
    Path(r"C:\temp\shadow_commission_london_maps_backup_20260611_183156\data\voices\voice_01.wav"),
]:
    with contextlib.closing(wave.open(str(p), "r")) as w:
        dur = w.getnframes() / w.getframerate()
        print(f"{p.name}: {w.getframerate()} Hz, {w.getnchannels()} ch, {w.getsampwidth() * 8}-bit, {dur:.2f}s")
