import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from . import __version__
from .config import Config
from .panel import weekly_window


async def doctor(config):
    import sounddevice as sd

    from .audio import cable_devices
    from .codex import CodexRPC
    from .grok import GrokUsage, GrokUsageError
    result = {"platform": sys.platform, "audio": "unavailable", "codex": "unavailable"}
    try:
        output, capture = cable_devices()
        result.update(audio="ready", virtual_output=sd.query_devices(output)["name"],
                      virtual_input=sd.query_devices(capture)["name"])
    except RuntimeError as exc:
        result["audio_message"] = str(exc)
    codex = CodexRPC(config.codex_command)
    try:
        await codex.start()
        result["codex"] = "ready" if weekly_window(await codex.limits()) else "weekly quota unavailable"
        threads = await codex.threads()
        result["stored_threads_readable"] = isinstance(threads.get("data"), list)
        result["keyboard_hid"] = "standard voice shortcuts; verify after flashing"
    except (RuntimeError, OSError, TimeoutError):
        result["codex_message"] = "Codex CLI login or app-server check required"
    finally:
        await codex.close()
    if config.grok_usage:
        try:
            reading = await asyncio.to_thread(GrokUsage(config.grok_auth_file).read)
            result.update(grok="ready", x_shared_left_pct=reading["left"],
                          x_shared_reset=reading["reset"], x_unified=reading["unified"])
        except GrokUsageError as exc:
            result.update(grok="unavailable", grok_message=str(exc))
    else:
        result["grok"] = "disabled"
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["codex"] == "ready" and (result["audio"] == "ready" or not config.microphone) else 2


async def execute(args):
    config = Config.load(args.config)
    if args.command == "init":
        if not args.config.exists():
            config.save(args.config)
        print(f"Configuration: {args.config.resolve()}")
        return 0
    if args.command == "doctor":
        return await doctor(config)
    if args.command == "scan":
        from .bridge import discover
        devices = await discover(config.address)
        print(json.dumps([{"name": device.name, "address": device.address} for device in devices],
                         indent=2, ensure_ascii=False))
        return 0
    from .bridge import Bridge
    await Bridge(config, args.config.parent / ".state" / "panel.json").run()
    return 0


def main():
    parser = argparse.ArgumentParser(description="Vibe Windows BLE voice and quota bridge")
    parser.add_argument("--version", action="version", version=f"Vibe {__version__}")
    parser.add_argument("command", choices=("init", "doctor", "scan", "run"), nargs="?", default="run")
    parser.add_argument("--config", type=Path, default=Path(__file__).resolve().parents[1] / "config.local.json")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if sys.platform != "win32":
        parser.error("This companion runs natively on Windows")
    # Establish MTA before importing PortAudio or PyWinRT; a console has no
    # Windows GUI message pump for STA Bluetooth callbacks.
    import ctypes
    result = ctypes.windll.ole32.CoInitializeEx(None, 0)
    if result not in (0, 1):
        parser.error("Windows COM MTA initialization failed")
    from bleak.exc import BleakError
    try:
        return asyncio.run(execute(args))
    except KeyboardInterrupt:
        return 0
    except (ValueError, RuntimeError, BleakError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
