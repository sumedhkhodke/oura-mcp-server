---
name: oura
description: Query Oura Ring health data: sleep, readiness, activity, workouts, HR, HRV, stress, SpO2, trends, and correlations
argument-hint: "[briefing | sleep | readiness | activity | workouts | stress | spo2 | sessions | tags | hr <start> <end> | trend <metric> [days] | correlate <m1> <m2> [lag]]"
allowed-tools: mcp__oura__get_daily_briefing, mcp__plugin_oura_oura__get_daily_briefing, mcp__oura__get_daily_sleep, mcp__plugin_oura_oura__get_daily_sleep, mcp__oura__get_daily_readiness, mcp__plugin_oura_oura__get_daily_readiness, mcp__oura__get_daily_activity, mcp__plugin_oura_oura__get_daily_activity, mcp__oura__get_sleep_periods, mcp__plugin_oura_oura__get_sleep_periods, mcp__oura__get_daily_spo2, mcp__plugin_oura_oura__get_daily_spo2, mcp__oura__get_daily_stress, mcp__plugin_oura_oura__get_daily_stress, mcp__oura__get_daily_resilience, mcp__plugin_oura_oura__get_daily_resilience, mcp__oura__get_daily_cardiovascular_age, mcp__plugin_oura_oura__get_daily_cardiovascular_age, mcp__oura__get_vo2_max, mcp__plugin_oura_oura__get_vo2_max, mcp__oura__get_heart_rate, mcp__plugin_oura_oura__get_heart_rate, mcp__oura__get_workouts, mcp__plugin_oura_oura__get_workouts, mcp__oura__get_sessions, mcp__plugin_oura_oura__get_sessions, mcp__oura__get_sleep_time, mcp__plugin_oura_oura__get_sleep_time, mcp__oura__get_rest_mode_periods, mcp__plugin_oura_oura__get_rest_mode_periods, mcp__oura__get_tags, mcp__plugin_oura_oura__get_tags, mcp__oura__get_personal_info, mcp__plugin_oura_oura__get_personal_info, mcp__oura__get_ring_configuration, mcp__plugin_oura_oura__get_ring_configuration, mcp__oura__get_metric_trend, mcp__plugin_oura_oura__get_metric_trend, mcp__oura__get_metric_correlation, mcp__plugin_oura_oura__get_metric_correlation
---

# /oura: Oura Ring Health Data

Query and present Oura Ring health data conversationally, leading with insight
rather than raw numbers.

## First-Time Setup

If a tool call fails with an auth error, do not retry. Tell the user how to fix
it based on their setup:

- **Local (stdio) server:** run `uv run oura-mcp-server login` in the server
  repo (reuses saved app credentials; pass `--client-id`/`--client-secret` on
  first ever login).
- **Plugin install:** the server runs from the plugin root, so run the same
  `login` command from there. Marketplace installs live under
  `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/` (e.g.
  `~/.claude/plugins/cache/oura-plugins/oura/<version>`). Tokens are saved
  to `~/.oura-mcp/tokens.json` and survive plugin updates.
- **Remote (HTTP) server:** reconnect the MCP server and complete the GitHub
  OAuth flow. Access is limited to GitHub users allowlisted by the server:
  if it is someone else's hosted server you must be on its
  `OURA_MCP_ALLOWED_GITHUB_USERS` list, otherwise deploy your own (see the
  README's Remote / HTTP transport section).

If tools return empty data, remind the user that most endpoints require an
active Oura membership, and that today's data syncs only after the ring syncs
with the phone app.

## When to Use

Trigger on phrases like: "how did I sleep", "am I recovered", "readiness",
"steps today", "any workouts", "heart rate during…", "how stressed",
"blood oxygen", "health trends", "does X affect my Y", "health briefing",
"how am I doing".

## Arguments

Parse from `$ARGUMENTS`. Dates default to today / the last 7 days; convert
relative dates ("yesterday", "last Tuesday") to `YYYY-MM-DD`.

| Argument | Action |
|----------|--------|
| *(empty)* or `briefing` | Daily health briefing |
| `sleep` | Nightly score, then per-night stage detail |
| `readiness` | Readiness score and contributors |
| `activity` | Steps, calories, activity score |
| `workouts` | Workouts with type, intensity, calories |
| `stress` | Daytime stress vs. recovery time |
| `spo2` | Blood oxygen + breathing disturbance |
| `sessions` | Meditation / breathing sessions |
| `tags` | User-logged tags (caffeine, naps, symptoms…) |
| `hr <start> <end>` | Raw heart rate for an ISO datetime window |
| `trend <metric> [days]` | Trend stats for one metric (default 7 days) |
| `correlate <m1> <m2> [lag]` | Pearson correlation between two metrics |

Metrics for `trend`/`correlate`: `sleep_score`, `readiness_score`,
`activity_score`, `total_sleep_hours`, `sleep_efficiency`,
`resting_heart_rate`, `average_hrv`, `temperature_deviation`, `steps`,
`active_calories`.

## Workflows

### Briefing (default)

1. Call `get_daily_briefing` (defaults to the last 7 days; today may be absent
   until the ring syncs; use the most recent day and say which day it is).
2. Lead with the three scores (Sleep / Readiness / Activity) as headline
   numbers, then anything notable: short sleep, elevated resting HR, HRV dip,
   temperature deviation, unusually low steps.
3. Keep it to 3 to 5 sentences. Offer: "Want the sleep detail, a trend, or a
   correlation?"

### Sleep

1. `get_daily_sleep` for scores; `get_sleep_periods` when the user wants depth.
2. Present score, total sleep, efficiency, stage breakdown (deep/REM/light),
   and overnight HR/HRV. Flag high awake time or low deep sleep.

### Readiness

1. `get_daily_readiness`.
2. Headline score, top positive and negative contributors, one actionable
   line (e.g., "recovery looks solid, good day to push" or "below baseline,
   take it easy").

### Activity / Workouts / Stress / SpO2 / Sessions / Tags

Call the matching tool; present compactly. Workouts: type, duration, calories,
intensity per entry. Stress: high-stress vs. recovery minutes and the balance.
SpO2: percentage and whether it's in the normal 95 to 100% range. No data → say
so plainly.

### Heart rate window

1. Require both ISO datetimes; if missing, ask for them.
2. `get_heart_rate`, then report min/max/average and notable spikes; if the
   window overlaps a workout, note it.

### Trend

1. `get_metric_trend` with the metric and day count.
2. Report mean/min/max, first-vs-last change, and direction. Note best/worst
   days and whether the latest value is above or below the period mean.

### Correlation

1. `get_metric_correlation` with both metrics; use `lag_days=1` when the
   question is "does last night's X affect tomorrow's Y".
2. Report the coefficient with a plain-language read (|r| < 0.3 weak,
   0.3 to 0.7 moderate, > 0.7 strong) and the sample size. With fewer than ~10
   paired days, caveat that the sample is small.

## Presentation Rules

- Insight first, numbers second; never dump raw JSON.
- Compare against the person's own recent baseline, not population norms.
- This is wellness data, not medical advice. For anything symptom-like,
  suggest the Oura app and a professional.
