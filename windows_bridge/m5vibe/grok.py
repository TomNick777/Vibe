"""Read the unified weekly pool through the official Grok client's billing route.

No prompts, purchases, resets, browser cookies, or credential copies. Each poll
reads the CLI's current login. Missing/invalid percentages remain unavailable.
"""
import hashlib
import http.client
import json
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

BILLING_URL = "https://cli-chat-proxy.grok.com/v1/billing?format=credits"


class GrokUsageError(RuntimeError):
    def __init__(self, message, *, keep_cache=False):
        super().__init__(message)
        self.keep_cache = keep_cache


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def parse_billing(body, now):
    config = body.get("config") if isinstance(body, dict) else None
    if not isinstance(config, dict) or config.get("isUnifiedBillingUser") is not True:
        raise GrokUsageError("X shared pool not confirmed for this account")
    used = config.get("creditUsagePercent")
    if type(used) not in (int, float) or not 0 <= used <= 100:
        raise GrokUsageError("X usage percentage unavailable")
    period = config.get("currentPeriod") or {}
    if not isinstance(period, dict) or period.get("type") != "USAGE_PERIOD_TYPE_WEEKLY":
        raise GrokUsageError("X weekly period unavailable")
    try:
        start = datetime.fromisoformat(period["start"])
        end = datetime.fromisoformat(period["end"])
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError
        start_epoch, end_epoch = start.timestamp(), end.timestamp()
        if not start_epoch <= now < end_epoch:
            raise ValueError
    except (KeyError, TypeError, ValueError, OverflowError):
        raise GrokUsageError("X weekly period invalid or expired") from None
    return {"left": round(100 - used), "used": used, "reset": end_epoch,
            "period_start": start_epoch, "at": now, "unified": True}


class GrokUsage:
    def __init__(self, auth_path=None):
        self.auth_path = Path(auth_path) if auth_path else Path.home() / ".grok" / "auth.json"
        self.account = None

    def read(self):
        self.account = None
        try:
            auth = json.loads(self.auth_path.read_text(encoding="utf-8"))
            accounts = [v for k, v in auth.items() if k.startswith("https://auth.x.ai::")
                        and isinstance(v, dict) and isinstance(v.get("key"), str)
                        and v["key"] and isinstance(v.get("user_id"), str) and v["user_id"]]
        except (OSError, ValueError, AttributeError):
            raise GrokUsageError("Grok login unavailable; run grok login --oauth") from None
        if len(accounts) != 1:
            raise GrokUsageError("A single Grok CLI account is required")
        account = accounts[0]
        self.account = hashlib.sha256(account["user_id"].encode()).hexdigest()[:20]
        request = urllib.request.Request(BILLING_URL, headers={
            "Authorization": "Bearer " + account["key"], "X-XAI-Token-Auth": "xai-grok-cli",
            "x-userid": account["user_id"], "x-grok-client-version": "1.0.46",
            "x-grok-client-mode": "headless", "Accept": "application/json",
        })
        try:
            with urllib.request.build_opener(NoRedirect()).open(request, timeout=12) as response:
                raw = response.read(1_048_577)
                if len(raw) > 1_048_576:
                    raise GrokUsageError("Grok billing response too large")
                body = json.loads(raw)
        except urllib.error.HTTPError as exc:
            message = ("Grok sign-in required; run grok login --oauth" if exc.code in (401, 403)
                       else f"Grok billing HTTP {exc.code}")
            raise GrokUsageError(message, keep_cache=True) from None
        except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException, EOFError):
            raise GrokUsageError("Grok billing connection unavailable", keep_cache=True) from None
        except ValueError:
            raise GrokUsageError("Grok billing returned invalid JSON") from None
        result = parse_billing(body, datetime.now(UTC).timestamp())
        result["account"] = self.account
        return result
