import asyncio
import json
import urllib.error
from datetime import UTC, datetime
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from m5vibe.bridge import Bridge
from m5vibe.config import Config
from m5vibe.grok import BILLING_URL, GrokUsage, GrokUsageError, NoRedirect, parse_billing
from m5vibe.panel import PanelState

NOW = datetime(2026, 10, 15, 12, tzinfo=UTC).timestamp()


def billing():
    return {"config": {"creditUsagePercent": 10.0, "isUnifiedBillingUser": True,
                       "currentPeriod": {"type": "USAGE_PERIOD_TYPE_WEEKLY",
                                         "start": "2026-10-13T06:22:18.043Z",
                                         "end": "2026-10-20T06:22:18.043Z"}}}


def test_actual_billing_shape_and_reset():
    reading = parse_billing(billing(), NOW)
    assert reading["left"] == 90 and reading["unified"]
    assert datetime.fromtimestamp(reading["reset"], UTC).isoformat() == "2026-10-20T06:22:18.043000+00:00"


@pytest.mark.parametrize("used", [None, True, -1, 101, "10", float("nan"), float("inf")])
def test_invalid_or_missing_percentage_is_not_a_full_ring(used):
    body = billing()
    body["config"]["creditUsagePercent"] = used
    with pytest.raises(GrokUsageError, match="percentage unavailable"):
        parse_billing(body, NOW)


def test_legacy_monthly_and_expired_periods_are_not_shared_weekly():
    body = billing()
    del body["config"]["isUnifiedBillingUser"]
    with pytest.raises(GrokUsageError, match="not confirmed"):
        parse_billing(body, NOW)
    body = billing()
    body["config"]["currentPeriod"]["type"] = "USAGE_PERIOD_TYPE_MONTHLY"
    with pytest.raises(GrokUsageError, match="weekly period"):
        parse_billing(body, NOW)
    with pytest.raises(GrokUsageError, match="invalid or expired"):
        parse_billing(billing(), NOW + 10 * 86400)


def test_provider_uses_only_official_host_and_never_logs_token(tmp_path, monkeypatch):
    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps({"https://auth.x.ai::client": {"key": "secret-test-token", "user_id": "user"}}))

    class Opener:
        def open(self, request, timeout):
            assert request.full_url == BILLING_URL and timeout == 12
            assert request.get_header("Authorization") == "Bearer secret-test-token"
            raise urllib.error.HTTPError(BILLING_URL, 401, "could echo secret-test-token", {}, None)

    monkeypatch.setattr("m5vibe.grok.urllib.request.build_opener", lambda handler: Opener())
    provider = GrokUsage(auth)
    with pytest.raises(GrokUsageError) as error:
        provider.read()
    assert "secret-test-token" not in str(error.value)
    assert error.value.keep_cache and provider.account != "user"
    assert NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.com") is None


def test_no_auth_no_network_and_ambiguous_accounts(tmp_path, monkeypatch):
    def forbidden(*args):
        raise AssertionError("Network must not be called")
    monkeypatch.setattr("m5vibe.grok.urllib.request.build_opener", forbidden)
    auth = tmp_path / "auth.json"
    with pytest.raises(GrokUsageError, match="login unavailable"):
        GrokUsage(auth).read()
    auth.write_text(json.dumps({"https://auth.x.ai::one": {"key": "one", "user_id": "one"},
                                "https://auth.x.ai::two": {"key": "two", "user_id": "two"}}))
    with pytest.raises(GrokUsageError, match="single Grok"):
        GrokUsage(auth).read()


def test_provider_accepts_valid_payload_without_persisting_credentials(tmp_path, monkeypatch):
    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps({"https://auth.x.ai::client": {"key": "secret-test-token", "user_id": "user"}}))
    # Give the mocked live response a period containing the actual test clock.
    now = datetime.now(UTC).timestamp()
    body = billing()
    body["config"]["currentPeriod"]["start"] = datetime.fromtimestamp(now - 3600, UTC).isoformat()
    body["config"]["currentPeriod"]["end"] = datetime.fromtimestamp(now + 3600, UTC).isoformat()

    class Opener:
        def open(self, request, timeout):
            return BytesIO(json.dumps(body).encode())
    monkeypatch.setattr("m5vibe.grok.urllib.request.build_opener", lambda handler: Opener())
    reading = GrokUsage(auth).read()
    assert reading["left"] == 90 and "account" in reading
    assert "secret-test-token" not in json.dumps(reading) and "user_id" not in reading


def test_cache_offline_expiry_and_account_isolation(tmp_path):
    panel = PanelState(tmp_path / "panel.json")
    assert panel.build(NOW)["grokbot"]["weekly"]["left_pct"] is None
    reading = dict(parse_billing(billing(), NOW), account="account-a")
    panel.grok_quota(reading)
    assert panel.build(NOW)["grokbot"]["weekly"]["left_pct"] == 90
    assert not panel.build(NOW)["grokbot"]["stale"]
    assert PanelState(panel.path).build(NOW + 601)["grokbot"]["stale"]
    panel.grok_failure("temporary outage", "account-a", keep_cache=True)
    assert panel.build(NOW)["grokbot"]["stale"]
    assert panel.build(NOW)["grokbot"]["weekly"]["left_pct"] == 90
    assert panel.build(reading["reset"])["grokbot"]["weekly"]["left_pct"] is None
    panel.grok_failure("different account", "account-b", keep_cache=True)
    assert panel.build(NOW)["grokbot"]["weekly"]["left_pct"] is None


@pytest.mark.parametrize("fail_codex", [False, True])
def test_one_provider_failure_does_not_disable_the_other(tmp_path, fail_codex):
    async def scenario():
        bridge = Bridge(Config(), tmp_path / "state.json")
        bridge.codex = SimpleNamespace(process=SimpleNamespace(returncode=None),
                                       limits=AsyncMock(return_value={"rateLimits": {"primary": {
                                           "windowDurationMins": 10080, "usedPercent": 20}}}),
                                       threads=AsyncMock(return_value={"data": []}))
        reading = dict(parse_billing(billing(), NOW), account="account-a")
        def read():
            if not fail_codex:
                raise GrokUsageError("Grok temporarily unavailable")
            return reading
        bridge.grok = SimpleNamespace(read=read, account="account-a")
        if fail_codex:
            bridge.codex.limits.side_effect = RuntimeError("Codex temporarily unavailable")
        await bridge.poll_quota()
        panel = bridge.state.build(NOW)
        if fail_codex:
            assert panel["grokbot"]["weekly"]["left_pct"] == 90
            assert not panel["codex"]["valid"]
        else:
            assert panel["codex"]["weekly"]["left_pct"] == 80
            assert panel["grokbot"]["weekly"]["left_pct"] is None
    asyncio.run(scenario())
