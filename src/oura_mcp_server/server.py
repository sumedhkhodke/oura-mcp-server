"""FastMCP server exposing the Oura Ring v2 API as MCP tools.

Each tool maps to an Oura ``usercollection`` endpoint. Date-range tools default
to the last 7 days (24 hours for heart rate) when no dates are given, so an
assistant can ask "how did I sleep this week?" without computing dates.

Dates are ISO ``YYYY-MM-DD``. Heart rate uses ISO 8601 datetimes.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from . import analytics, webhook_receiver
from .analytics import METRIC_KEYS
from .client import OuraClient, OuraError
from .webhook import DATA_TYPES, EVENT_TYPES, WebhookClient

logger = logging.getLogger("oura_mcp_server")

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


def _parse_date(value: str) -> date:
    """Parse ``YYYY-MM-DD``; raises ``ValueError`` with a message that names the bad input."""
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"invalid date '{value}': expected YYYY-MM-DD") from exc


def _parse_datetime(value: str) -> datetime:
    """Parse an ISO 8601 datetime, accepting a trailing ``Z`` for UTC on every supported Python."""
    normalized = value[:-1] + "+00:00" if value.endswith(("Z", "z")) else value
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"invalid datetime '{value}': expected ISO 8601, e.g. 2026-07-10T00:00:00Z") from exc


def _default_dates(start_date: str | None, end_date: str | None, *, days: int = 7) -> dict[str, str]:
    """Fill in a ``days``-day window (inclusive of ``end_date``) when the caller omits one.

    Matches :func:`analytics.date_window` so "last 7 days" means 7 calendar days everywhere.
    """
    end_dt = _parse_date(end_date) if end_date else date.today()
    start_dt = _parse_date(start_date) if start_date else end_dt - timedelta(days=max(days - 1, 0))
    return {"start_date": start_dt.isoformat(), "end_date": end_dt.isoformat()}


async def _collection(endpoint: str, start_date: str | None, end_date: str | None) -> dict[str, Any]:
    """Shared implementation for every date-ranged collection tool."""
    try:
        params = _default_dates(start_date, end_date)
    except ValueError as exc:
        return {"error": str(exc), "endpoint": endpoint}
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
async def get_daily_cardiovascular_age(start_date: str | None = None, end_date: str | None = None) -> dict[str, Any]:
    """Daily Cardiovascular Age estimate (vascular age vs. chronological age)."""
    return await _collection("daily_cardiovascular_age", start_date, end_date)


@mcp.tool
async def get_vo2_max(start_date: str | None = None, end_date: str | None = None) -> dict[str, Any]:
    """VO2 max (cardiorespiratory fitness) estimates in the date range."""
    # Note the Oura endpoint is spelled `vO2_max`.
    return await _collection("vO2_max", start_date, end_date)


@mcp.tool
async def get_heart_rate(start_datetime: str | None = None, end_datetime: str | None = None) -> dict[str, Any]:
    """Time-series heart rate samples (bpm) with source (awake/sleep/rest/
    workout) and timestamp. Uses ISO 8601 datetimes; defaults to the last 24
    hours. Windows can be large — this is raw samples, not a daily summary."""
    try:
        end_dt = _parse_datetime(end_datetime) if end_datetime else datetime.now(timezone.utc)
        start_dt = _parse_datetime(start_datetime) if start_datetime else end_dt - timedelta(days=1)
    except ValueError as exc:
        return {"error": str(exc), "endpoint": "heartrate"}
    end_datetime = end_datetime or end_dt.isoformat()
    start_datetime = start_datetime or start_dt.isoformat()
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
async def get_rest_mode_periods(start_date: str | None = None, end_date: str | None = None) -> dict[str, Any]:
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


# --------------------------------------------------------------------------- #
# Derived analytics (briefing, trends, correlations)
# --------------------------------------------------------------------------- #


@mcp.tool
async def get_daily_briefing(start_date: str | None = None, end_date: str | None = None) -> dict[str, Any]:
    """Combined day-by-day recovery briefing: Sleep/Readiness/Activity scores
    plus total sleep hours, resting heart rate, average HRV, temperature
    deviation, steps, and active calories for each day. The 'how am I doing?'
    tool — one call instead of stitching several endpoints together. Defaults
    to the last 7 days."""
    try:
        dates = _default_dates(start_date, end_date)
    except ValueError as exc:
        return {"error": str(exc)}
    try:
        records = await analytics.build_daily_records(_get_client(), dates["start_date"], dates["end_date"])
    except OuraError as exc:
        return {"error": str(exc)}
    return {
        "start_date": dates["start_date"],
        "end_date": dates["end_date"],
        "days": len(records),
        "briefing": list(records.values()),
    }


@mcp.tool
async def get_metric_trend(metric: str, days: int = 14, end_date: str | None = None) -> dict[str, Any]:
    """Trend statistics for one metric over the last N days: mean, min, max,
    first-vs-last change, delta from the mean, and direction.

    `metric` must be one of: sleep_score, readiness_score, activity_score,
    total_sleep_hours, sleep_efficiency, resting_heart_rate, average_hrv,
    temperature_deviation, steps, active_calories."""
    if metric not in METRIC_KEYS:
        return {"error": f"unknown metric '{metric}'", "valid_metrics": METRIC_KEYS}
    try:
        start, end = analytics.date_window(days, end_date)
    except ValueError as exc:
        return {"error": str(exc)}
    try:
        records = await analytics.build_daily_records(_get_client(), start, end)
    except OuraError as exc:
        return {"error": str(exc)}
    result = analytics.summarize_metric(records, metric)
    result["start_date"] = start
    result["end_date"] = end
    result["series"] = [{"day": d, metric: r.get(metric)} for d, r in records.items() if r.get(metric) is not None]
    return result


@mcp.tool
async def get_metric_correlation(
    metric_a: str,
    metric_b: str,
    days: int = 30,
    lag_days: int = 0,
    end_date: str | None = None,
) -> dict[str, Any]:
    """Pearson correlation between two metrics over the last N days.

    Set `lag_days` to relate metric_a on a given day to metric_b that many days
    later — e.g. metric_a='total_sleep_hours', metric_b='readiness_score',
    lag_days=1 answers "how does last night's sleep affect tomorrow's
    readiness?". Valid metrics: sleep_score, readiness_score, activity_score,
    total_sleep_hours, sleep_efficiency, resting_heart_rate, average_hrv,
    temperature_deviation, steps, active_calories."""
    for m in (metric_a, metric_b):
        if m not in METRIC_KEYS:
            return {"error": f"unknown metric '{m}'", "valid_metrics": METRIC_KEYS}
    try:
        start, end = analytics.date_window(days, end_date)
    except ValueError as exc:
        return {"error": str(exc)}
    try:
        records = await analytics.build_daily_records(_get_client(), start, end)
    except OuraError as exc:
        return {"error": str(exc)}
    result = analytics.correlate(records, metric_a, metric_b, lag_days)
    result["start_date"] = start
    result["end_date"] = end
    return result


# --------------------------------------------------------------------------- #
# Analysis prompt templates
# --------------------------------------------------------------------------- #


@mcp.prompt
def analyze_recovery(days: int = 7) -> str:
    """Analyze the user's recovery over the last N days."""
    return (
        f"Analyze my Oura recovery over the last {days} days. Call "
        f"get_daily_briefing for the period, then get_metric_trend for "
        "readiness_score, average_hrv, and resting_heart_rate. Summarize how "
        "recovered I am, call out any concerning trends (rising resting HR, "
        "falling HRV, temperature deviations), and give one concrete "
        "recommendation for tomorrow."
    )


@mcp.prompt
def weekly_review() -> str:
    """Produce a full weekly sleep, activity, and recovery review."""
    return (
        "Give me a weekly review from my Oura data. Use get_daily_briefing for "
        "the last 7 days, then get_metric_trend for sleep_score, "
        "readiness_score, activity_score, and total_sleep_hours. Highlight my "
        "best and worst nights, my activity consistency, and whether I'm "
        "trending up or down. Keep it to a short, skimmable summary with "
        "specific numbers."
    )


@mcp.prompt
def sleep_optimization() -> str:
    """Investigate what most affects the user's sleep and readiness."""
    return (
        "Help me optimize my sleep. Use get_metric_correlation to test how "
        "total_sleep_hours (lag_days=1) relates to readiness_score, how steps "
        "relates to total_sleep_hours, and how average_hrv relates to "
        "readiness_score over the last 30 days. Explain which factors most "
        "influence my recovery and what I should change."
    )


# --------------------------------------------------------------------------- #
# Webhook subscription management (push updates)
# --------------------------------------------------------------------------- #


async def _with_webhook_client(coro_factory: Callable[[WebhookClient], Awaitable[Any]]) -> dict[str, Any]:
    try:
        wc = WebhookClient()
    except OuraError as exc:
        return {"error": str(exc)}
    try:
        result = await coro_factory(wc)
        return {"result": result}
    except OuraError as exc:
        return {"error": str(exc)}
    finally:
        await wc.aclose()


@mcp.tool
async def list_webhook_subscriptions() -> dict[str, Any]:
    """List the account's active Oura webhook subscriptions."""
    return await _with_webhook_client(lambda wc: wc.list())


@mcp.tool
async def create_webhook_subscription(
    callback_url: str, verification_token: str, event_type: str, data_type: str
) -> dict[str, Any]:
    """Create a webhook subscription so Oura pushes updates to your callback URL.

    `event_type` is one of create/update/delete. `data_type` is a resource like
    daily_sleep, daily_readiness, workout, sleep, tag, etc. Oura verifies the
    subscription by sending a challenge GET to `callback_url` that your server
    must echo — so your callback endpoint must be publicly reachable first."""
    if event_type not in EVENT_TYPES:
        return {"error": f"event_type must be one of {EVENT_TYPES}"}
    if data_type not in DATA_TYPES:
        return {"error": f"data_type must be one of {DATA_TYPES}"}
    return await _with_webhook_client(lambda wc: wc.create(callback_url, verification_token, event_type, data_type))


@mcp.tool
async def renew_webhook_subscription(subscription_id: str) -> dict[str, Any]:
    """Renew a webhook subscription before it expires."""
    return await _with_webhook_client(lambda wc: wc.renew(subscription_id))


@mcp.tool
async def delete_webhook_subscription(subscription_id: str) -> dict[str, Any]:
    """Delete a webhook subscription by id."""
    return await _with_webhook_client(lambda wc: wc.delete(subscription_id))


# --------------------------------------------------------------------------- #
# Webhook callback receiver (Oura -> this server)
# --------------------------------------------------------------------------- #


@mcp.custom_route("/webhook", methods=["GET", "POST"])
async def oura_webhook_callback(request: Request) -> JSONResponse:
    """Answer Oura's verification challenge (GET) and record pushed events (POST).

    Oura cannot complete the MCP OAuth flow, so this route sits outside the MCP
    auth layer. It is gated by OURA_WEBHOOK_VERIFICATION_TOKEN instead and is
    disabled (503) when that env var is unset.
    """
    token = webhook_receiver.verification_token()
    if token is None:
        return JSONResponse({"error": "webhook receiver not configured"}, status_code=503)

    if request.method == "GET":
        if request.query_params.get("verification_token") != token:
            return JSONResponse({"error": "bad verification token"}, status_code=403)
        return JSONResponse({"challenge": request.query_params.get("challenge", "")})

    try:
        event = await request.json()
    except ValueError:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)
    webhook_receiver.record_event(event)
    logger.info("Oura webhook event: %s", event)
    return JSONResponse({"status": "received"})


@mcp.tool
async def get_recent_webhook_events(limit: int = 50) -> dict[str, Any]:
    """Recent Oura webhook events received by this server's /webhook endpoint.

    Newest first. The buffer is in-memory (last 200 events) and clears on server
    restart. Events carry identifiers only (data_type, object_id, user_id) — use
    the matching get_* tool to fetch the actual data."""
    events = webhook_receiver.recent_events(limit)
    return {"count": len(events), "events": events}


def run(transport: str = "stdio", host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run the server.

    ``transport='stdio'`` (default) is what Claude Desktop/Code launch. Use
    ``transport='http'`` for a remote/hosted deployment reachable over the
    network (Streamable HTTP at http://host:port/mcp).

    The HTTP transport is **fail-closed**: it requires a fully configured GitHub
    OAuth proxy and a non-empty GitHub user allowlist. Static shared bearer tokens
    are intentionally unsupported.
    """
    if transport == "http":
        from .mcp_auth import McpAuthConfigurationError, build_github_oauth

        try:
            mcp.auth = build_github_oauth()
        except McpAuthConfigurationError as exc:
            raise SystemExit(f"Refusing to start HTTP transport: {exc}") from exc
        logger.info("HTTP transport: GitHub OAuth enabled.")
        mcp.run(transport="http", host=host, port=port)
    else:
        mcp.run()
