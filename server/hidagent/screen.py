"""The phone's screen, received over AirPlay mirroring by UxPlay, as JPEG frames."""

import asyncio
import logging
import os
import socket
import subprocess
import threading
import time

log = logging.getLogger(__name__)


class JpegFrames:
    """Frame a JPEG byte stream independently of pipe/TCP packet boundaries."""

    def __init__(self, limit: int = 8 << 20):
        self.buffer = b""
        self.limit = limit

    def feed(self, chunk: bytes) -> list[bytes]:
        self.buffer += chunk
        frames = []
        while True:
            start = self.buffer.find(b"\xff\xd8")
            if start < 0:
                self.buffer = self.buffer[-1:] if self.buffer.endswith(b"\xff") else b""
                break
            self.buffer = self.buffer[start:]
            end = self.buffer.find(b"\xff\xd9", 2)
            if end < 0:
                if len(self.buffer) > self.limit:
                    self.buffer = b""
                break
            if end + 2 <= self.limit:
                frames.append(self.buffer[:end + 2])
            self.buffer = self.buffer[end + 2:]
        return frames


class Screen:
    """Runs UxPlay with a GStreamer sink that writes JPEGs into a pipe; keeps the latest one."""

    def __init__(self, name: str = "iPhone Agent", fps: int = 8, quality: int = 75):
        self.name, self.fps, self.quality = name, fps, quality
        self.frame: bytes | None = None
        self.updated = 0.0
        self._proc = None
        self._clients_at, self._clients_n = 0.0, None
        self._stopping = False
        self._thread = None
        self._connection = None
        self._listener = None
        self.executable = os.environ.get("UXPLAY_BINARY", "uxplay")

    def start(self) -> None:
        self._thread = threading.Thread(target=self._supervise, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stopping = True
        if self._proc:
            self._proc.terminate()
        for endpoint in (self._connection, self._listener):
            if endpoint:
                try:
                    endpoint.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                endpoint.close()
        if self._thread:
            self._thread.join(timeout=3)

    def _arguments(self, sink: str) -> list[str]:
        return [self.executable, "-n", self.name, "-nh", "-a", "-reset", "0", "-vs", sink]

    def _jpeg_pipeline(self) -> str:
        return (f"videorate drop-only=true ! video/x-raw,framerate={self.fps}/1 ! "
                f"jpegenc quality={self.quality} ! ")

    def _supervise(self) -> None:
        """Keep UxPlay running: it exits on some disconnects, so restart it every time."""
        while not self._stopping:
            try:
                if os.name == "nt":
                    self._run_tcp()
                else:
                    self._run_pipe()
            except OSError as error:
                if not self._stopping:
                    log.error("AirPlay receiver error: %s", error)
            finally:
                if self._proc and self._proc.poll() is None:
                    self._proc.terminate()
                    try:
                        self._proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        self._proc.kill()
                        self._proc.wait()
                self.frame = None
            if not self._stopping:
                log.warning("AirPlay receiver stopped, restarting")
                time.sleep(1)

    def _run_pipe(self) -> None:
        read_fd, write_fd = os.pipe()
        try:
            sink = self._jpeg_pipeline() + f"fdsink fd={write_fd}"
            self._proc = subprocess.Popen(self._arguments(sink), pass_fds=(write_fd,))
        except OSError:
            os.close(read_fd)
            raise
        finally:
            os.close(write_fd)
        self._read(read_fd)

    def _run_tcp(self) -> None:
        # Windows cannot pass a POSIX file descriptor to UxPlay. GStreamer's
        # TCP sink feeds the same JPEG parser over a loopback-only connection.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            self._listener = listener
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            listener.settimeout(0.25)
            port = listener.getsockname()[1]
            sink = self._jpeg_pipeline() + f"tcpclientsink host=127.0.0.1 port={port} sync=false"
            self._proc = subprocess.Popen(self._arguments(sink), creationflags=subprocess.CREATE_NO_WINDOW)
            log.info("AirPlay receiver '%s' started (pid %d)", self.name, self._proc.pid)
            try:
                while not self._stopping and self._proc.poll() is None:
                    try:
                        connection, _ = listener.accept()
                    except TimeoutError:
                        continue
                    with connection:
                        self._connection = connection
                        connection.settimeout(0.25)
                        self._read_socket(connection)
                        self.frame = None
                    self._connection = None
            finally:
                self._listener = self._connection = None

    def _read_socket(self, connection: socket.socket) -> None:
        decoder = JpegFrames()
        while not self._stopping:
            try:
                chunk = connection.recv(1 << 16)
            except TimeoutError:
                if self._proc.poll() is not None:
                    return
                continue
            except OSError:
                if self._stopping:
                    return
                raise
            if not chunk:
                return
            for frame in decoder.feed(chunk):
                self.frame, self.updated = frame, time.time()

    @property
    def live(self) -> bool:
        running = self._proc is not None and self._proc.poll() is None
        if not running or self.frame is None:
            return False
        clients = self._clients()
        if clients is not None:  # Linux: is a phone connected to UxPlay right now?
            return clients > 0
        return time.time() - self.updated < 90  # elsewhere: AirPlay sends no frames while the screen is still

    def _clients(self) -> int | None:
        """Established TCP connections of the UxPlay process (a mirroring phone keeps some open).

        Read from /proc, cached for a second; None where /proc is not available (e.g. macOS).
        """
        if time.time() - self._clients_at < 1:
            return self._clients_n
        try:
            fds = os.listdir(f"/proc/{self._proc.pid}/fd")
            inodes = set()
            for fd in fds:
                link = os.readlink(f"/proc/{self._proc.pid}/fd/{fd}")
                if link.startswith("socket:["):
                    inodes.add(link[8:-1])
            n = 0
            for table in ("/proc/net/tcp", "/proc/net/tcp6"):
                with open(table) as f:
                    for row in f.readlines()[1:]:
                        cols = row.split()
                        n += cols[3] == "01" and cols[9] in inodes  # 01 = ESTABLISHED
        except OSError:
            n = None
        self._clients_at, self._clients_n = time.time(), n
        return n

    @property
    def aspect(self) -> float:
        """Frame width / height, read from the JPEG header (portrait iPhone as a fallback)."""
        f = self.frame or b""
        i = f.find(b"\xff\xc0")  # baseline start-of-frame: ... height(2) width(2)
        if i < 0 or len(f) < i + 9:
            return 9 / 19.5
        return int.from_bytes(f[i + 7:i + 9], "big") / int.from_bytes(f[i + 5:i + 7], "big")

    async def settled(self, quiet: float = 0.35, least: float = 0.25, most: float = 4) -> None:
        """Wait until the screen stops changing (AirPlay only sends frames on change)."""
        started = time.time()
        await asyncio.sleep(least)
        while time.time() - self.updated < quiet and time.time() - started < most:
            await asyncio.sleep(0.1)

    async def fresh(self, since: float, timeout: float = 0.8) -> bytes | None:
        """The first frame received after `since`, or None if none arrives in time."""
        deadline = time.time() + timeout
        while self.updated <= since:
            if time.time() > deadline:
                return None
            await asyncio.sleep(0.02)
        return self.frame

    def _read(self, fd: int) -> None:
        decoder = JpegFrames()
        with os.fdopen(fd, "rb", buffering=0) as pipe:
            while chunk := pipe.read(1 << 16):
                for frame in decoder.feed(chunk):
                    self.frame, self.updated = frame, time.time()
