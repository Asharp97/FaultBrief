from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app
from demo.app.main import app as demo_app


def api_client() -> TestClient:
    settings = Settings(
        _env_file=None,
        database_url="postgresql://private-user:private-password@example.invalid/db",
        ai_provider_api_key="private-test-key",
        cors_allowed_origins=["http://localhost:3000"],
    )
    return TestClient(create_app(settings))


def test_health_does_not_expose_connection_or_provider_secrets() -> None:
    response = api_client().get("/health")
    assert response.status_code == 200
    assert "private-password" not in response.text
    assert "private-test-key" not in response.text
    assert "database_url" not in response.json()


def test_only_configured_browser_origin_receives_cors_permission() -> None:
    client = api_client()
    allowed = client.get("/health", headers={"Origin": "http://localhost:3000"})
    denied = client.get("/health", headers={"Origin": "https://untrusted.example"})
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "access-control-allow-origin" not in denied.headers


def test_disallowed_preflight_is_rejected() -> None:
    response = api_client().options(
        "/health",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_api_and_demo_have_distinct_service_identities() -> None:
    api_identity = api_client().get("/health").json()["service"]
    demo_identity = TestClient(demo_app).get("/health").json()["service"]
    assert api_identity != demo_identity
