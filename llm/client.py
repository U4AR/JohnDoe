from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from config import Settings, load_settings


@dataclass
class LocalLlamaClient:
    settings: Settings

    @classmethod
    def from_settings(cls) -> "LocalLlamaClient":
        return cls(load_settings())

    def chat(self, system_prompt: str, user_prompt: str, temperature: float = 0.4) -> str:
        url = f"{self.settings.llamacpp_base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": self.settings.llm_model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Could not reach local llama.cpp server at {url}") from exc

        return data["choices"][0]["message"]["content"]

    def json_chat(self, system_prompt: str, user_prompt: str, temperature: float = 0.2) -> dict[str, Any]:
        content = self.chat(system_prompt, user_prompt, temperature=temperature)
        return parse_json_object(content)


def parse_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"LLM response did not contain a JSON object: {text[:200]}")
    return json.loads(stripped[start : end + 1])

