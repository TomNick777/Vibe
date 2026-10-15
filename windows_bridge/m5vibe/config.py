import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Config:
    address: str = ""
    microphone: bool = True
    audio_diagnostics: bool = False  # Read virtual-input levels while recording; no audio files.
    codex_command: str = "codex"
    quota_poll_seconds: int = 300
    grok_usage: bool = True
    grok_auth_file: str = ""  # Empty means the official CLI's ~/.grok/auth.json.
    input_mode: str = "wechat_ime"
    primary_key: int = 0
    primary_modifier: int = 9  # Left Ctrl (0x01) + Left Win (0x08), matching the user's hold shortcut.
    confirm_key: int = 40  # Return
    confirm_modifier: int = 0
    confirm_long_key: int = 40
    confirm_long_modifier: int = 1  # Left Control, rather than macOS Command.
    # Toggle: A starts, A/B stops; hold: release ends capture.
    voice_mode: str = "hold"

    @classmethod
    def load(cls, path: Path):
        config = cls(**json.loads(path.read_text(encoding="utf-8"))) if path.exists() else cls()
        for name in ("primary_key", "primary_modifier", "confirm_key", "confirm_modifier",
                     "confirm_long_key", "confirm_long_modifier"):
            value = getattr(config, name)
            if type(value) is not int or not 0 <= value <= 255:
                raise ValueError(f"{name} must be an integer between 0 and 255")
        if type(config.microphone) is not bool or config.voice_mode not in ("toggle", "hold"):
            raise ValueError("Invalid microphone or voice_mode setting")
        if type(config.audio_diagnostics) is not bool:
            raise ValueError("audio_diagnostics must be a boolean")
        if type(config.grok_usage) is not bool or not isinstance(config.grok_auth_file, str):
            raise ValueError("Invalid Grok usage configuration")
        if config.input_mode not in ("wechat_ime", "typeless"):
            raise ValueError("input_mode must be wechat_ime or typeless")
        if (config.input_mode == "wechat_ime") != (config.voice_mode == "hold"):
            raise ValueError("wechat_ime requires hold mode; typeless requires toggle mode")
        if type(config.quota_poll_seconds) is not int or not 60 <= config.quota_poll_seconds <= 3600:
            raise ValueError("quota_poll_seconds must be between 60 and 3600")
        return config

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2) + "\n", encoding="utf-8")

    def ready_message(self, ready: bool) -> dict:
        return {"type": "bridge_ready", "input_mode": self.input_mode,
                "primary_key": self.primary_key, "primary_modifier": self.primary_modifier,
                "confirm_key": self.confirm_key, "confirm_modifier": self.confirm_modifier,
                "confirm_long_key": self.confirm_long_key, "confirm_long_modifier": self.confirm_long_modifier,
                "confirm_long_action": "Ctrl+Return", "shake_action": "None",
                "microphone_gate_enabled": self.microphone, "microphone_ready": ready}
