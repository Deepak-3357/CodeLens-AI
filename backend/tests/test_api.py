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


def test_analyze_supports_mini_c() -> None:
    response = client.post("/api/analyze", json={"language": "mini_c", "code": "int x = 1;"})
    assert response.status_code == 200
    assert response.json()["success"] is True


def test_analyze_rejects_unknown_language() -> None:
    response = client.post("/api/analyze", json={"language": "mini_java", "code": "int x = 1;"})
    assert response.status_code == 422


def test_analyze_rejects_oversized_source() -> None:
    response = client.post("/api/analyze", json={"language": "mini_python", "code": "x" * 100001})
    assert response.status_code == 422
