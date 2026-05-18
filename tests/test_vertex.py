from __future__ import annotations

import os

import pytest

from anibot.llm import vertex as vertex_module
from anibot.llm.vertex import VertexClient


def test_vertex_status_reports_missing_required_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANIBOT_VERTEX_PROJECT", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS_JSON", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)

    status = VertexClient().status()

    assert status.available is False
    assert "ANIBOT_VERTEX_PROJECT" in status.message
    assert "GOOGLE_APPLICATION_CREDENTIALS_JSON" in status.message


def test_vertex_status_reports_maas_model_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANIBOT_VERTEX_PROJECT", "demo-project")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS_JSON", '{"type":"service_account"}')

    status = VertexClient().status()

    assert status.available is True
    assert status.model == "gemma-4-26b-a4b-it-maas"
    assert "Vertex AI MaaS" in status.message


def test_vertex_writes_service_account_json_to_runtime_tmp(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    credentials_path = tmp_path / "credentials.json"
    monkeypatch.setattr(vertex_module, "CREDENTIALS_PATH", credentials_path)
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS_JSON", '{"type":"service_account","project_id":"demo"}')
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)

    vertex_module._write_service_account_credentials()

    assert credentials_path.read_text(encoding="utf-8") == '{"type":"service_account","project_id":"demo"}'
    assert os.environ["GOOGLE_APPLICATION_CREDENTIALS"] == str(credentials_path)


def test_vertex_rejects_invalid_service_account_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS_JSON", "not-json")
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)

    with pytest.raises(RuntimeError, match="valid service account JSON"):
        vertex_module._write_service_account_credentials()

