from __future__ import annotations

import json
import logging

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.languages.mini_cpp.analyzer import analyze_mini_cpp


client = TestClient(app)


class FakeResponse:
    def __init__(self, status_code: int = 200, payload: object | None = None) -> None:
        self.status_code = status_code
        self.payload = payload

    def json(self) -> object:
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def configure_groq(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODELENS_AI_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "placeholder-key")
    monkeypatch.setenv("GROQ_API_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("GROQ_MODEL", "openai/gpt-oss-20b")
    monkeypatch.setenv("CODELENS_AI_TIMEOUT_SECONDS", "60")


def test_generation_uses_groq_and_keeps_source_separate(monkeypatch: pytest.MonkeyPatch) -> None:
    configure_groq(monkeypatch)
    captured: dict[str, object] = {}

    def fake_post(url: str, **kwargs: object) -> FakeResponse:
        captured.update({"url": url, **kwargs})
        return FakeResponse(payload={"id": "chatcmpl-test", "object": "chat.completion", "choices": [{"index": 0, "message": {"role": "assistant", "content": "```python\ny = 10\nprint(y)\n```"}, "finish_reason": "stop"}]})

    monkeypatch.setattr("app.ai_provider.httpx.post", fake_post)
    source = "x = 10\nprint(x)"
    response = client.post("/api/generate-alternative", json={"language": "mini_python", "source_code": source})
    assert response.status_code == 200
    assert response.json() == {"language": "mini_python", "generated_code": "y = 10\nprint(y)", "provider": "groq", "model": "openai/gpt-oss-20b"}
    assert captured["url"] == "https://example.invalid/v1/chat/completions"
    assert captured["headers"] == {"Authorization": "Bearer placeholder-key", "Content-Type": "application/json"}
    assert source not in response.json()["generated_code"]
    assert captured["json"]["messages"][0]["role"] == "system"  # type: ignore[index]
    assert captured["json"]["messages"][1]["role"] == "user"  # type: ignore[index]


@pytest.mark.parametrize("language", ["mini_python", "mini_c", "mini_cpp"])
def test_generation_accepts_supported_languages(monkeypatch: pytest.MonkeyPatch, language: str) -> None:
    configure_groq(monkeypatch)
    monkeypatch.setattr("app.ai_provider.httpx.post", lambda *args, **kwargs: FakeResponse(payload={"choices": [{"message": {"content": "alternative"}}]}))
    response = client.post("/api/generate-alternative", json={"language": language, "source_code": "x"})
    assert response.status_code == 200
    assert response.json()["language"] == language


def test_cpp_generated_alternative_still_requires_independent_analysis(monkeypatch: pytest.MonkeyPatch) -> None:
    configure_groq(monkeypatch)
    generated = "int main() { std::cout << 1 << std::endl; }"
    monkeypatch.setattr("app.ai_provider.httpx.post", lambda *args, **kwargs: FakeResponse(payload={"choices": [{"message": {"content": generated}}]}))
    response = client.post("/api/generate-alternative", json={"language": "mini_cpp", "source_code": "int main() { return 0; }"})
    assert response.status_code == 200
    analyzed = analyze_mini_cpp(response.json()["generated_code"])
    assert analyzed["language"] == "mini_cpp"
    assert analyzed["parse_status"] == "valid_complete"
    assert analyzed["tree_complete"] is True


def test_generation_rejects_invalid_input(monkeypatch: pytest.MonkeyPatch) -> None:
    configure_groq(monkeypatch)
    assert client.post("/api/generate-alternative", json={"language": "python", "source_code": "x"}).status_code == 422
    assert client.post("/api/generate-alternative", json={"language": "mini_python", "source_code": "   "}).status_code == 422
    assert client.post("/api/generate-alternative", json={"language": "mini_python", "source_code": "x" * 100001}).status_code == 422


def test_generation_requires_backend_key(monkeypatch: pytest.MonkeyPatch) -> None:
    configure_groq(monkeypatch)
    monkeypatch.delenv("GROQ_API_KEY")
    response = client.post("/api/generate-alternative", json={"language": "mini_python", "source_code": "x"})
    assert response.status_code == 503
    assert "placeholder-key" not in response.text


@pytest.mark.parametrize(("status_code", "expected_status"), [(400, 400), (401, 401), (403, 403), (404, 404), (429, 429), (500, 502)])
def test_provider_http_errors_are_safe(monkeypatch: pytest.MonkeyPatch, status_code: int, expected_status: int) -> None:
    configure_groq(monkeypatch)
    monkeypatch.setattr("app.ai_provider.httpx.post", lambda *args, **kwargs: FakeResponse(status_code=status_code, payload={"error": "secret upstream detail"}))
    response = client.post("/api/generate-alternative", json={"language": "mini_python", "source_code": "x"})
    assert response.status_code == expected_status
    assert "secret upstream detail" not in response.text
    assert "placeholder-key" not in response.text


def test_provider_network_and_timeout_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    configure_groq(monkeypatch)
    monkeypatch.setattr("app.ai_provider.httpx.post", lambda *args, **kwargs: (_ for _ in ()).throw(httpx.ConnectError("network secret")))
    response = client.post("/api/generate-alternative", json={"language": "mini_python", "source_code": "x"})
    assert response.status_code == 502
    assert "network secret" not in response.text
    monkeypatch.setattr("app.ai_provider.httpx.post", lambda *args, **kwargs: (_ for _ in ()).throw(httpx.ReadTimeout("timeout secret")))
    response = client.post("/api/generate-alternative", json={"language": "mini_python", "source_code": "x"})
    assert response.status_code == 504
    assert "timeout secret" not in response.text


@pytest.mark.parametrize("payload", [None, {"choices": []}, {"choices": [{"message": {"content": ""}}]}, {"choices": [{"message": {"content": "```python\nmissing close"}}]}])
def test_malformed_or_empty_provider_output_is_rejected(monkeypatch: pytest.MonkeyPatch, payload: object) -> None:
    configure_groq(monkeypatch)
    monkeypatch.setattr("app.ai_provider.httpx.post", lambda *args, **kwargs: FakeResponse(payload=payload))
    response = client.post("/api/generate-alternative", json={"language": "mini_python", "source_code": "x"})
    assert response.status_code == 502


def test_malformed_json_is_rejected_without_echoing_provider_body(monkeypatch: pytest.MonkeyPatch) -> None:
    configure_groq(monkeypatch)
    monkeypatch.setattr("app.ai_provider.httpx.post", lambda *args, **kwargs: FakeResponse(payload=json.JSONDecodeError("provider secret", "", 0)))
    response = client.post("/api/generate-alternative", json={"language": "mini_python", "source_code": "x"})
    assert response.status_code == 502
    assert "provider secret" not in response.text


def test_provider_diagnostics_are_categorized_without_sensitive_payload(caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    configure_groq(monkeypatch)
    caplog.set_level(logging.WARNING)
    monkeypatch.setattr("app.ai_provider.httpx.post", lambda *args, **kwargs: FakeResponse(status_code=404, payload={"error": {"code": "model_not_found", "message": "model openai/gpt-oss-20b was not found"}}))
    response = client.post("/api/generate-alternative", json={"language": "mini_python", "source_code": "secret_source = 1"})
    assert response.status_code == 404
    assert "category=model_or_endpoint_not_found" in caplog.text
    assert "provider_code=model_not_found" in caplog.text
    assert "secret_source" not in caplog.text
    assert "model openai/gpt-oss-20b was not found" in caplog.text


def test_incomplete_response_and_provider_error_object_are_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    configure_groq(monkeypatch)
    monkeypatch.setattr("app.ai_provider.httpx.post", lambda *args, **kwargs: FakeResponse(payload={"choices": [{"message": {}}]}))
    response = client.post("/api/generate-alternative", json={"language": "mini_python", "source_code": "x"})
    assert response.status_code == 502
    assert "no generated text" in response.text
    monkeypatch.setattr("app.ai_provider.httpx.post", lambda *args, **kwargs: FakeResponse(payload={"error": {"code": "provider_error", "message": "provider failed"}}))
    response = client.post("/api/generate-alternative", json={"language": "mini_python", "source_code": "x"})
    assert response.status_code == 502
    assert "provider failed" not in response.text


def test_provider_selection_does_not_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    configure_groq(monkeypatch)
    monkeypatch.setenv("CODELENS_AI_PROVIDER", "ollama")
    response = client.post("/api/generate-alternative", json={"language": "mini_python", "source_code": "x"})
    assert response.status_code == 503
