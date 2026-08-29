from bambu_p1s_mcp.status import ams_view, deep_merge, summarize


def test_deep_merge_p1s_partial():
    state = {"print": {"gcode_state": "IDLE", "mc_percent": 0, "nozzle_temper": 25.0}}
    deep_merge(state, {"print": {"gcode_state": "RUNNING", "mc_percent": 12}})
    assert state["print"]["gcode_state"] == "RUNNING"
    assert state["print"]["mc_percent"] == 12
    assert state["print"]["nozzle_temper"] == 25.0


def test_summarize_running_job():
    snap = summarize(
        {
            "print": {
                "gcode_state": "RUNNING",
                "subtask_name": "lamp",
                "gcode_file": "lamp.gcode",
                "mc_percent": 42,
                "layer_num": 12,
                "total_layer_num": 40,
                "mc_remaining_time": 23,
                "nozzle_temper": "220.5",
                "bed_temper": 65,
                "hms": [],
                "print_error": 0,
            }
        },
        connected=True,
    )
    assert snap["has_job"] is True
    assert snap["job_name"] == "lamp"
    assert snap["progress_percent"] == 42
    assert "layer 12/40" in snap["summary"]
    assert "~23 min left" in snap["summary"]


def test_summarize_idle():
    snap = summarize({"print": {"gcode_state": "IDLE"}}, connected=True)
    assert snap["has_job"] is False
    assert snap["summary"].startswith("IDLE")


def test_ams_trays():
    view = ams_view(
        {
            "print": {
                "ams": {
                    "tray_now": "0",
                    "ams": [
                        {
                            "id": "0",
                            "humidity": "4",
                            "temp": "22.7",
                            "tray": [
                                {"id": "0"},
                                {
                                    "id": "1",
                                    "tray_type": "PLA",
                                    "tray_color": "FFFFFFFF",
                                    "nozzle_temp_min": "190",
                                    "nozzle_temp_max": "240",
                                },
                            ],
                        }
                    ],
                }
            }
        }
    )
    assert view["tray_now"] == "0"
    assert view["trays"][0]["empty"] is True
    assert view["trays"][1]["type"] == "PLA"
