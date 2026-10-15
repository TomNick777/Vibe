"""Pinned M5stopwatch-vibecoding BLE protocol and IMA-ADPCM decoding."""
import json
import struct
from dataclasses import dataclass

import numpy as np

COMPANION = "abcd0000-e819-b394-6344-2a2f31424c45"
EVENT = "abcd0001-e819-b394-6344-2a2f31424c45"
STATUS = "abcd0002-e819-b394-6344-2a2f31424c45"
PANEL = "abcd0003-e819-b394-6344-2a2f31424c45"
MIC_CONTROL = "7d2f0002-5cf1-4f3c-9f42-a8c8f6a1b001"
MIC_AUDIO = "7d2f0003-5cf1-4f3c-9f42-a8c8f6a1b001"
MIC_STATS = "7d2f0004-5cf1-4f3c-9f42-a8c8f6a1b001"

STEP = (
    7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31,
    34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88, 97, 107, 118, 130, 143,
    157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449, 494, 544,
    598, 658, 724, 796, 876, 963, 1060, 1166, 1282, 1411, 1552, 1707,
    1878, 2066, 2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871,
    5358, 5894, 6484, 7132, 7845, 8630, 9493, 10442, 11487, 12635,
    13899, 15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794, 32767,
)
INDEX = (-1, -1, -1, -1, 2, 4, 6, 8)


@dataclass(frozen=True)
class AudioFrame:
    sequence: int
    sample_index: int
    pcm: np.ndarray


def decode_audio(packet: bytes) -> AudioFrame:
    if len(packet) != 174:
        raise ValueError("BLE audio packet must be 174 bytes")
    sequence, codec, flags, first, count, predictor, index, reserved = struct.unpack_from("<HBBIHhBB", packet)
    if codec != 1 or flags != 0 or reserved != 0 or count != 320 or index > 88:
        raise ValueError("Unsupported or malformed BLE audio header")
    pcm = np.empty(count, dtype=np.int16)
    pcm[0] = predictor
    for sample in range(1, count):
        byte = packet[14 + (sample - 1) // 2]
        code = (byte >> (4 * ((sample - 1) % 2))) & 15
        step = STEP[index]
        diff = (step >> 3) + (step if code & 4 else 0) + (step >> 1 if code & 2 else 0)
        diff += step >> 2 if code & 1 else 0
        predictor = max(-32768, min(32767, predictor + (-diff if code & 8 else diff)))
        index = max(0, min(88, index + INDEX[code & 7]))
        pcm[sample] = predictor
    return AudioFrame(sequence, first, pcm)


class AudioContinuity:
    """A missing packet fails the utterance; the next utterance starts fresh."""

    def __init__(self):
        self.expected_sequence = None
        self.expected_sample = None

    def reset(self):
        self.expected_sequence = self.expected_sample = None

    def accept(self, frame: AudioFrame):
        if self.expected_sequence is not None and (
            frame.sequence != self.expected_sequence or frame.sample_index != self.expected_sample
        ):
            raise ValueError("BLE audio interrupted: packet or sample gap; record again")
        self.expected_sequence = (frame.sequence + 1) & 0xFFFF
        self.expected_sample = (frame.sample_index + 320) & 0xFFFFFFFF


def json_bytes(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode("ascii")


def panel_chunks(value: dict, sequence: int, max_payload: int = 180) -> list[bytes]:
    raw = json_bytes(value)
    if len(raw) > 20 * 1024:
        raise ValueError("Panel exceeds firmware limit")
    # Reserve enough JSON overhead even when sequence/part numbers grow.
    chunk_size = (max_payload - 96) // 2
    if chunk_size < 1:
        raise ValueError("ATT payload is too small for panel chunks")
    parts = (len(raw) + chunk_size - 1) // chunk_size
    result = [json_bytes({"type": "panel_chunk", "seq": sequence, "part": part + 1,
                          "parts": parts, "data": raw[start:start + chunk_size].hex()})
              for part, start in enumerate(range(0, len(raw), chunk_size))]
    if any(len(chunk) > max_payload for chunk in result):
        raise ValueError("Panel chunk exceeds ATT payload")
    return result
