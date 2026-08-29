from __future__ import annotations

import ftplib
import os
import socket
import ssl
from pathlib import Path

from bambu_p1s_mcp.config import Settings


class ImplicitFTP_TLS(ftplib.FTP_TLS):
    """Bambu printers speak implicit FTPS on port 990."""

    def __init__(self) -> None:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        super().__init__(context=context)

    def connect(self, host="", port=0, timeout=-999, source_address=None):  # noqa: ANN001
        if host:
            self.host = host
        if port > 0:
            self.port = port
        if timeout != -999:
            self.timeout = timeout
        self.sock = socket.create_connection((self.host, self.port), self.timeout, source_address)
        self.af = self.sock.family
        self.sock = self.context.wrap_socket(self.sock, server_hostname=self.host)
        self.file = self.sock.makefile("r", encoding=self.encoding)
        self.welcome = self.getresp()
        return self.welcome


def _connect(settings: Settings) -> ImplicitFTP_TLS:
    ftp = ImplicitFTP_TLS()
    ftp.connect(settings.ip, settings.ftp_port, timeout=15)
    ftp.login(settings.mqtt_username, settings.access_code)
    try:
        ftp.prot_p()
    except ftplib.error_perm:
        pass
    ftp.set_pasv(True)
    return ftp


def list_files(settings: Settings, path: str = "/") -> list[str]:
    ftp = _connect(settings)
    try:
        try:
            names = ftp.nlst(path)
        except ftplib.error_perm:
            names = ftp.nlst()
        return sorted(n for n in names if n not in (".", ".."))
    finally:
        try:
            ftp.quit()
        except Exception:
            ftp.close()


def upload_file(settings: Settings, local_path: str, remote_name: str | None = None) -> str:
    src = Path(local_path).expanduser().resolve()
    if not src.is_file():
        raise FileNotFoundError(f"local file not found: {src}")
    suffix = src.name.lower()
    if not suffix.endswith((".gcode.3mf", ".3mf", ".gcode")):
        raise ValueError("only .gcode.3mf, .3mf, or .gcode can be uploaded")
    dest = remote_name or src.name
    dest = dest.lstrip("/")
    ftp = _connect(settings)
    try:
        with src.open("rb") as handle:
            ftp.storbinary(f"STOR {dest}", handle)
        return dest
    finally:
        try:
            ftp.quit()
        except Exception:
            ftp.close()


def tcp_probe(host: str, port: int, timeout: float = 3.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def file_size(path: str) -> int:
    return os.path.getsize(path)
