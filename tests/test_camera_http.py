import asyncio
import base64
import time
from unittest.mock import Mock

import pytest
from starlette.testclient import TestClient

from bambu_p1s_mcp import http, server
from bambu_p1s_mcp.camera import CameraError, CameraFrame
from bambu_p1s_mcp.config import Settings

JPEG = b"\xff\xd8test\xff\xd9"
SETTINGS = Settings("printer", "secretcode", "serial", mcp_token="servertoken")
AUTH = {"Authorization": "Bearer servertoken"}


@pytest.fixture
def camera_session(monkeypatch):
    session = Mock()
    session.snapshot.return_value = CameraFrame(1, JPEG, time.monotonic())
    monkeypatch.setattr(http, "get_camera", lambda settings: session)
    monkeypatch.setattr(server, "get_camera", lambda: session)
    monkeypatch.setattr(server, "_settings", lambda: SETTINGS)
    return session


@pytest.mark.parametrize("path", ["/camera/snapshot.jpg", "/camera/stream.mjpg"])
def test_camera_data_requires_token_before_connecting(path, camera_session):
    client = TestClient(http.build_http_app(SETTINGS))
    for headers in ({}, {"Authorization": "Bearer wrong"}):
        response = client.get(path, headers=headers)
        assert response.status_code == 401
    assert client.get(path + "?token=servertoken").status_code == 401
    camera_session.snapshot.assert_not_called()


def test_viewer_shell_contains_no_credentials_or_camera_data(camera_session):
    client = TestClient(http.build_http_app(SETTINGS))
    response = client.get("/camera")
    assert response.status_code == 200
    assert "const authRequired = true" in response.text
    assert "secretcode" not in response.text
    assert "servertoken" not in response.text
    assert response.headers["cache-control"] == "no-store"
    camera_session.snapshot.assert_not_called()


def test_authenticated_snapshot(camera_session):
    client = TestClient(http.build_http_app(SETTINGS))
    response = client.get("/camera/snapshot.jpg", headers=AUTH)
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["cache-control"] == "no-store"
    assert response.content == JPEG


def test_local_viewer_without_token(camera_session):
    client = TestClient(
        http.build_http_app(Settings("printer", "code", "serial")), base_url="http://127.0.0.1:8765"
    )
    assert "const authRequired = false" in client.get("/camera").text
    assert client.get("/camera/snapshot.jpg").content == JPEG


@pytest.mark.parametrize("path", ["/mcp", "/camera/snapshot.jpg", "/camera/stream.mjpg"])
@pytest.mark.parametrize("host", [
    "untrusted.example", "127.0.0.1.example.com", "localhost.example.com",
    "localhost@untrusted.example", "untrusted.example@localhost", "[::1", "localhost:invalid",
])
def test_local_listener_rejects_untrusted_hosts_before_connecting(path, host, camera_session):
    client = TestClient(http.build_http_app(Settings("printer", "code", "serial")))
    assert client.get(path, headers={"Host": host}).status_code == 400
    camera_session.snapshot.assert_not_called()


@pytest.mark.parametrize("origin", ["https://untrusted.example", "null", "http://127.0.0.1:9999"])
def test_local_listener_rejects_foreign_origins_before_connecting(origin, camera_session):
    client = TestClient(
        http.build_http_app(Settings("printer", "code", "serial")), base_url="http://127.0.0.1:8765"
    )
    assert client.get("/camera/snapshot.jpg", headers={"Origin": origin}).status_code == 403
    camera_session.snapshot.assert_not_called()


def test_remote_authenticated_camera_allows_lan_hostname(camera_session):
    client = TestClient(
        http.build_http_app(Settings("printer", "code", "serial", mcp_host="0.0.0.0", mcp_token="servertoken")),
        base_url="http://printer-host:8765",
    )
    assert client.get("/camera/snapshot.jpg", headers=AUTH).content == JPEG


def test_mjpeg_stream_and_disconnect(camera_session):
    camera_session.next_frame.side_effect = [
        CameraFrame(2, JPEG, time.monotonic()), CameraError("disconnected")
    ]
    client = TestClient(http.build_http_app(SETTINGS))
    response = client.get("/camera/stream.mjpg", headers=AUTH)
    assert response.status_code == 200
    assert response.headers["content-type"] == "multipart/x-mixed-replace; boundary=frame"
    assert response.headers["x-accel-buffering"] == "no"
    part = b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: 8\r\n\r\n" + JPEG + b"\r\n"
    assert response.content == part * 2 + b"--frame--\r\n"
    assert [call.args for call in camera_session.next_frame.call_args_list] == [(1,), (2,)]


@pytest.mark.parametrize("path", ["/camera/snapshot.jpg", "/camera/stream.mjpg"])
def test_camera_error_is_503_and_redacted(path, camera_session):
    camera_session.snapshot.side_effect = CameraError("failed secretcode servertoken")
    client = TestClient(http.build_http_app(SETTINGS))
    response = client.get(path, headers=AUTH)
    assert response.status_code == 503
    assert response.json()["ok"] is False
    assert "secretcode" not in response.text
    assert "servertoken" not in response.text


def test_mcp_returns_image_content(camera_session):
    # Exercise FastMCP serialization, not just the tool's Python return type.
    result = asyncio.run(server.mcp.call_tool("printer_camera_snapshot", {}))
    assert len(result) == 1
    assert result[0].type == "image"
    assert result[0].mimeType == "image/jpeg"
    assert base64.b64decode(result[0].data) == JPEG


def test_mcp_snapshot_error_is_redacted(camera_session):
    camera_session.snapshot.side_effect = CameraError("failed secretcode")
    result = asyncio.run(server.mcp.call_tool("printer_camera_snapshot", {}))
    assert result[0].type == "text"
    assert "secretcode" not in result[0].text
    assert '"ok": false' in result[0].text


def test_stream_instructions_work_without_camera_or_http_daemon(camera_session):
    result = server.printer_camera_stream()
    assert result["requires_http_daemon"] is True
    assert result["viewer_path"] == "/camera"
    assert "secretcode" not in str(result)
    assert "servertoken" not in str(result)
    camera_session.snapshot.assert_not_called()
