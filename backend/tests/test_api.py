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
    assert [item["id"] for item in response.json()["languages"]] == ["mini_python", "mini_c"]
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
    for language in ("mini_python", "mini_c"):
        response = client.post("/api/analyze", json={"language": language, "code": ""})
        assert response.json()["parse_status"] == "invalid_no_tree"
        assert response.json()["tree_complete"] is False
        assert response.json()["tree"] is None


def test_analyze_rejects_unknown_language() -> None:
    response = client.post("/api/analyze", json={"language": "mini_java", "code": "int x = 1;"})
    assert response.status_code == 422


def test_analyze_rejects_oversized_source() -> None:
    response = client.post("/api/analyze", json={"language": "mini_python", "code": "x" * 100001})
    assert response.status_code == 422
