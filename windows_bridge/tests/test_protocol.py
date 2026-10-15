import json
import os
import struct
import subprocess
from pathlib import Path

import numpy as np
import pytest

from m5vibe.protocol import AudioContinuity, decode_audio, panel_chunks


def packet(sequence=0, sample=0, predictor=0, index=0, code=0):
    return struct.pack("<HBBIHhBB", sequence, 1, 0, sample, 320, predictor, index, 0) + bytes([code] * 160)


@pytest.mark.parametrize("predictor", [-32768, -5000, 0, 5000, 32767])
def test_constant_signal(predictor):
    frame = decode_audio(packet(predictor=predictor))
    assert frame.pcm.dtype == np.int16
    assert len(frame.pcm) == 320
    assert np.all(frame.pcm == predictor)


@pytest.mark.parametrize("offset,value", [(2, 2), (3, 1), (8, 0), (12, 89), (13, 1)])
def test_invalid_header(offset, value):
    data = bytearray(packet())
    data[offset] = value
    with pytest.raises(ValueError):
        decode_audio(data)


@pytest.mark.parametrize("size", [0, 173, 175])
def test_packet_length(size):
    with pytest.raises(ValueError):
        decode_audio(bytes(size))


def test_continuity_wrap_and_new_utterance():
    stream = AudioContinuity()
    stream.accept(decode_audio(packet(65535, 0xFFFFFF00)))
    stream.accept(decode_audio(packet(0, 64)))
    with pytest.raises(ValueError, match="record again"):
        stream.accept(decode_audio(packet(2, 704)))
    stream.reset()
    stream.accept(decode_audio(packet()))


def test_sample_gap_even_when_sequence_matches():
    stream = AudioContinuity()
    stream.accept(decode_audio(packet()))
    with pytest.raises(ValueError):
        stream.accept(decode_audio(packet(1, 321)))


def test_clipping():
    assert np.all(decode_audio(packet(predictor=32767, index=88, code=0x77)).pcm == 32767)
    assert np.all(decode_audio(packet(predictor=-32768, index=88, code=0xFF)).pcm == -32768)


@pytest.mark.parametrize("payload", [100, 180, 244])
def test_unicode_panel_chunk_reassembly(payload):
    panel = {"codex": {"message": "语音输入", "weekly": {"left_pct": 62}}, "activity": list(range(24))}
    chunks = [json.loads(chunk) for chunk in panel_chunks(panel, 999999999, payload)]
    assert [chunk["part"] for chunk in chunks] == list(range(1, len(chunks) + 1))
    assembled = b"".join(bytes.fromhex(chunk["data"]) for chunk in chunks)
    assert json.loads(assembled) == panel


def test_upstream_cpp_encoder_to_windows_decoder(tmp_path):
    root = Path(__file__).resolve().parents[2]
    compiler = root / ".tools/msys64/ucrt64/bin/g++.exe"
    if not compiler.exists():
        pytest.skip("Install the workspace UCRT64 compiler for the cross-language check")
    source = tmp_path / "encoder.cpp"
    source.write_text('''#include "ima_adpcm.h"
#include <cstdio>
int main() {
    ima_adpcm::Encoder encoder;
    short samples[320];
    for (int i=0; i<320; ++i) samples[i] = i * 31 - 4000;
    ima_adpcm::Block block;
    if (!encoder.encode(samples,320,block)) return 1;
    std::printf("%d %u ",block.predictor,block.step_index);
    for (auto value : block.encoded) std::printf("%02x",value);
}
''')
    executable = tmp_path / "encoder.exe"
    environment = os.environ.copy()
    environment["PATH"] = str(compiler.parent) + os.pathsep + environment.get("PATH", "")
    subprocess.run([str(compiler), "-static", "-std=c++17", "-I", str(root / "main/hal"), str(source),
                    str(root / "main/hal/ima_adpcm.cpp"), "-o", str(executable)], check=True, capture_output=True,
                   env=environment)
    predictor, index, encoded = subprocess.check_output([str(executable)], text=True).split()
    data = struct.pack("<HBBIHhBB", 0, 1, 0, 0, 320, int(predictor), int(index), 0) + bytes.fromhex(encoded)
    pcm = decode_audio(data).pcm.astype(float)
    expected = np.arange(320) * 31 - 4000
    assert np.sqrt(np.mean((pcm[40:] - expected[40:]) ** 2)) < 30
