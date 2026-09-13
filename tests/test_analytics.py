"""Tests for derived analytics and the tools that use them."""

import httpx
import respx

from oura_mcp_server import analytics

BASE = "https://api.ouraring.com/v2"


def _records():
    return {
        "2026-07-01": {"day": "2026-07-01", "sleep_score": 70, "readiness_score": 60, "total_sleep_hours": 6.0},
        "2026-07-02": {"day": "2026-07-02", "sleep_score": 80, "readiness_score": 70, "total_sleep_hours": 7.0},
        "2026-07-03": {"day": "2026-07-03", "sleep_score": 90, "readiness_score": 85, "total_sleep_hours": 8.0},
    }


def test_summarize_metric():
    s = analytics.summarize_metric(_records(), "sleep_score")
    assert s["count"] == 3
    assert s["mean"] == 80.0
    assert s["min"] == 70 and s["max"] == 90
    assert s["change"] == 20.0
    assert s["direction"] == "up"


def test_summarize_missing_metric():
    s = analytics.summarize_metric(_records(), "steps")
    assert s["count"] == 0


def test_pearson_perfect_positive():
    assert analytics.pearson([1, 2, 3], [2, 4, 6]) == 1.0


def test_pearson_undefined_for_constant():
    assert analytics.pearson([1, 1, 1], [2, 4, 6]) is None


def test_correlate_same_day():
    r = analytics.correlate(_records(), "total_sleep_hours", "readiness_score")
    assert r["paired_points"] == 3
    assert r["pearson_r"] > 0.9  # sleep and readiness rise together here


def test_correlate_with_lag():
    # sleep on day D vs readiness on day D+1 -> only two pairs align
    r = analytics.correlate(_records(), "total_sleep_hours", "readiness_score", lag_days=1)
    assert r["paired_points"] == 2
    assert "reading" in r


def test_date_window():
    start, end = analytics.date_window(7, end_date="2026-07-20")
    assert end == "2026-07-20"
    assert start == "2026-07-14"


@respx.mock
async def test_build_daily_records_merges_endpoints(monkeypatch):
    monkeypatch.setenv("OURA_ACCESS_TOKEN", "t")
    from oura_mcp_server.client import OuraClient

    respx.get(f"{BASE}/usercollection/daily_sleep").mock(
        return_value=httpx.Response(200, json={"data": [{"day": "2026-07-01", "score": 75}], "next_token": None})
    )
    respx.get(f"{BASE}/usercollection/daily_readiness").mock(
        return_value=httpx.Response(
            200, json={"data": [{"day": "2026-07-01", "score": 65, "temperature_deviation": 0.2}], "next_token": None}
        )
    )
    respx.get(f"{BASE}/usercollection/daily_activity").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [{"day": "2026-07-01", "score": 88, "steps": 9000, "active_calories": 400}],
                "next_token": None,
            },
        )
    )
    respx.get(f"{BASE}/usercollection/sleep").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "day": "2026-07-01",
                        "type": "long_sleep",
                        "total_sleep_duration": 28800,
                        "efficiency": 92,
                        "lowest_heart_rate": 48,
                        "average_hrv": 55,
                    },
                    {
                        "day": "2026-07-01",
                        "type": "late_nap",
                        "total_sleep_duration": 1800,
                        "lowest_heart_rate": 60,
                        "average_hrv": 40,
                    },
                ],
                "next_token": None,
            },
        )
    )
    client = OuraClient()
    records = await analytics.build_daily_records(client, "2026-07-01", "2026-07-01")
    r = records["2026-07-01"]
    assert r["sleep_score"] == 75
    assert r["readiness_score"] == 65
    assert r["steps"] == 9000
    assert r["total_sleep_hours"] == 8.0  # long_sleep chosen over the nap
    assert r["resting_heart_rate"] == 48
    assert r["average_hrv"] == 55
    await client.aclose()


def test_pick_main_sleep_skips_periods_without_day():
    picked = analytics._pick_main_sleep([{"type": "long_sleep"}, {"day": "2026-07-01", "total_sleep_duration": 10}])
    assert list(picked) == ["2026-07-01"]


def test_correlate_unknown_metric_has_no_pairs():
    r = analytics.correlate(_records(), "sleep_score", "not_a_metric")
    assert r["paired_points"] == 0
    assert "note" in r


def test_correlate_negative_lag():
    # sleep on day D vs readiness on day D-1: two pairs align, ordering reversed
    r = analytics.correlate(_records(), "total_sleep_hours", "readiness_score", lag_days=-1)
    assert r["paired_points"] == 2
    assert r["lag_days"] == -1
    assert "-1 day(s) later" in r["reading"]


def test_interpret_negligible():
    records = {
        "2026-07-01": {"a": 1.0, "b": 2.0},
        "2026-07-02": {"a": 2.0, "b": 1.0},
        "2026-07-03": {"a": 3.0, "b": 3.0},
        "2026-07-04": {"a": 4.0, "b": 1.0},
        "2026-07-05": {"a": 5.0, "b": 2.0},
    }
    r = analytics.correlate(records, "a", "b")
    assert r["interpretation"] == "negligible relationship"
