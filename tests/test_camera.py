import io
import socket
import struct
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from unittest.mock import Mock

import pytest

from bambu_p1s_mcp import camera
from bambu_p1s_mcp.camera import CameraError, CameraSession, auth_packet, read_frame
from bambu_p1s_mcp.config import Settings

JPEG = b"\xff\xd8\xff\xe0sample image\xff\xd9"


class FragmentedSocket:
    def __init__(self, data, chunk_size=1):
        self.data = io.BytesIO(data)
        self.chunk_size = chunk_size
        self.timeouts = []

    def settimeout(self, timeout):
        self.timeouts.append(timeout)

    def recv(self, size):
        return self.data.read(min(size, self.chunk_size))


def wire_frame(jpeg=JPEG):
    return struct.pack("<IIII", len(jpeg), 0, 1, 0) + jpeg


def test_camera_auth_packet():
    packet = auth_packet("12345678")
    assert len(packet) == 80
    assert packet[:16] == b"\x40\x00\x00\x00\x00\x30\x00\x00" + b"\x00" * 8
    assert packet[16:48] == b"bblp" + b"\x00" * 28
    assert packet[48:] == b"12345678" + b"\x00" * 24


@pytest.mark.parametrize("code", ["", "x" * 33, "not-ascii-\N{SNOWMAN}"])
def test_invalid_access_code_is_not_echoed(code):
    with pytest.raises(CameraError) as error:
        auth_packet(code)
    if code:
        assert code not in str(error.value)


@pytest.mark.parametrize("chunk_size", [1, 7, 16, 4096])
def test_fragmented_and_consecutive_frames(chunk_size):
    connection = FragmentedSocket(wire_frame() * 2, chunk_size)
    assert read_frame(connection) == JPEG
    assert read_frame(connection) == JPEG
    assert all(0 < timeout <= 15 for timeout in connection.timeouts)


@pytest.mark.parametrize("size", [0, 3, camera.MAX_FRAME_BYTES + 1, 0xFFFFFFFF])
def test_invalid_length_rejected_before_reading_body(size):
    connection = FragmentedSocket(struct.pack("<IIII", size, 0, 1, 0), 16)
    with pytest.raises(CameraError, match="length"):
        read_frame(connection)


@pytest.mark.parametrize("data", [b"", wire_frame()[:9], wire_frame()[:-1]])
def test_truncated_stream(data):
    with pytest.raises(CameraError, match="closed the connection"):
        read_frame(FragmentedSocket(data))


def test_non_jpeg_payload():
    with pytest.raises(CameraError, match="JPEG"):
        read_frame(FragmentedSocket(wire_frame(b"not a jpeg")))


def test_frame_has_one_deadline_even_when_bytes_keep_arriving(monkeypatch):
    now = iter([0, 0.1, 0.5, 1.1])
    monkeypatch.setattr(camera.time, "monotonic", lambda: next(now))
    with pytest.raises(TimeoutError):
        read_frame(FragmentedSocket(wire_frame()), timeout=1)


def test_tls_connection_sends_auth_and_closes(monkeypatch):
    calls = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            calls.append("closed")

        def sendall(self, data):
            calls.append(data)

    class Context:
        def wrap_socket(self, raw, server_hostname):
            assert server_hostname == "printer.test"
            return Connection()

    def connect(address, timeout):
        assert address == ("printer.test", 16000)
        assert timeout > 0
        return Connection()

    monkeypatch.setattr(camera.socket, "create_connection", connect)
    monkeypatch.setattr(camera.ssl, "SSLContext", lambda protocol: Context())
    with camera.connect_camera(Settings("printer.test", "testcode", "", camera_port=16000)):
        pass
    assert calls == [auth_packet("testcode"), "closed", "closed"]


def test_viewers_share_connection_and_idle_reader_stops(monkeypatch):
    connections = []
    closed = threading.Event()

    @contextmanager
    def connect(settings):
        connections.append(settings)
        try:
            yield Mock()
        finally:
            closed.set()

    def read(connection):
        time.sleep(0.01)
        return JPEG

    monkeypatch.setattr(camera, "connect_camera", connect)
    monkeypatch.setattr(camera, "read_frame", read)
    session = CameraSession(Settings("printer", "testcode", ""), idle_timeout=0.03)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(session.snapshot)
            second = pool.submit(session.snapshot)
            frame1, frame2 = first.result(timeout=2), second.result(timeout=2)
        assert frame1.jpeg == frame2.jpeg == JPEG
        assert len(connections) == 1
        # snapshot waits for a *new* frame even with one already cached.
        assert session.snapshot().sequence > max(frame1.sequence, frame2.sequence)
        assert closed.wait(timeout=2)
        assert session.snapshot().jpeg == JPEG
        assert len(connections) == 2
    finally:
        session.close()


def test_reader_recovers_after_disconnect_and_redacts_error(monkeypatch):
    attempts = []

    @contextmanager
    def connect(settings):
        attempts.append(1)
        if len(attempts) == 1:
            raise OSError("rejected testcode")
        yield Mock()

    def read(connection):
        time.sleep(0.01)
        return JPEG

    monkeypatch.setattr(camera, "connect_camera", connect)
    monkeypatch.setattr(camera, "read_frame", read)
    session = CameraSession(Settings("printer", "testcode", ""))
    try:
        with pytest.raises(CameraError) as error:
            session.snapshot()
        assert "testcode" not in str(error.value)
        with session._condition:
            assert session._condition.wait_for(lambda: session._frame is not None, timeout=3)
        assert session.snapshot().jpeg == JPEG
        assert len(attempts) == 2
    finally:
        session.close()


def test_close_interrupts_reader_and_releases_waiters(monkeypatch):
    reading = threading.Event()
    disconnected = threading.Event()

    class Connection:
        def shutdown(self, how):
            assert how == socket.SHUT_RDWR
            disconnected.set()

    @contextmanager
    def connect(settings):
        yield Connection()

    def read(connection):
        reading.set()
        assert disconnected.wait(timeout=2)
        raise OSError("closed")

    monkeypatch.setattr(camera, "connect_camera", connect)
    monkeypatch.setattr(camera, "read_frame", read)
    session = CameraSession(Settings("printer", "testcode", ""))
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(session.snapshot)
        assert reading.wait(timeout=2)
        session.close()
        with pytest.raises(CameraError, match="closed"):
            pending.result(timeout=2)
    assert session._thread is None
