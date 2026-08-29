from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from bambu_p1s_mcp.config import Settings

P1S_MACHINE = "Bambu Lab P1S 0.4 nozzle.json"
P1S_PROCESS = "0.20mm Standard @BBL X1C.json"
P1S_FILAMENT = "Bambu PLA Basic @BBL P1S 0.4 nozzle.json"


def which_slicer(settings: Settings) -> str | None:
    if settings.slicer:
        path = Path(settings.slicer).expanduser()
        if path.is_file():
            return str(path)
    found = shutil.which("bambu-studio") or shutil.which("BambuStudio") or shutil.which("orca-slicer")
    return found


def _under(root: Path, *parts: str) -> Path | None:
    path = root.joinpath(*parts)
    return path if path.is_file() else None


def default_settings_files(settings: Settings) -> dict[str, Path | None]:
    if settings.machine_json and settings.process_json and settings.filament_json:
        return {
            "machine": settings.machine_json,
            "process": settings.process_json,
            "filament": settings.filament_json,
        }
    studio = settings.studio_config
    machine = settings.machine_json
    process = settings.process_json
    filament = settings.filament_json
    if studio:
        bbl = studio / "system" / "BBL"
        machine = machine or _under(bbl, "machine", P1S_MACHINE)
        process = process or _under(bbl, "process", P1S_PROCESS)
        filament = filament or _under(bbl, "filament", P1S_FILAMENT)
    return {"machine": machine, "process": process, "filament": filament}


def build_slice_argv(
    slicer: str,
    source: Path,
    output: Path,
    *,
    plate: int = 1,
    machine: Path | None = None,
    process: Path | None = None,
    filament: Path | None = None,
    orient: bool = False,
    arrange: bool = False,
) -> list[str]:
    argv = [slicer, "--slice", str(plate), "--debug", "1", "--export-3mf", str(output)]
    if machine and process:
        argv.extend(["--load-settings", f"{machine};{process}"])
    if filament:
        argv.extend(["--load-filaments", str(filament)])
    if orient:
        argv.extend(["--orient", "1"])
    if arrange:
        argv.extend(["--arrange", "1"])
    argv.append(str(source))
    return argv


def slice_model(
    settings: Settings,
    source: str,
    *,
    plate: int = 1,
    output: str | None = None,
    orient: bool = False,
    arrange: bool = False,
    timeout_s: int = 600,
) -> dict:
    slicer = which_slicer(settings)
    if not slicer:
        raise FileNotFoundError(
            "no slicer CLI found; set BAMBU_SLICER to bambu-studio (or orca-slicer) and retry"
        )
    src = Path(source).expanduser().resolve()
    if not src.is_file():
        raise FileNotFoundError(f"model not found: {src}")
    settings.slice_dir.mkdir(parents=True, exist_ok=True)
    dest = Path(output).expanduser() if output else settings.slice_dir / f"{src.stem}.gcode.3mf"
    dest.parent.mkdir(parents=True, exist_ok=True)
    files = default_settings_files(settings)
    needs_profiles = src.suffix.lower() in {".stl", ".obj", ".step", ".stp"}
    if needs_profiles and not (files["machine"] and files["process"] and files["filament"]):
        raise FileNotFoundError(
            "STL/STEP slice needs BAMBU_MACHINE_JSON, BAMBU_PROCESS_JSON, BAMBU_FILAMENT_JSON "
            "(or a BambuStudio system/BBL tree under BAMBU_STUDIO_CONFIG)"
        )
    argv = build_slice_argv(
        slicer,
        src,
        dest,
        plate=plate,
        machine=files["machine"],
        process=files["process"],
        filament=files["filament"],
        orient=orient,
        arrange=arrange,
    )
    proc = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=timeout_s,
        check=False,
    )
    log_tail = (proc.stdout or "")[-4000:] + "\n" + (proc.stderr or "")[-4000:]
    if proc.returncode != 0 or not dest.is_file():
        raise RuntimeError(
            f"slicer exited {proc.returncode}; output missing={not dest.is_file()}\n{log_tail.strip()}"
        )
    return {
        "ok": True,
        "source": str(src),
        "output": str(dest),
        "plate": plate,
        "slicer": slicer,
        "bytes": dest.stat().st_size,
        "argv": argv,
    }
