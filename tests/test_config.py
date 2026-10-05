from bambu_p1s_mcp.config import load_settings


def test_aliases(monkeypatch):
    monkeypatch.setenv("BAMBU_PRINTER_IP", "10.0.0.9")
    monkeypatch.setenv("BAMBU_TOKEN", "abc12345")
    monkeypatch.setenv("BAMBU_DEVICE_ID", "01P00A999")
    settings = load_settings()
    assert settings.ip == "10.0.0.9"
    assert settings.access_code == "abc12345"
    assert settings.serial == "01P00A999"
    assert settings.missing() == []
    public = settings.public_dict()
    assert public["access_code"] == "***"
    assert "abc12345" not in str(public)


def test_missing_env(monkeypatch):
    for key in (
        "BAMBU_IP",
        "BAMBU_PRINTER_IP",
        "BAMBU_HOST",
        "BAMBU_LAB_MQTT_HOST",
        "BAMBU_ACCESS_CODE",
        "BAMBU_TOKEN",
        "BAMBU_MQTT_PASSWORD",
        "BAMBU_LAB_MQTT_PASSWORD",
        "BAMBU_SERIAL",
        "BAMBU_DEVICE_ID",
        "BAMBU_SERIAL_NUMBER",
        "BAMBU_LAB_DEVICE_ID",
    ):
        monkeypatch.delenv(key, raising=False)
    settings = load_settings()
    assert set(settings.missing()) == {"BAMBU_IP", "BAMBU_ACCESS_CODE", "BAMBU_SERIAL"}


def test_camera_port(monkeypatch):
    monkeypatch.delenv("BAMBU_CAMERA_PORT", raising=False)
    assert load_settings().camera_port == 6000
    monkeypatch.setenv("BAMBU_CAMERA_PORT", "16000")
    assert load_settings().public_dict()["camera_port"] == 16000
