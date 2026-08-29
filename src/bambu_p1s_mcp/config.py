from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_ENV_FILES = (
    Path.cwd() / ".env",
    Path(__file__).resolve().parents[2] / ".env",
    Path.home() / ".config" / "bambu-p1s-mcp" / ".env",
)


def _first(*names: str, default: str | None = None) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value is not None and value.strip() != "":
            return value.strip()
    return default


def _load_env() -> None:
    if os.environ.get("BAMBU_MCP_SKIP_DOTENV") == "1":
        return
    for path in _ENV_FILES:
        if path.is_file():
            load_dotenv(path, override=False)


@dataclass(frozen=True)
class Settings:
    ip: str
    access_code: str
    serial: str
    model: str = "P1S"
    mqtt_port: int = 8883
    ftp_port: int = 990
    mqtt_username: str = "bblp"
    slicer: str | None = None
    studio_config: Path | None = None
    machine_json: Path | None = None
    process_json: Path | None = None
    filament_json: Path | None = None
    slice_dir: Path = Path("/tmp/bambu-p1s-mcp-slice")
    mcp_host: str = "127.0.0.1"
    mcp_port: int = 8765
    mcp_token: str | None = None
    mcp_path: str = "/mcp"

    @property
    def report_topic(self) -> str:
        return f"device/{self.serial}/report"

    @property
    def request_topic(self) -> str:
        return f"device/{self.serial}/request"

    def missing(self) -> list[str]:
        missing: list[str] = []
        if not self.ip:
            missing.append("BAMBU_IP")
        if not self.access_code:
            missing.append("BAMBU_ACCESS_CODE")
        if not self.serial:
            missing.append("BAMBU_SERIAL")
        return missing

    def public_dict(self) -> dict:
        return {
            "ip": self.ip,
            "serial": self.serial,
            "model": self.model,
            "mqtt_port": self.mqtt_port,
            "ftp_port": self.ftp_port,
            "slicer": self.slicer,
            "studio_config": str(self.studio_config) if self.studio_config else None,
            "machine_json": str(self.machine_json) if self.machine_json else None,
            "process_json": str(self.process_json) if self.process_json else None,
            "filament_json": str(self.filament_json) if self.filament_json else None,
            "slice_dir": str(self.slice_dir),
            "mcp_host": self.mcp_host,
            "mcp_port": self.mcp_port,
            "mcp_path": self.mcp_path,
            "mcp_token_set": bool(self.mcp_token),
            "access_code": "***",
        }


def _optional_path(value: str | None) -> Path | None:
    if not value:
        return None
    return Path(value).expanduser()


def load_settings() -> Settings:
    _load_env()
    studio = _optional_path(_first("BAMBU_STUDIO_CONFIG"))
    if studio is None:
        guessed = Path.home() / ".config" / "BambuStudio"
        if guessed.is_dir():
            studio = guessed
    return Settings(
        ip=_first("BAMBU_IP", "BAMBU_PRINTER_IP", "BAMBU_HOST", "BAMBU_LAB_MQTT_HOST") or "",
        access_code=_first(
            "BAMBU_ACCESS_CODE",
            "BAMBU_TOKEN",
            "BAMBU_MQTT_PASSWORD",
            "BAMBU_LAB_MQTT_PASSWORD",
        )
        or "",
        serial=_first("BAMBU_SERIAL", "BAMBU_DEVICE_ID", "BAMBU_SERIAL_NUMBER", "BAMBU_LAB_DEVICE_ID")
        or "",
        model=_first("BAMBU_MODEL", default="P1S") or "P1S",
        mqtt_port=int(_first("BAMBU_MQTT_PORT", default="8883") or "8883"),
        ftp_port=int(_first("BAMBU_FTP_PORT", default="990") or "990"),
        mqtt_username=_first("BAMBU_MQTT_USERNAME", default="bblp") or "bblp",
        slicer=_first("BAMBU_SLICER"),
        studio_config=studio,
        machine_json=_optional_path(_first("BAMBU_MACHINE_JSON")),
        process_json=_optional_path(_first("BAMBU_PROCESS_JSON")),
        filament_json=_optional_path(_first("BAMBU_FILAMENT_JSON")),
        slice_dir=Path(_first("BAMBU_SLICE_DIR", default="/tmp/bambu-p1s-mcp-slice") or "/tmp/bambu-p1s-mcp-slice"),
        mcp_host=_first("BAMBU_MCP_HOST", default="127.0.0.1") or "127.0.0.1",
        mcp_port=int(_first("BAMBU_MCP_PORT", default="8765") or "8765"),
        mcp_token=_first("BAMBU_MCP_TOKEN"),
        mcp_path=_first("BAMBU_MCP_PATH", default="/mcp") or "/mcp",
    )
