import json
from datetime import UTC, datetime
from pathlib import Path


def quota_window(limits: dict, minutes: int):
    buckets = limits.get("rateLimitsByLimitId") or {}
    bucket = buckets.get("codex", limits.get("rateLimits") or {})
    for key in ("primary", "secondary"):
        window = bucket.get(key)
        if not isinstance(window, dict) or window.get("windowDurationMins") != minutes:
            continue
        used = window.get("usedPercent")
        if type(used) not in (int, float) or not 0 <= used <= 100:
            continue
        reset = window.get("resetsAt")
        return {"left": round(100 - used), "reset": reset}
    return None


def weekly_window(limits: dict):
    return quota_window(limits, 10080)


class PanelState:
    def __init__(self, path: Path):
        self.path = path
        try:
            self.data = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            self.data = {}

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.data, separators=(",", ":")), encoding="utf-8")
        temporary.replace(self.path)

    def quota(self, limits, now):
        five = quota_window(limits, 300)
        if five:
            self.data.update(five_left=five["left"], five_reset=five["reset"], five_at=now)
        else:
            self.data.pop("five_left", None)
        window = weekly_window(limits)
        if window:
            # UTC midnight is Beijing 08:00, matching the upstream day boundary.
            day = datetime.fromtimestamp(now, UTC).date().isoformat()
            if self.data.get("day") != day:
                self.data.update(day=day, today=0, baseline=window["left"], last_left=window["left"],
                                 # Only a continuously running bridge can establish a day boundary baseline.
                                 baseline_known=self.data.get("quota_at", 0) >= now - 600)
            elif self.data.get("reset") == window["reset"]:
                self.data["today"] += max(0, self.data.get("last_left", window["left"]) - window["left"])
            self.data.update(left=window["left"], last_left=window["left"], reset=window["reset"], quota_at=now)
        self.save()
        return window

    def activity(self, now, seconds=0, starts=0, operations=0):
        key = str(int(now // 600))
        activity = self.data.setdefault("activity", {})
        bucket = activity.setdefault(key, {"seconds": 0, "starts": 0, "operations": 0})
        bucket["seconds"] += seconds
        bucket["starts"] += starts
        bucket["operations"] += operations
        self.data["activity"] = {k: v for k, v in activity.items() if int(k) >= int(now // 600) - 23}

    def grok_quota(self, reading):
        self.data["grok_shared"] = reading
        self.data.pop("grok_error", None)
        self.save()

    def grok_failure(self, message, account=None, keep_cache=False):
        if not keep_cache or not account or self.data.get("grok_shared", {}).get("account") != account:
            self.data.pop("grok_shared", None)
        self.data["grok_error"] = message
        self.save()

    def build(self, now, threads=None, error="", threads_at=None):
        quota_at = self.data.get("quota_at", 0)
        valid = "left" in self.data
        stale = bool(error) or now - quota_at > 600
        reset = self.data.get("reset")
        hours = max(0, int((reset - now) // 3600)) if isinstance(reset, int) else None
        buckets = []
        for index in range(int(now // 600) - 23, int(now // 600) + 1):
            bucket = self.data.get("activity", {}).get(str(index), {})
            buckets.append(min(1, 0.7 * bucket.get("seconds", 0) / 600
                               + 0.3 * min(1, bucket.get("starts", 0) / 10)))
        current = (threads or [{}])[0]
        if threads_at is not None and now - threads_at > 30:
            threads = []
            current = {}
        state = current.get("status", {}).get("type", "notLoaded")
        five_reset = self.data.get("five_reset")
        five_minutes = max(0, int((five_reset - now) // 60)) if isinstance(five_reset, int) else None
        five_reset_label = f"{five_minutes // 60}h {five_minutes % 60}m" if five_minutes is not None else "--"
        # Local app-server schema: ThreadActiveFlag explicitly names these states.
        needs_confirmation = any(
            thread.get("status", {}).get("type") == "active"
            and any(flag in ("waitingOnApproval", "waitingOnUserInput")
                    for flag in thread.get("status", {}).get("activeFlags", []))
            for thread in (threads or [])
        )
        grok = self.data.get("grok_shared", {})
        grok_current = grok.get("unified") is True and grok.get("period_start", now + 1) <= now < grok.get("reset", 0)
        grok_minutes = max(0, int((grok.get("reset", now) - now) // 60))
        grok_stale = bool(self.data.get("grok_error")) or now - grok.get("at", 0) > 600
        return {"server_epoch": int(now), "grokbot": {
            "source": "X shared weekly", "unified": grok_current,
            "stale": grok_stale or not grok_current,
            "weekly": {"left_pct": grok.get("left") if grok_current else None,
                       "reset_in": f"{grok_minutes // 1440}d {grok_minutes % 1440 // 60}h {grok_minutes % 60}m"
                       if grok_current else "--"}}, "codex": {
            "status": "ok" if valid else "unknown", "valid": valid, "stale": stale,
            "source": "Windows BLE", "updated_at": datetime.fromtimestamp(quota_at, UTC).isoformat(),
            "host": {"name": "Windows"},
            "weekly": {"left_pct": self.data.get("left"),
                       "reset_in": f"{hours // 24}d {hours % 24}h" if hours is not None else "--",
                       "daily_tracking": {"day_start_left_pct": self.data.get("baseline", -1)
                                          if self.data.get("baseline_known") else -1,
                                          "today_used_pct_points": self.data.get("today", 0)}},
            "processing": any(thread.get("status", {}).get("type") == "active" for thread in (threads or [])),
            "needs_confirmation": needs_confirmation,
            "five_hour": {"left_pct": self.data.get("five_left"),
                          "stale": bool(error) or now - self.data.get("five_at", 0) > 600,
                          "reset_in": five_reset_label},
            "openwatcher_home": {"session_title": "State unavailable" if state == "notLoaded" else state,
                                 "model_label": "--", "reasoning_label": "--",
                                 "activity_label": "Last 4h", "activity_live": True,
                                 "activity_buckets": buckets},
            "message": "Quota unavailable" if not valid else ("Quota stale" if stale else "Quota synced"),
        }}
