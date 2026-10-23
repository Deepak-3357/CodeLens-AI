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
    assert all(item["status"] == "planned subset" for item in response.json()["languages"])
