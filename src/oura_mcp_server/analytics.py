"""Derived analytics over Oura data: daily records, trends, correlations.

These helpers fetch the underlying endpoints and reduce them to tidy per-day
scalar series so the higher-level MCP tools can summarize, trend, and correlate
without each re-implementing the plumbing. No third-party math deps — Pearson
is computed directly.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

from .client import OuraClient

# Per-day metrics we expose for trends/correlation, and how to read each one.
# Values are pulled in build_daily_records below.
METRIC_KEYS = [
    "sleep_score",
    "readiness_score",
    "activity_score",
    "total_sleep_hours",
    "sleep_efficiency",
    "resting_heart_rate",
    "average_hrv",
    "temperature_deviation",
    "steps",
    "active_calories",
]


def date_window(days: int, end_date: str | None = None) -> tuple[str, str]:
    """Return ``(start, end)`` ISO dates covering ``days`` calendar days ending on ``end_date`` (default today)."""
    try:
        end = date.fromisoformat(end_date) if end_date else date.today()
    except ValueError as exc:
        raise ValueError(f"invalid date '{end_date}': expected YYYY-MM-DD") from exc
    start = end - timedelta(days=max(days - 1, 0))
    return start.isoformat(), end.isoformat()


def _pick_main_sleep(periods: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Reduce sleep periods to one 'main' sleep per day (longest, prefer long_sleep)."""
    by_day: dict[str, dict[str, Any]] = {}
    for p in periods:
        day = p.get("day")
        if not day:
            continue
        current = by_day.get(day)
        better = (
            current is None
            or (p.get("type") == "long_sleep" and current.get("type") != "long_sleep")
            or (p.get("total_sleep_duration") or 0) > (current.get("total_sleep_duration") or 0)
        )
        if better:
            by_day[day] = p
    return by_day


async def build_daily_records(client: OuraClient, start_date: str, end_date: str) -> dict[str, dict[str, Any]]:
    """Return ``{day: {metric: value, ...}}`` across sleep/readiness/activity."""
    params = {"start_date": start_date, "end_date": end_date}
    daily_sleep = await client.get_collection("daily_sleep", params)
    daily_readiness = await client.get_collection("daily_readiness", params)
    daily_activity = await client.get_collection("daily_activity", params)
    sleep_periods = await client.get_collection("sleep", params)

    records: dict[str, dict[str, Any]] = {}

    def rec(day: str) -> dict[str, Any]:
        return records.setdefault(day, {"day": day})

    for d in daily_sleep:
        if d.get("day"):
            rec(d["day"])["sleep_score"] = d.get("score")
    for d in daily_readiness:
        if d.get("day"):
            r = rec(d["day"])
            r["readiness_score"] = d.get("score")
            r["temperature_deviation"] = d.get("temperature_deviation")
    for d in daily_activity:
        if d.get("day"):
            r = rec(d["day"])
            r["activity_score"] = d.get("score")
            r["steps"] = d.get("steps")
            r["active_calories"] = d.get("active_calories")

    for day, s in _pick_main_sleep(sleep_periods).items():
        r = rec(day)
        tsd = s.get("total_sleep_duration")
        r["total_sleep_hours"] = round(tsd / 3600, 2) if tsd else None
        r["sleep_efficiency"] = s.get("efficiency")
        r["resting_heart_rate"] = s.get("lowest_heart_rate")
        r["average_hrv"] = s.get("average_hrv")

    return dict(sorted(records.items()))


def _series(records: dict[str, dict[str, Any]], metric: str) -> list[tuple[str, float]]:
    out: list[tuple[str, float]] = []
    for day, r in records.items():
        v = r.get(metric)
        if isinstance(v, (int, float)):
            out.append((day, float(v)))
    return out


def summarize_metric(records: dict[str, dict[str, Any]], metric: str) -> dict[str, Any]:
    """Mean/min/max, first-vs-last delta, and a direction label for one metric."""
    series = _series(records, metric)
    if not series:
        return {"metric": metric, "count": 0, "note": "no data points in range"}
    values = [v for _, v in series]
    n = len(values)
    mean = sum(values) / n
    first_day, first_val = series[0]
    last_day, last_val = series[-1]
    change = last_val - first_val
    direction = "flat" if abs(change) < 1e-9 else "up" if change > 0 else "down"
    return {
        "metric": metric,
        "count": n,
        "mean": round(mean, 2),
        "min": min(values),
        "max": max(values),
        "latest": {"day": last_day, "value": last_val},
        "earliest": {"day": first_day, "value": first_val},
        "change": round(change, 2),
        "change_vs_mean": round(last_val - mean, 2),
        "direction": direction,
    }


def pearson(xs: list[float], ys: list[float]) -> float | None:
    """Pearson correlation coefficient, or None if undefined."""
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx == 0 or vy == 0:
        return None
    return cov / math.sqrt(vx * vy)


def _interpret_r(r: float) -> str:
    a = abs(r)
    strength = (
        "negligible"
        if a < 0.1
        else "weak"
        if a < 0.3
        else "moderate"
        if a < 0.5
        else "strong"
        if a < 0.7
        else "very strong"
    )
    if a < 0.1:
        return "negligible relationship"
    return f"{strength} {'positive' if r > 0 else 'negative'} relationship"


def correlate(records: dict[str, dict[str, Any]], metric_a: str, metric_b: str, lag_days: int = 0) -> dict[str, Any]:
    """Correlate metric_a on day D with metric_b on day D+lag_days."""
    a_by_day = dict(_series(records, metric_a))
    b_by_day = dict(_series(records, metric_b))
    xs: list[float] = []
    ys: list[float] = []
    for day, a_val in a_by_day.items():
        target = (date.fromisoformat(day) + timedelta(days=lag_days)).isoformat()
        if target in b_by_day:
            xs.append(a_val)
            ys.append(b_by_day[target])
    r = pearson(xs, ys)
    result = {
        "metric_a": metric_a,
        "metric_b": metric_b,
        "lag_days": lag_days,
        "paired_points": len(xs),
    }
    if r is None:
        result["note"] = "not enough overlapping data (need >=2 paired points with variance)"
    else:
        result["pearson_r"] = round(r, 3)
        result["interpretation"] = _interpret_r(r)
        if lag_days:
            result["reading"] = f"{metric_a} shows a {_interpret_r(r)} with {metric_b} {lag_days} day(s) later"
    return result
