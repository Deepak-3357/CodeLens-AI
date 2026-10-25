from __future__ import annotations

import json

import httpx
import pytest

from app.onlinecompiler import OnlineCompilerConfig, OnlineCompilerError, OnlineCompilerProvider


def config(**overrides: object) -> OnlineCompilerConfig:
    values = {
        "api_key": "provider-secret",
        "base_url": "https://compiler.test",
        "python_compiler": "python-3.14",
        "c_compiler": "gcc-15",
        "request_timeout_seconds": 1.0,
        "time_limit_seconds": 2.0,
        "max_input_length": 10,
        "max_output_length": 20,
    }
    values.update(overrides)
    return OnlineCompilerConfig(**values)


class FakeClient:
    def __init__(self, handler):
        self.handler = handler
        self.requests: list[httpx.Request] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def post(self, url, **kwargs):
        request = httpx.Request("POST", url, headers=kwargs["headers"], content=json.dumps(kwargs["json"]).encode())
        self.requests.append(request)
        return self.handler(request)


def response(request: httpx.Request, body: dict, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, json=body, request=request)


def install_client(monkeypatch, handler):
    clients: list[FakeClient] = []

    def factory(*_args, **_kwargs):
        client = FakeClient(handler)
        clients.append(client)
        return client

    monkeypatch.setattr("app.onlinecompiler.httpx.Client", factory)
    return clients


def test_python_hello_world_and_stdin(monkeypatch):
    clients = install_client(monkeypatch, lambda request: response(request, {"output": "Hello, World!\n", "error": "", "status": "success", "exit_code": 0, "signal": None, "truncated": False, "time": "0.02", "total": "0.03", "memory": "8192"}))
    result = OnlineCompilerProvider(config()).execute("mini_python", "print(input())", "World\n")
    assert result.status == "Success"
    assert result.stdout == "Hello, World!\n"
    assert result.duration_ms == 30.0
    body = json.loads(clients[0].requests[0].content)
    assert body["compiler"] == "python-3.14"
    assert body["input"] == "World\n"
    assert clients[0].requests[0].headers["Authorization"] == "provider-secret"


def test_c_hello_world_uses_configured_compiler(monkeypatch):
    clients = install_client(monkeypatch, lambda request: response(request, {"output": "Hello from C\n", "error": "", "status": "success", "exit_code": 0, "signal": None, "truncated": False, "time": "0.01", "total": "0.02", "memory": "8192"}))
    result = OnlineCompilerProvider(config(c_compiler="gcc-15")).execute("mini_c", "#include <stdio.h>\nint main(){puts(\"Hello from C\");}")
    assert result.status == "Success"
    assert json.loads(clients[0].requests[0].content)["compiler"] == "gcc-15"


def test_compilation_and_runtime_errors_are_not_success(monkeypatch):
    install_client(monkeypatch, lambda request: response(request, {"output": "", "error": "compiler error", "status": "error", "exit_code": 1, "signal": None, "truncated": False, "time": "0", "total": "0.01"}))
    result = OnlineCompilerProvider(config()).execute("mini_c", "invalid source")
    assert result.status == "Error"
    assert result.error_category == "runtime_or_compilation"
    assert result.stderr == "compiler error"


def test_timeout_and_truncation_are_safe(monkeypatch):
    install_client(monkeypatch, lambda request: response(request, {"output": "", "error": "timed out", "status": "error", "exit_code": 124, "signal": None, "truncated": False, "total": "2"}))
    result = OnlineCompilerProvider(config()).execute("mini_python", "while True: pass")
    assert result.status == "Timed Out"
    assert result.error_category == "timeout"

    install_client(monkeypatch, lambda request: response(request, {"output": "012345678901234567890123", "error": "", "status": "success", "exit_code": 0, "signal": None, "truncated": True, "total": "0.01"}))
    result = OnlineCompilerProvider(config()).execute("mini_python", "print('x')")
    assert result.status == "Error"
    assert result.error_category == "output_limit"


def test_limits_and_missing_configuration_prevent_submission(monkeypatch):
    called = False

    def unexpected(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("provider must not be called")

    monkeypatch.setattr("app.onlinecompiler.httpx.Client", unexpected)
    with pytest.raises(OnlineCompilerError, match="input exceeds"):
        OnlineCompilerProvider(config()).execute("mini_python", "print(1)", "01234567890")
    assert called is False

    monkeypatch.delenv("ONLINECOMPILER_API_KEY", raising=False)
    outcome = OnlineCompilerProvider().execute("mini_python", "print(1)")
    assert outcome.status == "Unsupported"
    assert outcome.error_category == "configuration"


@pytest.mark.parametrize("status_code", [401, 403, 429, 500, 503])
def test_provider_failures_are_sanitized(monkeypatch, status_code):
    install_client(monkeypatch, lambda request: httpx.Response(status_code, text="secret provider response", request=request))
    with pytest.raises(OnlineCompilerError) as error:
        OnlineCompilerProvider(config()).execute("mini_python", "print(1)")
    assert "secret provider response" not in str(error.value)
    assert error.value.category == "provider"


def test_malformed_response_and_network_timeout_are_safe(monkeypatch):
    install_client(monkeypatch, lambda request: httpx.Response(200, text="not-json", request=request))
    with pytest.raises(OnlineCompilerError, match="malformed JSON"):
        OnlineCompilerProvider(config()).execute("mini_python", "print(1)")

    class TimeoutClient(FakeClient):
        def post(self, *_args, **_kwargs):
            raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr("app.onlinecompiler.httpx.Client", lambda *_args, **_kwargs: TimeoutClient(lambda request: response(request, {})))
    with pytest.raises(OnlineCompilerError) as error:
        OnlineCompilerProvider(config()).execute("mini_python", "print(1)")
    assert error.value.timed_out is True


def test_api_key_is_not_in_public_error_or_result(monkeypatch):
    install_client(monkeypatch, lambda request: httpx.Response(401, text="invalid", request=request))
    with pytest.raises(OnlineCompilerError) as error:
        OnlineCompilerProvider(config()).execute("mini_python", "print('source-secret')")
    assert "provider-secret" not in str(error.value)
    assert "source-secret" not in str(error.value)
