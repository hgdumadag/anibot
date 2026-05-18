from __future__ import annotations

import json

import httpx
import pytest

from anibot.llm.ollama import DEFAULT_OLLAMA_NUM_PREDICT, DEFAULT_OLLAMA_TIMEOUT_SECONDS, OllamaClient


def test_default_ollama_timeout_allows_slow_local_model_loads() -> None:
    assert DEFAULT_OLLAMA_TIMEOUT_SECONDS == 120
    assert DEFAULT_OLLAMA_NUM_PREDICT == 1400


def test_generate_json_reads_streamed_ollama_fragments(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    class FakeResponse:
        status_code = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def raise_for_status(self) -> None:
            return None

        def iter_lines(self):
            yield json.dumps({"response": '{"timeline":', "done": False})
            yield json.dumps({"response": "[]}", "done": True})

    def fake_stream(method: str, url: str, **kwargs):
        captured["method"] = method
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(httpx, "stream", fake_stream)

    payload = OllamaClient(timeout_seconds=77).generate_json("prompt")

    assert payload == {"timeline": []}
    assert captured["method"] == "POST"
    assert captured["url"] == "http://127.0.0.1:11434/api/generate"
    assert captured["json"]["stream"] is True
    assert captured["json"]["keep_alive"] == "30m"
    assert captured["timeout"].read == 77


def test_generate_json_reports_read_timeout_with_configured_seconds(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_stream(method: str, url: str, **kwargs):
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(httpx, "stream", fake_stream)

    with pytest.raises(TimeoutError, match="after 12 seconds"):
        OllamaClient(timeout_seconds=12).generate_json("prompt")
