#!/bin/bash
# KALIYA Playwright Session Cleanup — Stop hook
# Closes only THIS project's browser session when Claude session ends.
# Other projects' sessions are UNTOUCHED — zero cross-project interference.

PLAYWRIGHT_CLI=$(which playwright-cli 2>/dev/null)
if [ -z "$PLAYWRIGHT_CLI" ]; then
    exit 0
fi

# Calculate THIS project's session name (same formula as all skills/agents)
S=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" | tr '[:upper:]' '[:lower:]' | tr ' _' '--')

# Edge case: if CWD is ~/.claude (or similar dot-prefixed), use "default"
if [ -z "$S" ] || [[ "$S" == .* ]]; then
    S="default"
fi

# Check if THIS project's session is currently open
# playwright-cli list output format:
#   - session-name:
#     - status: open
#     ...
SESSION_OPEN=$("$PLAYWRIGHT_CLI" list 2>/dev/null | grep -A1 "^- ${S}:" | grep -c "status: open" || true)

if [ "$SESSION_OPEN" -gt 0 ]; then
    "$PLAYWRIGHT_CLI" -s="$S" close 2>/dev/null
fi

exit 0
