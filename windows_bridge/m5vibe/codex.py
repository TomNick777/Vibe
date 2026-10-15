"""Read-only Codex app-server RPC. Authentication stays with Codex."""
import asyncio
import json
import shutil
import subprocess
from contextlib import suppress

from . import __version__


class CodexRPC:
    def __init__(self, command="codex"):
        self.command = command
        self.process = None
        self.reader = None
        self.pending = {}
        self.next_id = 0

    async def start(self):
        executable = shutil.which(self.command)
        if not executable:
            raise RuntimeError("Codex CLI not found; set codex_command in config.local.json")
        self.process = await asyncio.create_subprocess_exec(
            executable, "app-server", "--listen", "stdio://", stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self.reader = asyncio.create_task(self._read())
        try:
            await self.request("initialize", {"clientInfo": {"name": "m5_stopwatch_windows",
                                                              "title": "Vibe Bridge", "version": __version__}})
            await self._write({"method": "initialized"})
        except BaseException:
            await self.close()
            raise

    async def _write(self, message):
        self.process.stdin.write(json.dumps(message, separators=(",", ":")).encode() + b"\n")
        await self.process.stdin.drain()

    async def request(self, method, params=None, timeout=20):
        self.next_id += 1
        request_id = self.next_id
        future = asyncio.get_running_loop().create_future()
        self.pending[request_id] = future
        try:
            message = {"id": request_id, "method": method}
            if params is not None:
                message["params"] = params
            await self._write(message)
            return await asyncio.wait_for(future, timeout)
        finally:
            self.pending.pop(request_id, None)

    async def _read(self):
        try:
            while line := await self.process.stdout.readline():
                message = json.loads(line)
                if "method" in message:
                    # This bridge never starts turns or accepts side-effect requests.
                    if "id" in message:
                        await self._write({"id": message["id"], "error": {"code": -32601,
                                                                                 "message": "Read-only client"}})
                    continue
                future = self.pending.get(message.get("id"))
                if future and not future.done():
                    if "error" in message:
                        future.set_exception(RuntimeError(f"Codex RPC error ({message['error'].get('code')})"))
                    else:
                        future.set_result(message.get("result", {}))
        except (ValueError, OSError):
            pass
        finally:
            for future in tuple(self.pending.values()):
                if not future.done():
                    future.set_exception(RuntimeError("Codex app-server disconnected"))

    async def limits(self):
        return await self.request("account/rateLimits/read")

    async def threads(self):
        return await self.request("thread/list", {"limit": 4, "sortKey": "updated_at",
                                                  "sourceKinds": ["appServer", "cli", "vscode"],
                                                  "useStateDbOnly": True})

    async def close(self):
        if self.process is not None:
            if self.process.returncode is None:
                with suppress(ProcessLookupError):
                    self.process.terminate()
                try:
                    await asyncio.wait_for(self.process.wait(), 5)
                except TimeoutError:
                    self.process.kill()
                    await self.process.wait()
            self.process = None
        if self.reader is not None:
            self.reader.cancel()
            with suppress(asyncio.CancelledError):
                await self.reader
            self.reader = None
