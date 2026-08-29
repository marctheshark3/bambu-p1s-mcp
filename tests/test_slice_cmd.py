from pathlib import Path

from bambu_p1s_mcp.guard import require_confirm
from bambu_p1s_mcp.slice import build_slice_argv


def test_slice_argv():
    argv = build_slice_argv(
        "/usr/bin/bambu-studio",
        Path("/tmp/part.stl"),
        Path("/tmp/part.gcode.3mf"),
        plate=1,
        machine=Path("/tmp/machine.json"),
        process=Path("/tmp/process.json"),
        filament=Path("/tmp/filament.json"),
        orient=True,
        arrange=True,
    )
    assert argv[0] == "/usr/bin/bambu-studio"
    assert "--slice" in argv
    assert argv[argv.index("--export-3mf") + 1] == "/tmp/part.gcode.3mf"
    assert argv[-1] == "/tmp/part.stl"
    assert "--orient" in argv
    assert "--arrange" in argv


def test_confirm_guard():
    assert require_confirm(False, "print") is not None
    assert require_confirm(True, "print") is None
