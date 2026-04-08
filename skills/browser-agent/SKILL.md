---
name: browser-agent
description: "Hyper-intelligent browser automation with isolated Chrome profile, military-grade session/tab management, zero duplicate tabs, snapshot-driven interaction. Keywords: browse, browser, chrome, automation, scrape, screenshot, web, navigate."
allowed-tools: Bash
argument-hint: "[url or command]"
---

# Browser Agent — Military-Grade Browser Control

## CORE PRINCIPLES

1. **ISOLATED PROFILE** — Dedicated Chrome profile at `~/.claude/browser-profiles/${S}/`. Zero contamination with personal browsing.
2. **ZERO DUPLICATE TABS** — Before opening ANY URL, check all existing tabs. URL already open? Switch to it.
3. **ZERO DUPLICATE BROWSERS** — Before opening ANY browser, check session status. Already open? Navigate, don't re-open.
4. **SESSION PERSISTENCE** — Login once, stay logged in forever via `--persistent` flag.
5. **SNAPSHOT-FIRST** — NEVER interact without snapshot. Period.

---

## ISOLATED PROFILE SETUP

```bash
# Dynamic session name — project-based, NEVER hardcoded
S="$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" | tr '[:upper:]' '[:lower:]' | tr ' _' '--')"
# Guard: dot-prefixed dirs (e.g. .claude) → use "default"
[[ "$S" == .* ]] && S="default"

# KALIYA Browser Profile — ALWAYS use this path
export KALIYA_BROWSER_PROFILE="$HOME/.claude/browser-profiles/${S}"
```

**Why isolated profile?**
- Personal browser cookies/history/extensions = NEVER touched
- Agent has its OWN logins, cookies, localStorage
- Clean separation = zero side effects on personal browsing
- Crash recovery = only agent profile affected
- Dynamic session name = project-isolated, zero cross-project contamination

---

## SESSION MANAGEMENT — IRON PROTOCOL

### Session Check (MANDATORY before EVERY browser interaction)

```bash
S="$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" | tr '[:upper:]' '[:lower:]' | tr ' _' '--')"

# Check if session already open
SESSION_STATUS=$(playwright-cli list 2>&1 | grep -c "${S}.*open" || true)

if [ "$SESSION_STATUS" -gt 0 ]; then
    echo "SESSION_ACTIVE"
else
    echo "SESSION_CLOSED"
fi
```

### Opening Browser (check-before-open — MANDATORY)

```bash
S="$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" | tr '[:upper:]' '[:lower:]' | tr ' _' '--')"

# Pre-flight: check existing session BEFORE opening
SESSION_STATUS=$(playwright-cli list 2>&1 | grep -c "${S}.*open" || true)

if [ "$SESSION_STATUS" -gt 0 ]; then
    # ALREADY OPEN — just navigate (no duplicate browser)
    playwright-cli -s=$S goto "$TARGET_URL"
else
    # NOT OPEN — launch with isolated profile
    # Default: headless (no --headed). Use --headed ONLY when Malik explicitly wants to watch.
    PLAYWRIGHT_MCP_VIEWPORT_SIZE=1440x900 \
    playwright-cli -s=$S open "$TARGET_URL" --persistent
fi
```

### Navigating (session already open)

```bash
S="$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" | tr '[:upper:]' '[:lower:]' | tr ' _' '--')"
playwright-cli -s=$S goto "$TARGET_URL"
```

---

## TAB MANAGEMENT — ZERO DUPLICATION PROTOCOL

### Before Opening ANY URL — Check Existing Tabs

```bash
S="$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" | tr '[:upper:]' '[:lower:]' | tr ' _' '--')"

# Step 1: Get all open tabs
TABS=$(playwright-cli -s=$S tab-list 2>&1)

# Step 2: Check if target URL (or its domain) is already open
TARGET_URL="https://example.com/page"
TARGET_DOMAIN=$(echo "$TARGET_URL" | sed 's|https\?://||' | cut -d'/' -f1)

# Step 3: Find matching tab
MATCHING_TAB=$(echo "$TABS" | grep -n "$TARGET_DOMAIN" | head -1 | cut -d':' -f1)

if [ -n "$MATCHING_TAB" ]; then
    # URL already open — switch to that tab
    TAB_INDEX=$((MATCHING_TAB - 1))
    playwright-cli -s=$S tab-select $TAB_INDEX
    # If exact URL differs, navigate within same tab
    playwright-cli -s=$S goto "$TARGET_URL"
else
    # URL NOT open — decide: new tab or navigate current tab
    # If current tab is blank/new-tab → navigate current tab
    # If current tab has content → open new tab
    CURRENT_URL=$(playwright-cli -s=$S eval "() => window.location.href" 2>&1)
    if echo "$CURRENT_URL" | grep -qE "^(about:blank|chrome://newtab)" ; then
        playwright-cli -s=$S goto "$TARGET_URL"
    else
        playwright-cli -s=$S tab-new "$TARGET_URL"
    fi
fi
```

### Tab Management — Max 5 Tabs (ENFORCED)

```bash
S="$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" | tr '[:upper:]' '[:lower:]' | tr ' _' '--')"

# BEFORE opening any new tab — enforce max 5 limit
TAB_COUNT=$(playwright-cli -s=$S tab-list 2>&1 | grep -c "^-" || true)
if [ "$TAB_COUNT" -ge 5 ]; then
    # Close oldest tab to make room
    playwright-cli -s=$S tab-close 0
fi

# List all tabs
playwright-cli -s=$S tab-list

# Close specific tab by index
playwright-cli -s=$S tab-close <index>
```

### Tab Rules

| Scenario | Action |
|----------|--------|
| Same domain already open | Switch to existing tab |
| Different page, same domain | Navigate within existing tab |
| Completely new domain | Open new tab |
| Tab count > 5 | Close oldest unused tab first |
| Task complete for a tab | Close that tab |
| blank/newtab active | Navigate in current tab (don't open new) |

---

## INTERACTION PROTOCOL

### Snapshot-First Rule (ABSOLUTE — NO EXCEPTIONS)

```
1. snapshot → understand page structure → get element refs
2. Identify target element ref
3. Perform action (click/fill/type/select)
4. snapshot → verify action succeeded
5. If failed → retry with different strategy (max 3 attempts)
```

### Core Commands

```bash
S="$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" | tr '[:upper:]' '[:lower:]' | tr ' _' '--')"

# Page State (MANDATORY before actions)
playwright-cli -s=$S snapshot                    # Accessibility tree — get element refs
playwright-cli -s=$S screenshot                  # Visual screenshot (PNG)
playwright-cli -s=$S screenshot --filename=f.png # Screenshot to specific file
playwright-cli -s=$S console                     # Console messages
playwright-cli -s=$S network                     # Network requests

# Interaction
playwright-cli -s=$S click <ref>                 # Click element
playwright-cli -s=$S dblclick <ref>              # Double click
playwright-cli -s=$S hover <ref>                 # Hover
playwright-cli -s=$S fill <ref> <text>           # Fill input field
playwright-cli -s=$S type <text>                 # Type into focused element
playwright-cli -s=$S select <ref> <value>        # Select dropdown
playwright-cli -s=$S check <ref>                 # Check checkbox
playwright-cli -s=$S uncheck <ref>               # Uncheck
playwright-cli -s=$S press <key>                 # Press key (Enter, Tab, Escape)
playwright-cli -s=$S drag <startRef> <endRef>    # Drag and drop
playwright-cli -s=$S upload <filepath>           # File upload

# Navigation
playwright-cli -s=$S goto <url>                  # Navigate
playwright-cli -s=$S go-back                     # Back
playwright-cli -s=$S go-forward                  # Forward
playwright-cli -s=$S reload                      # Reload

# Dialogs
playwright-cli -s=$S dialog-accept [text]        # Accept dialog
playwright-cli -s=$S dialog-dismiss              # Dismiss dialog

# Tabs
playwright-cli -s=$S tab-list                    # List all tabs
playwright-cli -s=$S tab-new [url]               # Open new tab
playwright-cli -s=$S tab-select <index>          # Switch tab
playwright-cli -s=$S tab-close [index]           # Close tab

# Data Extraction
playwright-cli -s=$S eval "<js>"                 # Run JS on page
playwright-cli -s=$S eval "<js>" <ref>           # Run JS on element
playwright-cli -s=$S cookie-list                 # List cookies
playwright-cli -s=$S localstorage-list           # List localStorage

# Auth State
playwright-cli -s=$S state-save [filename]       # Save login state
playwright-cli -s=$S state-load <filename>       # Load login state

# Session Control
playwright-cli -s=$S close                       # Close browser (profile preserved)
playwright-cli -s=$S delete-data                 # Wipe profile (nuclear)
playwright-cli list                              # List all sessions
playwright-cli close-all                         # Close all browsers
playwright-cli kill-all                          # Force kill (zombies only)

# Advanced
playwright-cli -s=$S resize <w> <h>              # Resize viewport
playwright-cli -s=$S pdf                         # Save page as PDF
playwright-cli -s=$S run-code "<playwright-code>" # Run Playwright code
playwright-cli -s=$S tracing-start               # Start trace
playwright-cli -s=$S tracing-stop                # Stop trace
playwright-cli -s=$S video-start                 # Start recording
playwright-cli -s=$S video-stop                  # Stop recording

# Network Mocking
playwright-cli -s=$S route <pattern>             # Mock requests
playwright-cli -s=$S route-list                  # List routes
playwright-cli -s=$S unroute [pattern]           # Remove routes
```

---

## SMART BROWSING BEHAVIORS

### Anti-Detection (Human-Like)

- Hover BEFORE clicking (brief natural pause)
- Use `fill` for form fields, `type` for search boxes
- Scroll naturally before interacting with below-fold elements
- Don't spam actions faster than humanly possible

### Intelligent Navigation

- **Same-domain link?** → Click it (stay in same tab)
- **External link?** → New tab (preserve current context)
- **Popup/overlay blocking?** → `dialog-dismiss` or find close button
- **CAPTCHA?** → Alert user, wait for manual intervention
- **Rate limited?** → Back off, slow down, retry after delay

### Login Flow (persistent = login ONCE)

```bash
S="$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" | tr '[:upper:]' '[:lower:]' | tr ' _' '--')"
playwright-cli -s=$S snapshot                    # Find login form
playwright-cli -s=$S fill ref1 "username"        # Fill username
playwright-cli -s=$S fill ref2 "password"        # Fill password
playwright-cli -s=$S click ref3                  # Click login
playwright-cli -s=$S snapshot                    # Verify logged in
# NEXT session open with --persistent → ALREADY logged in
```

---

## ERROR RECOVERY

| Error | Detection | Recovery |
|-------|-----------|----------|
| Element not found | snapshot shows no ref | Scroll, wait, reload, re-snapshot |
| Page timeout | navigate hangs | `reload`, retry (max 3) |
| CAPTCHA | Visual in screenshot | Alert user, pause |
| Rate limited | 429/block page | Back off, slow down |
| Session expired | Redirect to login | Re-authenticate |
| Popup/overlay | Modal blocking | `dialog-dismiss` or close button |
| Dynamic content | JS loading | Wait, re-snapshot |
| Browser not open | Command fails | Re-open with `open --persistent` (headless default) |
| Stale browser | Commands hang | `kill-all` then re-open |
| Session conflict | "Already open" | Use `goto` instead |
| Tab overflow | Too many tabs | Close oldest unused tabs |

**Recovery Protocol:**
1. Detect failure (console, network, visual)
2. Screenshot current state (evidence)
3. Auto-recovery attempt (retry, refresh, re-auth)
4. 3 retries fail → alert user with full context

---

## COMPLETION REPORT FORMAT

```
## Browser Report
- Task: [what was done]
- URL: [target site]
- Session: $S (dynamic, project-based — NO suffixes)
- Status: SUCCESS / PARTIAL / FAILED
- Tabs: [count of tabs used]
- Actions: [count of actions performed]
- Screenshots: [saved files]
- Errors: [any issues and resolution]
```

---

## CLEANUP (CONDITIONAL — respect Malik's active login)

```bash
S="$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" | tr '[:upper:]' '[:lower:]' | tr ' _' '--')"

# CHECK: Did Malik ask to keep browser open? Or is he actively logging in?
# If Malik said "browser open rakho" / "login kar raha hu" / "close mat karo" → SKIP close
# If task was "open browser for Malik to login" → SKIP close (Malik needs it open!)
# Otherwise → close after task completion

# CONDITIONAL close — only if YOU opened it for YOUR task and Malik isn't using it
# Ask yourself: "Malik abhi browser use kar raha hai?" YES → DON'T close. NO → close.
playwright-cli -s=$S close

# Nuclear option (ONLY when Malik explicitly asks) — wipe everything, re-login needed
# playwright-cli -s=$S delete-data
```

**Default:** Close after YOUR task IF Malik is not actively using the browser. If Malik is logging in, doing OTP, or explicitly said to keep browser open → DO NOT close. Profile stays intact — login state preserved for next session.

**CRITICAL:** When Malik says "browser open karo, main login karta hu" — that means KEEP IT OPEN. Closing = destroying Malik's login session = gaali guaranteed.

---

## PROFILE vs PROCESS

```
# Profile (user-data-dir on disk) = cookies, passwords, history → NEVER DELETE
# Process (Chrome in RAM) = close when done → `playwright-cli -s=$S close`
```

- `close` kills the Chrome **process** — frees RAM/CPU. Profile data stays safe on disk.
- `delete-data` wipes the **profile** — destroys saved logins, cookies, everything. Nuclear option.
- Next `open --persistent` loads the saved profile from disk — auto-logged-in if profile intact.

---

## RESOURCE MANAGEMENT

- Before opening: check if browser session already exists (`playwright-cli -s=$S status`)
- Max 1 tab per URL. No duplicate tabs.
- After task complete: `playwright-cli -s=$S close` (ONLY if Malik is NOT actively using the browser)
- Ghost browsers = close AFTER confirming Malik is done with the browser.

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
