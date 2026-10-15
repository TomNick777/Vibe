"""Windows AirPlay byte transport and shutdown without a physical phone."""
import io
import socket
import threading
from unittest.mock import Mock

from PIL import Image

from hidagent.screen import JpegFrames, Screen


def jpeg(color):
    buffer = io.BytesIO()
    Image.new("RGB", (32, 64), color).save(buffer, "JPEG")
    return buffer.getvalue()


def test_frames_split_at_every_byte_and_combined():
    first, second = jpeg("red"), jpeg("blue")
    parser = JpegFrames()
    result = []
    for byte in b"junk" + first + second:
        result.extend(parser.feed(bytes([byte])))
    assert result == [first, second]
    assert JpegFrames().feed(first + second) == [first, second]


def test_incomplete_or_oversize_frames_do_not_grow_unbounded():
    parser = JpegFrames(limit=100)
    assert parser.feed(b"\xff\xd8" + b"x" * 200) == []
    assert parser.buffer == b""
    assert parser.feed(b"x" * 10000) == []
    assert parser.buffer == b""
    assert parser.feed(b"\xff") == []
    assert parser.feed(b"\xd8data\xff\xd9") == [b"\xff\xd8data\xff\xd9"]


def test_socket_transport_delivers_real_jpeg_and_exits_on_disconnect():
    screen = Screen()
    screen._proc = Mock()
    screen._proc.poll.return_value = None
    receiver, sender = socket.socketpair()
    with receiver, sender:
        receiver.settimeout(0.25)
        thread = threading.Thread(target=screen._read_socket, args=(receiver,))
        thread.start()
        frame = jpeg("green")
        sender.sendall(frame[:7])
        sender.sendall(frame[7:])
        sender.shutdown(socket.SHUT_WR)
        thread.join(timeout=2)
        assert not thread.is_alive()
        assert screen.frame == frame
        assert screen.updated > 0
        assert screen.aspect == 0.5


def test_stop_interrupts_idle_windows_receiver():
    screen = Screen()
    screen._proc = Mock()
    screen._proc.poll.return_value = None
    receiver, sender = socket.socketpair()
    with receiver, sender:
        receiver.settimeout(0.25)
        screen._connection = receiver
        screen._thread = threading.Thread(target=screen._read_socket, args=(receiver,))
        screen._thread.start()
        screen.stop()
        assert not screen._thread.is_alive()
        screen._proc.terminate.assert_called_once()
