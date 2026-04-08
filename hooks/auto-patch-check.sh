#!/bin/bash
# auto-patch-check.sh — SessionStart hook
# Detects when CLI binary was updated (patches lost) and re-applies automatically
# Runs on: startup, resume
# Must be FAST (<5s normal path). 60s timeout is safety net for patcher.
#
# Features:
#   - MD5 hash version tracking at /tmp/kaliya-binary-version
#   - Auto-reapply patches on binary change (update detected)
#   - Pre-patch backup of new binary
#   - JSONL version change log
#   - Notification with patch count

VERSIONS_DIR="/Users/niwash/.local/share/claude/versions"
PATCHER="/Users/niwash/.claude/kaliya-patcher.py"
PATCHES_JSON="/Users/niwash/.claude/kaliya-patches-v2.json"
VERSION_FILE="/Users/niwash/.claude/kaliya-patch-version.txt"
HASH_FILE="/tmp/kaliya-binary-version"
VERSION_LOG="$HOME/.claude_2/projects/-Users-niwash/memory/binary-version-log.jsonl"
SIGNATURE="COMPACT RECOVERY"  # From patch #6 compact-header — verified in binary

# Find current binary — newest regular file in versions dir, exclude temp/backup files
BINARY=$(ls -t "$VERSIONS_DIR"/* 2>/dev/null | grep -v '\.pre-fix\|\.cstemp\|\.bak\|\.pre-patch-backup' | head -1)
if [ -z "$BINARY" ] || [ ! -f "$BINARY" ]; then
    exit 0  # No binary found, skip silently
fi

# Patcher must exist
if [ ! -f "$PATCHER" ]; then
    exit 0  # No patcher available, skip silently
fi

# --- Compute current binary hash ---
CURRENT_MD5=$(md5 -q "$BINARY" 2>/dev/null)
if [ -z "$CURRENT_MD5" ]; then
    exit 0  # Can't compute hash, skip
fi

# --- Fast path: compare with stored hash ---
STORED_MD5=""
if [ -f "$HASH_FILE" ]; then
    STORED_MD5=$(cat "$HASH_FILE" 2>/dev/null)
fi

if [ "$CURRENT_MD5" = "$STORED_MD5" ]; then
    # Same binary hash — patches should be intact, verify quickly
    if strings "$BINARY" 2>/dev/null | grep -q "$SIGNATURE"; then
        exit 0  # All good, fastest exit
    fi
    # Hash matches but signature missing — something corrupted patches
    # Fall through to re-apply
fi

# --- Hash differs or no stored hash: check if patches are present ---
if strings "$BINARY" 2>/dev/null | grep -q "$SIGNATURE"; then
    # Patches present, just update tracking files
    echo "$CURRENT_MD5" > "$HASH_FILE"
    {
        echo "binary=$BINARY"
        echo "md5=$CURRENT_MD5"
        echo "timestamp=$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
        echo "status=patched"
    } > "$VERSION_FILE"
    exit 0  # Patches confirmed present
fi

# --- PATCHES MISSING — Binary was updated. Auto-reapply sequence. ---

# Count enabled patches from config
ENABLED_COUNT=0
if [ -f "$PATCHES_JSON" ]; then
    ENABLED_COUNT=$(python3 -c "
import json, sys
try:
    d = json.load(open('${PATCHES_JSON}'))
    print(sum(1 for p in d.get('patches', []) if p.get('enabled', True)))
except Exception:
    print(0)
" 2>/dev/null)
fi

# Step 1: Backup the new (unpatched) binary before we modify it
BACKUP_PATH="${BINARY}.pre-patch-backup"
if [ ! -f "$BACKUP_PATH" ] || [ "$CURRENT_MD5" != "$(md5 -q "$BACKUP_PATH" 2>/dev/null)" ]; then
    cp "$BINARY" "$BACKUP_PATH" 2>/dev/null
fi

# Step 2: Unlock binary if locked with uchg flag
chflags nouchg "$BINARY" 2>/dev/null

# Step 3: Run patcher to reapply all patches
PATCH_OUTPUT=$(python3 "$PATCHER" --apply 2>&1)
PATCH_EXIT=$?

# Extract actual patches applied count from patcher output
APPLIED_COUNT=$(echo "$PATCH_OUTPUT" | grep -oE '[0-9]+ applied' | grep -oE '[0-9]+' | head -1)
if [ -z "$APPLIED_COUNT" ]; then
    APPLIED_COUNT="$ENABLED_COUNT"
fi

if [ $PATCH_EXIT -eq 0 ]; then
    # Step 4: Do NOT lock binary — patcher needs write access for future manual runs
    # chflags uchg "$BINARY" — REMOVED: locks binary, breaks manual patcher

    # Step 5: Update hash tracking
    NEW_MD5=$(md5 -q "$BINARY" 2>/dev/null)
    echo "$NEW_MD5" > "$HASH_FILE"
    {
        echo "binary=$BINARY"
        echo "md5=$NEW_MD5"
        echo "timestamp=$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
        echo "status=patched"
        echo "auto_patched=true"
    } > "$VERSION_FILE"

    # Step 6: Log version change to JSONL
    LOG_DIR=$(dirname "$VERSION_LOG")
    if [ -d "$LOG_DIR" ]; then
        OLD_HASH="${STORED_MD5:-unknown}"
        LOG_DATE=$(date -u '+%Y-%m-%d')
        LOG_TIMESTAMP=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
        BINARY_NAME=$(basename "$BINARY")
        echo "{\"date\":\"${LOG_DATE}\",\"timestamp\":\"${LOG_TIMESTAMP}\",\"binary\":\"${BINARY_NAME}\",\"old_hash\":\"${OLD_HASH}\",\"new_hash\":\"${NEW_MD5}\",\"action\":\"auto-reapply\",\"patches_applied\":${APPLIED_COUNT}}" >> "$VERSION_LOG"
    fi

    # Step 7: Notification
    echo "[BINARY UPDATE DETECTED] Version changed. ${APPLIED_COUNT} patches auto-reapplied." >&2
else
    # Patcher failed — log the failure
    LOG_DIR=$(dirname "$VERSION_LOG")
    if [ -d "$LOG_DIR" ]; then
        OLD_HASH="${STORED_MD5:-unknown}"
        LOG_DATE=$(date -u '+%Y-%m-%d')
        LOG_TIMESTAMP=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
        BINARY_NAME=$(basename "$BINARY")
        echo "{\"date\":\"${LOG_DATE}\",\"timestamp\":\"${LOG_TIMESTAMP}\",\"binary\":\"${BINARY_NAME}\",\"old_hash\":\"${OLD_HASH}\",\"new_hash\":\"${CURRENT_MD5}\",\"action\":\"auto-reapply-FAILED\",\"exit_code\":${PATCH_EXIT}}" >> "$VERSION_LOG"
    fi

    # Still update hash file so we don't retry every session
    echo "$CURRENT_MD5" > "$HASH_FILE"

    echo "WARNING: KALIYA patches could not be re-applied (exit=$PATCH_EXIT)." >&2
    echo "Run manually: python3 $PATCHER --apply" >&2
fi

exit 0
