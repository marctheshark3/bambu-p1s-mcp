"""Read the P1S LAN camera's length-prefixed JPEG stream over TLS.

Protocol reference (independent implementation):
https://github.com/greghesp/ha-bambulab/blob/main/custom_components/bambu_lab/pybambu/bambu_client.py
"""

from __future__ import annotations

import atexit
import socket
import ssl
import struct
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

from bambu_p1s_mcp.config import Settings, load_settings
from bambu_p1s_mcp.redact import public_error

MAX_FRAME_BYTES = 8 * 1024 * 1024
FRAME_TIMEOUT = 15.0
CAMERA_HINT = "Check LAN/Developer Mode, the access code, and camera port 6000."


class CameraError(RuntimeError):
    pass


def auth_packet(access_code: str) -> bytes:
    try:
        password = access_code.encode("ascii")
    except UnicodeEncodeError:
        raise CameraError("BAMBU_ACCESS_CODE must contain ASCII characters") from None
    if not password or len(password) > 32:
        raise CameraError("BAMBU_ACCESS_CODE must contain 1 to 32 ASCII characters")
    return struct.pack("<IIII32s32s", 0x40, 0x3000, 0, 0, b"bblp", password)


@contextmanager
def connect_camera(settings: Settings) -> Iterator[ssl.SSLSocket]:
    if not settings.ip:
        raise CameraError("missing required env: BAMBU_IP")
    packet = auth_packet(settings.access_code)
    # Like the MQTT/FTPS clients, trust the printer's self-signed LAN certificate.
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    with socket.create_connection((settings.ip, settings.camera_port), timeout=5) as raw:
        with context.wrap_socket(raw, server_hostname=settings.ip) as connection:
            connection.sendall(packet)
            yield connection


def _read_exact(connection: ssl.SSLSocket, size: int, deadline: float) -> bytes:
    data = bytearray()
    while len(data) < size:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("camera frame timed out")
        connection.settimeout(remaining)
        chunk = connection.recv(min(size - len(data), 65536))
        if not chunk:
            raise CameraError("camera closed the connection; " + CAMERA_HINT)
        data.extend(chunk)
    return bytes(data)


def read_frame(connection: ssl.SSLSocket, timeout: float = FRAME_TIMEOUT) -> bytes:
    # TCP/TLS can split or combine packets anywhere, including within the header.
    deadline = time.monotonic() + timeout
    header = _read_exact(connection, 16, deadline)
    size = struct.unpack_from("<I", header)[0]
    if not 4 <= size <= MAX_FRAME_BYTES:
        raise CameraError("invalid camera frame length")
    jpeg = _read_exact(connection, size, deadline)
    if not jpeg.startswith(b"\xff\xd8") or not jpeg.endswith(b"\xff\xd9"):
        raise CameraError("camera returned an invalid JPEG frame")
    return jpeg


@dataclass(frozen=True)
class CameraFrame:
    sequence: int
    jpeg: bytes
    received_at: float


class CameraSession:
    """One on-demand producer shared by MCP snapshots and HTTP viewers.

    Only the latest frame is retained; slow viewers skip frames. Reconnects use
    bounded backoff, and the socket closes when nobody requests frames anymore.
    """

    def __init__(self, settings: Settings, *, idle_timeout: float = 10.0) -> None:
        self.settings = settings
        self.idle_timeout = idle_timeout
        self._condition = threading.Condition()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._connection: ssl.SSLSocket | None = None
        self._frame: CameraFrame | None = None
        self._sequence = 0
        self._error: str | None = None
        self._waiters = 0
        self._idle_deadline = 0.0

    def snapshot(self, timeout: float = FRAME_TIMEOUT) -> CameraFrame:
        """Wait for a frame received after this call; never return a stale still."""
        with self._condition:
            after = self._sequence
        return self.next_frame(after, timeout)

    def next_frame(self, after: int, timeout: float = FRAME_TIMEOUT) -> CameraFrame:
        deadline = time.monotonic() + timeout
        with self._condition:
            self._waiters += 1
            try:
                while True:
                    if self._stop.is_set():
                        raise CameraError("camera session is closed")
                    if self._thread is None:
                        self._error = None
                        self._thread = threading.Thread(target=self._run, name="p1s-camera", daemon=True)
                        self._thread.start()
                    if self._error:
                        raise CameraError(self._error)
                    if (self._frame and self._frame.sequence > after
                            and time.monotonic() - self._frame.received_at < 5):
                        return self._frame
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise CameraError("timed out waiting for a camera frame; " + CAMERA_HINT)
                    self._condition.wait(remaining)
            finally:
                self._waiters -= 1
                self._idle_deadline = time.monotonic() + self.idle_timeout

    def _wanted(self) -> bool:
        with self._condition:
            return not self._stop.is_set() and (
                self._waiters > 0 or time.monotonic() < self._idle_deadline
            )

    def _run(self) -> None:
        backoff = 1.0
        try:
            while self._wanted():
                try:
                    with connect_camera(self.settings) as connection:
                        with self._condition:
                            self._connection = connection
                        while self._wanted():
                            jpeg = read_frame(connection)
                            with self._condition:
                                self._sequence += 1
                                self._frame = CameraFrame(self._sequence, jpeg, time.monotonic())
                                self._error = None
                                self._condition.notify_all()
                            backoff = 1.0
                except Exception as exc:
                    with self._condition:
                        self._frame = None
                        self._error = public_error(exc, self.settings.access_code)
                        self._condition.notify_all()
                    self._stop.wait(backoff)
                    backoff = min(backoff * 2, 10.0)
                finally:
                    with self._condition:
                        self._connection = None
        finally:
            with self._condition:
                self._thread = None
                self._condition.notify_all()

    def close(self) -> None:
        self._stop.set()
        with self._condition:
            connection = self._connection
            thread = self._thread
            self._condition.notify_all()
        if connection:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        if thread:
            thread.join(timeout=1)


_SESSION: CameraSession | None = None
_SESSION_LOCK = threading.Lock()


def get_camera(settings: Settings | None = None) -> CameraSession:
    global _SESSION
    settings = settings or load_settings()
    with _SESSION_LOCK:
        if _SESSION is not None:
            old = _SESSION.settings
            if (old.ip, old.camera_port, old.access_code) != (
                settings.ip, settings.camera_port, settings.access_code
            ):
                _SESSION.close()
                _SESSION = None
        if _SESSION is None:
            _SESSION = CameraSession(settings)
        return _SESSION


def close_camera() -> None:
    global _SESSION
    with _SESSION_LOCK:
        if _SESSION is not None:
            _SESSION.close()
            _SESSION = None


atexit.register(close_camera)
