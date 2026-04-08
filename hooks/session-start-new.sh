#!/bin/bash
set -uo pipefail
# Session Start v8 — Human-like subconscious auto-recall.
# v8: Cross-project brain sync, recent mistakes injection, session analytics
#     insights, memory GC trigger, project-specific learning recall.

# Read input first to get SESSION_ID before cleanup
INPUT=$(cat)
CWD=$(echo "$INPUT" | jq -r '.cwd // empty' 2>/dev/null)
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)

# Reset session-scoped markers
SID="${SESSION_ID:-default}"
rm -f "/tmp/claude-step0-done-${SID}" "/tmp/claude-step0-grep-${SID}"
rm -f "/tmp/claude-agent-done-${SID}" "/tmp/claude-verified-${SID}" "/tmp/kaliya-agent-verified-${SID}"
rm -f /tmp/claude-step0-done /tmp/claude-agent-done /tmp/claude-verified

# Reset trackers for fresh session
echo '{"calls":0,"reads":0,"edits":0,"agents":0}' > /tmp/claude-context-tracker.json 2>/dev/null || true
echo "{\"session\":\"${SID}\",\"agents\":[],\"summary\":{},\"last_updated\":\"$(date -u +%Y-%m-%dT%H:%M:%S)\"}" > "/tmp/kaliya-dashboard-${SID}.json" 2>/dev/null || true
echo '{"total":0,"completed":0,"in_progress":0,"pending":0}' > /tmp/kaliya-task-state.json 2>/dev/null || true

# Save session ID
SID_DIR="/tmp/claude-current-session"
mkdir -p "$SID_DIR" 2>/dev/null
if [ -n "$SESSION_ID" ]; then
    echo "$SESSION_ID" > "$SID_DIR/id"
    echo "$CWD" > "$SID_DIR/cwd"
    date -u +"%Y-%m-%dT%H:%M:%SZ" > "$SID_DIR/started_at"
fi

MEMORY_BASE="$HOME/.claude/projects"
HOME_HASH=$(echo "$HOME" | sed 's|[/.]|-|g')
CTX="[SESSION START] ID: ${SESSION_ID:-unknown} | CWD: ${CWD:-unknown}"

# ─── Last session context ───
STATE_FILE=""
if [ -n "$CWD" ]; then
    PROJECT_HASH=$(echo "$CWD" | sed 's|[/.]|-|g')
    CANDIDATE="$MEMORY_BASE/$PROJECT_HASH/memory/state.json"
    [ -f "$CANDIDATE" ] && STATE_FILE="$CANDIDATE"
fi
[ -z "$STATE_FILE" ] && { HC="$MEMORY_BASE/$HOME_HASH/memory/state.json"; [ -f "$HC" ] && STATE_FILE="$HC"; }

if [ -f "$STATE_FILE" ] && jq empty "$STATE_FILE" 2>/dev/null; then
    LAST_CWD=$(jq -r '.cwd // ""' "$STATE_FILE" 2>/dev/null)
    LAST_TS=$(jq -r '.timestamp // ""' "$STATE_FILE" 2>/dev/null)
    GIT_BRANCH=$(jq -r '.git_branch // ""' "$STATE_FILE" 2>/dev/null)
    CTX="$CTX | Last: ${LAST_CWD} at ${LAST_TS}"
    [ -n "$GIT_BRANCH" ] && CTX="$CTX branch:${GIT_BRANCH}"
    LAST_CALLS=$(jq -r '.context_stats.calls // "?"' "$STATE_FILE" 2>/dev/null)
    LAST_READS=$(jq -r '.context_stats.reads // "?"' "$STATE_FILE" 2>/dev/null)
    LAST_EDITS=$(jq -r '.context_stats.edits // "?"' "$STATE_FILE" 2>/dev/null)
    LAST_REASON=$(jq -r '.compact_reason // "unknown"' "$STATE_FILE" 2>/dev/null)
    CTX="$CTX | Last compact: ${LAST_REASON} after ${LAST_CALLS} calls"
    CTX="$CTX | Last session stats: ${LAST_CALLS} calls, ${LAST_READS} reads, ${LAST_EDITS} edits"
    PREV_AGENTS=$(jq -r '.running_agents | length // 0' "$STATE_FILE" 2>/dev/null)
    [ "${PREV_AGENTS:-0}" -gt 0 ] 2>/dev/null && CTX="$CTX | [WARNING] ${PREV_AGENTS} agents at compact."
fi

CTX="$CTX | [1M CONTEXT] Full depth mode. NEVER suggest new session below 80%. Work until done or auto-compact."

# ─── Cross-Project Brain Sync (every 24h) ───
SYNC_F="/tmp/kaliya-last-brain-sync"
SYNC_NEEDED=false
if [ -f "$SYNC_F" ]; then
    [ "$(( $(date +%s) - $(cat "$SYNC_F" 2>/dev/null || echo 0) ))" -gt 86400 ] && SYNC_NEEDED=true
else
    SYNC_NEEDED=true
fi
if $SYNC_NEEDED && [ -x "$HOME/.claude/tools/kaliya-cross-project-sync.sh" ]; then
    "$HOME/.claude/tools/kaliya-cross-project-sync.sh" --force >/dev/null 2>&1 || true
    date +%s > "$SYNC_F" 2>/dev/null
fi

# ─── Memory GC (every 48h) ───
GC_F="/tmp/kaliya-last-gc"
GC_NEEDED=false
if [ -f "$GC_F" ]; then
    [ "$(( $(date +%s) - $(cat "$GC_F" 2>/dev/null || echo 0) ))" -gt 172800 ] && GC_NEEDED=true
else
    GC_NEEDED=true
fi
if $GC_NEEDED && [ -x "$HOME/.claude/tools/kaliya-memory-gc.sh" ]; then
    "$HOME/.claude/tools/kaliya-memory-gc.sh" --force >/dev/null 2>&1 || true
    date +%s > "$GC_F" 2>/dev/null
fi

# ─── Memory Consolidation (episodic → semantic, every 72h) ───
CONSOL_SCRIPT="$HOME/.claude/tools/kaliya-memory-consolidation.py"
if [ -f "$CONSOL_SCRIPT" ]; then
    python3 "$CONSOL_SCRIPT" >/dev/null 2>&1 || true
fi

# ─── Memory health ───
GLOBAL_MEMORY="$MEMORY_BASE/$HOME_HASH/memory/MEMORY.md"
if [ -f "$GLOBAL_MEMORY" ]; then
    MEM_LINES=$(wc -l < "$GLOBAL_MEMORY" 2>/dev/null | tr -d ' ')
    [ "${MEM_LINES:-0}" -gt 170 ] 2>/dev/null && \
        CTX="$CTX | [MEMORY OVERFLOW] ${MEM_LINES}/200 lines — move detail to topic files."
fi

# ─── Recent Mistakes (top 3 from global brain — human recall) ───
GLOBAL_BRAIN="$HOME/.claude_2/projects/-Users-niwash/memory/mistakes-learnings.md"
if [ -f "$GLOBAL_BRAIN" ]; then
    RECENT=$(grep "^## " "$GLOBAL_BRAIN" | tail -3 | sed 's/^## /- /')
    [ -n "$RECENT" ] && CTX="$CTX
[RECENT LEARNINGS (avoid repeating)]
$RECENT"
fi

# ─── Session Analytics Insights ───
ANALYTICS="$HOME/.claude_2/projects/-Users-niwash/memory/session-analytics.jsonl"
if [ -f "$ANALYTICS" ] && [ "$(wc -l < "$ANALYTICS" | tr -d ' ')" -gt 2 ]; then
    STATS=$(python3 -c "
import json
L=[json.loads(l) for l in open('$ANALYTICS') if l.strip()]
D=[x.get('duration_min',0) for x in L]
A=sum(x.get('agents_dispatched',0) for x in L)
print(f'Sessions:{len(D)} Avg:{sum(D)//max(len(D),1)}m Agents:{A}')
" 2>/dev/null || true)
    [ -n "$STATS" ] && CTX="$CTX
[SESSION STATS] $STATS"
fi

# ─── Project-Specific Learnings ───
if [ -n "${PROJECT_HASH:-}" ]; then
    PROJ_M="$HOME/.claude_2/projects/$PROJECT_HASH/memory/mistakes-learnings.md"
    if [ -f "$PROJ_M" ]; then
        PROJ_R=$(grep "^## " "$PROJ_M" | tail -2 | sed 's/^## /- /')
        [ -n "$PROJ_R" ] && CTX="$CTX
[PROJECT LEARNINGS]
$PROJ_R"
    fi
fi

# ─── Memory Engine Auto-Recall ───
RECALL=""
if [ -f "$HOME/.claude/memory-engine/.venv/bin/python3" ] && [ -f "$HOME/.claude/memory-engine/cli.py" ]; then
    RECALL=$("$HOME/.claude/memory-engine/.venv/bin/python3" "$HOME/.claude/memory-engine/cli.py" recall \
        --project "${CWD:-$HOME}" --budget 1024 2>/dev/null || true)
fi
if [ -n "$RECALL" ] && [ ${#RECALL} -gt 10 ]; then
    CTX="$CTX
[MEMORY RECALL]
$RECALL"
fi

CTX=$(printf '%s' "$CTX" | tr -d '\000-\010\013\014\016-\037' | head -c 3000)
jq -n --arg ctx "$CTX" '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":$ctx},"suppressOutput":true}'
exit 0
