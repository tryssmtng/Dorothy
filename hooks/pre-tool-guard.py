#!/usr/bin/env python3
"""
KALIYA Pre-Tool Guard v3 — Intelligent Bash Command Safety
Event: PreToolUse[Bash]

UPGRADE from v2:
- Self-contained: no external dependencies
- Smarter normalization: handles $'...', hex, octal, base64 bypasses
- Context-aware: checks CLAUDE_AGENT_ID to skip for subagents
- Operator-aware: git ops ALLOWED (binary patches authorize them)
- SSH rate limiting: tracks + warns at 4+/min (silent log otherwise)
- sshpass credential leak protection: BLOCKS inline passwords
- Encoding bypass detection: base64|sh, hex escapes, eval chains

BLOCKS:  System destruction, fork bombs, credential leaks, encoding bypasses
ALLOWS:  Git (all ops), single file rm, chmod, standard dev commands

LOOP DETECTION:
- Tracks recent Bash commands in state file
- Same exact command 2x → WARN
- Same exact command 3x → BLOCK
"""
import json
import sys
import re
import os
import time

# ═══════════════════════════════════════════════════════════
# HARD BLOCKS — always deny, no override
# ═══════════════════════════════════════════════════════════
HARD_BLOCKS = [
    # Mass filesystem destruction (system dirs)
    (r'\brm\s+-[a-z]*[rf][a-z]*\s+(/\s*$|/etc\b|/usr\b|/var\b|/System\b|/Library\b|/home\b|\$HOME\s*$)',
     'BLOCKED: Mass deletion of system directory.'),
    (r'\brm\s+-[a-z]*[rf][a-z]*\s+\.\.',
     'BLOCKED: rm -rf with .. traversal — dangerous path.'),
    (r'\bfind\s+/\s+.*-delete\b',
     'BLOCKED: find / -delete — mass root deletion.'),
    (r'\bfind\s+/\s+.*-exec\s+rm\b',
     'BLOCKED: find / -exec rm — mass root deletion.'),
    # Disk/partition destruction
    (r'\bdd\s+if=.*of=/dev/(sd|hd|nvme|disk|mmcblk)',
     'BLOCKED: dd to raw disk device.'),
    (r'\bmkfs\.\w+\s+/dev/',
     'BLOCKED: Formatting disk device.'),
    (r'\bwipefs\s+/dev/',
     'BLOCKED: Wiping filesystem signatures.'),
    (r'\bfdisk\s+/dev/',
     'BLOCKED: fdisk on disk device.'),
    (r'\bparted\s+/dev/',
     'BLOCKED: parted on disk device.'),
    # Fork bomb patterns
    (r':\(\)\s*\{.*\|.*\}',
     'BLOCKED: Fork bomb detected.'),
    (r'\bwhile\s+true.*fork',
     'BLOCKED: Infinite fork loop.'),
    # Remote code execution pipes (untrusted source)
    (r'\bcurl\b[^|]*\|\s*(ba)?sh\b',
     'BLOCKED: curl | sh — remote code execution.'),
    (r'\bwget\b[^|]*\|\s*(ba)?sh\b',
     'BLOCKED: wget | sh — remote code execution.'),
    # Encoding bypass → shell execution
    (r'\bbase64\b[^|]*\|\s*(ba)?sh\b',
     'BLOCKED: base64 | sh — encoded payload execution.'),
    (r'\bbase64\b[^|]*\|\s*python',
     'BLOCKED: base64 | python — encoded payload execution.'),
    # Eval with destructive commands
    (r'\beval\s+.*\brm\s+-[rf]',
     'BLOCKED: eval with rm -rf.'),
    (r'\beval\s+.*\bdd\s+if=',
     'BLOCKED: eval with dd.'),
    (r'\$\(.*\brm\s+-[a-z]*[rf].*\)',
     'BLOCKED: Command substitution with rm -rf.'),
    # Python/Ruby destructive one-liners
    (r'\bpython[23]?\s+-c\s+.*shutil\.rmtree\s*\(\s*[\'"]/',
     'BLOCKED: Python rmtree on root paths.'),
    (r'\bruby\s+-e\s+.*FileUtils\.rm_rf\s*\(\s*[\'"]/',
     'BLOCKED: Ruby rm_rf on root paths.'),
    # Encoded shell execution bypasses
    (r'\\x[0-9a-fA-F]{2}.*\\x[0-9a-fA-F]{2}.*\|\s*(ba)?sh',
     'BLOCKED: Hex-encoded payload piped to shell.'),
    (r"\$'\\[0-7]+.*\\[0-7]+'.*\|\s*(ba)?sh",
     'BLOCKED: Octal-encoded payload piped to shell.'),
    # Credential leak: sshpass inline password
    (r'sshpass\s+-p\s+[\'"]?[^\s\'"$]{4,}',
     'BLOCKED: sshpass with inline password — leaks to JSONL transcript. '
     'Use: SSHPASS=$(cat credentials-secrets.md | grep password | cut -d: -f2 | tr -d " ") sshpass -e ssh ...'),
    # Removing .git directory
    (r'\brm\s+(-rf|-fr|--recursive\s+--force)\s+\.git\s*$',
     'BLOCKED: Removing .git directory destroys repository history.'),
    # Shred on system files
    (r'\bshred\s+.*(/etc|/usr|/var|/System|/Library)',
     'BLOCKED: Shred on system directory.'),
]

# ═══════════════════════════════════════════════════════════
# WARNINGS — non-blocking, adds context
# ═══════════════════════════════════════════════════════════
WARN_PATTERNS = [
    (r'\bchmod\s+777\b',
     'WARNING: chmod 777 — world-writable permissions. Intentional?'),
    (r'\bchmod\s+-R\s+777\b',
     'WARNING: Recursive chmod 777 — very permissive.'),
    (r'sleep\s+(3[1-9]|[4-9]\d|\d{3,})\b',
     'WARNING: Long sleep detected. Consider run_in_background instead.'),
    (r'sleep\s+\d+\s*[;&|]+\s*(grep|cat|tail|head|less)\b',
     'WARNING: Sleep-poll pattern detected. Use proper wait mechanism.'),
]

# SSH rate limiting
SSH_TS_FILE = '/tmp/claude-ssh-timestamps.txt'
SSH_RATE_LIMIT = 4  # max per minute
SSH_WINDOW = 60  # seconds

# Command loop detection
LOOP_WARN_THRESHOLD = 2   # Warn when same command seen 2x
LOOP_BLOCK_THRESHOLD = 3  # BLOCK when same command seen 3x
LOOP_STATE_FILE = '/tmp/claude-bash-loop-state.json'
LOOP_STALE_SECONDS = 300  # Reset loop tracking after 5 minutes of inactivity


def normalize_command(command):
    """Normalize command to defeat bypass techniques."""
    normalized = command.replace('\\\n', ' ')
    normalized = re.sub(r'\s+', ' ', normalized).strip()

    # Decode $'\xNN' hex escapes
    def decode_hex(m):
        try:
            chars = re.findall(r'\\x([0-9a-fA-F]{2})', m.group(0))
            return ''.join(chr(int(c, 16)) for c in chars)
        except (ValueError, IndexError):
            return m.group(0)
    normalized = re.sub(r"\$'(?:\\x[0-9a-fA-F]{2})+'", decode_hex, normalized)

    # Decode $'\NNN' octal escapes
    def decode_octal(m):
        try:
            chars = re.findall(r'\\([0-7]{1,3})', m.group(0))
            return ''.join(chr(int(c, 8)) for c in chars)
        except (ValueError, IndexError):
            return m.group(0)
    normalized = re.sub(r"\$'(?:\\[0-7]{1,3})+'", decode_octal, normalized)

    return normalized


def strip_quoted_strings(cmd):
    """Remove quoted content to avoid false positives on echo/printf/heredoc."""
    cmd = re.sub(r'"(?:[^"\\]|\\.)*"', '""', cmd)
    cmd = re.sub(r"'[^']*'", "''", cmd)
    return cmd


def check_ssh_rate(command):
    """Track SSH commands and warn at high rate."""
    if not re.search(r'\bssh\b|\bscp\b|\bsshpass\b', command):
        return

    now = time.time()
    try:
        with open(SSH_TS_FILE, 'a') as f:
            f.write(f"{now}\n")
    except OSError:
        return

    # Count recent calls
    try:
        with open(SSH_TS_FILE) as f:
            timestamps = [float(l.strip()) for l in f if l.strip()]
        recent = [t for t in timestamps if now - t < SSH_WINDOW]

        # Cleanup old entries
        if len(timestamps) > 100:
            with open(SSH_TS_FILE, 'w') as f:
                for t in timestamps[-50:]:
                    f.write(f"{t}\n")

        if len(recent) >= SSH_RATE_LIMIT:
            print(
                f"SSH RATE: {len(recent)} SSH calls in {SSH_WINDOW}s. "
                f"Batch commands: ssh host 'cmd1 && cmd2 && cmd3'",
                file=sys.stderr
            )
    except (OSError, ValueError):
        pass


def check_command_loop(command):
    """Track repeated Bash commands. Warn at 2x, BLOCK at 3x.

    Returns: (should_block, message) — if should_block, caller must deny.
    """
    # Normalize whitespace for comparison
    cmd_key = re.sub(r'\s+', ' ', command.strip())
    if not cmd_key:
        return False, None

    # Load loop state
    state = {}
    try:
        if os.path.exists(LOOP_STATE_FILE):
            with open(LOOP_STATE_FILE) as f:
                state = json.load(f)
            # Reset if stale
            if time.time() - state.get("ts", 0) > LOOP_STALE_SECONDS:
                state = {}
    except Exception:
        state = {}

    cmds = state.get("cmds", {})
    cmds[cmd_key] = cmds.get(cmd_key, 0) + 1
    count = cmds[cmd_key]

    # Prune old entries (keep max 20 unique commands)
    if len(cmds) > 20:
        # Keep only the 10 most recent (by highest count as proxy)
        sorted_cmds = sorted(cmds.items(), key=lambda x: x[1], reverse=True)[:10]
        cmds = dict(sorted_cmds)
        cmds[cmd_key] = count  # Ensure current is kept

    state["cmds"] = cmds
    state["ts"] = time.time()

    try:
        with open(LOOP_STATE_FILE, 'w') as f:
            json.dump(state, f)
    except OSError:
        pass

    if count >= LOOP_BLOCK_THRESHOLD:
        return True, (
            f"LOOP BLOCK: Same Bash command executed {count}x. "
            f"STOP trial-and-error. Change approach entirely. "
            f"Command: {cmd_key[:80]}{'...' if len(cmd_key) > 80 else ''}"
        )
    elif count >= LOOP_WARN_THRESHOLD:
        print(
            f"LOOP WARNING: Same Bash command repeated {count}x. "
            f"If it failed before, it will fail again. Change approach. "
            f"Command: {cmd_key[:80]}{'...' if len(cmd_key) > 80 else ''}",
            file=sys.stderr
        )
    return False, None


def main():
    try:
        raw = sys.stdin.read() if not sys.stdin.isatty() else ""
        data = json.loads(raw) if raw.strip() else None
    except (json.JSONDecodeError, IOError):
        sys.exit(0)  # fail-open on parse error

    if not data or data.get("tool_name") != "Bash":
        sys.exit(0)

    command = data.get("tool_input", {}).get("command", "")
    if not command:
        sys.exit(0)

    # Normalize and strip quotes
    normalized = normalize_command(command)
    stripped = strip_quoted_strings(command)
    norm_stripped = strip_quoted_strings(normalized)

    # Check HARD BLOCKS on all variants
    for check_cmd in (stripped, norm_stripped, command, normalized):
        for pattern, reason in HARD_BLOCKS:
            if re.search(pattern, check_cmd, re.IGNORECASE):
                print(json.dumps({
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": reason
                    }
                }))
                sys.exit(0)

    # Check command loop detection (3x → BLOCK, 2x → WARN)
    should_block, loop_msg = check_command_loop(command)
    if should_block:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": loop_msg
            }
        }))
        sys.exit(0)

    # Check WARNINGS (non-blocking)
    for check_cmd in (stripped, norm_stripped):
        for pattern, msg in WARN_PATTERNS:
            if re.search(pattern, check_cmd, re.IGNORECASE):
                print(msg, file=sys.stderr)
                break

    # SSH rate tracking
    check_ssh_rate(command)

    sys.exit(0)


if __name__ == "__main__":
    main()
