---
name: speak
description: "Toggle KALIYA TTS — speaks assistant responses aloud via Sarvam AI. Multi-session: ALL terminals with TTS enabled speak simultaneously. Use when: speak, tts, voice output, read aloud, stop speaking, mute."
argument-hint: "[on/off/status/stop/test/speaker <name>/pace <value>]"
---

# KALIYA TTS Control — /speak

Controls the Sarvam AI Text-to-Speech daemon. Multi-session: ALL terminals where TTS is enabled speak simultaneously.

## Command: `$ARGUMENTS`

Parse the command from arguments. Default (no args) = toggle on/off.

## Commands

### `on` or no args (toggle) — Enable TTS for THIS session

1. Find current session's JSONL file:
```bash
# IMPORTANT: Use the session ID from the conversation context (system-reminder has it)
# Extract session ID and find exact JSONL — NEVER use ls -t (picks wrong session)
# The session ID is visible in system-reminder like: "ID: e72b792e-0d59-48dd-b960-f5682f3e9c6d"
JSONL_PATH=$(find ~/.claude/projects/ -name "<SESSION_ID>*.jsonl" 2>/dev/null | head -1)
echo "Session JSONL: $JSONL_PATH"
```
**CRITICAL:** Replace `<SESSION_ID>` with the actual session ID from the current conversation's system-reminder. NEVER use `ls -t` — it picks whichever session was modified last, which could be a DIFFERENT terminal.

2. Start daemon if not running:
```bash
if [ -f /tmp/kaliya-tts-daemon.pid ] && kill -0 $(cat /tmp/kaliya-tts-daemon.pid) 2>/dev/null; then
    echo "Daemon already running"
else
    python3 ~/.claude/tools/sarvam-tts-daemon.py --daemon
fi
```

3. Register this session in the multi-session directory:
```bash
mkdir -p /tmp/kaliya-tts-sessions
echo "$JSONL_PATH" > /tmp/kaliya-tts-sessions/<SESSION_ID>
```

4. Report: "TTS ON for this session. Speaker: shubh, language: hi-IN."

### `off` — Disable TTS for THIS session (keep daemon alive for other sessions)

1. Remove THIS session's file from the directory:
```bash
rm -f /tmp/kaliya-tts-sessions/<SESSION_ID>
```

2. Stop current playback:
```bash
touch /tmp/kaliya-tts-stop
```

3. Report: "TTS OFF for this session. Daemon still alive for other sessions — `/speak on` se wapas chalu."

### `stop` — Kill daemon completely (stops ALL sessions)

```bash
python3 ~/.claude/tools/sarvam-tts-daemon.py --stop
```

This kills the daemon AND removes `/tmp/kaliya-tts-sessions/` directory entirely.

Report: "TTS daemon stopped. ALL sessions silenced. `/speak on` se restart."

### `status` — Check state

```bash
python3 ~/.claude/tools/sarvam-tts-daemon.py --status
```

Show: daemon running/stopped, how many sessions active, which JSONLs.

### `test` or `test <text>` — Test TTS

```bash
# Default test
python3 ~/.claude/tools/sarvam-tts-daemon.py --test "KALIYA TTS test. Sab sahi chal rha hai Malik."

# Custom text
python3 ~/.claude/tools/sarvam-tts-daemon.py --test "<user text>"
```

### `speaker <name>` — Change voice

Available Hindi male speakers: amit, aditya, rahul, rohan, dev, kabir, varun, manan, sumit, shubh

```bash
export SARVAM_TTS_SPEAKER=<name>
python3 ~/.claude/tools/sarvam-tts-daemon.py --stop
python3 ~/.claude/tools/sarvam-tts-daemon.py --daemon
# Re-enable for current session
mkdir -p /tmp/kaliya-tts-sessions
JSONL_PATH=$(find ~/.claude/projects/ -name "<SESSION_ID>*.jsonl" 2>/dev/null | head -1)
echo "$JSONL_PATH" > /tmp/kaliya-tts-sessions/<SESSION_ID>
```

Report: "Speaker changed to <name>. Restart kiya."

### `pace <value>` — Change speed (0.5-2.0)

```bash
export SARVAM_TTS_PACE=<value>
python3 ~/.claude/tools/sarvam-tts-daemon.py --stop
python3 ~/.claude/tools/sarvam-tts-daemon.py --daemon
mkdir -p /tmp/kaliya-tts-sessions
JSONL_PATH=$(find ~/.claude/projects/ -name "<SESSION_ID>*.jsonl" 2>/dev/null | head -1)
echo "$JSONL_PATH" > /tmp/kaliya-tts-sessions/<SESSION_ID>
```

### `log` — Show recent TTS log

```bash
tail -20 /tmp/kaliya-tts-daemon.log
```

## Toggle Behavior (no args)

If no argument given:
- TTS currently OFF for this session -> turn ON (start daemon + register session)
- TTS currently ON for this session -> turn OFF (remove session file, keep daemon)

Check state: `[ -f /tmp/kaliya-tts-sessions/<SESSION_ID> ]`

## Multi-Session Architecture

- `/tmp/kaliya-tts-sessions/` is a directory containing one file per active TTS session
- Each file is named by session ID and contains the FULL PATH to that session's JSONL
- Daemon monitors ALL files in this directory — ALL enabled sessions speak simultaneously
- `/speak on` in terminal A creates `/tmp/kaliya-tts-sessions/<A_SESSION_ID>`
- `/speak on` in terminal B creates `/tmp/kaliya-tts-sessions/<B_SESSION_ID>`
- Both terminals speak independently — no overwriting, no conflicts
- `/speak off` only removes THIS session's file — other sessions unaffected
- `/speak stop` kills daemon and removes entire directory (stops ALL sessions)
- Daemon auto-detects new/removed sessions every 2 seconds
- Stale entries (JSONL file deleted) are auto-cleaned by the daemon
- Backward compat: old `/tmp/kaliya-tts-session` single file is auto-migrated to the directory
- Log: `/tmp/kaliya-tts-daemon.log`
- PID: `/tmp/kaliya-tts-daemon.pid`
- Sessions dir: `/tmp/kaliya-tts-sessions/`
