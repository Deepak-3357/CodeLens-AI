"""Backend-only adapter for OnlineCompiler.io's synchronous run API."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx


class OnlineCompilerError(Exception):
    """A sanitized provider error suitable for the public API."""

    def __init__(self, message: str, *, category: str = "provider", timed_out: bool = False) -> None:
        super().__init__(message)
        self.category = category
        self.timed_out = timed_out


@dataclass(frozen=True)
class OnlineCompilerConfig:
    api_key: str
    base_url: str
    python_compiler: str
    c_compiler: str
    request_timeout_seconds: float
    time_limit_seconds: float
    max_input_length: int
    max_output_length: int

    @classmethod
    def from_env(cls) -> "OnlineCompilerConfig | None":
        api_key = os.getenv("ONLINECOMPILER_API_KEY", "").strip()
        python_compiler = os.getenv("ONLINECOMPILER_PYTHON_COMPILER", "").strip()
        c_compiler = os.getenv("ONLINECOMPILER_C_COMPILER", "").strip()
        if not api_key or not python_compiler or not c_compiler:
            return None
        return cls(
            api_key=api_key,
            base_url=os.getenv("ONLINECOMPILER_BASE_URL", "https://api.onlinecompiler.io").strip().rstrip("/"),
            python_compiler=python_compiler,
            c_compiler=c_compiler,
            request_timeout_seconds=_bounded_float("ONLINECOMPILER_REQUEST_TIMEOUT_SECONDS", 35.0, 1.0, 45.0),
            time_limit_seconds=_bounded_float("ONLINECOMPILER_TIME_LIMIT_SECONDS", 10.0, 0.1, 30.0),
            max_input_length=_bounded_int("ONLINECOMPILER_MAX_INPUT_LENGTH", 100_000, 0, 100_000),
            max_output_length=_bounded_int("ONLINECOMPILER_MAX_OUTPUT_LENGTH", 64_000, 1, 64_000),
        )


@dataclass(frozen=True)
class ExecutionOutcome:
    status: str
    stdout: str
    stderr: str
    compile_output: str
    duration_ms: float | None
    message: str
    error_category: str | None = None


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        return max(minimum, min(maximum, int(os.getenv(name, str(default)))))
    except ValueError:
        return default


def _bounded_float(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        return max(minimum, min(maximum, float(os.getenv(name, str(default)))))
    except ValueError:
        return default


def _bounded_text(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    if len(value) <= limit:
        return value
    return value[:limit] + "\n[output truncated by CodeLens AI]"


class OnlineCompilerProvider:
    def __init__(self, config: OnlineCompilerConfig | None = None) -> None:
        self.config = config or OnlineCompilerConfig.from_env()

    def execute(self, language: str, source_code: str, stdin: str | None = None) -> ExecutionOutcome:
        input_limit = self.config.max_input_length if self.config is not None else _bounded_int("ONLINECOMPILER_MAX_INPUT_LENGTH", 100_000, 0, 100_000)
        if stdin is not None and len(stdin) > input_limit:
            raise OnlineCompilerError("Execution input exceeds the configured size limit.", category="input_limit")
        if self.config is None:
            return ExecutionOutcome(
                status="Unsupported",
                stdout="",
                stderr="",
                compile_output="",
                duration_ms=None,
                message="Execution is unavailable: OnlineCompiler.io is not configured. No code was executed.",
                error_category="configuration",
            )

        compiler = self.config.python_compiler if language == "mini_python" else self.config.c_compiler
        payload: dict[str, Any] = {
            "compiler": compiler,
            "code": source_code,
            "time_limit": self.config.time_limit_seconds,
        }
        if stdin:
            payload["input"] = stdin
        headers = {"Authorization": self.config.api_key, "Content-Type": "application/json", "Accept": "application/json"}
        endpoint = f"{self.config.base_url}/api/run-code-sync/"
        try:
            with httpx.Client(timeout=self.config.request_timeout_seconds) as client:
                response = client.post(endpoint, json=payload, headers=headers)
        except httpx.TimeoutException as error:
            raise OnlineCompilerError("The execution provider request timed out.", category="provider_timeout", timed_out=True) from error
        except httpx.HTTPError as error:
            raise OnlineCompilerError("The execution provider could not be reached.", category="provider") from error

        if response.status_code >= 400:
            raise OnlineCompilerError(_provider_http_message(response.status_code), category="provider")
        try:
            result = response.json()
        except ValueError as error:
            raise OnlineCompilerError("The execution provider returned malformed JSON.", category="provider") from error
        if not isinstance(result, dict):
            raise OnlineCompilerError("The execution provider returned malformed JSON.", category="provider")
        return _outcome_from_result(result, self.config.max_output_length)


def _provider_http_message(status_code: int) -> str:
    if status_code in {401, 403}:
        return "The execution provider rejected its configured API key."
    if status_code == 429:
        return "The execution provider rate limit was reached."
    if status_code >= 500:
        return "The execution provider returned a server error."
    return "The execution provider rejected the execution request."


def _outcome_from_result(result: dict[str, Any], output_limit: int) -> ExecutionOutcome:
    status = result.get("status")
    exit_code = result.get("exit_code")
    if not isinstance(status, str) or not isinstance(exit_code, int):
        raise OnlineCompilerError("The execution provider returned an incomplete result.", category="provider")
    stdout = _bounded_text(result.get("output"), output_limit)
    stderr = _bounded_text(result.get("error"), output_limit)
    duration_ms = _duration_ms(result)
    truncated = result.get("truncated") is True or len(stdout) > output_limit or len(stderr) > output_limit
    if exit_code == 124:
        return ExecutionOutcome("Timed Out", stdout, stderr, "", duration_ms, "Execution exceeded the configured runtime limit.", "timeout")
    if status.lower() == "success" and exit_code == 0 and result.get("signal") in (None, "") and not truncated:
        return ExecutionOutcome("Success", stdout, stderr, "", duration_ms, "Execution completed successfully in the isolated runtime.")
    if truncated:
        return ExecutionOutcome("Error", stdout, stderr, "", duration_ms, "Execution completed but its output was truncated by the provider or configured limit.", "output_limit")
    return ExecutionOutcome("Error", stdout, stderr, "", duration_ms, "Execution failed in the configured runtime.", "runtime_or_compilation")


def _duration_ms(result: dict[str, Any]) -> float | None:
    for key in ("total", "time"):
        value = result.get(key)
        try:
            return float(value) * 1000
        except (TypeError, ValueError):
            continue
    return None
