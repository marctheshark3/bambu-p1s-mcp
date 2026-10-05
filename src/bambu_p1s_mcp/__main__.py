from __future__ import annotations

import argparse
import json
import sys

from bambu_p1s_mcp.config import load_settings
from bambu_p1s_mcp.ftp import list_files, tcp_probe
from bambu_p1s_mcp.printer import get_session
from bambu_p1s_mcp.redact import public_error
from bambu_p1s_mcp.server import mcp
from bambu_p1s_mcp.slice import which_slicer


def _doctor() -> int:
    settings = load_settings()
    missing = settings.missing()
    result = {
        "missing_env": missing,
        "settings": settings.public_dict(),
        "ports": {
            "mqtt": bool(settings.ip) and tcp_probe(settings.ip, settings.mqtt_port),
            "ftps": bool(settings.ip) and tcp_probe(settings.ip, settings.ftp_port),
            "camera": bool(settings.ip) and tcp_probe(settings.ip, settings.camera_port),
        },
        "slicer": which_slicer(settings),
    }
    if not missing and result["ports"]["mqtt"]:
        try:
            session = get_session(settings)
            session.ensure()
            result["mqtt"] = {"connected": session.connected(), "status": session.snapshot(fresh=True)}
        except Exception as exc:
            result["mqtt"] = {"connected": False, "error": public_error(exc, settings.access_code)}
    if not missing and result["ports"]["ftps"]:
        try:
            names = list_files(settings)
            result["ftp"] = {"connected": True, "files": names[:50], "file_count": len(names)}
        except Exception as exc:
            result["ftp"] = {"connected": False, "error": public_error(exc, settings.access_code)}
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0 if not missing and result.get("mqtt", {}).get("connected") else 1


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="bambu-p1s-mcp")
    parser.add_argument("--http", action="store_true", help="Serve Streamable HTTP instead of stdio")
    parser.add_argument("--host", default=None, help="HTTP bind host (default BAMBU_MCP_HOST)")
    parser.add_argument("--port", type=int, default=None, help="HTTP bind port (default BAMBU_MCP_PORT)")
    parser.add_argument("command", nargs="?", choices=["doctor"])
    args = parser.parse_args(argv)

    if args.command == "doctor":
        raise SystemExit(_doctor())

    if args.http:
        from dataclasses import replace

        from bambu_p1s_mcp.http import run_http

        settings = load_settings()
        if args.host:
            settings = replace(settings, mcp_host=args.host)
        if args.port:
            settings = replace(settings, mcp_port=args.port)
        run_http(settings)
        return

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
