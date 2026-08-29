from __future__ import annotations

from pathlib import Path


def print_command(seq: int, command: str, **extra) -> dict:
    body = {"sequence_id": str(seq), "command": command}
    body.update(extra)
    return {"print": body}


def pause(seq: int) -> dict:
    return print_command(seq, "pause", param="")


def resume(seq: int) -> dict:
    return print_command(seq, "resume", param="")


def stop(seq: int) -> dict:
    return print_command(seq, "stop", param="")


def pushall(seq: int) -> dict:
    return {
        "pushing": {
            "sequence_id": str(seq),
            "command": "pushall",
            "version": 1,
            "push_target": 1,
        }
    }


def get_version(seq: int) -> dict:
    return {"info": {"sequence_id": str(seq), "command": "get_version"}}


def print_speed(seq: int, level: int) -> dict:
    if level not in (1, 2, 3, 4):
        raise ValueError("speed level must be 1 silent, 2 standard, 3 sport, 4 ludicrous")
    return print_command(seq, "print_speed", param=str(level))


def gcode_file(seq: int, filename: str) -> dict:
    return print_command(seq, "gcode_file", param=filename)


def project_file(
    seq: int,
    filename: str,
    *,
    plate: int = 1,
    use_ams: bool = True,
    bed_levelling: bool = True,
    flow_cali: bool = True,
    vibration_cali: bool = True,
    layer_inspect: bool = True,
    timelapse: bool = False,
    subtask_name: str | None = None,
) -> dict:
    name = subtask_name or Path(filename).name
    url = filename if filename.startswith(("ftp://", "file://")) else f"ftp:///{Path(filename).name.lstrip('/')}"
    return print_command(
        seq,
        "project_file",
        param=f"Metadata/plate_{plate}.gcode",
        project_id="0",
        profile_id="0",
        task_id="0",
        subtask_id="0",
        subtask_name=name,
        file="",
        url=url,
        md5="",
        timelapse=timelapse,
        bed_type="auto",
        bed_levelling=bed_levelling,
        flow_cali=flow_cali,
        vibration_cali=vibration_cali,
        layer_inspect=layer_inspect,
        use_ams=use_ams,
    )


SPEED_NAMES = {
    "silent": 1,
    "standard": 2,
    "sport": 3,
    "ludicrous": 4,
}


def speed_level(value: str | int) -> int:
    if isinstance(value, int):
        return value
    key = str(value).strip().lower()
    if key.isdigit():
        return int(key)
    if key in SPEED_NAMES:
        return SPEED_NAMES[key]
    raise ValueError(f"unknown speed {value!r}; use silent|standard|sport|ludicrous")
