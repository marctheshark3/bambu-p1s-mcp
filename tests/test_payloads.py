from bambu_p1s_mcp.payloads import pause, project_file, pushall, speed_level, stop


def test_pause_shape():
    body = pause(3)
    assert body["print"]["command"] == "pause"
    assert body["print"]["sequence_id"] == "3"


def test_stop_qos_payload():
    assert stop(1)["print"]["command"] == "stop"


def test_project_file_url_and_plate():
    body = project_file(9, "lamp.gcode.3mf", plate=2, use_ams=True)
    print_ = body["print"]
    assert print_["command"] == "project_file"
    assert print_["param"] == "Metadata/plate_2.gcode"
    assert print_["url"] == "ftp:///lamp.gcode.3mf"
    assert print_["use_ams"] is True
    assert print_["project_id"] == "0"


def test_pushall():
    body = pushall(1)
    assert body["pushing"]["command"] == "pushall"


def test_speed_names():
    assert speed_level("silent") == 1
    assert speed_level("ludicrous") == 4
    assert speed_level(2) == 2
