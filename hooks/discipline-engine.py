#!/usr/bin/env python3
"""
KALIYA Discipline Engine v1.1 — Self-Monitoring Hook
Event: PreToolUse[Edit|Write|Bash|Agent]

2 JOBS (Anti-Loop REMOVED — model handles this via CLAUDE.md instructions):
  1. Progress Injection: every 15 calls, prompt self-check
  2. memory_daily Reminder: warn if missing after task completion

State: /tmp/kaliya-discipline-{session_id}.json
Replaces: tasklist-enforcer.py
"""
import json
import sys
import os
import time

STALE_SECONDS = 7200  # 2 hours
PROGRESS_INTERVAL = 15
MEMORY_DAILY_WINDOW = 15


def _get_session_id():
    """Get session ID: env var -> saved file -> default."""
    sid = os.environ.get("CLAUDE_SESSION_ID")
    if sid:
        return sid
    try:
        with open("/tmp/claude-current-session/id") as f:
            content = f.read().strip()
            if content:
                return content
    except (OSError, IOError):
        pass
    return "default"


def _state_path():
    return f"/tmp/kaliya-discipline-{_get_session_id()}.json"


def load_state():
    default = {
        "total_calls": 0,
        "awaiting_memory_daily": False,
        "calls_since_completed": 0,
        "first_call_ts": time.time(),
        "ts": time.time(),
    }
    path = _state_path()
    if not os.path.exists(path):
        return default
    try:
        with open(path) as f:
            s = json.load(f)
        # Stale session — full reset
        if time.time() - s.get("ts", 0) > STALE_SECONDS:
            return default
        # Ensure all fields exist (forward compat)
        s.setdefault("total_calls", 0)
        s.setdefault("awaiting_memory_daily", False)
        s.setdefault("calls_since_completed", 0)
        s.setdefault("first_call_ts", time.time())
        return s
    except (json.JSONDecodeError, TypeError, KeyError, ValueError):
        return default
    except Exception:
        return default


def save_state(s):
    s["ts"] = time.time()
    try:
        with open(_state_path(), "w") as f:
            json.dump(s, f)
    except OSError:
        pass


def _read_perception_items():
    """Read item_count from perception state, return int or None."""
    try:
        with open("/tmp/kaliya-perception-state.json") as f:
            data = json.load(f)
        count = data.get("item_count")
        if isinstance(count, int) and count > 0:
            return count
    except (OSError, IOError, json.JSONDecodeError, TypeError):
        pass
    return None


def job_progress_injection(state):
    """JOB 1: Every 15 calls, inject self-check reminder."""
    total = state.get("total_calls", 0)
    if total <= 0 or total % PROGRESS_INTERVAL != 0:
        return

    perception = _read_perception_items()
    if perception is not None:
        print(
            f"SELF-CHECK: {total} calls done. {perception} perception items tracked. "
            f"Are you on track? Root cause or symptom?",
            file=sys.stderr,
        )
    else:
        print(
            f"SELF-CHECK: {total} calls done. "
            f"Are you on track? Check perception items. Root cause or symptom?",
            file=sys.stderr,
        )


def job_memory_daily_reminder(state, tool_name):
    """JOB 2: Warn if memory_daily missing after task completion (flag set by done-gate)."""
    if not state.get("awaiting_memory_daily", False):
        return

    # memory_daily clears the flag (check both MCP and short name)
    if tool_name in ("memory_daily", "mcp__memory-engine__memory_daily"):
        state["awaiting_memory_daily"] = False
        state["calls_since_completed"] = 0
        return

    state["calls_since_completed"] = state.get("calls_since_completed", 0) + 1

    if state["calls_since_completed"] >= MEMORY_DAILY_WINDOW:
        print(
            f"memory_daily missing after task completion. "
            f"{state['calls_since_completed']} calls since task completed — "
            f"save progress before compact wipes context.",
            file=sys.stderr,
        )
        # Reset so warning fires once, not every call
        state["awaiting_memory_daily"] = False
        state["calls_since_completed"] = 0


def main():
    # Skip for subagents — they don't need discipline monitoring
    if os.environ.get("CLAUDE_AGENT_ID") or os.environ.get("CLAUDE_CODE_AGENT_MODE"):
        sys.exit(0)

    # Read stdin
    try:
        raw = sys.stdin.read() if not sys.stdin.isatty() else ""
        data = json.loads(raw) if raw.strip() else None
    except (json.JSONDecodeError, TypeError, ValueError):
        sys.exit(0)

    if not data or not isinstance(data, dict):
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})

    if not isinstance(tool_input, dict):
        tool_input = {}

    state = load_state()

    # Increment total calls
    state["total_calls"] = state.get("total_calls", 0) + 1

    # --- JOB 1: Progress Injection ---
    job_progress_injection(state)

    # --- JOB 2: memory_daily Reminder ---
    job_memory_daily_reminder(state, tool_name)

    # --- Agent verification marker ---
    # If commander uses Read/Bash after agent completed, mark as verified
    sid = _get_session_id()
    agent_done_marker = f"/tmp/claude-agent-done-{sid}"
    agent_verified = f"/tmp/kaliya-agent-verified-{sid}"
    if os.path.exists(agent_done_marker) and tool_name in ("Read", "Bash", "Grep"):
        if not os.path.exists(agent_verified):
            try:
                open(agent_verified, "w").close()
            except OSError:
                pass

    # Save state after all jobs
    save_state(state)
    sys.exit(0)


if __name__ == "__main__":
    main()
