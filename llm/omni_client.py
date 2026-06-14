from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config import Settings, load_settings
from llm.audio import wav_to_float32_base64


LLM_MODEL_PATTERN = re.compile(r"MiniCPM-o-4_5-(.+)\.gguf$", re.IGNORECASE)
COMPANION_HINTS = ("audio", "vision", "tts", "token2wav", "vpm", "apm")


@dataclass
class OmniResponse:
    text: str
    audio_data: str | None = None
    audio_sample_rate: int | None = None


@dataclass
class OmniClient:
    settings: Settings

    @classmethod
    def from_settings(cls) -> "OmniClient":
        return cls(load_settings())

    def health(self, timeout: float = 0.75) -> dict[str, Any]:
        if self.settings.llm_provider in {"llama_cpp_server", "external_llama_cpp_server"}:
            base_url = self.settings.llamacpp_base_url.rstrip("/")
            try:
                with urllib.request.urlopen(f"{base_url}/models", timeout=timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                return {
                    "reachable": response.status == 200,
                    "ready": response.status == 200 and bool(payload.get("data")),
                    "detail": payload,
                }
            except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                return {"reachable": False, "ready": False, "detail": f"{exc.__class__.__name__}: {exc}"}
        return self.omni_health(timeout)

    def omni_health(self, timeout: float = 0.75) -> dict[str, Any]:
        base_url = self.settings.omni_gateway_url.rstrip("/")
        try:
            with urllib.request.urlopen(f"{base_url}/health", timeout=timeout) as response:
                health_payload = json.loads(response.read().decode("utf-8"))
            healthy = response.status == 200 and str(health_payload.get("status", "")).lower() in {"ok", "healthy"}
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            return {"reachable": False, "ready": False, "detail": f"{exc.__class__.__name__}: {exc}"}
        try:
            with urllib.request.urlopen(f"{base_url}/status", timeout=timeout) as response:
                status_payload = json.loads(response.read().decode("utf-8"))
            total = int(status_payload.get("total_workers", 0))
            unavailable = sum(int(status_payload.get(key, 0)) for key in ("loading_workers", "error_workers", "offline_workers"))
            ready = healthy and total > 0 and unavailable < total
            return {
                "reachable": True,
                "ready": ready,
                "detail": {"health": health_payload, "workers": status_payload},
            }
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
            return {
                "reachable": healthy,
                "ready": False,
                "detail": {"health": health_payload, "workers": f"{exc.__class__.__name__}: {exc}"},
            }

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        task: str = "story",
        temperature: float = 0.4,
        tts: bool = False,
        ref_audio_path: str | None = None,
        messages: list[dict[str, Any]] | None = None,
    ) -> OmniResponse:
        from game.context_budget import ContextBudget

        budget = ContextBudget.for_context(self.settings.llamacpp_context_length)
        text = self._text_completion(
            system_prompt,
            user_prompt,
            messages=messages,
            temperature=temperature,
            max_tokens=budget.output_tokens,
            json_mode=task in {"decision", "story", "witness", "case"},
        )
        if not tts:
            return OmniResponse(text=text)

        # MiniCPM-o's TTS branch has a strong Chinese training prior and
        # frequently ignores generic "repeat verbatim" instructions when given
        # English input. Mitigations: (1) drop temperature to 0 so it can't
        # creatively drift, (2) put a sharp English-only directive in the
        # system block (which is what the gateway extracts for the voice-clone
        # prompt), (3) also embed the English text in the user message so the
        # literal target text is present in two places, (4) cap max_new_tokens
        # to discourage long divergence.
        english_text = text.strip()
        system_prompt = (
            "You are an English text-to-speech narrator. Read aloud, in English, "
            "EXACTLY the text the user provides. Do not translate. Do not add "
            "words. Do not speak Chinese or any other language. If the user "
            "text is short, your output is exactly that short text."
        )
        user_prompt = english_text
        messages = None
        content = [dict(item) for item in (messages or [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ])]
        ref_audio_data: str | None = None
        ref_duration = 0.0
        if ref_audio_path:
            ref_audio = Path(ref_audio_path)
            if ref_audio.exists():
                ref_audio_data, ref_duration = wav_to_float32_base64(ref_audio)
                for item in content:
                    if item.get("role") != "system":
                        continue
                    prompt = item.get("content")
                    prompt_text = prompt if isinstance(prompt, str) else system_prompt
                    item["content"] = [
                        {"type": "text", "text": "Clone the voice in this reference audio."},
                        {
                            "type": "audio",
                            "data": ref_audio_data,
                            "name": ref_audio.name,
                            "duration": ref_duration,
                        },
                        {"type": "text", "text": prompt_text},
                    ]
                    break
        # Generation knobs sized for "speak this exact short text" — we don't
        # want the model exploring; we want it to read what we gave it.
        tts_max_tokens = min(budget.output_tokens, max(64, len(english_text.split()) * 6))
        payload = {
            "messages": content,
            "streaming": True,
            "lang": "en",
            "generation": {
                "max_new_tokens": tts_max_tokens,
                "temperature": 0.0,
                "do_sample": False,
                "repeat_penalty": 1.0,
            },
            "tts": {
                "enabled": tts,
                "mode": "audio_assistant",
                "lang": "en",
                **({"ref_audio_data": ref_audio_data} if tts and ref_audio_data else {}),
            },
            "use_tts_template": tts,
            "omni_mode": False,
            "enable_thinking": False,
        }
        gateway = self.settings.omni_gateway_url.rstrip("/")
        if gateway.startswith("https://"):
            gateway = "wss://" + gateway[8:]
        elif gateway.startswith("http://"):
            gateway = "ws://" + gateway[7:]

        text_chunks: list[str] = []
        audio_chunks: list[bytes] = []
        final_text = ""
        sample_rate: int | None = None
        try:
            from websockets.sync.client import connect
            from websockets.exceptions import WebSocketException

            with connect(
                f"{gateway}/ws/chat",
                open_timeout=15,
                close_timeout=5,
                max_size=128 * 1024 * 1024,
            ) as websocket:
                websocket.send(json.dumps(payload))
                while True:
                    raw = websocket.recv(timeout=300)
                    data = json.loads(raw)
                    message_type = data.get("type")
                    if message_type == "error":
                        raise RuntimeError(data.get("error") or "MiniCPM-o request failed.")
                    if message_type == "chunk":
                        if data.get("text_delta"):
                            text_chunks.append(str(data["text_delta"]))
                        if data.get("audio_data"):
                            audio_chunks.append(base64.b64decode(data["audio_data"]))
                        if data.get("audio_sample_rate"):
                            sample_rate = int(data["audio_sample_rate"])
                    if message_type == "done":
                        final_text = str(data.get("text") or "")
                        if data.get("audio_data"):
                            audio_chunks.append(base64.b64decode(data["audio_data"]))
                        if data.get("audio_sample_rate"):
                            sample_rate = int(data["audio_sample_rate"])
                        break
        except (OSError, TimeoutError, WebSocketException) as exc:
            raise RuntimeError("MiniCPM-o gateway could not be reached.") from exc
        return OmniResponse(
            text=text,
            audio_data=base64.b64encode(b"".join(audio_chunks)).decode("ascii") if audio_chunks else None,
            audio_sample_rate=sample_rate or (24000 if audio_chunks else None),
        )

    def _text_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        messages: list[dict[str, Any]] | None,
        temperature: float,
        max_tokens: int,
        json_mode: bool = False,
    ) -> str:
        content = messages or [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        if self.settings.llm_provider in {"llama_cpp_server", "external_llama_cpp_server"}:
            text_url = f"{self.settings.llamacpp_base_url.rstrip('/')}/chat/completions"
            model = self.settings.llm_model or (self.settings.llamacpp_model_path.name if self.settings.llamacpp_model_path else "local")
        else:
            gateway = urllib.parse.urlparse(self.settings.omni_gateway_url)
            host = gateway.hostname or "127.0.0.1"
            if ":" in host and not host.startswith("["):
                host = f"[{host}]"
            scheme = "https" if gateway.scheme == "https" else "http"
            text_url = f"{scheme}://{host}:19060/v1/chat/completions"
            model = self.settings.minicpm_quantization or self.settings.llm_model
        payload = {
            "model": model,
            "messages": content,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
            **({"response_format": {"type": "json_object"}} if json_mode else {}),
        }
        request = urllib.request.Request(
            text_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            backend = "llama.cpp" if self.settings.llm_provider in {"llama_cpp_server", "external_llama_cpp_server"} else "MiniCPM-o llama.cpp"
            raise RuntimeError(f"{backend} text endpoint could not be reached.") from exc
        try:
            return str(data["choices"][0]["message"]["content"]).strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("MiniCPM-o returned an invalid text response.") from exc

    def json_chat(self, system_prompt: str, user_prompt: str, *, task: str, temperature: float = 0.2) -> dict[str, Any]:
        return parse_json_object(self.chat(system_prompt, user_prompt, task=task, temperature=temperature).text)


def scan_minicpm_models(model_dir: Path | None) -> dict[str, Any]:
    if model_dir is None or not model_dir.exists():
        return {"models": [], "companions": [], "complete": False}
    models: list[dict[str, Any]] = []
    companions: list[str] = []
    for path in sorted(model_dir.rglob("*.gguf")):
        match = LLM_MODEL_PATTERN.match(path.name)
        lowered = path.name.lower()
        relative = path.relative_to(model_dir).as_posix()
        if match and path.parent == model_dir and not any(hint in lowered for hint in COMPANION_HINTS):
            models.append({
                "filename": path.name,
                "path": str(path),
                "quantization": match.group(1),
                "size_bytes": path.stat().st_size,
            })
        else:
            companions.append(relative)
    companion_text = " ".join(companions).lower()
    complete = bool(models) and all(group in companion_text for group in ("audio/", "tts/", "token2wav-gguf/"))
    return {"models": models, "companions": companions, "complete": complete}


def parse_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end < start:
        raise ValueError("Model response did not contain a JSON object.")
    return json.loads(stripped[start : end + 1])
