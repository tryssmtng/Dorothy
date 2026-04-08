#!/usr/bin/env bash
set -uo pipefail

# ═══════════════════════════════════════════════════════════════
# KALIYA Agent Lifecycle v1.0 — SubagentStop
# MERGES: agent-complete-tracker.sh + subagent-verify.sh
#
# Human Mind System #5: AGENT MANAGEMENT
# Single script handles agent completion:
#   1. Quality gate on output (from subagent-verify)
#   2. Dashboard update + cockpit display (from agent-complete-tracker)
#   3. Marker file for done-gate
# ═══════════════════════════════════════════════════════════════

INPUT=$(cat)
DISPLAY_FILE="/tmp/kaliya-dashboard-display.txt"

# Session ID resolution
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)
[ -z "$SESSION_ID" ] && SESSION_ID="${CLAUDE_SESSION_ID:-}"
[ -z "$SESSION_ID" ] && SESSION_ID=$(cat /tmp/claude-current-session/id 2>/dev/null || echo "default")

DASHBOARD="/tmp/kaliya-dashboard-${SESSION_ID}.json"

# Touch marker for done-gate
touch "/tmp/claude-agent-done-${SESSION_ID}"

# ─── Quality Gate (from subagent-verify.sh) ───
AGENT_OUTPUT=$(echo "$INPUT" | jq -r '.result // empty' 2>/dev/null)
QUALITY_WARNING=""

if [ -n "$AGENT_OUTPUT" ]; then
    TODO_COUNT=$(echo "$AGENT_OUTPUT" | grep -ci "TODO\|FIXME\|HACK\|XXX\|PLACEHOLDER" 2>/dev/null | tr -d '[:space:]' || echo 0)
    FAKE_COUNT=$(echo "$AGENT_OUTPUT" | grep -ci "example\.com\|fake-\|dummy-\|lorem ipsum" 2>/dev/null | tr -d '[:space:]' || echo 0)
    EMPTY_FN=$(echo "$AGENT_OUTPUT" | grep -c "pass$\|return None$" 2>/dev/null | tr -d '[:space:]' || echo 0)
    NOT_IMPL=$(echo "$AGENT_OUTPUT" | grep -ci "not implemented\|implementation pending" 2>/dev/null | tr -d '[:space:]' || echo 0)
    TODO_COUNT=${TODO_COUNT:-0}; FAKE_COUNT=${FAKE_COUNT:-0}; EMPTY_FN=${EMPTY_FN:-0}; NOT_IMPL=${NOT_IMPL:-0}

    TOTAL_ISSUES=$(( TODO_COUNT + FAKE_COUNT + EMPTY_FN + NOT_IMPL ))

    if [ "$TOTAL_ISSUES" -gt 3 ]; then
        QUALITY_WARNING="[AGENT QUALITY WARNING] ${TOTAL_ISSUES} issues (${TODO_COUNT} TODOs, ${FAKE_COUNT} fakes, ${EMPTY_FN} empty fns, ${NOT_IMPL} not-impl). Verify before accepting."
    fi
fi

# ─── Dashboard Update + Cockpit (from agent-complete-tracker.sh) ───
export DASHBOARD DISPLAY_FILE SESSION_ID QUALITY_WARNING
export AGENT_INPUT="$INPUT"

python3 -c "
import json, os, sys, time
from datetime import datetime, timezone

dashboard_path = os.environ['DASHBOARD']
display_path = os.environ['DISPLAY_FILE']
session_id = os.environ['SESSION_ID']
quality_warning = os.environ.get('QUALITY_WARNING', '')
raw_input = os.environ.get('AGENT_INPUT', '{}')

agent_name = 'unknown'
task_desc = 'unknown'
success = False
agent_result_text = ''
agent_type_from_stop = ''

try:
    data = json.loads(raw_input)
    agent_result_text = str(data.get('result', '')).strip()
    agent_type_from_stop = data.get('agent_type', '')

    if agent_result_text:
        for line in agent_result_text.split('\n'):
            stripped = line.strip().lstrip('#').lstrip(' ').strip()
            if stripped and len(stripped) > 5 and not stripped.startswith('---'):
                task_desc = stripped[:150]
                break

    result_lower = agent_result_text.lower() if agent_result_text else ''
    success_ind = ['done', 'completed', 'verified', 'pass', 'success',
                   'kar diya', 'ho gaya', 'fixed', 'implemented',
                   'delivered', 'built', 'deployed', 'all items covered']
    failure_ind = ['failed', 'could not', 'unable to', 'not done',
                   'partial', 'blocked', 'fatal', 'traceback', 'abort',
                   'nahi ho paya']

    has_s = any(i in result_lower for i in success_ind)
    has_f = any(i in result_lower for i in failure_ind)

    if has_f and not has_s:
        success = False
    elif has_s:
        success = True
    elif len(agent_result_text) > 50:
        success = True
except Exception:
    pass

now_epoch = int(time.time())
now_iso = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')

# Load dashboard
dashboard = {'session': session_id, 'agents': [], 'summary': {}, 'last_updated': ''}
if os.path.exists(dashboard_path):
    try:
        with open(dashboard_path) as f:
            dashboard = json.load(f)
    except Exception:
        pass

agents = dashboard.get('agents', [])

# Match running agent
matched = None
if agent_type_from_stop:
    for a in agents:
        if a.get('status') == 'running' and a.get('type') == agent_type_from_stop:
            matched = a
            break

if not matched and task_desc != 'unknown':
    td = task_desc[:30].lower()
    for a in agents:
        if a.get('status') == 'running':
            ad = a.get('description', '').lower()
            if td[:15] in ad or ad[:15] in td:
                matched = a
                break

if not matched:
    for a in agents:
        if a.get('status') == 'running':
            matched = a
            break

if matched:
    agent_name = matched.get('name', 'unknown')
    start_epoch = matched.get('start_epoch', now_epoch)
    elapsed = now_epoch - start_epoch
    if elapsed < 60:
        elapsed_d = f'{elapsed}s'
    elif elapsed < 3600:
        m, s = divmod(elapsed, 60)
        elapsed_d = f'{m}m {s}s'
    else:
        h, rem = divmod(elapsed, 3600)
        m = rem // 60
        elapsed_d = f'{h}h {m}m'

    matched['status'] = 'completed' if success else 'failed'
    matched['completed_at'] = now_iso
    matched['elapsed_sec'] = elapsed
    matched['elapsed_display'] = elapsed_d
    matched['result'] = task_desc
    matched['success'] = success

running = sum(1 for a in agents if a['status'] == 'running')
completed = sum(1 for a in agents if a['status'] == 'completed')
failed = sum(1 for a in agents if a['status'] == 'failed')

dashboard['agents'] = agents
dashboard['summary'] = {'total': len(agents), 'running': running, 'completed': completed, 'failed': failed}
dashboard['last_updated'] = now_iso

tmp_path = dashboard_path + '.tmp'
with open(tmp_path, 'w') as f:
    json.dump(dashboard, f, indent=2)
os.replace(tmp_path, dashboard_path)

# Cockpit display
lines = ['>> AGENTS \u2501' * 3]
order = {'completed': 0, 'running': 1, 'failed': 2}
for a in sorted(agents, key=lambda x: order.get(x.get('status', 'running'), 3)):
    s = a.get('status', 'running')
    label = a.get('label', 'AGENT').ljust(8)
    desc = a.get('description', '?')[:25].ljust(25)
    if s == 'completed':
        sym = '\u2713'
        r = a.get('result', 'done')[:30]
        ed = a.get('elapsed_display', '')
        right = f'\u25b6 {r} ({ed})' if ed else f'\u25b6 {r}'
    elif s == 'failed':
        sym = '\u2717'
        ed = a.get('elapsed_display', '')
        right = f'\u25b6 failed ({ed})' if ed else '\u25b6 failed'
    else:
        se = a.get('start_epoch', now_epoch)
        le = now_epoch - se
        if le < 60: ed = f'{le}s'
        elif le < 3600:
            m, s2 = divmod(le, 60)
            ed = f'{m}m {s2}s'
        else:
            h, rem = divmod(le, 3600)
            m = rem // 60
            ed = f'{h}h {m}m'
        sym = '\u25cf'
        right = f'\u25b6 working ({ed})'
    lines.append(f'   {sym}  {label}{desc} {right}')

done_count = completed + failed
total_count = len(agents)
bar_len = min(total_count, 10)
filled = min(int((done_count / total_count) * bar_len) if total_count > 0 else 0, bar_len)
bar = '\u25a0' * filled + '\u25a1' * (bar_len - filled)
lines.append(f'   {done_count}/{total_count} {bar}')
cockpit = '\n'.join(lines)

with open(display_path, 'w') as f:
    f.write(cockpit + '\n')

# Stderr tracking
if matched:
    aid = matched.get('id', '?')
    alabel = matched.get('label', 'AGENT')
    adesc = matched.get('description', '?')[:40]
    aelapsed = matched.get('elapsed_display', '?')
    astatus = 'done' if success else 'FAILED'
    print(f'[DASHBOARD] Agent #{aid} {alabel} {astatus}: {adesc} ({aelapsed})', file=sys.stderr)

# Build output
if matched:
    aid = matched.get('id', '?')
    alabel = matched.get('label', 'AGENT')
    aname = matched.get('name', '')
    aresult = matched.get('result', 'done')
    aelapsed = matched.get('elapsed_display', '?')
    ns = f' ({aname})' if aname else ''
    header = f'[AGENT COMPLETED] #{aid} {alabel}{ns} done \u25b6 {aresult} ({aelapsed})'
else:
    header = '[AGENT COMPLETED] (unmatched)'

ctx = header + '\n\nCURRENT DASHBOARD:\n' + cockpit
if quality_warning:
    ctx += f'\n\n{quality_warning}'
ctx += '\n\nREMINDER: Verify agent output with Read/Bash before marking done.'

output = {
    'hookSpecificOutput': {
        'hookEventName': 'SubagentStop',
        'additionalContext': ctx,
    },
    'suppressOutput': True,
}
print(json.dumps(output))
" 2>/dev/null
