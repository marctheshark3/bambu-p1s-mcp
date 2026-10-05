import pytest
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


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.50", "100.64.0.10", "printer-host", "127.0.0.1.example.com"])
@pytest.mark.parametrize("token", [None, "", "   "])
def test_network_listener_requires_token(host, token):
    with pytest.raises(ValueError, match="BAMBU_MCP_TOKEN is required"):
        build_http_app(_settings(mcp_host=host, mcp_token=token))


@pytest.mark.parametrize("host", ["127.0.0.1", "127.0.0.2", "::1", "localhost"])
def test_loopback_can_run_without_token(host):
    authority = f"[{host}]" if ":" in host else host
    client = TestClient(
        build_http_app(_settings(mcp_host=host, mcp_token=None)),
        # TestClient's httpx transport cannot parse IPv6 base URLs. The Host
        # header still exercises the application's real IPv6 validation.
        base_url="http://127.0.0.1:8765", headers={"Host": f"{authority}:8765"},
    )
    assert client.get("/health").status_code == 200
    assert client.get("/health", headers={"Origin": f"http://{authority}:8765"}).status_code == 200


def test_network_listener_with_token_keeps_data_private():
    client = TestClient(build_http_app(_settings(mcp_host="0.0.0.0")))
    assert client.get("/health").status_code == 200
    for path in ["/mcp", "/camera/snapshot.jpg", "/camera/stream.mjpg"]:
        assert client.get(path).status_code == 401
