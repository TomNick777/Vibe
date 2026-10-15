import asyncio
import logging
import time
from collections import deque
from contextlib import suppress
from pathlib import Path

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.winrt.util import uninitialize_sta
from bleak.exc import BleakError
from sounddevice import PortAudioError

from .audio import VirtualMicrophone
from .codex import CodexRPC
from .config import Config
from .grok import GrokUsage, GrokUsageError
from .panel import PanelState
from .protocol import (
    EVENT,
    MIC_AUDIO,
    MIC_CONTROL,
    MIC_STATS,
    PANEL,
    STATUS,
    AudioContinuity,
    decode_audio,
    json_bytes,
    panel_chunks,
)

LOG = logging.getLogger("m5vibe")


async def discover(address="", timeout=10):
    # PortAudio can initialize the main thread as STA during import. A CLI
    # has no GUI message loop, so WinRT BLE must restore its MTA apartment.
    uninitialize_sta()
    devices = await BleakScanner.discover(timeout=timeout, return_adv=True)
    return [device for device, adv in devices.values()
            if (address and device.address.lower() == address.lower())
            or (not address and (adv.local_name or device.name or "").startswith(("Vibe-", "M5Codex-")))]


class Bridge:
    def __init__(self, config: Config, state_path: Path):
        self.config = config
        self.state = PanelState(state_path)
        self.codex = CodexRPC(config.codex_command)
        self.grok = GrokUsage(config.grok_auth_file)
        self.microphone = VirtualMicrophone(monitor=config.audio_diagnostics)
        self.continuity = AudioContinuity()
        self.client = None
        self.write_lock = asyncio.Lock()
        self.events = asyncio.Queue(maxsize=32)
        self.recording = False
        self.interrupted = False
        self.fault = ""
        self.mic_ready = False
        self.last_audio = 0
        self.started_at = 0
        self.last_tick = 0
        self.panel_sequence = 0
        self.threads = []
        self.quota_error = "Quota waiting"
        self.last_quota_poll = 0
        self.last_panel = 0
        self.last_ready = 0
        self.preroll = deque(maxlen=8)
        self.preroll_at = 0

    async def write(self, uuid, data):
        async with self.write_lock:
            await asyncio.wait_for(self.client.write_gatt_char(uuid, data, response=True), 5)

    async def status(self, value):
        await self.write(STATUS, json_bytes(value))

    async def ready(self, ready):
        await self.status({"type": "bridge_ready", "microphone_gate_enabled": self.config.microphone,
                           "microphone_ready": ready})
        self.mic_ready = ready
        self.last_ready = time.monotonic()

    async def voice(self, phase):
        await self.status({"voice_active": phase in ("recording", "processing"), "phase": phase})

    def on_event(self, _characteristic, data):
        event = bytes(data).decode("utf-8", errors="replace")
        try:
            self.events.put_nowait(event)
        except asyncio.QueueFull:
            self.fault = "Device event overflow; record again"

    def on_audio(self, _characteristic, data):
        if self.interrupted:
            return
        try:
            frame = decode_audio(bytes(data))
            if not self.recording:
                if frame.sample_index == 0:
                    self.preroll.clear()
                    self.preroll_at = time.monotonic()
                if time.monotonic() - self.preroll_at < 0.2:
                    self.preroll.append(frame)
                return
            self.continuity.accept(frame)
            self.microphone.push(frame.pcm)
            self.last_audio = time.monotonic()
        except (ValueError, RuntimeError) as exc:
            self.fault = str(exc)
            self.microphone.end()

    async def configure(self):
        # Close the gate before changing bindings. Keep every write below ATT payload.
        await self.ready(False)
        values = self.config.ready_message(False)
        for keys in (("input_mode", "primary_key", "primary_modifier"),
                     ("confirm_key", "confirm_modifier"),
                     ("confirm_long_key", "confirm_long_modifier", "confirm_long_action", "shake_action")):
            await self.status({"type": "bridge_ready", **{key: values[key] for key in keys}})
        await self.voice("idle")

    async def prepare_microphone(self):
        if not self.config.microphone:
            await self.ready(False)
            return
        self.microphone.close()
        try:
            await asyncio.to_thread(self.microphone.open)
            await self.write(MIC_CONTROL, b"\x02")  # Arm on demand, acknowledged write.
            stats = bytes(await asyncio.wait_for(self.client.read_gatt_char(MIC_STATS), 5))
            if len(stats) < 20 or not stats[2] or int.from_bytes(stats[4:8], "little") != 16000:
                raise RuntimeError("BLE microphone subscription/format is not ready")
            self.microphone.validate_route()
            await self.ready(True)
            LOG.info("Microphone ready -> CABLE Output (VB-Audio Virtual Cable)")
        except (RuntimeError, OSError, ValueError, PortAudioError, BleakError) as exc:
            self.microphone.close()
            await self.ready(False)
            LOG.warning("Microphone unavailable: %s", exc)

    async def begin_recording(self):
        if not self.config.microphone:
            return
        if not self.microphone.ready or not self.mic_ready:
            await self.prepare_microphone()
        if not self.microphone.ready or not self.mic_ready:
            await self.voice("error")
            return
        self.microphone.begin()
        self.continuity.reset()
        self.interrupted = False
        self.fault = ""
        self.started_at = self.last_audio = self.last_tick = time.monotonic()
        self.recording = True
        if self.preroll and self.preroll[0].sample_index == 0 and time.monotonic() - self.preroll_at < 0.2:
            for frame in self.preroll:
                self.continuity.accept(frame)
                self.microphone.push(frame.pcm)
        self.preroll.clear()
        try:
            await self.write(MIC_CONTROL, b"\x03")
            await self.voice("recording")
        except BaseException:
            self.recording = False
            self.microphone.end()
            raise
        self.state.activity(time.time(), starts=1)
        LOG.info("Recording")

    async def stop_recording(self, error=False):
        self.recording = False
        self.microphone.end()
        self.preroll.clear()
        stats = self.microphone.statistics()
        LOG.info("Audio: BLE %.2fs, virtual output %.2fs, RMS %.1fdBFS, peak %.1fdBFS",
                 stats["input_seconds"], stats["output_seconds"], stats["rms_dbfs"], stats["peak_dbfs"])
        if self.config.audio_diagnostics:
            LOG.info("CABLE input: %.2fs, RMS %.1fdBFS, peak %.1fdBFS", stats["capture_seconds"],
                     stats["capture_rms_dbfs"], stats["capture_peak_dbfs"])
        await self.write(MIC_CONTROL, b"\x04")
        self.state.save()
        self.interrupted = error
        await self.voice("error" if error else "idle")
        LOG.info("Record again" if error else "Ready")

    async def interrupt(self, reason):
        self.fault = ""
        await self.stop_recording(error=True)
        await self.ready(False)
        LOG.warning("Recording interrupted: %s", reason)
        # Rebuild the local output and re-arm BLE, but never resume the utterance.
        await self.prepare_microphone()

    async def handle_event(self, event):
        self.state.activity(time.time(), operations=1)
        if event == "input_primary_down":
            if self.recording:
                await self.stop_recording()
            else:
                await self.begin_recording()
        elif event == "input_primary_up" and self.config.voice_mode == "hold" and self.recording:
            await self.stop_recording()
        elif event == "shake_action":
            if self.recording:
                await self.stop_recording()
        # The device sends voice shortcuts through the standard keyboard HID.
        # The bridge only carries audio and panel data, avoiding duplicate keys.

    async def poll_quota(self):
        try:
            if self.codex.process is None or self.codex.process.returncode is not None:
                await self.codex.close()
                await self.codex.start()
            limits = await self.codex.limits()
            window = self.state.quota(limits, time.time())
            self.quota_error = "" if window else "Weekly quota unavailable"
            try:
                self.threads = (await self.codex.threads()).get("data", [])
                self.threads_at = time.time()
            except (RuntimeError, TimeoutError):
                self.threads = []
        except (RuntimeError, OSError, TimeoutError):
            self.quota_error = "Codex unavailable"
            LOG.warning("Codex state unavailable; keeping cached quota marked stale")
        self.last_quota_poll = time.monotonic()
        if self.config.grok_usage:
            try:
                reading = await asyncio.to_thread(self.grok.read)
                self.state.grok_quota(reading)
                LOG.info("X shared weekly quota: %s%% remaining", reading["left"])
            except GrokUsageError as exc:
                self.state.grok_failure(str(exc), self.grok.account, exc.keep_cache)
                LOG.warning("X shared quota: %s", exc)
        else:
            self.state.grok_failure("X usage disabled")

    async def send_panel(self):
        self.panel_sequence = (self.panel_sequence + 1) % 1_000_000_000
        panel = self.state.build(time.time(), self.threads, self.quota_error,
                                 threads_at=getattr(self, "threads_at", 0))
        payload = min(240, self.client.mtu_size - 3)
        for chunk in panel_chunks(panel, self.panel_sequence, payload):
            if not self.events.empty():
                return  # A new panel starts at part 1 after the input event completes.
            await self.write(PANEL, chunk)
        self.last_panel = time.monotonic()

    async def session(self, device):
        self.recording = self.interrupted = self.mic_ready = False
        self.fault = ""
        self.preroll.clear()
        self.events = asyncio.Queue(maxsize=32)
        # The firmware advertises a static random address. After unpairing,
        # Windows can no longer infer that type from the old paired cache.
        async with BleakClient(device, pair=True, timeout=60,
                               winrt={"use_cached_services": False, "address_type": "random"}) as client:
            self.client = client
            try:
                for uuid in (EVENT, STATUS, PANEL, MIC_CONTROL, MIC_AUDIO, MIC_STATS):
                    if client.services.get_characteristic(uuid) is None:
                        raise RuntimeError("Required GATT service missing; check integrated firmware")
                if self.config.microphone and client.mtu_size < 177:
                    raise RuntimeError("BLE ATT MTU below 177; microphone cannot stream")
                # Keep only a verified peripheral identity. Windows HID can
                # reconnect first and stop its advertising before this process.
                self.state.data["device_address"] = device.address
                self.state.save()
                await self.configure()
                await client.start_notify(EVENT, self.on_event)
                if self.config.microphone:
                    await client.start_notify(MIC_AUDIO, self.on_audio)
                    await self.prepare_microphone()
                LOG.info("Vibe BLE connected; voice shortcuts use standard keyboard HID")
                while client.is_connected:
                    now = time.monotonic()
                    if self.recording:
                        self.state.activity(time.time(), seconds=min(1, now - self.last_tick))
                        self.last_tick = now
                        reason = self.fault or self.microphone.fault
                        if now - self.last_audio > 1.2:
                            reason = "BLE audio stalled"
                        if reason:
                            await self.interrupt(reason)
                        else:
                            self.microphone.validate_route()
                    try:
                        event = await asyncio.wait_for(self.events.get(), 0.2)
                    except TimeoutError:
                        event = None
                    if event:
                        await self.handle_event(event)
                    # Defer quota and panel writes during capture; heartbeat remains short.
                    if not self.recording:
                        if now - self.last_panel >= 10:
                            await self.send_panel()
                    if now - self.last_ready >= 10:
                        await self.ready(self.microphone.ready and self.mic_ready)
            finally:
                self.microphone.end()
                if client.is_connected:
                    with suppress(Exception):
                        await self.write(MIC_CONTROL, b"\x00")
                        await self.voice("error" if self.recording else "idle")
                        await self.ready(False)
                self.recording = self.mic_ready = False
                self.microphone.close()
                self.state.save()
                self.client = None

    async def run(self):
        await self.poll_quota()
        quota_task = asyncio.create_task(self.quota_loop())
        address = self.config.address or self.state.data.get("device_address", "")
        known_device = BLEDevice(address, "Vibe", None) if address else None
        try:
            while True:
                devices = [known_device] if known_device else await discover(self.config.address)
                if len(devices) > 1:
                    raise RuntimeError("Multiple StopWatch devices found; set address in config.local.json")
                if not devices:
                    LOG.info("Waiting for Vibe-* or legacy M5Codex-*; open Vibe on StopWatch")
                    await asyncio.sleep(5)
                    continue
                known_device = devices[0]
                try:
                    await self.session(known_device)
                except (RuntimeError, OSError, TimeoutError, BleakError, PortAudioError) as exc:
                    LOG.warning("BLE session ended: %s", exc)
                await asyncio.sleep(5)
        finally:
            quota_task.cancel()
            with suppress(asyncio.CancelledError):
                await quota_task
            self.microphone.close()
            await self.codex.close()

    async def quota_loop(self):
        while True:
            await asyncio.sleep(self.config.quota_poll_seconds)
            await self.poll_quota()
