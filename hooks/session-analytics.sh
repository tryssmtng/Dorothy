#!/usr/bin/env bash
set -uo pipefail
# Session Analytics — Stop hook. Saves session metrics as JSONL. Cleans stale files.

INPUT=$(cat)
SID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)
SID_DIR="/tmp/claude-current-session"

# Fallback: read session ID from file if hook input is empty
[ -z "$SID" ] && SID=$(cat "$SID_DIR/id" 2>/dev/null || true)
[ -z "$SID" ] && exit 0  # No session — nothing to log

# ── Collect metrics ──
START_TS=$(cat "$SID_DIR/started_at" 2>/dev/null || true)
CWD=$(cat "$SID_DIR/cwd" 2>/dev/null || true)
NOW_EPOCH=$(date -u +%s)
TODAY=$(date -u +%Y-%m-%d)
DAY=$(date -u +%a)

# Duration in minutes
DURATION_MIN=0
if [ -n "$START_TS" ]; then
    START_EPOCH=$(date -j -u -f "%Y-%m-%dT%H:%M:%SZ" "$START_TS" +%s 2>/dev/null || true)
    if [ -n "$START_EPOCH" ] && [ "$START_EPOCH" -gt 0 ] 2>/dev/null; then
        DURATION_MIN=$(( (NOW_EPOCH - START_EPOCH) / 60 ))
        [ "$DURATION_MIN" -lt 0 ] 2>/dev/null && DURATION_MIN=0
    fi
fi

# Project name from CWD (last path component)
PROJECT="unknown"
[ -n "$CWD" ] && PROJECT=$(basename "$CWD" 2>/dev/null || echo "unknown")

# ── Agent metrics from dashboard ──
DASH="/tmp/kaliya-dashboard-${SID}.json"
AGENTS_DISPATCHED=0
AGENTS_SUCCESS=0
AGENT_NAMES="[]"

if [ -f "$DASH" ] && jq empty "$DASH" 2>/dev/null; then
    AGENTS_DISPATCHED=$(jq '[.agents[]? | select(.status != null)] | length' "$DASH" 2>/dev/null || echo 0)
    AGENTS_SUCCESS=$(jq '[.agents[]? | select(.success == true)] | length' "$DASH" 2>/dev/null || echo 0)
    AGENT_NAMES=$(jq -c '[.agents[]?.name // empty]' "$DASH" 2>/dev/null || echo "[]")
fi

# ── Write analytics JSONL ──
ANALYTICS_DIR="$HOME/.claude_2/projects/-Users-niwash/memory"
ANALYTICS_FILE="$ANALYTICS_DIR/session-analytics.jsonl"
mkdir -p "$ANALYTICS_DIR" 2>/dev/null || true

jq -n -c \
    --arg sid "$SID" \
    --arg date "$TODAY" \
    --arg day "$DAY" \
    --arg cwd "${CWD:-unknown}" \
    --argjson dur "${DURATION_MIN:-0}" \
    --argjson dispatched "${AGENTS_DISPATCHED:-0}" \
    --argjson success "${AGENTS_SUCCESS:-0}" \
    --arg project "$PROJECT" \
    --argjson names "$AGENT_NAMES" \
    '{session_id:$sid, date:$date, day:$day, cwd:$cwd, duration_min:$dur,
      agents_dispatched:$dispatched, agents_success:$success,
      agent_names:$names, project:$project}' \
    >> "$ANALYTICS_FILE" 2>/dev/null || true

# ── TTS sessions: DO NOT touch ──
# TTS sessions are managed by /speak on|off. Never clean them from here.
# Old bug: this hook deleted OTHER sessions' TTS files on session stop.

# ── Cleanup: old dashboard JSONs (>2 days) ──
find /tmp -maxdepth 1 -name "kaliya-dashboard-*.json" -mtime +2 -delete 2>/dev/null || true

exit 0
