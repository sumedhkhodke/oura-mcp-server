"""FastMCP server exposing the Oura Ring v2 API as MCP tools.

Each tool maps to an Oura ``usercollection`` endpoint. Date-range tools default
to the last 7 days (24 hours for heart rate) when no dates are given, so an
assistant can ask "how did I sleep this week?" without computing dates.

Dates are ISO ``YYYY-MM-DD``. Heart rate uses ISO 8601 datetimes.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastmcp import FastMCP

from .client import OuraClient, OuraError

mcp = FastMCP(
    name="oura-mcp-server",
    instructions=(
        "Access the user's Oura Ring health data (sleep, readiness, activity, "
        "HRV, heart rate, SpO2, stress, resilience, workouts, and more) via the "
        "Oura v2 API. Date-range tools default to the last 7 days when dates are "
        "omitted. All data is read-only."
    ),
)

# One shared client for the process lifetime; created lazily on first use so
# importing the module (e.g. for tests) does not require a token.
_client: OuraClient | None = None


def _get_client() -> OuraClient:
    global _client
    if _client is None:
        _client = OuraClient()
    return _client


def _default_dates(start_date: str | None, end_date: str | None, *, days: int = 7) -> dict[str, str]:
    """Fill in a sensible date window when the caller omits one."""
    end = end_date or date.today().isoformat()
    if start_date:
        start = start_date
    else:
        end_dt = date.fromisoformat(end)
        start = (end_dt - timedelta(days=days)).isoformat()
    return {"start_date": start, "end_date": end}


async def _collection(endpoint: str, start_date: str | None, end_date: str | None) -> dict[str, Any]:
    """Shared implementation for every date-ranged collection tool."""
    params = _default_dates(start_date, end_date)
    try:
        data = await _get_client().get_collection(endpoint, params)
    except OuraError as exc:
        return {"error": str(exc), "endpoint": endpoint}
    return {
        "endpoint": endpoint,
        "start_date": params["start_date"],
        "end_date": params["end_date"],
        "count": len(data),
        "data": data,
    }


# --------------------------------------------------------------------------- #
# Daily summary scores
# --------------------------------------------------------------------------- #

@mcp.tool
async def get_daily_sleep(start_date: str | None = None, end_date: str | None = None) -> dict[str, Any]:
    """Daily Sleep scores and contributors (deep sleep, efficiency, latency,
    REM, restfulness, timing, total sleep) for each night in the range."""
    return await _collection("daily_sleep", start_date, end_date)


@mcp.tool
async def get_daily_readiness(start_date: str | None = None, end_date: str | None = None) -> dict[str, Any]:
    """Daily Readiness scores and contributors (activity balance, body temp,
    HRV balance, resting heart rate, recovery index, sleep balance)."""
    return await _collection("daily_readiness", start_date, end_date)


@mcp.tool
async def get_daily_activity(start_date: str | None = None, end_date: str | None = None) -> dict[str, Any]:
    """Daily Activity scores: steps, active/total calories, MET minutes,
    activity levels, and the contributor breakdown for each day."""
    return await _collection("daily_activity", start_date, end_date)


# --------------------------------------------------------------------------- #
# Detailed biometrics
# --------------------------------------------------------------------------- #

@mcp.tool
async def get_sleep_periods(start_date: str | None = None, end_date: str | None = None) -> dict[str, Any]:
    """Detailed sleep periods (the richest sleep resource): per-period stages
    in seconds, HR/HRV time series, respiratory rate, latency, efficiency, and
    the sleep hypnogram. There can be more than one period per night."""
    return await _collection("sleep", start_date, end_date)


@mcp.tool
async def get_daily_spo2(start_date: str | None = None, end_date: str | None = None) -> dict[str, Any]:
    """Nightly average blood oxygen (SpO2) percentage and breathing
    disturbance index."""
    return await _collection("daily_spo2", start_date, end_date)


@mcp.tool
async def get_daily_stress(start_date: str | None = None, end_date: str | None = None) -> dict[str, Any]:
    """Daytime stress summary: seconds spent in high-stress vs. recovery, and
    an overall day summary label."""
    return await _collection("daily_stress", start_date, end_date)


@mcp.tool
async def get_daily_resilience(start_date: str | None = None, end_date: str | None = None) -> dict[str, Any]:
    """Daily Resilience: long-term stress/recovery capacity level with
    sleep-recovery, daytime-recovery, and daytime-stress contributors."""
    return await _collection("daily_resilience", start_date, end_date)


@mcp.tool
async def get_daily_cardiovascular_age(
    start_date: str | None = None, end_date: str | None = None
) -> dict[str, Any]:
    """Daily Cardiovascular Age estimate (vascular age vs. chronological age)."""
    return await _collection("daily_cardiovascular_age", start_date, end_date)


@mcp.tool
async def get_vo2_max(start_date: str | None = None, end_date: str | None = None) -> dict[str, Any]:
    """VO2 max (cardiorespiratory fitness) estimates in the date range."""
    # Note the Oura endpoint is spelled `vO2_max`.
    return await _collection("vO2_max", start_date, end_date)


@mcp.tool
async def get_heart_rate(
    start_datetime: str | None = None, end_datetime: str | None = None
) -> dict[str, Any]:
    """Time-series heart rate samples (bpm) with source (awake/sleep/rest/
    workout) and timestamp. Uses ISO 8601 datetimes; defaults to the last 24
    hours. Windows can be large — this is raw samples, not a daily summary."""
    if end_datetime is None:
        end_datetime = datetime.now(timezone.utc).isoformat()
    if start_datetime is None:
        start_datetime = (datetime.fromisoformat(end_datetime) - timedelta(days=1)).isoformat()
    try:
        data = await _get_client().get_collection(
            "heartrate",
            {"start_datetime": start_datetime, "end_datetime": end_datetime},
        )
    except OuraError as exc:
        return {"error": str(exc), "endpoint": "heartrate"}
    return {
        "endpoint": "heartrate",
        "start_datetime": start_datetime,
        "end_datetime": end_datetime,
        "count": len(data),
        "data": data,
    }


# --------------------------------------------------------------------------- #
# Activity detail, sessions, tags, config
# --------------------------------------------------------------------------- #

@mcp.tool
async def get_workouts(start_date: str | None = None, end_date: str | None = None) -> dict[str, Any]:
    """Recorded workouts: activity type, intensity, calories, distance, and
    start/end times (auto-detected or imported from Apple Health / Google Fit)."""
    return await _collection("workout", start_date, end_date)


@mcp.tool
async def get_sessions(start_date: str | None = None, end_date: str | None = None) -> dict[str, Any]:
    """Moment / meditation / rest / breathing sessions with HR, HRV, and
    motion-count time series."""
    return await _collection("session", start_date, end_date)


@mcp.tool
async def get_sleep_time(start_date: str | None = None, end_date: str | None = None) -> dict[str, Any]:
    """Recommended optimal bedtime windows and sleep-timing guidance."""
    return await _collection("sleep_time", start_date, end_date)


@mcp.tool
async def get_rest_mode_periods(
    start_date: str | None = None, end_date: str | None = None
) -> dict[str, Any]:
    """Rest Mode periods (when the user flagged illness/recovery) and their
    episodes."""
    return await _collection("rest_mode_period", start_date, end_date)


@mcp.tool
async def get_tags(start_date: str | None = None, end_date: str | None = None) -> dict[str, Any]:
    """Enhanced Tags — user-logged notes/events (e.g. caffeine, alcohol,
    naps, symptoms) with timestamps and optional comments."""
    return await _collection("enhanced_tag", start_date, end_date)


@mcp.tool
async def get_personal_info() -> dict[str, Any]:
    """The user's profile: age, biological sex, height, weight, and email as
    recorded in Oura."""
    try:
        return await _get_client().get_single("personal_info")
    except OuraError as exc:
        return {"error": str(exc), "endpoint": "personal_info"}


@mcp.tool
async def get_ring_configuration() -> dict[str, Any]:
    """Ring hardware details: model, hardware type, color, size, and firmware
    for the rings on the account."""
    try:
        data = await _get_client().get_collection("ring_configuration", None)
    except OuraError as exc:
        return {"error": str(exc), "endpoint": "ring_configuration"}
    return {"endpoint": "ring_configuration", "count": len(data), "data": data}


def run() -> None:
    """Run the server over stdio (the transport Claude Desktop uses)."""
    mcp.run()
