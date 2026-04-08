#!/usr/bin/env python3
"""
KALIYA Agent Gate v1.0 — Merged Agent Validator Hook
Event: PreToolUse[Agent]

Combines two previously separate hooks into one:
  1. Dashboard Recording (was agent-tracker.sh)
  2. Spawn Prompt Quality Gate (was agent-param-validator.sh)

NEVER blocks — exit 0 always. Warns on stderr for quality issues.
Writes dashboard to /tmp/kaliya-dashboard-{session_id}.json.
"""
import json
import os
import sys
import time
from datetime import datetime, timezone

# ═══════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════

TYPE_LABELS = {
    'general-purpose': 'BUILD',
    'Explore': 'SCOUT',
    'Plan': 'PLAN',
    'code-reviewer': 'REVIEW',
    'site-auditor': 'TEST',
    'qa-tester': 'TEST',
    'web-automator': 'AUTO',
    'documenter': 'DOCS',
    'system-guardian': 'GUARD',
    'researcher': 'INTEL',
    'deployer': 'DEPLOY',
    'explorer': 'SCOUT',
    'ui-builder': 'BUILD',
    'builder': 'BUILD',
}

MAX_DASHBOARD_AGENTS = 20
MIN_PROMPT_LENGTH = 50


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════

def get_session_id(hook_data):
    """Resolve session ID: env var > hook JSON > file fallback > default."""
    sid = os.environ.get('CLAUDE_SESSION_ID', '')
    if sid:
        return sid
    sid = hook_data.get('session_id', '')
    if sid:
        return sid
    try:
        with open('/tmp/claude-current-session/id', 'r') as f:
            sid = f.read().strip()
            if sid:
                return sid
    except (OSError, IOError):
        pass
    return 'default'


def resolve_label(agent_type):
    """Map agent type to short dashboard label."""
    label = TYPE_LABELS.get(agent_type)
    if label:
        return label
    if agent_type and agent_type.startswith('feature-dev'):
        return 'BUILD'
    return 'AGENT'


def load_dashboard(path, session_id):
    """Load existing dashboard or create new one. Handles corrupt JSON."""
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            if isinstance(data, dict) and 'agents' in data:
                return data
        except (json.JSONDecodeError, OSError, IOError, KeyError):
            pass
    return {
        'session': session_id,
        'agents': [],
        'summary': {},
        'last_updated': '',
    }


def save_dashboard(path, dashboard):
    """Write dashboard atomically via tmp file."""
    tmp_path = path + '.tmp'
    try:
        with open(tmp_path, 'w') as f:
            json.dump(dashboard, f, indent=2)
        os.replace(tmp_path, path)
    except (OSError, IOError) as e:
        # Fallback: direct write
        try:
            with open(path, 'w') as f:
                json.dump(dashboard, f, indent=2)
        except (OSError, IOError):
            print(f'[AGENT-GATE] Dashboard write failed: {e}', file=sys.stderr)


# ═══════════════════════════════════════════════════════════
# FUNCTION 1: DASHBOARD RECORDING
# ═══════════════════════════════════════════════════════════

def record_agent(dashboard, tool_input, session_id, now_iso, now_epoch):
    """Add agent entry to dashboard, return new agent id."""
    description = tool_input.get('description', 'unknown task')
    agent_type = tool_input.get('subagent_type', 'general-purpose')
    prompt = tool_input.get('prompt', '')
    background = str(tool_input.get('run_in_background', False)).lower()
    agent_name = tool_input.get('name', '')
    label = resolve_label(agent_type)

    prompt_preview = prompt[:200].replace('\n', ' ') if prompt else ''

    agents = dashboard.get('agents', [])
    new_id = max((a.get('id', 0) for a in agents), default=0) + 1

    entry = {
        'id': new_id,
        'type': agent_type,
        'label': label,
        'description': description,
        'name': agent_name,
        'prompt_preview': prompt_preview,
        'background': background,
        'started_at': now_iso,
        'start_epoch': now_epoch,
        'status': 'running',
        'completed_at': None,
        'elapsed_sec': None,
        'elapsed_display': None,
        'result': None,
        'success': None,
    }
    agents.append(entry)

    # Cap at MAX_DASHBOARD_AGENTS
    if len(agents) > MAX_DASHBOARD_AGENTS:
        agents = agents[-MAX_DASHBOARD_AGENTS:]

    dashboard['agents'] = agents

    # Update summary counts
    running = sum(1 for a in agents if a.get('status') == 'running')
    completed = sum(1 for a in agents if a.get('status') == 'completed')
    failed = sum(1 for a in agents if a.get('status') == 'failed')

    dashboard['summary'] = {
        'total': len(agents),
        'running': running,
        'completed': completed,
        'failed': failed,
    }
    dashboard['last_updated'] = now_iso

    print(
        f'[DASHBOARD] +Agent #{new_id}: {label}  {description} | '
        f'{running} running, {completed} done',
        file=sys.stderr,
    )
    return new_id


# ═══════════════════════════════════════════════════════════
# FUNCTION 2: SPAWN PROMPT QUALITY GATE
# ═══════════════════════════════════════════════════════════

def validate_prompt(prompt):
    """Check prompt quality. Returns list of warning strings."""
    warnings = []

    if not prompt:
        warnings.append('EMPTY PROMPT — agent received no instructions at all')
        return warnings

    # Length check
    if len(prompt) < MIN_PROMPT_LENGTH:
        warnings.append(
            f'VAGUE PROMPT (<{MIN_PROMPT_LENGTH} chars) — '
            'agent needs detailed instructions with file paths and numbered requirements'
        )

    # File paths check
    has_paths = ('/' in prompt) or ('~/' in prompt)
    if not has_paths and 'file' not in prompt.lower():
        warnings.append(
            'NO FILE PATHS — include EXACT absolute paths so agent knows what to read/modify'
        )

    # Numbered requirements check
    has_numbered = any(f'{i}.' in prompt or f'{i})' in prompt for i in range(1, 10))
    has_bullets = prompt.count('- ') >= 2
    if not has_numbered and not has_bullets:
        warnings.append(
            'NO NUMBERED REQUIREMENTS — list items as 1. 2. 3. so agent delivers ALL of them'
        )

    # Completion criteria check
    prompt_lower = prompt.lower()
    has_done_when = any(marker in prompt_lower for marker in [
        'done when', 'done:', 'completion criteria',
        'success criteria', 'verify', 'build passes',
    ])
    if not has_done_when:
        warnings.append(
            'NO COMPLETION CRITERIA — add "Done When:" so agent knows when to stop'
        )

    return warnings


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

def main():
    # Skip for subagent contexts
    if os.environ.get('CLAUDE_AGENT_ID') or os.environ.get('CLAUDE_CODE_AGENT_MODE'):
        print(json.dumps({'suppressOutput': True}))
        return

    # Read stdin
    try:
        raw = sys.stdin.read()
    except Exception:
        raw = ''

    if not raw.strip():
        print(json.dumps({'suppressOutput': True}))
        return

    # Parse hook input
    try:
        hook_data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        print(json.dumps({'suppressOutput': True}))
        return

    tool_input = hook_data.get('tool_input', {})
    if not isinstance(tool_input, dict):
        tool_input = {}

    prompt = tool_input.get('prompt', '')

    # Resolve session
    session_id = get_session_id(hook_data)
    dashboard_path = f'/tmp/kaliya-dashboard-{session_id}.json'

    now_epoch = int(time.time())
    now_iso = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')

    # --- Function 1: Dashboard Recording ---
    dashboard = load_dashboard(dashboard_path, session_id)
    record_agent(dashboard, tool_input, session_id, now_iso, now_epoch)
    save_dashboard(dashboard_path, dashboard)

    # --- Function 2: Prompt Quality Gate ---
    warnings = validate_prompt(prompt)

    if warnings:
        reason = 'AGENT PROMPT QUALITY: ' + ' | '.join(warnings)
        reason += ' -- Use the Spawn Prompt Template from CLAUDE.md.'
        print(json.dumps({
            'decision': 'warn',
            'reason': reason,
        }))
    else:
        print(json.dumps({'suppressOutput': True}))


if __name__ == '__main__':
    main()
