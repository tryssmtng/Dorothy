#!/usr/bin/env python3
"""
KALIYA Done-Gate — Evidence Enforcement Hook v1.0
Event: PreToolUse[TaskUpdate]

Gates TaskUpdate(completed) with two checks:
  1. Perception engine item count reminder (from /tmp/kaliya-perception-state.json)
  2. Agent verification file check (/tmp/kaliya-agent-verified-{SID})

Exit 0 always — warns via stderr, never blocks.
"""
import json
import sys
import os


def _get_session_id():
    """Get session ID: env var -> saved file -> default."""
    sid = os.environ.get("CLAUDE_SESSION_ID")
    if sid:
        return sid
    try:
        with open("/tmp/claude-current-session/id") as f:
            return f.read().strip()
    except (OSError, IOError):
        return "default"


def _read_perception_state():
    """Read perception engine state. Returns dict or None if missing/invalid."""
    path = "/tmp/kaliya-perception-state.json"
    try:
        with open(path) as f:
            data = json.load(f)
        if isinstance(data, dict) and "item_count" in data:
            return data
    except (OSError, IOError, json.JSONDecodeError, ValueError):
        pass
    return None


def _check_agent_verified(session_id):
    """Check if agent verification file exists for this session."""
    path = f"/tmp/kaliya-agent-verified-{session_id}"
    return os.path.exists(path)


def main():
    # Read stdin
    try:
        raw = sys.stdin.read() if not sys.stdin.isatty() else ""
        data = json.loads(raw) if raw.strip() else None
    except (json.JSONDecodeError, ValueError, TypeError):
        sys.exit(0)

    if not data:
        sys.exit(0)

    # Only gate on TaskUpdate
    if data.get("tool_name") != "TaskUpdate":
        sys.exit(0)

    tool_input = data.get("tool_input", {})
    status = tool_input.get("status", "")

    # Only gate on "completed" — all other statuses pass freely
    if status != "completed":
        sys.exit(0)

    session_id = _get_session_id()
    warnings = []

    # Check 1: Perception engine item count
    perception = _read_perception_state()
    if perception is not None:
        item_count = perception.get("item_count", 0)
        if item_count > 0:
            warnings.append(
                f"DONE-GATE: perception-engine detected {item_count} items. "
                f"Verify ALL {item_count} delivered with evidence before completing."
            )

    # Check 2: Agent verification file
    if not _check_agent_verified(session_id):
        # Check if an agent marker exists (agent was dispatched)
        agent_marker = f"/tmp/claude-agent-done-{session_id}"
        if os.path.exists(agent_marker):
            warnings.append(
                "DONE-GATE: Agent output not verified. "
                "Read agent result before marking done."
            )

    # Emit warnings to stderr
    for w in warnings:
        print(w, file=sys.stderr)

    # Always allow — advisory hook, not a blocker
    sys.exit(0)


if __name__ == "__main__":
    main()
