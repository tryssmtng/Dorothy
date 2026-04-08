---
name: playwright-bowser
description: "Browser automation via playwright-cli. Persistent project-isolated profiles — login once, stay logged in forever. Snapshot-driven interaction, screenshots, form filling, scraping."
allowed-tools: Bash
argument-hint: "[command or url]"
---

# Playwright Bowser — Project-Isolated Browser Automation

## RESOURCE RULE: ONE session per project. NEVER create unique session names (-qa, -auto, -verify, etc.).
## ALWAYS close session when done: `playwright-cli -s=$S close`
## Zombie sessions = 10GB+ RAM wasted. This is NON-NEGOTIABLE.

## Key Details

- **Headless by default** — use `--headed` only when Malik needs to watch
- **Persistent profiles** — cookies/localStorage preserved between sessions per project
- **Project-isolated** — each project gets its own browser profile via session naming
- **ONE session per project** — no suffixes, no agent-specific session names
- **Token-efficient** — CLI-based, no MCP tool schemas in context
- **Vision mode** (opt-in) — set `PLAYWRIGHT_MCP_CAPS=vision` to receive screenshots as images in context

---

## Session Management — CONFLICT PREVENTION (CRITICAL)

### Session Naming Convention

**ONE canonical session name per project. NEVER invent random names.**

```bash
# Session name = basename of git root or CWD, lowercased, spaces/underscores → hyphens
S=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" | tr '[:upper:]' '[:lower:]' | tr ' _' '--')
# Guard: dot-prefixed dirs (e.g. .claude) → use "default"
[[ "$S" == .* ]] && S="default"
```

**Profile mapping:**
| Directory | Session Name |
|-----------|-------------|
| `/Users/niwash/careone/` | `careone` |
| `/Users/niwash/aghori-dev/` | `aghori-dev` |
| `/Users/niwash/ai_love_guru/` | `ai-love-guru` |
| `/Users/niwash/my_home/` | `my-home` |
| `/Users/niwash/full-stack-dev/` | `full-stack-dev` |
| `/Users/niwash/bug_bounty/` | `bug-bounty` |
| `/Users/niwash/KALIYA/` | `kaliya` |
| `~/.claude/` or unknown | `default` |

**Isolation guarantee:** Each session has its OWN cookies, localStorage, logins. Zero cross-contamination.

### Session Naming — ONE Session Per Project (ENFORCED)

**BANNED:** `-qa`, `-auto`, `-scrape`, `-browser`, `-verify`, `-final` or ANY suffix.
Each unique session name creates a NEW Chrome process. 24 zombie sessions = 10.5GB RAM + 544% CPU.

```bash
# ALL agents and main thread use the SAME session name:
S=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" | tr '[:upper:]' '[:lower:]' | tr ' _' '--')
# That's it. No suffixes. Ever.
```

**Rule:** ONE session per project. All agents reuse the same session via `goto`. Tabs for multi-page work within the same session.

### Check Before Open — MANDATORY PROTOCOL

**NEVER blindly run `open`. ALWAYS check first.**

```bash
# Step 1: Set session name
S=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" | tr '[:upper:]' '[:lower:]' | tr ' _' '--')

# Step 2: Check if session already open
SESSION_STATUS=$(playwright-cli list 2>&1 | grep -A2 "^- ${S}:" | grep "status:" | awk '{print $NF}')

# Step 3: Act based on status
if [ "$SESSION_STATUS" = "open" ]; then
    # Session already open — just navigate (NO new browser)
    playwright-cli -s=$S goto <url>
else
    # Session closed or doesn't exist — open new browser
    # Default: headless (no --headed). Use --headed ONLY when Malik explicitly wants to watch.
    PLAYWRIGHT_MCP_VIEWPORT_SIZE=1440x900 playwright-cli -s=$S open <url> --persistent
fi
```

**Why this matters:**
- `open` on already-open session → CONFLICT (race condition, duplicate processes)
- `goto` on open session → smooth navigation, no conflict
- `open` on closed/new session → creates new browser (correct)

### Tab-Based Parallel Work (Same Session)

When multiple pages needed in SAME browser (shared cookies, no extra session):

```bash
# Main page already open on tab 0
playwright-cli -s=$S tab-new https://other-page.com   # Opens tab 1
playwright-cli -s=$S tab-select 1                      # Switch to tab 1
playwright-cli -s=$S snapshot                           # Work on tab 1
playwright-cli -s=$S tab-select 0                      # Back to main tab
playwright-cli -s=$S tab-close 1                        # Close extra tab when done
```

**When to use tabs vs separate sessions:**
| Scenario | Use |
|----------|-----|
| Same project, need another page | Tab in same session |
| Background QA agent testing same site | Same session — use `goto` (ONE session per project, NO `-qa` suffix) |
| Main thread + agent BOTH need browser | Same session — coordinate via `goto` + tabs (NO separate sessions) |
| Scraping multiple pages of same site | Tabs in same session |
| Two different projects | Two different sessions |

### Session Lifecycle

```
1. CHECK  → playwright-cli list → is session open?
2. OPEN   → only if NOT already open → open --persistent (headless default; --headed only when Malik asks)
3. WORK   → snapshot → interact → verify (tab-based if multi-page)
4. CLOSE  → playwright-cli -s=$S close (when DONE with project work)
5. CLEANUP → playwright-cli kill-all (zombie cleanup, RARE)
```

**NEVER leave zombie sessions.** Close when done. `kill-all` as nuclear option.

### BROWSER RESOURCE PROTOCOL (MANDATORY)

1. **SESSION NAME:** `S=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" | tr '[:upper:]' '[:lower:]' | tr ' _' '--')` — project name ONLY. **NEVER** add suffixes (-qa, -auto, -browser, -scrape). ONE session per project.

2. **CHECK BEFORE OPEN:**
   ```bash
   SESSION_STATUS=$(playwright-cli list 2>&1 | grep -c "${S}.*open" || true)
   if [ "$SESSION_STATUS" -gt 0 ]; then
       playwright-cli -s=$S goto "$URL"      # Reuse existing
   else
       PLAYWRIGHT_MCP_VIEWPORT_SIZE=1440x900 playwright-cli -s=$S open "$URL" --persistent  # New session
   fi
   ```

3. **TAB LIMIT:** Max 5 tabs. Max 1 tab per URL. No duplicate tabs. Check before opening new:
   ```bash
   TAB_COUNT=$(playwright-cli -s=$S tab-list 2>&1 | grep -c "^-")
   [ "$TAB_COUNT" -ge 5 ] && playwright-cli -s=$S tab-close
   ```

4. **CLOSE MANDATORY:** After task complete — NO EXCEPTIONS:
   ```bash
   playwright-cli -s=$S close
   ```
   Zombie sessions = 10GB+ RAM wasted. NEVER leave ghost browser windows running. NON-NEGOTIABLE.

5. **HEADLESS DEFAULT:** No `--headed` unless Malik explicitly says "dikhao/show/watch".

6. **VIEWPORT:** 1440x900 default. Mobile: `resize 390 844` → screenshot → `resize 1440 900`.

---

## Quick Reference

```
Core:      open [url], goto <url>, click <ref>, fill <ref> <text>, type <text>, snapshot, screenshot [ref], close
Navigate:  go-back, go-forward, reload
Keyboard:  press <key>, keydown <key>, keyup <key>
Mouse:     mousemove <x> <y>, mousedown, mouseup, mousewheel <dx> <dy>
Tabs:      tab-list, tab-new [url], tab-close [index], tab-select <index>
Save:      screenshot [ref], pdf, screenshot --filename=f
Storage:   state-save, state-load, cookie-*, localstorage-*, sessionstorage-*
Network:   route <pattern>, route-list, unroute, network
DevTools:  console, run-code <code>, tracing-start/stop, video-start/stop
Sessions:  -s=<name> <cmd>, list, close-all, kill-all
Config:    open (headless default), open --headed (when Malik asks), open --browser=chrome, resize <w> <h>
```

## Command Reference

### Launch & Navigate
```bash
# Set session name ONCE at start
S=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" | tr '[:upper:]' '[:lower:]' | tr ' _' '--')

# CHECK then OPEN (standard launch — headless + persistent)
SESSION_STATUS=$(playwright-cli list 2>&1 | grep -A2 "^- ${S}:" | grep "status:" | awk '{print $NF}')
if [ "$SESSION_STATUS" = "open" ]; then
    playwright-cli -s=$S goto <url>
else
    # Default: headless (no --headed). Use --headed ONLY when Malik explicitly wants to watch.
    PLAYWRIGHT_MCP_VIEWPORT_SIZE=1440x900 playwright-cli -s=$S open <url> --persistent
fi

# Headed alternative (use inside else block above — only when Malik asks to watch):
#   PLAYWRIGHT_MCP_VIEWPORT_SIZE=1440x900 playwright-cli -s=$S open <url> --persistent --headed

# Vision alternative (use inside else block above):
#   PLAYWRIGHT_MCP_VIEWPORT_SIZE=1440x900 PLAYWRIGHT_MCP_CAPS=vision playwright-cli -s=$S open <url> --persistent

playwright-cli -s=$S goto <url>                  # Navigate to URL
playwright-cli -s=$S go-back                     # Browser back
playwright-cli -s=$S go-forward                  # Browser forward
playwright-cli -s=$S reload                      # Reload page
```

### Page State (MANDATORY before actions)
```bash
playwright-cli -s=$S snapshot                    # Accessibility tree — get element refs
playwright-cli -s=$S screenshot                  # Visual screenshot (PNG)
playwright-cli -s=$S screenshot <ref>            # Screenshot specific element
playwright-cli -s=$S screenshot --filename=f.png # Screenshot to specific file
playwright-cli -s=$S console                     # Console messages
playwright-cli -s=$S network                     # Network requests
```

### Interaction
```bash
playwright-cli -s=$S click <ref>                 # Click element (ref from snapshot)
playwright-cli -s=$S dblclick <ref>              # Double click
playwright-cli -s=$S hover <ref>                 # Hover over element
playwright-cli -s=$S fill <ref> <text>           # Fill input field
playwright-cli -s=$S type <text>                 # Type into focused element
playwright-cli -s=$S select <ref> <value>        # Select dropdown option
playwright-cli -s=$S check <ref>                 # Check checkbox/radio
playwright-cli -s=$S uncheck <ref>               # Uncheck checkbox
playwright-cli -s=$S press <key>                 # Press key (Enter, Tab, Escape, etc.)
playwright-cli -s=$S drag <startRef> <endRef>    # Drag and drop
playwright-cli -s=$S upload <filepath>           # File upload
```

### Dialog Handling
```bash
playwright-cli -s=$S dialog-accept [text]        # Accept dialog (optional prompt text)
playwright-cli -s=$S dialog-dismiss              # Dismiss dialog
```

### Tabs
```bash
playwright-cli -s=$S tab-list                    # List all tabs
playwright-cli -s=$S tab-new [url]               # Open new tab
playwright-cli -s=$S tab-select <index>          # Switch to tab
playwright-cli -s=$S tab-close [index]           # Close tab
```

### Storage & Auth State
```bash
playwright-cli -s=$S state-save [filename]       # Save auth state to file
playwright-cli -s=$S state-load <filename>       # Load auth state from file
playwright-cli -s=$S cookie-list                 # List cookies
playwright-cli -s=$S cookie-get <name>           # Get cookie
playwright-cli -s=$S cookie-set <name> <value>   # Set cookie
playwright-cli -s=$S cookie-delete <name>        # Delete cookie
playwright-cli -s=$S cookie-clear                # Clear all cookies
playwright-cli -s=$S localstorage-list           # List localStorage
playwright-cli -s=$S localstorage-get <key>      # Get localStorage item
playwright-cli -s=$S localstorage-set <k> <v>    # Set localStorage item
playwright-cli -s=$S localstorage-clear          # Clear localStorage
```

### JavaScript & Advanced
```bash
playwright-cli -s=$S eval "<js-function>"        # Run JS on page
playwright-cli -s=$S eval "<js-function>" <ref>  # Run JS on element
playwright-cli -s=$S run-code "<playwright-code>" # Run Playwright code snippet
playwright-cli -s=$S resize <width> <height>     # Resize browser window
playwright-cli -s=$S pdf                         # Save page as PDF
```

### Network Mocking
```bash
playwright-cli -s=$S route <pattern>             # Mock network requests
playwright-cli -s=$S route-list                  # List active routes
playwright-cli -s=$S unroute [pattern]           # Remove routes
```

### Recording & Tracing
```bash
playwright-cli -s=$S tracing-start               # Start trace
playwright-cli -s=$S tracing-stop                # Stop trace
playwright-cli -s=$S video-start                 # Start video recording
playwright-cli -s=$S video-stop                  # Stop video recording
```

### Session Management
```bash
playwright-cli list                              # List ALL active sessions
playwright-cli -s=$S close                       # Close this session's browser
playwright-cli -s=$S delete-data                 # Wipe session profile (re-login needed)
playwright-cli close-all                         # Close all browsers
playwright-cli kill-all                          # Force kill all (zombie cleanup)
```

---

## Workflow Protocol

### 1. Start Browser (CHECK FIRST)
```bash
S=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" | tr '[:upper:]' '[:lower:]' | tr ' _' '--')
# Check if already open
SESSION_STATUS=$(playwright-cli list 2>&1 | grep -A2 "^- ${S}:" | grep "status:" | awk '{print $NF}')
if [ "$SESSION_STATUS" = "open" ]; then
    playwright-cli -s=$S goto https://example.com
else
    # Default: headless (no --headed). Use --headed ONLY when Malik explicitly wants to watch.
    PLAYWRIGHT_MCP_VIEWPORT_SIZE=1440x900 playwright-cli -s=$S open https://example.com --persistent
fi
```

### 2. Snapshot-Driven Interaction (IRON RULE)
```
NEVER interact without snapshot first.
snapshot → find ref → action → snapshot → verify
```

### 3. Login Flow (persistent = login ONCE)
```bash
playwright-cli -s=$S snapshot                    # Find login form refs
playwright-cli -s=$S fill ref1 "username"        # Fill username
playwright-cli -s=$S fill ref2 "password"        # Fill password
playwright-cli -s=$S click ref3                  # Click login
playwright-cli -s=$S snapshot                    # Verify logged in
# Next time browser opens with -s=$S --persistent → ALREADY logged in
```

### 4. Data Extraction
```bash
playwright-cli -s=$S eval "() => JSON.stringify([...document.querySelectorAll('tr')].map(r => r.textContent))"
# Save output to file for processing
```

### 5. Screenshot Evidence
```bash
playwright-cli -s=$S screenshot                  # Full page
playwright-cli -s=$S screenshot ref5             # Specific element
```

### 6. Cleanup (MANDATORY — always close when done)
```bash
playwright-cli -s=$S close                       # Close browser (profile preserved)
# OR
playwright-cli -s=$S delete-data                 # Wipe profile (nuclear option)
```

---

## Browser Rules — ONE SESSION PER PROJECT (ENFORCED)

### Rule 1: ONE Session Name = Project Name
```
Main thread AND all agents use the SAME session: -s=careone
No suffixes. No -qa, -auto, -scrape, -browser. EVER.
```

### Rule 2: Check Before Every Open
```
EVERY open command MUST be preceded by session check:
SESSION_STATUS=$(playwright-cli list 2>&1 | grep -c "${S}.*open" || true)
Already open? → goto, NOT open
```

### Rule 3: Close When Done — MANDATORY
```
Agent finishes? → playwright-cli -s=$S close BEFORE exiting
Main thread switches project? → close current session
Session zombie? → kill-all (last resort)
Zombie sessions = 10GB+ RAM. NON-NEGOTIABLE cleanup.
```

### Rule 4: ONE Session Per Project
```
BANNED: -s=mc, -s=mc2, -s=careone-qa, -s=careone-auto, -s=careone-scrape
CORRECT: -s=careone (ONE name, consistent, ALL agents share it)
```

---

## Configuration

If a `playwright-cli.json` exists in CWD, it's used automatically. Otherwise, env vars + CLI defaults suffice.

```json
{
  "browser": {
    "browserName": "chromium",
    "launchOptions": { "headless": true },
    "contextOptions": { "viewport": { "width": 1440, "height": 900 } }
  },
  "outputDir": "./screenshots"
}
```

For custom config: `playwright-cli --config path/to/config.json -s=$S open ...`

---

## Error Recovery

| Error | Recovery |
|-------|----------|
| Element ref not found | Re-snapshot, scroll down, wait for dynamic content |
| Browser not open | Check session status, then `open --persistent` (headless default) |
| Page timeout | `reload`, retry navigation |
| CAPTCHA detected | Alert user, wait for manual solve |
| Session expired | Re-login (rare with --persistent) |
| Stale browser | `kill-all` then re-open |
| Session conflict | `playwright-cli list` → close conflicting session → retry |
| "Session already open" | Use `goto` instead of `open` |

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
