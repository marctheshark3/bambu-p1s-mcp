from __future__ import annotations

from typing import Any


def deep_merge(dst: dict, src: dict) -> dict:
    for key, value in src.items():
        if isinstance(value, dict) and isinstance(dst.get(key), dict):
            deep_merge(dst[key], value)
        else:
            dst[key] = value
    return dst


def _num(value: Any, default: float | int | None = None) -> float | int | None:
    if value is None or value == "":
        return default
    try:
        if isinstance(value, bool):
            return default
        if isinstance(value, (int, float)):
            return value
        text = str(value).strip()
        if "." in text:
            return float(text)
        return int(text)
    except (TypeError, ValueError):
        return default


def _ams_trays(print_state: dict) -> list[dict]:
    ams = print_state.get("ams") or {}
    units = ams.get("ams") or []
    trays: list[dict] = []
    for unit in units:
        unit_id = unit.get("id", "0")
        for tray in unit.get("tray") or []:
            trays.append(
                {
                    "ams_id": unit_id,
                    "slot": tray.get("id"),
                    "type": tray.get("tray_type") or None,
                    "color": tray.get("tray_color") or None,
                    "empty": not bool(tray.get("tray_type")),
                    "nozzle_temp_min": _num(tray.get("nozzle_temp_min")),
                    "nozzle_temp_max": _num(tray.get("nozzle_temp_max")),
                }
            )
    vt = print_state.get("vt_tray")
    if isinstance(vt, dict):
        trays.append(
            {
                "ams_id": "external",
                "slot": vt.get("id", 254),
                "type": vt.get("tray_type") or None,
                "color": vt.get("tray_color") or None,
                "empty": not bool(vt.get("tray_type")),
                "nozzle_temp_min": _num(vt.get("nozzle_temp_min")),
                "nozzle_temp_max": _num(vt.get("nozzle_temp_max")),
            }
        )
    return trays


def summarize(state: dict, *, connected: bool, last_error: str | None = None) -> dict:
    print_state = state.get("print") or {}
    gcode_state = str(print_state.get("gcode_state") or "UNKNOWN")
    job = print_state.get("subtask_name") or print_state.get("gcode_file") or ""
    percent = _num(print_state.get("mc_percent"), 0) or 0
    remaining = _num(print_state.get("mc_remaining_time"), 0) or 0
    layer = _num(print_state.get("layer_num"), 0) or 0
    total = _num(print_state.get("total_layer_num"), 0) or 0
    hms = print_state.get("hms") or []
    print_error = _num(print_state.get("print_error"), 0) or 0
    busy_states = {"RUNNING", "PAUSE", "PREPARE", "SLICING", "FAILED"}
    has_job = bool(job) or gcode_state in busy_states
    bits = [
        gcode_state,
        (job or "no job"),
    ]
    if gcode_state in {"RUNNING", "PAUSE", "PREPARE"}:
        bits.append(f"{percent}%")
        if total:
            bits.append(f"layer {layer}/{total}")
        if remaining:
            bits.append(f"~{remaining} min left")
    if print_error:
        bits.append(f"error={print_error}")
    if hms:
        bits.append(f"hms={len(hms)}")
    return {
        "connected": connected,
        "gcode_state": gcode_state,
        "has_job": has_job,
        "job_name": job or None,
        "gcode_file": print_state.get("gcode_file") or None,
        "progress_percent": percent,
        "layer": layer,
        "total_layers": total,
        "remaining_minutes": remaining,
        "nozzle_c": _num(print_state.get("nozzle_temper")),
        "nozzle_target_c": _num(print_state.get("nozzle_target_temper")),
        "bed_c": _num(print_state.get("bed_temper")),
        "bed_target_c": _num(print_state.get("bed_target_temper")),
        "chamber_c": _num(print_state.get("chamber_temper")),
        "wifi": print_state.get("wifi_signal"),
        "sdcard": print_state.get("sdcard"),
        "print_error": print_error,
        "hms": hms,
        "ams_tray_now": (print_state.get("ams") or {}).get("tray_now"),
        "summary": ", ".join(str(b) for b in bits if b),
        "last_error": last_error,
    }


def ams_view(state: dict) -> dict:
    print_state = state.get("print") or {}
    ams = print_state.get("ams") or {}
    return {
        "tray_now": ams.get("tray_now"),
        "humidity": [(u.get("id"), u.get("humidity"), u.get("temp")) for u in (ams.get("ams") or [])],
        "trays": _ams_trays(print_state),
    }
