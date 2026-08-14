from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_is_non_sensitive_and_available() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "goreecloud-notes-api",
    }


def test_versioned_api_metadata() -> None:
    response = client.get("/api/v1/meta")

    assert response.status_code == 200
    assert response.json() == {
        "product": "GoreeCloud Notes",
        "api_version": "v1",
        "status": "native-foundation",
    }
