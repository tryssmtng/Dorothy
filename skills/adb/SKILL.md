---
name: adb
description: "KALIYA Android Device Domination — Full phone control via ADB. uiautomator dump for pixel-perfect coordinates, tap/swipe/type, app control, file ops, system settings, screenshot proof, auto-cleanup (ZERO temp file bloat). Use when: adb, android, phone, device, tap, click, swipe, type, install, screenshot, app, logcat, wifi adb, notification, permission, gps, clipboard, unlock, settings, automation, ui dump, coordinates."
argument-hint: "[task description or adb command]"
allowed-tools: Bash, Read, Write, Glob, Grep
---

# KALIYA Android Device Domination — Military Grade

Full phone control via ADB. Pixel-perfect precision. Auto-cleanup. Zero bloat.

## Task: `$ARGUMENTS`

If no task described, run device detection + status report.

---

## PHASE 0: DEVICE LOCK-ON (ALWAYS FIRST — NO EXCEPTIONS)

```bash
# Detect all connected devices
adb devices -l
```

**Decision Matrix:**
| Scenario | Action |
|---|---|
| 1 device connected | Auto-use, proceed |
| Multiple devices | Ask Malik which one, set `SERIAL=<chosen>`, prefix ALL commands with `adb -s $SERIAL` |
| 0 devices | Check: `adb kill-server && adb start-server && adb devices -l`. Still 0? Ask Malik to check USB/WiFi |
| Unauthorized | Tell Malik to tap "Allow USB debugging" on phone |

**Device Info Snapshot (run once on first connect):**
```bash
SERIAL=$(adb devices | grep -w "device" | head -1 | awk '{print $1}')
MODEL=$(adb -s $SERIAL shell getprop ro.product.model)
ANDROID=$(adb -s $SERIAL shell getprop ro.build.version.release)
SDK=$(adb -s $SERIAL shell getprop ro.build.version.sdk)
RESOLUTION=$(adb -s $SERIAL shell wm size | awk '{print $NF}')
DENSITY=$(adb -s $SERIAL shell wm density | awk '{print $NF}')
ROOT=$(adb -s $SERIAL shell su -c id 2>/dev/null && echo "YES" || echo "NO")
echo "Device: $MODEL | Android: $ANDROID | SDK: $SDK | Res: $RESOLUTION | DPI: $DENSITY | Root: $ROOT"
```

---

## PHASE 1: UI INTELLIGENCE — uiautomator Dump & Parse

**IRON RULE: NEVER guess coordinates. ALWAYS dump → parse → calculate → act.**

### 1.1 — Fast Dump (pipe directly, no file on phone)

**Method A — Direct pipe (FAST, no file created on phone):**
```bash
adb shell uiautomator dump /dev/tty 2>/dev/null | head -1 > /tmp/ui_dump.xml
```

**Method B — Standard (if Method A fails on some devices):**
```bash
adb shell uiautomator dump /sdcard/ui_dump.xml && adb pull /sdcard/ui_dump.xml /tmp/ui_dump.xml && adb shell rm /sdcard/ui_dump.xml
```
Note: **rm immediately after pull** — zero bloat.

### 1.2 — Smart Element Search

**Search Priority (most reliable first):**

```bash
# 1. By resource-id (most reliable)
grep -oP 'resource-id="[^"]*target[^"]*"[^>]*bounds="[^"]*"' /tmp/ui_dump.xml

# 2. By visible text (exact match)
grep -oP 'text="Target Text"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"' /tmp/ui_dump.xml

# 3. By text (case-insensitive partial)
grep -i 'text="[^"]*target[^"]*"' /tmp/ui_dump.xml

# 4. By content-desc
grep -i 'content-desc="[^"]*target[^"]*"' /tmp/ui_dump.xml

# 5. By class + clickable (buttons, inputs)
grep 'class="android.widget.Button".*clickable="true"' /tmp/ui_dump.xml
grep 'class="android.widget.EditText"' /tmp/ui_dump.xml

# 6. ALL clickable elements (full interaction map)
grep 'clickable="true"' /tmp/ui_dump.xml | grep -oP '(text|resource-id|content-desc)="[^"]*".*?bounds="\[[^\]]*\]\[[^\]]*\]"'
```

### 1.3 — Coordinate Extraction & Center Calculation

**WORKFLOW — Do NOT skip steps:**
1. Dump UI (section 1.1)
2. Run the Full Screen Map script (section 1.4) — gives ALL elements with their CENTER coordinates
3. Read the map output, find the target element by text/resource-id/description
4. Use the EXACT `[x,y]` center coordinates from the map — **NEVER calculate manually, NEVER guess**
5. `adb shell input tap <x> <y>` with those exact coordinates

**Manual extraction (fallback only — prefer the Full Screen Map above):**
```bash
# Extract bounds and calculate tap center
# bounds="[540,1200][900,1350]" → center: x=(540+900)/2=720, y=(1200+1350)/2=1275

# One-liner: extract bounds for element with matching text, calculate center
grep -i 'text="Login"' /tmp/ui_dump.xml | grep -oP 'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"' | head -1 | \
  sed 's/bounds="\[\([0-9]*\),\([0-9]*\)\]\[\([0-9]*\),\([0-9]*\)\]"/\1 \2 \3 \4/' | \
  awk '{printf "Tap: %d %d\n", ($1+$3)/2, ($2+$4)/2}'
```

### 1.4 — Full Screen Map (all elements with class, bounds, center)

```bash
# Generate complete interaction map: element → center coordinates + class + bounds
# Output sorted by Y coordinate (top to bottom = natural screen reading order)
python3 -c "
import xml.etree.ElementTree as ET, sys
try:
    tree = ET.parse('/tmp/ui_dump.xml')
    rows = []
    for elem in tree.iter():
        bounds = elem.get('bounds','')
        if not bounds: continue
        text = elem.get('text','')
        rid = elem.get('resource-id','')
        desc = elem.get('content-desc','')
        click = elem.get('clickable','')
        enabled = elem.get('enabled','')
        clsname = elem.get('class','')
        if not (text or rid or desc): continue
        parts = bounds.replace('][',',').replace('[','').replace(']','').split(',')
        x1,y1,x2,y2 = int(parts[0]),int(parts[1]),int(parts[2]),int(parts[3])
        cx, cy = (x1+x2)//2, (y1+y2)//2
        label = text or rid.split('/')[-1] or desc
        shortclass = clsname.split('.')[-1] if clsname else '?'
        flags = f\"click={'Y' if click=='true' else 'N'} en={'Y' if enabled=='true' else 'N'}\"
        rows.append((cy, cx, f'  [{cx:4d},{cy:4d}] [{x1},{y1}][{x2},{y2}] {shortclass:<20s} {flags} | {label[:55]}'))
    # Header
    print(f\"  {'CENTER':>11s}  {'BOUNDS':>21s} {'CLASS':<20s} {'FLAGS':>10s} | LABEL\")
    print('  ' + '-'*110)
    # Sort by Y (top of screen first), then X
    for _, _, line in sorted(rows, key=lambda r: (r[0], r[1])):
        print(line)
except Exception as e:
    print(f'Parse error: {e}', file=sys.stderr)
"
```
**Key columns:** CENTER = exact tap coordinates. BOUNDS = element rectangle. CLASS = widget type (Button, TextView, EditText, etc). FLAGS = clickable + enabled.

### 1.5 — MANDATORY WORKFLOW: Dump-Map-Act (follow this EVERY time)

**NEVER skip this sequence. NEVER guess coordinates. NEVER calculate manually.**

```
1. DUMP:   adb shell uiautomator dump /dev/tty 2>/dev/null | head -1 > /tmp/ui_dump.xml
2. MAP:    Run the Full Screen Map Python script (section 1.4)
3. FIND:   Read the map output — locate target element by text/id/desc
           Note its EXACT [x,y] center coordinates from the map
4. ACT:    adb shell input tap <x> <y>   ← coordinates FROM MAP, never invented
5. WAIT:   sleep 1-2 (UI needs render time for transitions)
6. VERIFY: Screenshot with resize:
           adb shell screencap /sdcard/_sc.png && adb pull /sdcard/_sc.png /tmp/adb_screen.png && adb shell rm /sdcard/_sc.png && sips --resampleHeightWidthMax 1600 /tmp/adb_screen.png >/dev/null 2>&1
           Read screenshot → verify correct element was activated
           rm -f /tmp/adb_screen.png   ← delete after viewing
7. RETRY:  If wrong element tapped or target not found:
           → Scroll (swipe up/down) → re-DUMP → re-MAP → find again → tap
           → NEVER re-tap same coordinates hoping for different result
```

**Common mistakes this prevents:**
- Guessing coordinates from memory → WRONG TAP
- Calculating center manually (arithmetic errors) → WRONG TAP
- Tapping stale coordinates after screen change → WRONG TAP
- Not scrolling when element is off-screen → ELEMENT NOT FOUND

---

## PHASE 2: INPUT ACTIONS — Precision Control

### 2.1 — Tap

```bash
# Single tap
adb shell input tap <x> <y>

# Double tap
adb shell input tap <x> <y> && sleep 0.1 && adb shell input tap <x> <y>

# Long press (swipe same point, 1500ms duration)
adb shell input swipe <x> <y> <x> <y> 1500
```

### 2.2 — Swipe & Scroll

```bash
# Scroll DOWN (swipe up) — standard scroll
adb shell input swipe 540 1500 540 500 300

# Scroll UP (swipe down)
adb shell input swipe 540 500 540 1500 300

# Swipe LEFT (next page)
adb shell input swipe 900 1000 100 1000 250

# Swipe RIGHT (previous page)
adb shell input swipe 100 1000 900 1000 250

# SLOW scroll (for precise lists)
adb shell input swipe 540 1200 540 900 500

# FAST fling
adb shell input swipe 540 1500 540 200 100

# Pinch zoom (needs 2 simultaneous inputs — use sendevent or input motionevent on Android 13+)
```

### 2.3 — Text Input

```bash
# Simple text (no spaces, no special chars)
adb shell input text "hello123"

# Text with spaces (encode as %s)
adb shell input text "hello%sworld%stest"

# FAST text input (ADBKeyboard method — if installed):
adb shell am broadcast -a ADB_INPUT_TEXT --es msg "Any text with spaces & special chars!"

# Clear text field (select all + delete)
adb shell input keyevent 29 113  # Ctrl+A (select all) — KEYCODE_A + META_CTRL
adb shell input keyevent 67      # DELETE

# Better clear: long press + select all + delete
adb shell input swipe <x> <y> <x> <y> 1500  # long press on field
sleep 0.3
adb shell input keyevent 29      # 'a' with ctrl (select all via menu if visible)
adb shell input keyevent 67      # delete
```

### 2.4 — Key Events (Complete Reference)

```bash
# Navigation
adb shell input keyevent 3    # HOME
adb shell input keyevent 4    # BACK
adb shell input keyevent 187  # RECENTS / APP_SWITCH
adb shell input keyevent 82   # MENU
adb shell input keyevent 66   # ENTER
adb shell input keyevent 61   # TAB
adb shell input keyevent 67   # BACKSPACE/DELETE
adb shell input keyevent 112  # DELETE_FORWARD

# Power & Lock
adb shell input keyevent 26   # POWER (toggle screen on/off)
adb shell input keyevent 224  # WAKEUP
adb shell input keyevent 223  # SLEEP
adb shell input keyevent 276  # SOFT_SLEEP

# Volume & Media
adb shell input keyevent 24   # VOLUME_UP
adb shell input keyevent 25   # VOLUME_DOWN
adb shell input keyevent 164  # MUTE
adb shell input keyevent 85   # PLAY/PAUSE
adb shell input keyevent 86   # STOP
adb shell input keyevent 87   # NEXT
adb shell input keyevent 88   # PREVIOUS

# Camera
adb shell input keyevent 27   # CAMERA
adb shell input keyevent 80   # FOCUS

# Misc
adb shell input keyevent 176  # SETTINGS
adb shell input keyevent 221  # BRIGHTNESS_UP
adb shell input keyevent 220  # BRIGHTNESS_DOWN
adb shell input keyevent 231  # VOICE_ASSIST (Google Assistant)
```

---

## PHASE 3: SCREEN CAPTURE & VERIFICATION

**RULE: Screenshot AFTER every action to verify it worked.**

### 3.1 — Screenshot (fast, auto-resize, auto-cleanup)

```bash
# Capture + pull + resize + cleanup phone — ALL in one chain
# WHY resize: Claude API many-image limit = 2000px. We resize to 1600px (safe margin)
# to prevent "exceeds dimension limit for many-image requests" errors in long sessions.
# sips is macOS built-in — no install needed.
adb shell screencap /sdcard/_sc.png && adb pull /sdcard/_sc.png /tmp/adb_screen.png && adb shell rm /sdcard/_sc.png && sips --resampleHeightWidthMax 1600 /tmp/adb_screen.png >/dev/null 2>&1
```
Then use **Read tool** to VIEW the screenshot (multimodal — see what's on screen).
After viewing, **delete immediately** — image is in Claude's context, file is waste:
```bash
rm -f /tmp/adb_screen.png
```

### 3.2 — Screen Recording

```bash
# Record 10 seconds (max 180s)
adb shell screenrecord /sdcard/_rec.mp4 --time-limit 10
# Pull + cleanup
adb pull /sdcard/_rec.mp4 /tmp/adb_recording.mp4 && adb shell rm /sdcard/_rec.mp4
```

### 3.3 — Screen State Check

```bash
# Is screen ON or OFF?
adb shell dumpsys power | grep "mWakefulness" | awk -F= '{print $2}'
# Display state: ON/OFF/DOZE
adb shell dumpsys display | grep "mScreenState"
# Is device locked?
adb shell dumpsys window | grep "mDreamingLockscreen"
```

---

## PHASE 4: APP MANAGEMENT

```bash
# Foreground app (what's on screen now)
adb shell dumpsys activity activities | grep -E "mResumedActivity|topResumedActivity" | head -1

# List packages (filtered)
adb shell pm list packages | grep <keyword>
# List 3rd-party apps only
adb shell pm list packages -3
# App info
adb shell dumpsys package <pkg> | grep -E "versionName|versionCode|firstInstallTime|lastUpdateTime|dataDir"

# Launch app
adb shell monkey -p <pkg> -c android.intent.category.LAUNCHER 1
# Launch specific activity
adb shell am start -n <pkg>/<activity>
# Launch with deep link
adb shell am start -a android.intent.action.VIEW -d "https://example.com"

# Force stop
adb shell am force-stop <pkg>
# Clear data (DESTRUCTIVE — resets app)
adb shell pm clear <pkg>

# Install APK
adb install -r -g /path/to/app.apk  # -r=replace, -g=grant all permissions
# Install split APKs
adb install-multiple -r base.apk split1.apk split2.apk
# Uninstall
adb shell pm uninstall <pkg>
# Uninstall but keep data
adb shell pm uninstall -k <pkg>

# Disable/Enable app
adb shell pm disable-user --user 0 <pkg>
adb shell pm enable <pkg>

# List running services
adb shell dumpsys activity services | grep <pkg>
# Kill background processes
adb shell am kill <pkg>
```

---

## PHASE 5: FILE OPERATIONS (with cleanup awareness)

```bash
# Push file to device
adb push /local/path /sdcard/path
# Pull file from device
adb pull /sdcard/path /local/path

# List files
adb shell ls -la /sdcard/
adb shell ls -laR /sdcard/Download/

# Read file on device (small files)
adb shell cat /sdcard/file.txt

# Delete file
adb shell rm /sdcard/file.txt
# Delete directory
adb shell rm -rf /sdcard/temp_dir/

# Check storage
adb shell df -h /sdcard
adb shell du -sh /sdcard/DCIM /sdcard/Download /sdcard/Android

# SharedPreferences (ROOT)
adb shell su -c "cat /data/data/<pkg>/shared_prefs/*.xml"
# Database (ROOT)
adb shell su -c "sqlite3 /data/data/<pkg>/databases/db.sqlite '.tables'"
adb shell su -c "sqlite3 /data/data/<pkg>/databases/db.sqlite 'SELECT * FROM users LIMIT 10;'"
```

---

## PHASE 6: SYSTEM CONTROL

### 6.1 — Network

```bash
# WiFi ON/OFF
adb shell svc wifi enable
adb shell svc wifi disable
# WiFi info
adb shell dumpsys wifi | grep "mWifiInfo" | head -3
# IP address
adb shell ip addr show wlan0 | grep "inet "

# Mobile data ON/OFF
adb shell svc data enable
adb shell svc data disable

# Airplane mode
adb shell settings put global airplane_mode_on 1
adb shell am broadcast -a android.intent.action.AIRPLANE_MODE --ez state true
# Airplane OFF
adb shell settings put global airplane_mode_on 0
adb shell am broadcast -a android.intent.action.AIRPLANE_MODE --ez state false

# WiFi ADB connect (device must be on same network)
adb tcpip 5555
# Then: adb connect <device-ip>:5555
```

### 6.2 — Display & Sound

```bash
# Brightness (0-255)
adb shell settings put system screen_brightness 128
adb shell settings put system screen_brightness_mode 0  # manual mode

# Screen timeout (ms)
adb shell settings put system screen_off_timeout 600000  # 10 min

# Screen rotation
adb shell settings put system accelerometer_rotation 0  # disable auto
adb shell settings put system user_rotation 0  # 0=portrait, 1=landscape, 2=reverse-portrait, 3=reverse-landscape

# Volume (0-15 typically)
adb shell media volume --stream 3 --set 10  # music
adb shell media volume --stream 2 --set 7   # ring
adb shell media volume --stream 1 --set 0   # system (silent)

# DND mode
adb shell settings put global zen_mode 1     # priority only
adb shell settings put global zen_mode 2     # total silence
adb shell settings put global zen_mode 0     # off
```

### 6.3 — Location & GPS

```bash
# Enable GPS
adb shell settings put secure location_mode 3  # high accuracy
# Disable
adb shell settings put secure location_mode 0

# Mock location (needs developer option enabled + mock location app)
# Use Frida or dedicated app for GPS spoofing
```

### 6.4 — Clipboard

```bash
# Set clipboard (Android 10+, may need root or accessibility service)
adb shell am broadcast -a clipper.set -e text "copied text"
# Get clipboard
adb shell am broadcast -a clipper.get
# Alternative using service call (device-specific)
adb shell service call clipboard 1 s16 "text to copy"
```

### 6.5 — Notifications

```bash
# Read current notifications
adb shell dumpsys notification --noredact | grep -A5 "NotificationRecord"
# Dismiss all notifications
adb shell service call notification 1
# Expand notification shade
adb shell cmd statusbar expand-notifications
# Collapse
adb shell cmd statusbar collapse
# Expand quick settings
adb shell cmd statusbar expand-settings
```

### 6.6 — Permissions

```bash
# Grant permission
adb shell pm grant <pkg> android.permission.CAMERA
adb shell pm grant <pkg> android.permission.READ_EXTERNAL_STORAGE
adb shell pm grant <pkg> android.permission.ACCESS_FINE_LOCATION
# Revoke permission
adb shell pm revoke <pkg> android.permission.CAMERA
# List permissions for app
adb shell dumpsys package <pkg> | grep "granted=true"
```

### 6.7 — Battery & Power

```bash
# Battery status
adb shell dumpsys battery
# Fake battery level (for testing)
adb shell dumpsys battery set level 5
adb shell dumpsys battery set status 1  # 1=unknown, 2=charging, 3=discharging
# Reset to real values
adb shell dumpsys battery reset

# Keep screen on while charging
adb shell settings put global stay_on_while_plugged_in 3
```

### 6.8 — Logcat & Debugging

```bash
# Filtered logcat (last 50 lines)
adb logcat -d -s <TAG>:* | tail -50
# Grep keyword from recent logs
adb logcat -d | grep -i "<keyword>" | tail -30
# Clear log buffer
adb logcat -c
# Live logcat with filter (background — Ctrl+C to stop)
adb logcat <TAG>:V *:S
# Crash logs
adb logcat -d -b crash | tail -30

# ANR traces
adb shell cat /data/anr/traces.txt 2>/dev/null | head -100
# Tombstones (native crashes, ROOT)
adb shell su -c "ls /data/tombstones/" 2>/dev/null
```

---

## PHASE 7: ADVANCED AUTOMATION PATTERNS

### 7.1 — Full UI Automation Cycle

**The Standard Loop (use for ANY UI task):**
```
1. Dump UI → parse elements → build interaction map
2. Identify target element → calculate center coordinates
3. Act (tap/type/swipe) → wait (sleep 1-2s for transition)
4. Verify (screenshot with resize to 1600px + new dump) → did it work?
5. If YES → next action. If NO → retry or scroll to find element.
6. CLEANUP: rm temp files on phone after task complete
```

### 7.2 — Scroll-Until-Found

```bash
MAX_SCROLLS=15
for i in $(seq 1 $MAX_SCROLLS); do
  adb shell uiautomator dump /dev/tty 2>/dev/null | head -1 > /tmp/ui_dump.xml
  if grep -qi "target_text" /tmp/ui_dump.xml; then
    echo "FOUND at scroll $i"
    # Extract coordinates and tap
    break
  fi
  adb shell input swipe 540 1500 540 600 300
  sleep 0.8
done
```

### 7.3 — Wait-For-Element (smart wait, not blind sleep)

```bash
MAX_WAIT=10
for i in $(seq 1 $MAX_WAIT); do
  adb shell uiautomator dump /dev/tty 2>/dev/null | head -1 > /tmp/ui_dump.xml
  if grep -qi "expected_element" /tmp/ui_dump.xml; then
    echo "Element appeared after ${i}s"
    break
  fi
  sleep 1
done
```

### 7.4 — Screen Unlock

```bash
# Wake up
adb shell input keyevent 224
sleep 0.5
# Swipe up to dismiss lock screen (no PIN)
adb shell input swipe 540 1800 540 800 300
# PIN unlock (example: 1234)
sleep 0.5
adb shell input text "1234"
adb shell input keyevent 66  # ENTER
# Pattern unlock — use swipe between dots
```

### 7.5 — Multi-Step Task Template

```bash
# Example: Open app → navigate → perform action → verify → cleanup

# Step 1: Launch
adb shell monkey -p com.target.app -c android.intent.category.LAUNCHER 1
sleep 3

# Step 2: Dump + find target
adb shell uiautomator dump /dev/tty 2>/dev/null | head -1 > /tmp/ui_dump.xml
# Parse, find coordinates...

# Step 3: Tap target
adb shell input tap <x> <y>
sleep 1.5

# Step 4: Verify (capture + resize to 1600px for Claude API limit)
adb shell screencap /sdcard/_sc.png && adb pull /sdcard/_sc.png /tmp/adb_screen.png && adb shell rm /sdcard/_sc.png && sips --resampleHeightWidthMax 1600 /tmp/adb_screen.png >/dev/null 2>&1
# Read screenshot to verify, then delete local copy immediately after viewing
# rm -f /tmp/adb_screen.png

# Step 5: Continue or done
```

### 7.6 — Batch Actions (multiple taps in sequence)

```bash
# Define action sequence: x y sleep_after
actions="540 800 1.0
540 1200 1.5
720 600 1.0
360 1400 2.0"

echo "$actions" | while read x y wait; do
  adb shell input tap $x $y
  sleep $wait
done
```

---

## PHASE 8: CLEANUP PROTOCOL — ZERO BLOAT

**MANDATORY after every operation session. Phone and /tmp MUST be clean.**

### 8.1 — Phone Cleanup (pattern-based, not hardcoded)

```bash
# Remove ALL known temp files from phone
adb shell "rm -f /sdcard/_sc.png /sdcard/ui_dump.xml /sdcard/_rec.mp4 /sdcard/before.xml /sdcard/after.xml /sdcard/screen.png /sdcard/recording.mp4" 2>/dev/null

# Remove any custom-named screenshots created during automation (common patterns from real sessions)
adb shell "rm -f /sdcard/screen*.png /sdcard/99a_*.png /sdcard/mb_*.png /sdcard/housing_*.png" 2>/dev/null

# Remove any stray XML dumps
adb shell "rm -f /sdcard/*.xml" 2>/dev/null

# VERIFY phone is clean — list any remaining png/xml on sdcard root
adb shell "ls /sdcard/*.png /sdcard/*.xml 2>/dev/null" || echo "Phone clean — no stray files"
```

### 8.2 — Local /tmp Cleanup (pattern-based)

```bash
# Clean standard temp files from this automation session
rm -f /tmp/ui_dump.xml /tmp/adb_screen.png /tmp/adb_screenshot.png /tmp/adb_recording.mp4 2>/dev/null

# Clean custom-named screenshots pulled from device (common patterns from real sessions)
rm -f /tmp/99a_*.png /tmp/mb_*.png /tmp/housing_*.png /tmp/screen*.png 2>/dev/null

# VERIFY local is clean
ls /tmp/adb_*.png /tmp/ui_dump.xml /tmp/*_screen*.png 2>/dev/null || echo "Local clean — no stray files"
```

### 8.3 — Inline Cleanup Rule (during operations)

**After EVERY screenshot Read (verified), delete the local file immediately:**
```bash
# Pattern: capture → pull → resize → Read (view in Claude) → delete local copy
# The image is already in Claude's context after Read — keeping the file is waste
rm -f /tmp/adb_screen.png
```

### 8.4 — Anti-Bloat Rules (NON-NEGOTIABLE)

- **NEVER leave screenshots on phone after pulling** — chain `&& adb shell rm` to every pull command
- **NEVER leave local /tmp screenshots after Read** — delete immediately after viewing
- **NEVER use bare `screencap` without the full capture+pull+resize+cleanup chain** from section 3.1
- `adb shell uiautomator dump /dev/tty` — dump to stdout, no file on phone at all
- During operations, use `_sc.png` and `ui_dump.xml` as temp names (underscore prefix = temp)
- If session interrupted mid-task, run full cleanup on next connect
- **Session end = phone and /tmp MUST be clean.** Verify with:
  ```bash
  adb shell "ls /sdcard/*.png /sdcard/*.xml 2>/dev/null" && echo "WARNING: stray files on phone!" || echo "Phone clean"
  ls /tmp/adb_*.png /tmp/ui_dump.xml 2>/dev/null && echo "WARNING: stray files in /tmp!" || echo "Local clean"
  ```

**LAST STEP of any ADB session = run full cleanup (8.1 + 8.2). No exceptions. Non-negotiable.**

---

## IRON RULES — NON-NEGOTIABLE

1. **DEVICE CHECK FIRST** — `adb devices -l` before ANY command. No device = STOP.
2. **DUMP BEFORE TAP** — NEVER guess coordinates. uiautomator dump → parse → calculate center → THEN tap.
3. **SCREENSHOT TO VERIFY** — After every significant action, screenshot + view to confirm.
4. **CLEANUP ALWAYS** — Every temp file created on phone = deleted after use. Phone stays clean.
5. **WAIT BETWEEN ACTIONS** — `sleep 1-2` after taps/transitions. UI needs render time.
6. **ROOT = CHECK FIRST** — Before any `su -c` command, verify root with `adb shell su -c id`.
7. **FAST PATH PREFERRED** — Direct pipe (`/dev/tty`) over file creation. Pull+delete over leave-on-device.
8. **ERROR RECOVERY** — Element not found? Scroll. Screen changed? Re-dump. App crashed? Relaunch + retry.
9. **EVIDENCE** — Screenshots at key steps. Malik sees what happened on device.
10. **MULTI-DEVICE** — If multiple devices, ALWAYS use `adb -s $SERIAL` for every command.

---

## KALIYA COMPLIANCE

### Output Standards
- **Structured completion report** — EVERY skill execution ends with:
  ```
  Done | [task summary]
  ├── Files: [modified files]
  ├── Verified: [how — compile, test, screenshot]
  └── Next: [pending or "Aur kuch?"]
  ```
- **Tables for 3+ items** — never list 3+ things as plain text
- **Evidence for every "done"** — build pass, test output, file read, screenshot

### Context Efficiency
- Check memory files for relevant context before starting work
- Check `~/.claude/projects/-Users-niwash/memory/mistakes-learnings.md` for known gotchas
- Budget tool calls: don't waste main thread context on things agents should do

### Quality Gates
- **Zero TODOs/placeholders** — write REAL code, never stubs
- **Read before edit** — ALWAYS read full file before modifying
- **Verify after change** — compile/test/screenshot before claiming done
- **No fake values** — never generate dummy data, fake URLs, placeholder functions
