from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "codelens-ai-backend"}


def test_languages_endpoint() -> None:
    response = client.get("/api/languages")
    assert response.status_code == 200
    assert [item["id"] for item in response.json()["languages"]] == ["mini_python", "mini_c", "mini_cpp"]
    assert all(item["status"] == "implemented subset" for item in response.json()["languages"])


def test_analyze_endpoint_returns_tokens_and_tree() -> None:
    response = client.post("/api/analyze", json={"language": "mini_python", "code": "x = 10\nprint(x)\n"})
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["grammar_version"] == "mini-python-1.0"
    assert body["tree"]["type"] == "Program"
    assert body["parse_tree"]["type"] == "Program"
    assert body["parse_status"] == "valid_complete"
    assert body["tree_complete"] is True


def test_analyze_supports_mini_c() -> None:
    response = client.post("/api/analyze", json={"language": "mini_c", "code": "int x = 1;"})
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["parse_status"] == "valid_complete"
    assert response.json()["tree_complete"] is True


def test_analyze_supports_mini_cpp() -> None:
    response = client.post("/api/analyze", json={"language": "mini_cpp", "code": "int main() { int x = 1; std::cout << x << std::endl; }"})
    assert response.status_code == 200
    body = response.json()
    assert body["language"] == "mini_cpp"
    assert body["grammar_version"] == "mini-cpp-1.0"
    assert body["success"] is True
    assert body["parse_status"] == "valid_complete"
    assert body["tree_complete"] is True


def test_analyze_marks_recovered_syntax_trees_as_partial() -> None:
    python_response = client.post("/api/analyze", json={"language": "mini_python", "code": "print(1 + 2\n"})
    c_response = client.post("/api/analyze", json={"language": "mini_c", "code": "int x = 1"})
    assert python_response.json()["success"] is False
    assert python_response.json()["parse_status"] == "invalid_partial"
    assert python_response.json()["tree_complete"] is False
    assert python_response.json()["tree"] is not None
    assert c_response.json()["success"] is False
    assert c_response.json()["parse_status"] == "invalid_partial"
    assert c_response.json()["tree_complete"] is False


def test_analyze_marks_empty_sources_as_no_tree() -> None:
    for language in ("mini_python", "mini_c", "mini_cpp"):
        response = client.post("/api/analyze", json={"language": language, "code": ""})
        assert response.json()["parse_status"] == "invalid_no_tree"
        assert response.json()["tree_complete"] is False
        assert response.json()["tree"] is None


def test_analyze_rejects_unknown_language() -> None:
    response = client.post("/api/analyze", json={"language": "mini_java", "code": "class Main {}"})
    assert response.status_code == 422


def test_analyze_rejects_oversized_source() -> None:
    response = client.post("/api/analyze", json={"language": "mini_python", "code": "x" * 100001})
    assert response.status_code == 422


def test_execute_rejects_invalid_source_before_any_runtime() -> None:
    response = client.post("/api/execute", json={"language": "mini_python", "code": "if x\n    print(x)\n"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "Error"
    assert body["stdout"] == ""
    assert body["diagnostics"][0]["code"] == "PY_EXPECTED_TOKEN"
    assert "not started" in body["stderr"]


def test_execute_reports_safe_runtime_block_without_executing_valid_source() -> None:
    response = client.post("/api/execute", json={"language": "mini_c", "code": "int x = 1;"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "Unsupported"
    assert body["stdout"] == ""
    assert body["diagnostics"] == []
    assert "No code was executed" in body["message"]


def test_execute_interprets_restricted_mini_cpp_without_a_compiler_provider() -> None:
    response = client.post("/api/execute", json={"language": "mini_cpp", "code": "int a = 10; int b = 20; cout << a + b;"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "Success"
    assert body["stdout"] == "30"
    assert "Interpreted Mini C++" in body["message"]


def test_execute_keeps_mini_cpp_unsupported_constructs_out_of_interpreter() -> None:
    response = client.post("/api/execute", json={"language": "mini_cpp", "code": "int main() { for (int i = 0; i < 2; i++) { cout << i; } }"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "Error"
    assert body["error_category"] == "unsupported"
    assert body["stdout"] == ""


def test_execute_passes_stdin_to_configured_provider(monkeypatch) -> None:
    class FakeProvider:
        def execute(self, language, code, stdin):
            assert language == "mini_python"
            assert code == "print(input())"
            assert stdin == "hello\n"
            return type("Outcome", (), {
                "status": "Success", "stdout": "hello\n", "stderr": "", "compile_output": "",
                "duration_ms": 3.0, "message": "Execution completed successfully in the isolated runtime.", "error_category": None,
            })()

    monkeypatch.setattr("app.main.OnlineCompilerProvider", FakeProvider)
    response = client.post("/api/execute", json={"language": "mini_python", "code": "print(input())", "stdin": "hello\n"})
    assert response.status_code == 200
    assert response.json()["status"] == "Success"
    assert response.json()["stdout"] == "hello\n"


def test_execute_rejects_unknown_language_and_oversized_source() -> None:
    assert client.post("/api/execute", json={"language": "ruby", "code": "puts 1"}).status_code == 422
    assert client.post("/api/execute", json={"language": "mini_python", "code": "x" * 100001}).status_code == 422
