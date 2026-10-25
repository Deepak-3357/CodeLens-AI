from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


class FakeResponse:
    def __init__(self, status_code: int = 200, payload: object | None = None) -> None:
        self.status_code = status_code
        self.payload = payload

    def json(self) -> object:
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def configure_grok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODELENS_AI_PROVIDER", "grok")
    monkeypatch.setenv("XAI_API_KEY", "placeholder-key")
    monkeypatch.setenv("XAI_API_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("XAI_MODEL", "grok-test-model")
    monkeypatch.setenv("CODELENS_AI_TIMEOUT_SECONDS", "60")


def test_generation_uses_grok_and_keeps_source_separate(monkeypatch: pytest.MonkeyPatch) -> None:
    configure_grok(monkeypatch)
    captured: dict[str, object] = {}

    def fake_post(url: str, **kwargs: object) -> FakeResponse:
        captured.update({"url": url, **kwargs})
        return FakeResponse(payload={"output_text": "```python\ny = 10\nprint(y)\n```"})

    monkeypatch.setattr("app.ai_provider.httpx.post", fake_post)
    source = "x = 10\nprint(x)"
    response = client.post("/api/generate-alternative", json={"language": "mini_python", "source_code": source})
    assert response.status_code == 200
    assert response.json() == {"language": "mini_python", "generated_code": "y = 10\nprint(y)", "provider": "grok", "model": "grok-test-model"}
    assert captured["url"] == "https://example.invalid/v1/responses"
    assert captured["headers"] == {"Authorization": "Bearer placeholder-key", "Content-Type": "application/json"}
    assert source not in response.json()["generated_code"]
    assert captured["json"]["input"][0]["role"] == "system"  # type: ignore[index]
    assert captured["json"]["input"][1]["role"] == "user"  # type: ignore[index]


@pytest.mark.parametrize("language", ["mini_python", "mini_c"])
def test_generation_accepts_supported_languages(monkeypatch: pytest.MonkeyPatch, language: str) -> None:
    configure_grok(monkeypatch)
    monkeypatch.setattr("app.ai_provider.httpx.post", lambda *args, **kwargs: FakeResponse(payload={"output": [{"type": "message", "content": [{"type": "output_text", "text": "alternative"}]}]}))
    response = client.post("/api/generate-alternative", json={"language": language, "source_code": "x"})
    assert response.status_code == 200
    assert response.json()["language"] == language


def test_generation_rejects_invalid_input(monkeypatch: pytest.MonkeyPatch) -> None:
    configure_grok(monkeypatch)
    assert client.post("/api/generate-alternative", json={"language": "python", "source_code": "x"}).status_code == 422
    assert client.post("/api/generate-alternative", json={"language": "mini_python", "source_code": "   "}).status_code == 422
    assert client.post("/api/generate-alternative", json={"language": "mini_python", "source_code": "x" * 100001}).status_code == 422


def test_generation_requires_backend_key(monkeypatch: pytest.MonkeyPatch) -> None:
    configure_grok(monkeypatch)
    monkeypatch.delenv("XAI_API_KEY")
    response = client.post("/api/generate-alternative", json={"language": "mini_python", "source_code": "x"})
    assert response.status_code == 503
    assert "placeholder-key" not in response.text


@pytest.mark.parametrize(
    ("status_code", "expected_status"),
    [(401, 502), (403, 502), (429, 429), (500, 502), (400, 502)],
)
def test_provider_http_errors_are_safe(monkeypatch: pytest.MonkeyPatch, status_code: int, expected_status: int) -> None:
    configure_grok(monkeypatch)
    monkeypatch.setattr("app.ai_provider.httpx.post", lambda *args, **kwargs: FakeResponse(status_code=status_code, payload={"error": "secret upstream detail"}))
    response = client.post("/api/generate-alternative", json={"language": "mini_python", "source_code": "x"})
    assert response.status_code == expected_status
    assert "secret upstream detail" not in response.text
    assert "placeholder-key" not in response.text


def test_provider_network_and_timeout_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    configure_grok(monkeypatch)
    monkeypatch.setattr("app.ai_provider.httpx.post", lambda *args, **kwargs: (_ for _ in ()).throw(httpx.ConnectError("network secret")))
    response = client.post("/api/generate-alternative", json={"language": "mini_python", "source_code": "x"})
    assert response.status_code == 502
    assert "network secret" not in response.text

    monkeypatch.setattr("app.ai_provider.httpx.post", lambda *args, **kwargs: (_ for _ in ()).throw(httpx.ReadTimeout("timeout secret")))
    response = client.post("/api/generate-alternative", json={"language": "mini_python", "source_code": "x"})
    assert response.status_code == 504
    assert "timeout secret" not in response.text


@pytest.mark.parametrize("payload", [None, {"output": []}, {"output_text": ""}, {"output_text": "```python\nmissing close"}])
def test_malformed_or_empty_provider_output_is_rejected(monkeypatch: pytest.MonkeyPatch, payload: object) -> None:
    configure_grok(monkeypatch)
    monkeypatch.setattr("app.ai_provider.httpx.post", lambda *args, **kwargs: FakeResponse(payload=payload))
    response = client.post("/api/generate-alternative", json={"language": "mini_python", "source_code": "x"})
    assert response.status_code == 502


def test_malformed_json_is_rejected_without_echoing_provider_body(monkeypatch: pytest.MonkeyPatch) -> None:
    configure_grok(monkeypatch)
    monkeypatch.setattr("app.ai_provider.httpx.post", lambda *args, **kwargs: FakeResponse(payload=json.JSONDecodeError("provider secret", "", 0)))
    response = client.post("/api/generate-alternative", json={"language": "mini_python", "source_code": "x"})
    assert response.status_code == 502
    assert "provider secret" not in response.text


def test_provider_selection_does_not_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    configure_grok(monkeypatch)
    monkeypatch.setenv("CODELENS_AI_PROVIDER", "ollama")
    response = client.post("/api/generate-alternative", json={"language": "mini_python", "source_code": "x"})
    assert response.status_code == 503
