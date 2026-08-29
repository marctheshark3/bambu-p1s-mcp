from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from bambu_p1s_mcp.config import load_settings
from bambu_p1s_mcp.ftp import list_files, tcp_probe, upload_file
from bambu_p1s_mcp.guard import require_confirm
from bambu_p1s_mcp.printer import get_session
from bambu_p1s_mcp.redact import public_error
from bambu_p1s_mcp.slice import slice_model, which_slicer

mcp = FastMCP(
    "bambu-p1s",
    instructions=(
        "Bambu Lab P1S on the local network. Read tools are safe. "
        "Write tools (pause/resume/stop/upload/print/speed/slice) require confirm=true. "
        "Always printer_status before starting or stopping a job."
    ),
    # Avoid FastMCP's localhost-only DNS-rebinding list so Hermes on Spark can
    # hit this host by LAN or Tailscale IP. Auth is BAMBU_MCP_TOKEN on HTTP.
    host="0.0.0.0",
)


def _settings():
    return load_settings()


def _err(exc: BaseException) -> dict:
    return {"ok": False, "error": public_error(exc, _settings().access_code)}


@mcp.tool()
def printer_doctor() -> dict:
    """Check env, LAN ports, MQTT, FTPS, and slicer CLI. Does not print or change printer state."""
    settings = _settings()
    missing = settings.missing()
    mqtt_open = bool(settings.ip) and tcp_probe(settings.ip, settings.mqtt_port)
    ftp_open = bool(settings.ip) and tcp_probe(settings.ip, settings.ftp_port)
    mqtt_ok = False
    mqtt_error = None
    ftp_ok = False
    ftp_error = None
    files: list[str] | None = None
    status = None
    if not missing and mqtt_open:
        try:
            session = get_session(settings)
            session.ensure()
            status = session.snapshot(fresh=True)
            mqtt_ok = session.connected()
        except Exception as exc:
            mqtt_error = public_error(exc, settings.access_code)
    if not missing and ftp_open:
        try:
            files = list_files(settings)
            ftp_ok = True
        except Exception as exc:
            ftp_error = public_error(exc, settings.access_code)
    slicer = which_slicer(settings)
    return {
        "ok": not missing and mqtt_ok,
        "missing_env": missing,
        "settings": settings.public_dict(),
        "ports": {
            "mqtt_8883": mqtt_open,
            "ftps_990": ftp_open,
        },
        "mqtt": {"connected": mqtt_ok, "error": mqtt_error, "status": status},
        "ftp": {"connected": ftp_ok, "error": ftp_error, "file_count": None if files is None else len(files)},
        "slicer": slicer,
        "hint": (
            "MCP must run on a host that can reach the printer LAN ports. "
            "Hermes on another machine should use Streamable HTTP against this host, not stdio on Spark."
            if not mqtt_open
            else None
        ),
    }


@mcp.tool()
def printer_status(fresh: bool = False) -> dict:
    """Current P1S state: idle/printing, job name, progress, temps, remaining time.

    Set fresh=true to request a full P1S pushall (avoid calling that in a tight loop).
    """
    try:
        return {"ok": True, **get_session().snapshot(fresh=fresh)}
    except Exception as exc:
        return _err(exc)


@mcp.tool()
def printer_ams() -> dict:
    """AMS / external spool trays: type, color, empty, active tray."""
    try:
        return {"ok": True, **get_session().ams()}
    except Exception as exc:
        return _err(exc)


@mcp.tool()
def printer_files(path: str = "/") -> dict:
    """List files on the printer SD card via FTPS."""
    try:
        names = list_files(_settings(), path)
        return {"ok": True, "path": path, "files": names}
    except Exception as exc:
        return _err(exc)


@mcp.tool()
def printer_pause(confirm: bool = False) -> dict:
    """Pause the current print. Requires confirm=true."""
    refused = require_confirm(confirm, "pause")
    if refused:
        return {"ok": False, "error": refused}
    try:
        payload = get_session().pause_print()
        return {"ok": True, "sent": payload}
    except Exception as exc:
        return _err(exc)


@mcp.tool()
def printer_resume(confirm: bool = False) -> dict:
    """Resume a paused print. Requires confirm=true."""
    refused = require_confirm(confirm, "resume")
    if refused:
        return {"ok": False, "error": refused}
    try:
        payload = get_session().resume_print()
        return {"ok": True, "sent": payload}
    except Exception as exc:
        return _err(exc)


@mcp.tool()
def printer_stop(confirm: bool = False) -> dict:
    """Stop the current print. Requires confirm=true."""
    refused = require_confirm(confirm, "stop")
    if refused:
        return {"ok": False, "error": refused}
    try:
        payload = get_session().stop_print()
        return {"ok": True, "sent": payload}
    except Exception as exc:
        return _err(exc)


@mcp.tool()
def printer_speed(profile: str, confirm: bool = False) -> dict:
    """Set speed profile: silent, standard, sport, ludicrous. Requires confirm=true."""
    refused = require_confirm(confirm, "speed")
    if refused:
        return {"ok": False, "error": refused}
    try:
        payload = get_session().set_speed(profile)
        return {"ok": True, "sent": payload}
    except Exception as exc:
        return _err(exc)


@mcp.tool()
def printer_upload(local_path: str, remote_name: str | None = None, confirm: bool = False) -> dict:
    """Upload a sliced .gcode.3mf / .3mf / .gcode to the printer over FTPS. Requires confirm=true."""
    refused = require_confirm(confirm, "upload")
    if refused:
        return {"ok": False, "error": refused}
    try:
        dest = upload_file(_settings(), local_path, remote_name)
        return {"ok": True, "remote_name": dest, "local_path": str(Path(local_path).expanduser().resolve())}
    except Exception as exc:
        return _err(exc)


@mcp.tool()
def printer_print(
    path: str,
    plate: int = 1,
    use_ams: bool = True,
    bed_levelling: bool = True,
    flow_cali: bool = False,
    vibration_cali: bool = True,
    layer_inspect: bool = True,
    timelapse: bool = False,
    confirm: bool = False,
) -> dict:
    """Start a print from a local sliced file (upload first) or a filename already on the printer.

    Requires confirm=true. Check printer_status first — do not start if a job is RUNNING.
    """
    refused = require_confirm(confirm, "print")
    if refused:
        return {"ok": False, "error": refused}
    try:
        session = get_session()
        current = session.snapshot()
        if current.get("gcode_state") in {"RUNNING", "PREPARE"}:
            return {
                "ok": False,
                "error": f"printer is {current.get('gcode_state')} job={current.get('job_name')}; stop or wait first",
            }
        local = Path(path).expanduser()
        remote = path
        uploaded = None
        if local.is_file():
            uploaded = upload_file(_settings(), str(local))
            remote = uploaded
        if remote.lower().endswith(".gcode") and not remote.lower().endswith(".gcode.3mf"):
            sent = session.start_gcode(remote)
        else:
            sent = session.start_project(
                remote,
                plate=plate,
                use_ams=use_ams,
                bed_levelling=bed_levelling,
                flow_cali=flow_cali,
                vibration_cali=vibration_cali,
                layer_inspect=layer_inspect,
                timelapse=timelapse,
            )
        return {"ok": True, "uploaded": uploaded, "remote": remote, "sent": sent}
    except Exception as exc:
        return _err(exc)


@mcp.tool()
def slice_model_file(
    source: str,
    plate: int = 1,
    output: str | None = None,
    orient: bool = False,
    arrange: bool = False,
    confirm: bool = False,
) -> dict:
    """Slice an STL/3MF with the Bambu Studio CLI into a printable .gcode.3mf. Requires confirm=true.

    STL/STEP needs machine/process/filament JSON (auto-discovered from BambuStudio config when present).
    A project .3mf that already contains settings can be sliced without extra profiles.
    """
    refused = require_confirm(confirm, "slice")
    if refused:
        return {"ok": False, "error": refused}
    try:
        result = slice_model(
            _settings(),
            source,
            plate=plate,
            output=output,
            orient=orient,
            arrange=arrange,
        )
        return result
    except Exception as exc:
        return _err(exc)
