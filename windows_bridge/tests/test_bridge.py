import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import numpy as np
import pytest

from m5vibe.bridge import Bridge
from m5vibe.config import Config
from m5vibe.protocol import MIC_CONTROL, AudioFrame, json_bytes


@pytest.mark.parametrize("name,expected", [("Vibe-GC", True), ("M5Codex-GC", True), ("Headphones", False)])
def test_discovery_keeps_legacy_devices_and_finds_vibe(name, expected, monkeypatch):
    from bleak.backends.device import BLEDevice

    from m5vibe.bridge import discover

    device = BLEDevice("C7:F5:47:B5:F0:C1", name, None)
    scanner = AsyncMock(return_value={device.address: (device, SimpleNamespace(local_name=name))})
    monkeypatch.setattr("m5vibe.bridge.BleakScanner.discover", scanner)
    monkeypatch.setattr("m5vibe.bridge.uninitialize_sta", lambda: None)
    found = asyncio.run(discover(timeout=0.01))
    assert found == ([device] if expected else [])


class FakeMic:
    ready = True
    fault = ""

    def __init__(self):
        self.active = False
        self.frames = []

    def begin(self):
        self.active = True

    def end(self):
        self.active = False

    def push(self, frame):
        self.frames.append(frame)

    def close(self):
        self.active = False

    def statistics(self):
        return {"input_seconds": 0, "output_seconds": 0, "rms_dbfs": float("-inf"),
                "peak_dbfs": float("-inf")}


def test_wechat_down_up_stream_and_no_duplicate_hid(tmp_path):
    async def scenario():
        bridge = Bridge(Config(), tmp_path / "state.json")
        bridge.microphone = FakeMic()
        bridge.mic_ready = True
        bridge.write = AsyncMock()
        bridge.voice = AsyncMock()
        await bridge.handle_event("input_primary_down")
        assert bridge.recording and bridge.microphone.active
        bridge.write.assert_called_once_with(MIC_CONTROL, b"\x03")
        await bridge.handle_event("input_primary_up")
        assert not bridge.recording and not bridge.microphone.active
        assert bridge.write.call_args.args == (MIC_CONTROL, b"\x04")
    asyncio.run(scenario())


def test_configuration_closes_gate_and_uses_att_sized_messages(tmp_path):
    async def scenario():
        bridge = Bridge(Config(), tmp_path / "state.json")
        bridge.status = AsyncMock()
        await bridge.configure()
        messages = [call.args[0] for call in bridge.status.call_args_list]
        assert messages[0]["microphone_gate_enabled"] and not messages[0]["microphone_ready"]
        assert all(len(json_bytes(message)) <= 244 for message in messages)
        assert messages[1]["input_mode"] == "wechat_ime"
    asyncio.run(scenario())


def test_preroll_does_not_splice_previous_utterance(tmp_path):
    async def scenario():
        bridge = Bridge(Config(), tmp_path / "state.json")
        bridge.microphone = FakeMic()
        bridge.mic_ready = True
        bridge.write = AsyncMock()
        bridge.voice = AsyncMock()
        bridge.preroll.append(AudioFrame(10, 3200, np.zeros(320, dtype=np.int16)))
        await bridge.begin_recording()
        assert not bridge.microphone.frames
    asyncio.run(scenario())


def test_fault_requires_fresh_press_and_never_resumes(tmp_path):
    async def scenario():
        bridge = Bridge(Config(), tmp_path / "state.json")
        bridge.microphone = FakeMic()
        bridge.write = AsyncMock()
        bridge.voice = AsyncMock()
        bridge.ready = AsyncMock()
        bridge.prepare_microphone = AsyncMock()
        bridge.recording = True
        await bridge.interrupt("packet gap")
        assert not bridge.recording and bridge.interrupted
        assert not bridge.microphone.active
        bridge.voice.assert_called_once_with("error")
        bridge.prepare_microphone.assert_awaited_once()
    asyncio.run(scenario())


def test_verified_device_reconnects_without_advertising(tmp_path, monkeypatch):
    async def scenario():
        bridge = Bridge(Config(), tmp_path / "state.json")
        bridge.state.data["device_address"] = "AA:BB:CC:DD:EE:FF"
        bridge.microphone = FakeMic()
        bridge.poll_quota = AsyncMock()
        bridge.codex.close = AsyncMock()
        bridge.session = AsyncMock(side_effect=asyncio.CancelledError)
        scanner = AsyncMock(side_effect=AssertionError("A known HID device need not advertise"))
        monkeypatch.setattr("m5vibe.bridge.discover", scanner)
        with pytest.raises(asyncio.CancelledError):
            await bridge.run()
        scanner.assert_not_called()
        assert bridge.session.call_args.args[0].address == "AA:BB:CC:DD:EE:FF"
    asyncio.run(scenario())


def test_fresh_pair_uses_firmware_static_random_address(tmp_path, monkeypatch):
    from bleak.backends.device import BLEDevice

    async def scenario():
        class CancelBeforeConnect:
            async def __aenter__(self):
                raise asyncio.CancelledError

            async def __aexit__(self, *_args):
                return False

        options = {}

        def client_factory(device, **kwargs):
            options.update(kwargs)
            return CancelBeforeConnect()

        monkeypatch.setattr("m5vibe.bridge.BleakClient", client_factory)
        bridge = Bridge(Config(), tmp_path / "state.json")
        with pytest.raises(asyncio.CancelledError):
            await bridge.session(BLEDevice("C7:F5:47:B5:F0:C1", "M5Codex-GC", None))
        assert options["pair"]
        assert options["winrt"] == {"use_cached_services": False, "address_type": "random"}

    asyncio.run(scenario())
