from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any


DEFAULT_VERTEX_LOCATION = os.getenv("ANIBOT_VERTEX_LOCATION", "global")
DEFAULT_VERTEX_MODEL = os.getenv("ANIBOT_VERTEX_MODEL", "gemma-4-26b-a4b-it")
DEFAULT_VERTEX_TIMEOUT_SECONDS = float(os.getenv("ANIBOT_VERTEX_TIMEOUT_SECONDS", "120"))
DEFAULT_VERTEX_NUM_PREDICT = int(os.getenv("ANIBOT_VERTEX_NUM_PREDICT", "1400"))
CREDENTIALS_ENV = "GOOGLE_APPLICATION_CREDENTIALS_JSON"
CREDENTIALS_PATH = Path(os.getenv("ANIBOT_VERTEX_CREDENTIALS_PATH", "/tmp/anibot-google-credentials.json"))


@dataclass(frozen=True)
class VertexStatus:
    available: bool
    project: str
    location: str
    model: str
    message: str


class VertexClient:
    generation_method = "vertex"

    def __init__(
        self,
        project: str | None = None,
        location: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
        num_predict: int | None = None,
    ):
        self.project = project or os.getenv("ANIBOT_VERTEX_PROJECT", "")
        self.location = location or os.getenv("ANIBOT_VERTEX_LOCATION", DEFAULT_VERTEX_LOCATION)
        self.model = model or os.getenv("ANIBOT_VERTEX_MODEL", DEFAULT_VERTEX_MODEL)
        self.timeout_seconds = timeout_seconds or float(os.getenv("ANIBOT_VERTEX_TIMEOUT_SECONDS", str(DEFAULT_VERTEX_TIMEOUT_SECONDS)))
        self.num_predict = num_predict or int(os.getenv("ANIBOT_VERTEX_NUM_PREDICT", str(DEFAULT_VERTEX_NUM_PREDICT)))

    def status(self) -> VertexStatus:
        missing = _missing_config(self.project)
        if missing:
            return VertexStatus(
                available=False,
                project=self.project,
                location=self.location,
                model=self.model,
                message=f"Vertex AI judging mode is not configured. Missing: {', '.join(missing)}.",
            )
        return VertexStatus(
            available=True,
            project=self.project,
            location=self.location,
            model=self.model,
            message=f"Vertex AI judging mode is configured for model '{self.model}'.",
        )

    def generate_json(self, prompt: str) -> dict[str, Any]:
        status = self.status()
        if not status.available:
            raise RuntimeError(status.message)
        _write_service_account_credentials()
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise RuntimeError("google-genai is required for Vertex AI judging mode.") from exc

        client = genai.Client(vertexai=True, project=self.project, location=self.location)
        response = client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
                top_p=0.8,
                max_output_tokens=self.num_predict,
            ),
        )
        text = (getattr(response, "text", None) or "").strip()
        if not text:
            raise ValueError("Vertex AI returned an empty response")
        return json.loads(text)


def _missing_config(project: str) -> list[str]:
    missing: list[str] = []
    if not project.strip():
        missing.append("ANIBOT_VERTEX_PROJECT")
    if not os.getenv(CREDENTIALS_ENV, "").strip() and not os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip():
        missing.append(CREDENTIALS_ENV)
    return missing


def _write_service_account_credentials() -> None:
    if os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip():
        return
    raw = os.getenv(CREDENTIALS_ENV, "").strip()
    if not raw:
        raise RuntimeError(f"{CREDENTIALS_ENV} is required for Vertex AI judging mode.")
    try:
        json.loads(raw)
    except ValueError as exc:
        raise RuntimeError(f"{CREDENTIALS_ENV} must contain valid service account JSON.") from exc
    CREDENTIALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CREDENTIALS_PATH.write_text(raw, encoding="utf-8")
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(CREDENTIALS_PATH)
