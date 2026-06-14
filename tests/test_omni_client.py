from __future__ import annotations

import base64
import json
import urllib.request
from array import array

from config import Settings
from llm.audio import wav_to_float32_base64
from llm.omni_client import OmniClient


class FakeWebSocket:
    def __init__(self, messages: list[dict]):
        self.messages = iter(messages)
        self.sent: dict | None = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def send(self, raw: str) -> None:
        self.sent = json.loads(raw)

    def recv(self, timeout: float | None = None) -> str:
        return json.dumps(next(self.messages))


class FakeHttpResponse:
    status = 200

    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_wav_reference_is_16khz_float32_pcm():
    settings = Settings()
    encoded, duration = wav_to_float32_base64(settings.witness_voice_dir / "voice_01.wav")
    pcm = base64.b64decode(encoded)

    assert not pcm.startswith(b"RIFF")
    assert len(pcm) % 4 == 0
    assert 4.5 < duration < 5.5
    assert len(pcm) // 4 == round(duration * 16000)


def test_chat_uses_comni_websocket_and_merges_streamed_audio(monkeypatch):
    audio_a = array("f", [0.1, 0.2]).tobytes()
    audio_b = array("f", [0.3]).tobytes()
    socket = FakeWebSocket([
        {"type": "prefill_done", "input_tokens": 12},
        {
            "type": "chunk",
            "text_delta": "Good ",
            "audio_data": base64.b64encode(audio_a).decode("ascii"),
            "audio_sample_rate": 24000,
        },
        {"type": "chunk", "text_delta": "evening.", "audio_data": base64.b64encode(audio_b).decode("ascii")},
        {"type": "done", "text": "Good evening."},
    ])
    monkeypatch.setattr("websockets.sync.client.connect", lambda *args, **kwargs: socket)
    monkeypatch.setattr(OmniClient, "_text_completion", lambda *args, **kwargs: "Good evening.")
    settings = Settings(omni_gateway_url="http://127.0.0.1:8006")

    response = OmniClient(settings).chat(
        "Stay in character.",
        "What did you see?",
        tts=True,
        ref_audio_path=str(settings.witness_voice_dir / "voice_01.wav"),
    )

    assert response.text == "Good evening."
    assert base64.b64decode(response.audio_data or "") == audio_a + audio_b
    assert response.audio_sample_rate == 24000
    assert socket.sent is not None
    assert socket.sent["streaming"] is True
    assert socket.sent["tts"]["enabled"] is True
    system_content = socket.sent["messages"][0]["content"]
    assert [item["type"] for item in system_content] == ["text", "audio", "text"]
    assert not base64.b64decode(system_content[1]["data"]).startswith(b"RIFF")


def test_external_llama_cpp_uses_configured_url_and_model(monkeypatch):
    requests: list[urllib.request.Request | str] = []

    def fake_urlopen(request, timeout=None):
        requests.append(request)
        if isinstance(request, str):
            return FakeHttpResponse({"object": "list", "data": [{"id": "user-model"}]})
        return FakeHttpResponse({"choices": [{"message": {"content": "External server works."}}]})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    settings = Settings(
        llm_provider="external_llama_cpp_server",
        llamacpp_base_url="http://127.0.0.1:9090/v1",
        llm_model="user-model",
    )
    client = OmniClient(settings)

    assert client.health()["ready"] is True
    assert client.chat("System", "Hello").text == "External server works."
    request = requests[-1]
    assert isinstance(request, urllib.request.Request)
    assert request.full_url == "http://127.0.0.1:9090/v1/chat/completions"
    assert json.loads(request.data or b"{}")["model"] == "user-model"
