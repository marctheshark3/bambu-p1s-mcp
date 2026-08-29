from __future__ import annotations

import json
import os
import ssl
import threading
import time
from typing import Any

import paho.mqtt.client as mqtt

from bambu_p1s_mcp.config import Settings
from bambu_p1s_mcp.payloads import get_version, pause, print_speed, project_file, pushall, resume, stop
from bambu_p1s_mcp.payloads import gcode_file as gcode_file_payload
from bambu_p1s_mcp.payloads import speed_level
from bambu_p1s_mcp.status import ams_view, deep_merge, summarize


def _new_client(client_id: str) -> mqtt.Client:
    kwargs: dict[str, Any] = {
        "client_id": client_id,
        "protocol": mqtt.MQTTv311,
        "clean_session": True,
    }
    if hasattr(mqtt, "CallbackAPIVersion"):
        kwargs["callback_api_version"] = mqtt.CallbackAPIVersion.VERSION1
    return mqtt.Client(**kwargs)


class PrinterSession:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._state: dict[str, Any] = {}
        self._lock = threading.Lock()
        self._connected = threading.Event()
        self._seq = 0
        self._client: mqtt.Client | None = None
        self._last_error: str | None = None
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        missing = self.settings.missing()
        if missing:
            raise RuntimeError("missing required env: " + ", ".join(missing))
        client_id = f"bambu-p1s-mcp-{os.getpid()}"
        client = _new_client(client_id)
        client.username_pw_set(self.settings.mqtt_username, self.settings.access_code)
        client.tls_set(cert_reqs=ssl.CERT_NONE)
        client.tls_insecure_set(True)
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        client.connect(self.settings.ip, self.settings.mqtt_port, keepalive=60)
        client.loop_start()
        self._client = client
        self._started = True
        if not self._connected.wait(timeout=12):
            raise ConnectionError(f"MQTT connect timeout to {self.settings.ip}:{self.settings.mqtt_port}")
        self.publish(pushall(self.next_seq()))
        self.publish(get_version(self.next_seq()))
        time.sleep(1.2)

    def stop(self) -> None:
        if self._client is not None:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception:
                pass
        self._started = False
        self._connected.clear()

    def ensure(self) -> None:
        if not self._started:
            self.start()
        elif not self._connected.is_set():
            self.stop()
            self.start()

    def next_seq(self) -> int:
        with self._lock:
            self._seq += 1
            return self._seq

    def publish(self, payload: dict, qos: int = 0) -> dict:
        self.ensure()
        assert self._client is not None
        body = json.dumps(payload, separators=(",", ":"))
        info = self._client.publish(self.settings.request_topic, body, qos=qos)
        info.wait_for_publish(timeout=5)
        return payload

    def snapshot(self, *, fresh: bool = False) -> dict:
        self.ensure()
        if fresh:
            self.publish(pushall(self.next_seq()))
            time.sleep(1.5)
        with self._lock:
            state = json.loads(json.dumps(self._state))
        return summarize(state, connected=self._connected.is_set(), last_error=self._last_error)

    def ams(self) -> dict:
        self.ensure()
        with self._lock:
            state = json.loads(json.dumps(self._state))
        return ams_view(state)

    def pause_print(self) -> dict:
        return self.publish(pause(self.next_seq()), qos=1)

    def resume_print(self) -> dict:
        return self.publish(resume(self.next_seq()), qos=1)

    def stop_print(self) -> dict:
        return self.publish(stop(self.next_seq()), qos=1)

    def set_speed(self, value: str | int) -> dict:
        return self.publish(print_speed(self.next_seq(), speed_level(value)), qos=1)

    def start_project(self, filename: str, **kwargs) -> dict:
        return self.publish(project_file(self.next_seq(), filename, **kwargs), qos=1)

    def start_gcode(self, filename: str) -> dict:
        return self.publish(gcode_file_payload(self.next_seq(), filename), qos=1)

    def raw_state(self) -> dict:
        with self._lock:
            return json.loads(json.dumps(self._state))

    def connected(self) -> bool:
        return self._connected.is_set()

    def _on_connect(self, client, userdata, flags, rc):  # noqa: ANN001
        if rc == 0:
            client.subscribe(self.settings.report_topic, qos=0)
            self._connected.set()
            self._last_error = None
        else:
            self._last_error = f"mqtt connect rc={rc}"
            self._connected.clear()

    def _on_disconnect(self, client, userdata, rc):  # noqa: ANN001
        self._connected.clear()
        if rc != 0:
            self._last_error = f"mqtt disconnect rc={rc}"

    def _on_message(self, client, userdata, msg):  # noqa: ANN001
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            self._last_error = f"bad mqtt json: {exc}"
            return
        if not isinstance(payload, dict):
            return
        with self._lock:
            deep_merge(self._state, payload)


_SESSION: PrinterSession | None = None
_SESSION_LOCK = threading.Lock()


def get_session(settings: Settings | None = None) -> PrinterSession:
    global _SESSION
    from bambu_p1s_mcp.config import load_settings

    with _SESSION_LOCK:
        if _SESSION is None:
            _SESSION = PrinterSession(settings or load_settings())
        return _SESSION
