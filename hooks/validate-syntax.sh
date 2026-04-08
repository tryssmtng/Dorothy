#!/bin/bash
set -uo pipefail
# ═══════════════════════════════════════════════════════════════
# KALIYA QUALITY GATE — PostToolUse[Edit|Write] Syntax Validator v2
# ═══════════════════════════════════════════════════════════════
# Auto-validates file syntax after Edit/Write operations.
# Catches syntax errors IMMEDIATELY — before they snowball.
#
# Exit 0 = syntax OK (silent)
# Exit 2 = SYNTAX ERROR — stderr feedback sent to Claude
# ═══════════════════════════════════════════════════════════════

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)

# No file or file doesn't exist = skip
if [ -z "$FILE_PATH" ] || [ ! -f "$FILE_PATH" ]; then
    echo '{"suppressOutput": true}'
    exit 0
fi

EXT="${FILE_PATH##*.}"
ERROR=""

validate_python() {
    FILE_PATH="$1" python3 -c "
import os, py_compile
try:
    py_compile.compile(os.environ['FILE_PATH'], doraise=True)
except py_compile.PyCompileError as e:
    print(str(e))
" 2>/dev/null
}

validate_json() {
    FILE_PATH="$1" python3 -c "
import os, json
try:
    with open(os.environ['FILE_PATH']) as f:
        json.load(f)
except Exception as e:
    print(str(e))
" 2>/dev/null
}

validate_yaml() {
    FILE_PATH="$1" python3 -c "
import os
try:
    import yaml
    with open(os.environ['FILE_PATH']) as f:
        yaml.safe_load(f)
except ImportError:
    print('WARNING: PyYAML not installed, YAML validation skipped')
except Exception as e:
    print(str(e))
" 2>/dev/null
}

validate_js() {
    if command -v node &>/dev/null; then
        # macOS doesn't have timeout — use perl fallback
        perl -e 'alarm shift; exec @ARGV' 5 node --check "$1" 2>&1 || true
    fi
}

validate_xml() {
    FILE_PATH="$1" python3 -c "
import os
from xml.etree import ElementTree
try:
    ElementTree.parse(os.environ['FILE_PATH'])
except Exception as e:
    print(str(e))
" 2>/dev/null
}

case "$EXT" in
    py)         ERROR=$(validate_python "$FILE_PATH") ;;
    json)       ERROR=$(validate_json "$FILE_PATH") ;;
    yaml|yml)   ERROR=$(validate_yaml "$FILE_PATH") ;;
    js|mjs|cjs) ERROR=$(validate_js "$FILE_PATH") ;;
    xml)        ERROR=$(validate_xml "$FILE_PATH") ;;
    *)          ;; # Unknown extension — no validator, skip
esac

if [ -n "$ERROR" ]; then
    # PostToolUse: exit 2 + stderr = feedback sent to Claude
    echo "SYNTAX ERROR in ${FILE_PATH}: ${ERROR}. Fix this syntax error immediately before proceeding." >&2
    exit 2
fi

exit 0
