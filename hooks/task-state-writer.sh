#!/bin/bash
# KALIYA Task State Writer — PostToolUse[TaskCreate|TaskUpdate|TaskList]
# Writes task counts to /tmp/kaliya-task-state.json for statusline consumption
# Lightweight — just parses tool result for task counts

INPUT=$(cat)
TASK_STATE="/tmp/kaliya-task-state.json"

# Extract tool result text
RESULT=$(echo "$INPUT" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    # Get the tool result/output
    result = data.get('tool_result', data.get('result', data.get('output', '')))
    if isinstance(result, dict):
        result = json.dumps(result)
    print(str(result)[:2000])
except Exception:
    print('')
" 2>/dev/null)

if [ -z "$RESULT" ]; then
    exit 0
fi

# Parse task info and update state file
export TASK_RESULT="$RESULT"
export TASK_STATE_PATH="$TASK_STATE"
python3 -c "
import json, os, re, sys

result = os.environ.get('TASK_RESULT', '')
state_path = os.environ.get('TASK_STATE_PATH', '/tmp/kaliya-task-state.json')

# Load existing state
state = {'total': 0, 'completed': 0, 'in_progress': 0, 'pending': 0}
if os.path.exists(state_path):
    try:
        with open(state_path) as f:
            state = json.load(f)
    except Exception:
        pass

# Detect TaskCreate (increments total)
if 'created successfully' in result:
    state['total'] = state.get('total', 0) + 1
    state['pending'] = state.get('pending', 0) + 1

# Detect TaskUpdate completed
if 'status' in result:
    if 'completed' in result.lower():
        state['completed'] = state.get('completed', 0) + 1
        state['in_progress'] = max(0, state.get('in_progress', 0) - 1)
    elif 'in_progress' in result.lower():
        state['in_progress'] = state.get('in_progress', 0) + 1
        state['pending'] = max(0, state.get('pending', 0) - 1)

# Detect TaskList output (parse actual counts)
if 'tasks found' in result.lower() or '#' in result:
    # Count task statuses from TaskList output
    completed = len(re.findall(r'\[completed\]', result, re.I))
    in_progress = len(re.findall(r'\[in_progress\]', result, re.I))
    pending = len(re.findall(r'\[pending\]', result, re.I))
    total = completed + in_progress + pending
    if total > 0:
        state = {
            'total': total,
            'completed': completed,
            'in_progress': in_progress,
            'pending': pending
        }

with open(state_path, 'w') as f:
    json.dump(state, f)
" 2>/dev/null

exit 0
