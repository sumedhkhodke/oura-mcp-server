"""End-to-end tests for the analytics MCP tools with a mocked API."""

import httpx
import pytest
import respx

BASE = "https://api.ouraring.com/v2"


@pytest.fixture
def server(monkeypatch):
    monkeypatch.setenv("OURA_ACCESS_TOKEN", "test-token")
    import oura_mcp_server.server as srv

    srv._client = None  # reset singleton so it picks up the env token
    return srv


def _mock_daily(day, sleep=80, readiness=75, activity=85):
    respx.get(f"{BASE}/usercollection/daily_sleep").mock(
        return_value=httpx.Response(200, json={"data": [{"day": day, "score": sleep}], "next_token": None})
    )
    respx.get(f"{BASE}/usercollection/daily_readiness").mock(
        return_value=httpx.Response(200, json={"data": [{"day": day, "score": readiness}], "next_token": None})
    )
    respx.get(f"{BASE}/usercollection/daily_activity").mock(
        return_value=httpx.Response(
            200, json={"data": [{"day": day, "score": activity, "steps": 8000}], "next_token": None}
        )
    )
    respx.get(f"{BASE}/usercollection/sleep").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "day": day,
                        "type": "long_sleep",
                        "total_sleep_duration": 25200,
                        "lowest_heart_rate": 50,
                        "average_hrv": 60,
                    }
                ],
                "next_token": None,
            },
        )
    )


@respx.mock
async def test_daily_briefing(server):
    _mock_daily("2026-07-10")
    out = await server.get_daily_briefing(start_date="2026-07-10", end_date="2026-07-10")
    assert out["days"] == 1
    row = out["briefing"][0]
    assert row["sleep_score"] == 80
    assert row["resting_heart_rate"] == 50
    assert row["total_sleep_hours"] == 7.0


@respx.mock
async def test_metric_trend(server):
    _mock_daily("2026-07-10")
    out = await server.get_metric_trend(metric="readiness_score", days=3, end_date="2026-07-10")
    assert out["metric"] == "readiness_score"
    assert out["count"] == 1
    assert out["mean"] == 75.0


async def test_metric_trend_rejects_bad_metric(server):
    out = await server.get_metric_trend(metric="not_a_metric")
    assert "error" in out
    assert "valid_metrics" in out


@respx.mock
async def test_correlation_tool(server):
    _mock_daily("2026-07-10")
    out = await server.get_metric_correlation(
        metric_a="total_sleep_hours", metric_b="readiness_score", days=1, end_date="2026-07-10"
    )
    # only one day of data -> not enough pairs for a coefficient
    assert out["paired_points"] == 1
    assert "note" in out


def test_default_dates_matches_analytics_window(server):
    from oura_mcp_server import analytics

    dates = server._default_dates(None, "2026-07-20")
    start, end = analytics.date_window(7, "2026-07-20")
    assert (dates["start_date"], dates["end_date"]) == (start, end) == ("2026-07-14", "2026-07-20")
    assert server._default_dates("2026-07-01", "2026-07-20") == {"start_date": "2026-07-01", "end_date": "2026-07-20"}


async def test_daily_sleep_rejects_bad_date(server):
    out = await server.get_daily_sleep(start_date="not-a-date")
    assert "error" in out and "not-a-date" in out["error"]
    out = await server.get_daily_sleep(end_date="2026-13-45")
    assert "error" in out


async def test_daily_briefing_rejects_bad_date(server):
    out = await server.get_daily_briefing(end_date="nope")
    assert "error" in out


async def test_trend_and_correlation_reject_bad_end_date(server):
    assert "error" in await server.get_metric_trend(metric="sleep_score", end_date="nope")
    assert "error" in await server.get_metric_correlation(metric_a="sleep_score", metric_b="steps", end_date="nope")


@respx.mock
async def test_heart_rate_accepts_trailing_z(server):
    route = respx.get(f"{BASE}/usercollection/heartrate").mock(
        return_value=httpx.Response(200, json={"data": [{"bpm": 60}], "next_token": None})
    )
    out = await server.get_heart_rate(start_datetime="2026-07-10T00:00:00Z", end_datetime="2026-07-11T00:00:00Z")
    assert out["count"] == 1
    assert route.calls[0].request.url.params["start_datetime"] == "2026-07-10T00:00:00Z"


@respx.mock
async def test_heart_rate_default_start_from_z_end(server):
    respx.get(f"{BASE}/usercollection/heartrate").mock(
        return_value=httpx.Response(200, json={"data": [], "next_token": None})
    )
    out = await server.get_heart_rate(end_datetime="2026-07-11T00:00:00Z")
    assert out["start_datetime"] == "2026-07-10T00:00:00+00:00"


async def test_heart_rate_rejects_bad_datetime(server):
    out = await server.get_heart_rate(start_datetime="yesterday")
    assert "error" in out and "yesterday" in out["error"]


def test_parse_datetime_helper(server):
    from datetime import timezone

    parsed = server._parse_datetime("2026-07-10T00:00:00Z")
    assert parsed.tzinfo is not None and parsed.utcoffset() == timezone.utc.utcoffset(None)
    with pytest.raises(ValueError, match="bogus"):
        server._parse_datetime("bogus")


DATE_TOOLS = [
    ("get_daily_sleep", "daily_sleep"),
    ("get_daily_readiness", "daily_readiness"),
    ("get_daily_activity", "daily_activity"),
    ("get_sleep_periods", "sleep"),
    ("get_daily_spo2", "daily_spo2"),
    ("get_daily_stress", "daily_stress"),
    ("get_daily_resilience", "daily_resilience"),
    ("get_daily_cardiovascular_age", "daily_cardiovascular_age"),
    ("get_vo2_max", "vO2_max"),
    ("get_workouts", "workout"),
    ("get_sessions", "session"),
    ("get_sleep_time", "sleep_time"),
    ("get_rest_mode_periods", "rest_mode_period"),
    ("get_tags", "enhanced_tag"),
]


@respx.mock
@pytest.mark.parametrize(("tool", "endpoint"), DATE_TOOLS)
async def test_date_ranged_tools_hit_their_endpoint(server, tool, endpoint):
    route = respx.get(f"{BASE}/usercollection/{endpoint}").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "x"}], "next_token": None})
    )
    out = await getattr(server, tool)(start_date="2026-07-01", end_date="2026-07-02")
    assert out["endpoint"] == endpoint
    assert out["count"] == 1
    assert route.calls[0].request.url.params["start_date"] == "2026-07-01"


@respx.mock
async def test_collection_error_branch(server):
    respx.get(f"{BASE}/usercollection/daily_sleep").mock(return_value=httpx.Response(500, text="down"))
    out = await server.get_daily_sleep(start_date="2026-07-01", end_date="2026-07-02")
    assert out["endpoint"] == "daily_sleep"
    assert "500" in out["error"]


@respx.mock
async def test_personal_info(server):
    respx.get(f"{BASE}/usercollection/personal_info").mock(return_value=httpx.Response(200, json={"age": 30}))
    assert await server.get_personal_info() == {"age": 30}
    respx.get(f"{BASE}/usercollection/personal_info").mock(return_value=httpx.Response(403))
    out = await server.get_personal_info()
    assert out["endpoint"] == "personal_info" and "403" in out["error"]


@respx.mock
async def test_ring_configuration(server):
    respx.get(f"{BASE}/usercollection/ring_configuration").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "ring"}], "next_token": None})
    )
    out = await server.get_ring_configuration()
    assert out == {"endpoint": "ring_configuration", "count": 1, "data": [{"id": "ring"}]}
    respx.get(f"{BASE}/usercollection/ring_configuration").mock(return_value=httpx.Response(429))
    out = await server.get_ring_configuration()
    assert out["endpoint"] == "ring_configuration" and "rate limit" in out["error"]


@respx.mock
async def test_heart_rate_defaults_to_last_24h(server):
    from datetime import datetime, timedelta

    route = respx.get(f"{BASE}/usercollection/heartrate").mock(
        return_value=httpx.Response(200, json={"data": [], "next_token": None})
    )
    out = await server.get_heart_rate()
    params = route.calls[0].request.url.params
    start = datetime.fromisoformat(params["start_datetime"])
    end = datetime.fromisoformat(params["end_datetime"])
    assert end - start == timedelta(days=1)
    assert out["start_datetime"] == params["start_datetime"]
    respx.get(f"{BASE}/usercollection/heartrate").mock(return_value=httpx.Response(500))
    assert "error" in await server.get_heart_rate()


@respx.mock
async def test_briefing_trend_and_correlation_api_errors(server):
    respx.get(url__regex=rf"{BASE}/usercollection/.*").mock(return_value=httpx.Response(500))
    assert "error" in await server.get_daily_briefing(start_date="2026-07-10", end_date="2026-07-10")
    assert "error" in await server.get_metric_trend(metric="sleep_score", days=1, end_date="2026-07-10")
    assert "error" in await server.get_metric_correlation(
        metric_a="sleep_score", metric_b="steps", days=1, end_date="2026-07-10"
    )


async def test_correlation_rejects_bad_metric(server):
    out = await server.get_metric_correlation(metric_a="sleep_score", metric_b="nope")
    assert "error" in out and "valid_metrics" in out


def test_prompts_render(server):
    assert "last 3 days" in server.analyze_recovery(days=3)
    assert "get_daily_briefing" in server.weekly_review()
    assert "get_metric_correlation" in server.sleep_optimization()


@pytest.fixture
def webhook_env(monkeypatch):
    monkeypatch.setenv("OURA_CLIENT_ID", "cid")
    monkeypatch.setenv("OURA_CLIENT_SECRET", "sec")


WEBHOOK_BASE = f"{BASE}/webhook/subscription"


@respx.mock
async def test_webhook_tools_success(server, webhook_env):
    respx.get(WEBHOOK_BASE).mock(return_value=httpx.Response(200, json=[{"id": "s1"}]))
    respx.post(WEBHOOK_BASE).mock(return_value=httpx.Response(201, json={"id": "s2"}))
    respx.put(f"{WEBHOOK_BASE}/renew/s1").mock(return_value=httpx.Response(200, json={"id": "s1"}))
    respx.delete(f"{WEBHOOK_BASE}/s1").mock(return_value=httpx.Response(204))
    assert await server.list_webhook_subscriptions() == {"result": [{"id": "s1"}]}
    created = await server.create_webhook_subscription("https://cb.example/hook", "vtok", "create", "daily_sleep")
    assert created == {"result": {"id": "s2"}}
    assert await server.renew_webhook_subscription("s1") == {"result": {"id": "s1"}}
    assert await server.delete_webhook_subscription("s1") == {"result": {"status": "ok"}}


@respx.mock
async def test_webhook_tool_api_error(server, webhook_env):
    respx.get(WEBHOOK_BASE).mock(return_value=httpx.Response(500, text="oops"))
    out = await server.list_webhook_subscriptions()
    assert "500" in out["error"]


async def test_create_webhook_subscription_validation(server, webhook_env):
    out = await server.create_webhook_subscription("https://cb.example/hook", "vtok", "explode", "daily_sleep")
    assert "event_type" in out["error"]
    out = await server.create_webhook_subscription("https://cb.example/hook", "vtok", "create", "unicorns")
    assert "data_type" in out["error"]


def test_run_stdio(server, monkeypatch):
    calls = []
    monkeypatch.setattr(server.mcp, "run", lambda **kwargs: calls.append(kwargs))
    server.run()
    assert calls == [{}]
