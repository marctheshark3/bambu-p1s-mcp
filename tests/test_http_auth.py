from starlette.testclient import TestClient

from bambu_p1s_mcp.config import Settings
from bambu_p1s_mcp.http import build_http_app


def _settings(**kwargs) -> Settings:
    base = dict(
        ip="192.168.1.50",
        access_code="secret",
        serial="01P00A",
        mcp_token="tok",
        mcp_path="/mcp",
        mcp_host="127.0.0.1",
        mcp_port=8765,
    )
    base.update(kwargs)
    return Settings(**base)


def test_health_open():
    client = TestClient(build_http_app(_settings()))
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_mcp_requires_bearer():
    # Middleware only — do not enter FastMCP lifespan (session manager is a singleton).
    client = TestClient(build_http_app(_settings()))
    denied = client.get("/mcp")
    assert denied.status_code == 401
    denied_health_ok = client.get("/health")
    assert denied_health_ok.status_code == 200
