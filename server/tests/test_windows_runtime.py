"""Optional smoke tests against the installed Windows native runtime."""
import os
import socket
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hidagent.screen import Screen

RUNTIME = Path(__file__).resolve().parents[2] / ".tools/msys64/ucrt64/bin"
pytestmark = pytest.mark.skipif(
    os.name != "nt" or not (RUNTIME / "uxplay.exe").is_file(), reason="native Windows runtime not installed"
)


def test_gstreamer_jpeg_tcp_transport():
    screen = Screen()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(10)
        port = listener.getsockname()[1]
        arguments = [
            str(RUNTIME / "gst-launch-1.0.exe"), "-q", "videotestsrc", "num-buffers=2", "!",
            "video/x-raw,width=64,height=128", "!", "jpegenc", "!", "tcpclientsink",
            "host=127.0.0.1", f"port={port}", "sync=false",
        ]
        with subprocess.Popen(arguments, creationflags=subprocess.CREATE_NO_WINDOW) as process:
            screen._proc = process
            try:
                receiver, _ = listener.accept()
                with receiver:
                    receiver.settimeout(0.25)
                    screen._read_socket(receiver)
                assert process.wait(timeout=5) == 0
                assert screen.frame.startswith(b"\xff\xd8")
                assert screen.frame.endswith(b"\xff\xd9")
                assert screen.aspect == 0.5
            finally:
                if process.poll() is None:
                    process.terminate()


def test_web_app_starts_native_airplay_and_shuts_it_down(monkeypatch, tmp_path):
    monkeypatch.setenv("UXPLAY_BINARY", str(RUNTIME / "uxplay.exe"))
    monkeypatch.setenv("HIDAGENT_DATA", str(tmp_path))
    monkeypatch.setenv("DEVICE_PORT", "0")
    from hidagent.app import app, screen

    screen.executable = str(RUNTIME / "uxplay.exe")
    with TestClient(app) as client:
        assert client.get("/").status_code == 200
        assert client.get("/static/app.js").status_code == 200
        status = client.get("/api/status")
        assert status.status_code == 200
        assert status.json()["device"] is False
        assert status.json()["agent"]["running"] is False
        assert client.get("/api/frame.jpg").status_code == 404
        deadline = time.monotonic() + 8
        while screen._proc is None and time.monotonic() < deadline:
            time.sleep(0.05)
        assert screen._proc is not None
        time.sleep(1)
        assert screen._proc.poll() is None
    assert not screen._thread.is_alive()
    assert screen._proc.poll() is not None
