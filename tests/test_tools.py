from bambu_p1s_mcp.server import mcp


def test_tool_catalog():
    names = {t.name for t in mcp._tool_manager.list_tools()}
    assert names == {
        "printer_doctor",
        "printer_status",
        "printer_ams",
        "printer_files",
        "printer_camera_snapshot",
        "printer_camera_stream",
        "printer_pause",
        "printer_resume",
        "printer_stop",
        "printer_speed",
        "printer_upload",
        "printer_print",
        "slice_model_file",
    }
