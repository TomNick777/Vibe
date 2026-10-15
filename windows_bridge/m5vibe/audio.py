"""Explicit VB-CABLE WASAPI output. The default speaker is never selected."""
from collections import deque
from threading import Lock

import numpy as np
import sounddevice as sd

OUTPUT_NAME = "CABLE Input (VB-Audio Virtual Cable)"
INPUT_NAME = "CABLE Output (VB-Audio Virtual Cable)"


def cable_devices(devices=None, hostapis=None) -> tuple[int, int]:
    devices = sd.query_devices() if devices is None else devices
    hostapis = sd.query_hostapis() if hostapis is None else hostapis
    output = [i for i, d in enumerate(devices) if d["name"] == OUTPUT_NAME
              and d["max_output_channels"] >= 2 and hostapis[d["hostapi"]]["name"] == "Windows WASAPI"]
    capture = [i for i, d in enumerate(devices) if d["name"] == INPUT_NAME
               and d["max_input_channels"] >= 2 and hostapis[d["hostapi"]]["name"] == "Windows WASAPI"]
    if len(output) != 1 or len(capture) != 1:
        raise RuntimeError("VB-CABLE WASAPI input/output pair is missing or ambiguous; install VB-CABLE and restart")
    return output[0], capture[0]


class VirtualMicrophone:
    def __init__(self, monitor=False):
        self.stream = None
        self.monitor = monitor
        self.capture_stream = None
        self.device = None
        self.capture_device = None
        self.lock = Lock()
        self.blocks = deque()
        self.samples = 0
        self.active = False
        self.primed = False
        self.fault = ""
        self.underflow_samples = 0
        self.delivered_samples = 0
        self.received_samples = 0
        self.sum_squares = 0.0
        self.peak = 0.0
        self.capture_samples = 0
        self.capture_energy = 0.0
        self.capture_peak = 0.0

    def open(self):
        self.device, self.capture_device = cable_devices()
        sd.check_output_settings(device=self.device, channels=2, dtype="float32", samplerate=48000)
        self.stream = sd.OutputStream(device=self.device, channels=2, samplerate=48000, dtype="float32",
                                      blocksize=480, callback=self._callback, latency=0.06,
                                      extra_settings=sd.WasapiSettings(auto_convert=True))
        try:
            if self.monitor:
                self.capture_stream = sd.InputStream(device=self.capture_device, channels=2, samplerate=48000,
                                                     dtype="float32", blocksize=480, callback=self._capture_callback,
                                                     extra_settings=sd.WasapiSettings(auto_convert=True))
                self.capture_stream.start()
            self.stream.start()
        except BaseException:
            self.close()
            raise

    @property
    def ready(self):
        capture_ready = not self.monitor or (self.capture_stream is not None and self.capture_stream.active)
        return self.stream is not None and self.stream.active and capture_ready and not self.fault

    def validate_route(self):
        output, capture = cable_devices()
        if output != self.device or capture != self.capture_device or not self.ready:
            raise RuntimeError("Virtual microphone output route changed or stopped")

    def begin(self):
        self.validate_route()
        with self.lock:
            self.blocks.clear()
            self.samples = self.underflow_samples = self.delivered_samples = 0
            self.received_samples = 0
            self.sum_squares = self.peak = 0.0
            self.capture_samples = 0
            self.capture_energy = self.capture_peak = 0.0
            self.primed = False
            self.active = True

    def end(self):
        with self.lock:
            self.active = False
            self.blocks.clear()
            self.samples = 0
            self.primed = False

    def push(self, pcm):
        # Linear 16 -> 48kHz resampling, then identical left/right channels.
        normalized = np.asarray(pcm, dtype=np.float64) / 32768
        mono = np.interp(np.arange(960) / 3, np.arange(320), pcm).astype(np.float32) / 32768
        block = np.column_stack((mono, mono))
        with self.lock:
            if not self.active:
                return
            self.received_samples += len(normalized)
            self.sum_squares += float(np.dot(normalized, normalized))
            self.peak = max(self.peak, float(np.max(np.abs(normalized))))
            if self.samples + len(block) > 14400:  # Cap latency at 300ms; fail this utterance on overflow.
                self.fault = "Audio buffer overflow; record again"
                self.active = False
                self.blocks.clear()
                self.samples = 0
                raise RuntimeError(self.fault)
            self.blocks.append(block)
            self.samples += len(block)

    def statistics(self):
        # Counts and levels only; never retain or log speech samples.
        with self.lock:
            rms = (self.sum_squares / self.received_samples) ** 0.5 if self.received_samples else 0.0
            return {"input_seconds": self.received_samples / 16000,
                    "output_seconds": self.delivered_samples / 48000,
                    "rms_dbfs": 20 * np.log10(rms) if rms else float("-inf"),
                    "peak_dbfs": 20 * np.log10(self.peak) if self.peak else float("-inf"),
                    "capture_seconds": self.capture_samples / 48000,
                    "capture_rms_dbfs": 10 * np.log10(self.capture_energy / self.capture_samples)
                    if self.capture_energy and self.capture_samples else float("-inf"),
                    "capture_peak_dbfs": 20 * np.log10(self.capture_peak) if self.capture_peak else float("-inf")}

    def _capture_callback(self, indata, frames, _time, status):
        with self.lock:
            if not self.active:
                return
            if status:
                self.fault = "Virtual input diagnostic callback error; record again"
                return
            mono = np.asarray(indata[:, 0], dtype=np.float64)
            self.capture_samples += frames
            self.capture_energy += float(np.dot(mono, mono))
            self.capture_peak = max(self.capture_peak, float(np.max(np.abs(mono))))

    def _callback(self, outdata, frames, _time, status):
        outdata.fill(0)
        with self.lock:
            if not self.active or self.fault:
                return
            if status:
                self.fault = "Virtual microphone callback error; record again"
                return
            if not self.primed:
                if self.samples < 2880:  # 60ms startup buffer.
                    return
                self.primed = True
            offset = 0
            while self.blocks and offset < frames:
                block = self.blocks[0]
                count = min(len(block), frames - offset)
                outdata[offset:offset + count] = block[:count]
                self.samples -= count
                offset += count
                if count == len(block):
                    self.blocks.popleft()
                else:
                    self.blocks[0] = block[count:]
            self.delivered_samples += offset
            self.underflow_samples = self.underflow_samples + frames - offset if offset < frames else 0
            if self.underflow_samples >= 4800:
                self.fault = "Virtual microphone buffer stalled; record again"

    def close(self):
        self.end()
        capture, self.capture_stream = self.capture_stream, None
        if capture is not None:
            try:
                capture.stop()
            finally:
                capture.close()
        stream, self.stream = self.stream, None
        if stream is not None:
            try:
                stream.stop()
            finally:
                stream.close()
        self.fault = ""
