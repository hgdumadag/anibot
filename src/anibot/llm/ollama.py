from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any

import httpx


DEFAULT_OLLAMA_HOST = os.getenv("ANIBOT_OLLAMA_HOST", "http://127.0.0.1:11434")
DEFAULT_OLLAMA_MODEL = os.getenv("ANIBOT_OLLAMA_MODEL", "gemma4:e2b")
DEFAULT_OLLAMA_TIMEOUT_SECONDS = float(os.getenv("ANIBOT_OLLAMA_TIMEOUT_SECONDS", "120"))
DEFAULT_OLLAMA_NUM_PREDICT = int(os.getenv("ANIBOT_OLLAMA_NUM_PREDICT", "1400"))


@dataclass(frozen=True)
class OllamaStatus:
    available: bool
    host: str
    model: str
    models: list[str]
    message: str


class OllamaClient:
    def __init__(
        self,
        host: str = DEFAULT_OLLAMA_HOST,
        model: str = DEFAULT_OLLAMA_MODEL,
        timeout_seconds: float = DEFAULT_OLLAMA_TIMEOUT_SECONDS,
        num_predict: int = DEFAULT_OLLAMA_NUM_PREDICT,
    ):
        self.host = host.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.num_predict = num_predict

    def status(self, timeout_seconds: float = 2.0) -> OllamaStatus:
        try:
            response = httpx.get(f"{self.host}/api/tags", timeout=timeout_seconds)
            response.raise_for_status()
            models = sorted(item.get("name", "") for item in response.json().get("models", []) if item.get("name"))
        except Exception as exc:
            return OllamaStatus(
                available=False,
                host=self.host,
                model=self.model,
                models=[],
                message=f"Ollama is not reachable: {exc}",
            )
        if self.model not in models:
            return OllamaStatus(
                available=False,
                host=self.host,
                model=self.model,
                models=models,
                message=f"Ollama is reachable, but model '{self.model}' is not installed.",
            )
        return OllamaStatus(
            available=True,
            host=self.host,
            model=self.model,
            models=models,
            message=f"Ollama is reachable and model '{self.model}' is installed.",
        )

    def generate_json(self, prompt: str) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": True,
            "format": "json",
            "keep_alive": "30m",
            "options": {
                "temperature": 0.1,
                "top_p": 0.8,
                "num_predict": self.num_predict,
            },
        }
        timeout = httpx.Timeout(connect=5.0, read=self.timeout_seconds, write=10.0, pool=5.0)
        raw = ""
        try:
            with httpx.stream("POST", f"{self.host}/api/generate", json=payload, timeout=timeout) as response:
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    response.read()
                    detail = _ollama_error_detail(response)
                    raise RuntimeError(f"Ollama generation failed with HTTP {response.status_code}: {detail}") from exc
                for line in response.iter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    error = chunk.get("error")
                    if isinstance(error, str) and error.strip():
                        raise RuntimeError(f"Ollama generation failed: {error.strip()[:500]}")
                    fragment = chunk.get("response", "")
                    if isinstance(fragment, str):
                        raw += fragment
                    if chunk.get("done") is True:
                        break
        except httpx.ReadTimeout as exc:
            raise TimeoutError(f"Ollama generation timed out after {self.timeout_seconds:g} seconds") from exc
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError("Ollama returned an empty response")
        return json.loads(raw)


def _ollama_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        text = response.text.strip()
        return text[:500] if text else "No error body returned"
    error = payload.get("error")
    if isinstance(error, str) and error.strip():
        return error.strip()[:500]
    return json.dumps(payload, ensure_ascii=True)[:500]
