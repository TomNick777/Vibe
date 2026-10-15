import numpy as np
import pytest

from m5vibe.audio import INPUT_NAME, OUTPUT_NAME, VirtualMicrophone, cable_devices
from m5vibe.config import Config
from m5vibe.panel import PanelState, quota_window, weekly_window


def device(name, input_channels=0, output_channels=0, hostapi=0):
    return {"name": name, "max_input_channels": input_channels,
            "max_output_channels": output_channels, "hostapi": hostapi}


def test_explicit_virtual_pair_and_physical_output_rejection():
    apis = [{"name": "Windows WASAPI"}]
    with pytest.raises(RuntimeError):
        cable_devices([device("Speakers", output_channels=2)], apis)
    devices = [device("Speakers", output_channels=2), device(OUTPUT_NAME, output_channels=2),
               device(INPUT_NAME, input_channels=2)]
    assert cable_devices(devices, apis) == (1, 2)
    with pytest.raises(RuntimeError):
        cable_devices(devices + [devices[1]], apis)
    with pytest.raises(RuntimeError):
        cable_devices(devices, [{"name": "MME"}])


def test_audio_queue_output_and_immediate_mute():
    mic = VirtualMicrophone()
    mic.active = True
    for _ in range(3):
        mic.push(np.full(320, 8192, dtype=np.int16))
    out = np.empty((480, 2), dtype=np.float32)
    mic._callback(out, 480, None, False)
    assert np.all(out == 0.25)
    stats = mic.statistics()
    assert stats["input_seconds"] == 0.06
    assert stats["output_seconds"] == 0.01
    assert stats["rms_dbfs"] == pytest.approx(-12.0412, abs=0.0001)
    assert stats["peak_dbfs"] == pytest.approx(-12.0412, abs=0.0001)
    mic.end()
    mic._callback(out, 480, None, False)
    assert np.all(out == 0)


def test_virtual_input_meter_counts_only_active_capture():
    mic = VirtualMicrophone(monitor=True)
    block = np.full((480, 2), 0.125, dtype=np.float32)
    mic._capture_callback(block, 480, None, False)
    assert mic.statistics()["capture_seconds"] == 0
    mic.active = True
    mic._capture_callback(block, 480, None, False)
    stats = mic.statistics()
    assert stats["capture_seconds"] == 0.01
    assert stats["capture_rms_dbfs"] == pytest.approx(-18.0618, abs=0.0001)
    mic.end()
    mic._capture_callback(block, 480, None, False)
    assert mic.statistics()["capture_seconds"] == 0.01


def test_audio_fault_mutes_and_queue_is_bounded():
    mic = VirtualMicrophone()
    mic.active = True
    for _ in range(15):
        mic.push(np.zeros(320, dtype=np.int16))
    with pytest.raises(RuntimeError, match="overflow"):
        mic.push(np.zeros(320, dtype=np.int16))
    assert mic.samples == 0
    out = np.empty((480, 2), dtype=np.float32)
    mic._callback(out, 480, None, False)
    assert np.all(out == 0)


def test_callback_underflow_marks_utterance_failed():
    mic = VirtualMicrophone()
    mic.active = mic.primed = True
    out = np.empty((480, 2), dtype=np.float32)
    for _ in range(10):
        mic._callback(out, 480, None, False)
    assert "record again" in mic.fault


def limits(left=80, reset=200000):
    return {"rateLimitsByLimitId": {"codex": {"primary": {"windowDurationMins": 300, "usedPercent": 100},
                                             "secondary": {"windowDurationMins": 10080,
                                                           "usedPercent": 100-left, "resetsAt": reset}}}}


def test_weekly_window_and_unknown():
    assert weekly_window(limits())["left"] == 80
    assert weekly_window({}) is None
    assert weekly_window({"rateLimits": {"primary": {"usedPercent": 90}}}) is None


def test_two_quota_windows_reversed_and_five_hour_only(tmp_path):
    data = {"rateLimits": {"secondary": {"windowDurationMins": 300, "usedPercent": 25,
                                        "resetsAt": 7200},
                           "primary": {"windowDurationMins": 10080, "usedPercent": 10}}}
    assert quota_window(data, 300)["left"] == 75
    assert weekly_window(data)["left"] == 90
    panel = PanelState(tmp_path / "panel.json")
    panel.quota(data, 3600)
    built = panel.build(3600)["codex"]
    assert built["five_hour"] == {"left_pct": 75, "stale": False, "reset_in": "1h 0m"}
    assert PanelState(panel.path).build(3600)["codex"]["five_hour"]["left_pct"] == 75
    assert panel.build(4300)["codex"]["five_hour"]["stale"]
    del data["rateLimits"]["primary"]
    panel.quota(data, 4400)
    assert panel.build(4400)["codex"]["five_hour"]["left_pct"] == 75
    panel.quota({}, 4500)
    assert panel.build(4500)["codex"]["five_hour"]["left_pct"] is None


@pytest.mark.parametrize("used", [None, True, -1, 101, "25", float("nan")])
def test_bad_five_hour_percentage_is_unknown(used):
    assert quota_window({"rateLimits": {"primary": {"windowDurationMins": 300, "usedPercent": used}}}, 300) is None


@pytest.mark.parametrize("flag", ["waitingOnApproval", "waitingOnUserInput"])
def test_confirmation_requires_explicit_active_flag(tmp_path, flag):
    panel = PanelState(tmp_path / "panel.json")
    assert not panel.build(3600, [{"status": {"type": "active"}}])["codex"]["needs_confirmation"]
    threads = [{"status": {"type": "idle"}}, {"status": {"type": "active", "activeFlags": [flag]}}]
    assert panel.build(3600, threads)["codex"]["needs_confirmation"]
    assert not panel.build(3600, threads, threads_at=3500)["codex"]["needs_confirmation"]
    threads[1]["status"]["type"] = "notLoaded"
    assert not panel.build(3600, threads)["codex"]["needs_confirmation"]


def test_partial_day_reset_offline_and_day_boundary(tmp_path):
    panel = PanelState(tmp_path / "panel.json")
    assert panel.build(86400)["codex"]["weekly"]["left_pct"] is None
    panel.quota(limits(80), 86400 + 400)
    panel.quota(limits(77), 86400 + 500)
    assert panel.data["today"] == 3
    assert not panel.data["baseline_known"]
    panel.quota(limits(100, reset=300000), 86400 + 600)
    panel.quota(limits(98, reset=300000), 86400 + 700)
    assert panel.data["today"] == 5
    assert panel.build(86400 + 2000)["codex"]["stale"]
    panel.quota(limits(96, reset=300000), 2 * 86400)
    assert panel.data["today"] == 0
    restored = PanelState(tmp_path / "panel.json")
    assert restored.data["left"] == 96


def test_activity_rolls_over_24_buckets(tmp_path):
    panel = PanelState(tmp_path / "panel.json")
    panel.activity(0, seconds=600, starts=10)
    buckets = panel.build(0)["codex"]["openwatcher_home"]["activity_buckets"]
    assert len(buckets) == 24 and buckets[-1] == 1
    panel.activity(24 * 600, starts=1)
    assert "0" not in panel.data["activity"]


def test_wechat_hold_binding_and_split_configuration(tmp_path):
    config = Config()
    assert config.ready_message(True)["primary_modifier"] == 9
    assert config.ready_message(True)["primary_key"] == 0
    path = tmp_path / "config.json"
    config.save(path)
    assert Config.load(path).voice_mode == "hold"
