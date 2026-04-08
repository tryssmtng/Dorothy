#!/bin/bash
set -uo pipefail
# ═══════════════════════════════════════════════════════════════
# KALIYA QUALITY GATE v3 — PreToolUse[Edit] Self-Sufficient
# ═══════════════════════════════════════════════════════════════
# 8 INTELLIGENT CHECKS — Zero external dependencies
#
# 1. File exists
# 2. old_string non-empty
# 3. Binary file detection (don't corrupt binaries with text Edit)
# 4. old_string pre-validation (grep in file — catches #1 Edit failure)
# 5. old_string uniqueness check (multiple matches = Edit might fail)
# 6. File size → agent territory (>500 lines)
# 7. Edit count tracking per burst (manager limit = 3)
# 8. Protected file caution (settings.json, .env, credentials, CLAUDE.md)
#
# Exit 0 = ALWAYS (warns, never blocks — Edit tool handles failures)
# ═══════════════════════════════════════════════════════════════

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
OLD_STRING=$(echo "$INPUT" | jq -r '.tool_input.old_string // empty' 2>/dev/null)
NEW_STRING=$(echo "$INPUT" | jq -r '.tool_input.new_string // empty' 2>/dev/null)

# No file path = nothing to check
[ -z "$FILE_PATH" ] && exit 0

# Skip for subagents — they handle their own edits
[ -n "${CLAUDE_AGENT_ID:-}" ] || [ -n "${CLAUDE_CODE_AGENT_MODE:-}" ] && exit 0

SID="${CLAUDE_SESSION_ID:-default}"
EDIT_COUNT_FILE="/tmp/claude-edit-count-${SID}"

# ─── CHECK 1: File exists ───
if [ ! -f "$FILE_PATH" ]; then
    echo "[QUALITY] File does not exist: ${FILE_PATH}. Edit will FAIL." >&2
    exit 0
fi

# ─── CHECK 2: Empty old_string ───
if [ -z "$OLD_STRING" ]; then
    echo "[QUALITY] Edit with empty old_string on ${FILE_PATH}." >&2
    exit 0
fi

# ─── CHECK 3: Binary file detection ───
MIME=$(file -b --mime-type "$FILE_PATH" 2>/dev/null || echo "text/plain")
case "$MIME" in
    text/*|application/json|application/xml|application/javascript|application/x-shellscript)
        ;; # OK — text file
    *)
        echo "[QUALITY] Binary file (${MIME}): ${FILE_PATH}. Text Edit on binary will corrupt data." >&2
        exit 0
        ;;
esac

# ─── CHECK 4: old_string exists in file (PRE-VALIDATE) ───
# This catches the #1 Edit failure: old_string doesn't match file content
# Use first line of old_string for grep (multiline old_string splits on newlines)
FIRST_LINE=$(printf '%s' "$OLD_STRING" | head -1)
if [ -n "$FIRST_LINE" ]; then
    MATCH_COUNT=$(grep -cF -- "$FIRST_LINE" "$FILE_PATH" 2>/dev/null || echo "0")
    if [ "$MATCH_COUNT" -eq 0 ]; then
        echo "[QUALITY] old_string NOT FOUND in ${FILE_PATH}. Edit will FAIL. Check indentation/whitespace match exactly." >&2
    fi
fi

# ─── CHECK 5: old_string uniqueness ───
# Edit tool requires old_string to be unique (unless replace_all=true)
REPLACE_ALL=$(echo "$INPUT" | jq -r '.tool_input.replace_all // "false"' 2>/dev/null)
if [ "$REPLACE_ALL" != "true" ] && [ -n "$FIRST_LINE" ]; then
    # Only warn if >1 match of full old_string's first line
    if [ "${MATCH_COUNT:-0}" -gt 1 ]; then
        echo "[QUALITY] old_string first line matches ${MATCH_COUNT}x in ${FILE_PATH}. Edit needs unique match or use replace_all=true." >&2
    fi
fi

# ─── CHECK 6: File size → agent territory ───
LINE_COUNT=$(wc -l < "$FILE_PATH" 2>/dev/null | tr -d ' ' || echo "0")
if [ "$LINE_COUNT" -gt 500 ]; then
    echo "[QUALITY] Large file (${LINE_COUNT} lines): ${FILE_PATH}. Dispatch agent for large-file edits." >&2
fi

# ─── CHECK 7: Edit count tracking per burst ───
NOW=$(date +%s)
COUNT=0
if [ -f "$EDIT_COUNT_FILE" ]; then
    LAST_TS=$(head -1 "$EDIT_COUNT_FILE" 2>/dev/null || echo "0")
    COUNT=$(tail -1 "$EDIT_COUNT_FILE" 2>/dev/null || echo "0")
    # Reset if >120 seconds since last edit (new message context)
    ELAPSED=$((NOW - LAST_TS))
    if [ "$ELAPSED" -gt 120 ]; then
        COUNT=0
    fi
fi
COUNT=$((COUNT + 1))
printf '%s\n%s\n' "$NOW" "$COUNT" > "$EDIT_COUNT_FILE" 2>/dev/null

if [ "$COUNT" -gt 15 ]; then
    echo "[QUALITY] ${COUNT} edits in burst. Consider agent for remaining multi-file edits." >&2
elif [ "$COUNT" -gt 10 ]; then
    echo "[QUALITY] ${COUNT} edits. Large batch — agent may be more efficient." >&2
fi

# ─── CHECK 8: Protected files ───
BASENAME=$(basename "$FILE_PATH")
case "$BASENAME" in
    settings.json)
        echo "[QUALITY] Editing settings.json — multiple Edits can corrupt JSON (trailing commas, invisible chars). Consider fresh Write for structural changes." >&2
        ;;
    .env|.env.*)
        echo "[QUALITY] Sensitive env file: ${BASENAME}. Verify no credentials leak to transcript." >&2
        ;;
    credentials*|secrets*|*.pem|*.key|*.p12)
        echo "[QUALITY] Credentials file: ${BASENAME}. Changes here affect auth across the system." >&2
        ;;
    CLAUDE.md)
        FILE_SIZE=$(wc -c < "$FILE_PATH" 2>/dev/null | tr -d ' ' || echo "0")
        if [ "$FILE_SIZE" -gt 35000 ]; then
            echo "[QUALITY] CLAUDE.md at ${FILE_SIZE} bytes (limit: 40960). ${FILE_SIZE}/40960 — careful with additions." >&2
        fi
        ;;
esac

exit 0
