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
