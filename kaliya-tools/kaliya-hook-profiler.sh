#!/usr/bin/env bash
set -uo pipefail

# KALIYA Hook Latency Profiler v1.0
# Measures execution time of every hook to find bottlenecks.
# Usage: kaliya-hook-profiler.sh [--analyze]
#
# With --analyze: reads stored profiling data and shows stats
# Without: profiles all hooks with synthetic input and shows timing

PROFILE_LOG="/tmp/kaliya-hook-profile.jsonl"
HOOKS_DIR="$HOME/.claude/hooks"
SETTINGS="$HOME/.claude/settings.json"

CYAN='\033[0;36m'
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

if [ "${1:-}" = "--analyze" ] && [ -f "$PROFILE_LOG" ]; then
    echo -e "${CYAN}>> HOOK LATENCY ANALYSIS${NC}"
    echo "============================================="

    # Aggregate by hook name
    python3 -c "
import json, sys
from collections import defaultdict

stats = defaultdict(lambda: {'count': 0, 'total_ms': 0, 'max_ms': 0, 'min_ms': 99999})

with open('$PROFILE_LOG') as f:
    for line in f:
        try:
            d = json.loads(line.strip())
            name = d['hook']
            ms = d['duration_ms']
            s = stats[name]
            s['count'] += 1
            s['total_ms'] += ms
            s['max_ms'] = max(s['max_ms'], ms)
            s['min_ms'] = min(s['min_ms'], ms)
        except:
            continue

print(f\"{'Hook':<35} {'Calls':>6} {'Avg':>8} {'Max':>8} {'Min':>8}\")
print('-' * 75)

for name, s in sorted(stats.items(), key=lambda x: x[1]['total_ms'], reverse=True):
    avg = s['total_ms'] / s['count']
    flag = ' <<< SLOW' if avg > 200 else ''
    print(f\"{name:<35} {s['count']:>6} {avg:>7.0f}ms {s['max_ms']:>7.0f}ms {s['min_ms']:>7.0f}ms{flag}\")

total = sum(s['total_ms'] for s in stats.values())
print(f\"\nTotal measured overhead: {total:.0f}ms across {sum(s['count'] for s in stats.values())} calls\")
" 2>/dev/null
    exit 0
fi

echo -e "${CYAN}>> KALIYA Hook Latency Profiler${NC}"
echo "============================================="
echo -e "Testing all hooks with synthetic input...\n"

# Synthetic hook input
SYNTHETIC_INPUT=$(cat <<'EOF'
{"session_id":"profiler-test","cwd":"/Users/niwash/.claude","hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"echo test"}}
EOF
)

# Clear previous profile data
> "$PROFILE_LOG"

total_ms=0
hook_count=0

# Profile each hook script
for hook_file in "$HOOKS_DIR"/*.sh "$HOOKS_DIR"/*.py; do
    [ -f "$hook_file" ] || continue
    [[ "$hook_file" == *.disabled ]] && continue

    hook_name=$(basename "$hook_file")

    # Time the execution
    start_ns=$(python3 -c "import time; print(int(time.time_ns()))")
    echo "$SYNTHETIC_INPUT" | bash "$hook_file" > /dev/null 2>&1 || true
    end_ns=$(python3 -c "import time; print(int(time.time_ns()))")

    duration_ms=$(( (end_ns - start_ns) / 1000000 ))
    total_ms=$((total_ms + duration_ms))
    hook_count=$((hook_count + 1))

    # Color code
    if [ "$duration_ms" -gt 500 ]; then
        color="$RED"
        status="SLOW"
    elif [ "$duration_ms" -gt 100 ]; then
        color="$YELLOW"
        status="WARN"
    else
        color="$GREEN"
        status="FAST"
    fi

    printf "${color}[%4s]${NC} %4dms  %s\n" "$status" "$duration_ms" "$hook_name"

    # Log to JSONL
    echo "{\"hook\":\"$hook_name\",\"duration_ms\":$duration_ms,\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"type\":\"profile\"}" >> "$PROFILE_LOG"
done

echo ""
echo "============================================="
echo -e "Hooks tested: ${hook_count}"
echo -e "Total latency: ${total_ms}ms"
echo -e "Avg per hook: $((total_ms / (hook_count > 0 ? hook_count : 1)))ms"

if [ "$total_ms" -gt 2000 ]; then
    echo -e "${RED}WARNING: Total hook overhead >2s — optimize slow hooks${NC}"
elif [ "$total_ms" -gt 1000 ]; then
    echo -e "${YELLOW}MODERATE: Total hook overhead >1s — consider optimization${NC}"
else
    echo -e "${GREEN}HEALTHY: Hook overhead under 1s${NC}"
fi

echo -e "\nProfile data saved to: $PROFILE_LOG"
echo "Run with --analyze for aggregated stats over time"
