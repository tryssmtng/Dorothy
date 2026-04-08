---
name: automate
description: "Browser automation — login flows, form filling, data scraping, multi-step web workflows, file downloads. Use when user wants to automate any web task, scrape data, extract information, fill forms, control browser, or run repetitive web workflows."
argument-hint: "[task description or url]"
---

# Web Automation — playwright-cli Workflows

Automate: `$ARGUMENTS`

If no task described, ask what to automate.

---

## Mode Selection

| Scope | Mode | Action |
|-------|------|--------|
| Simple (1-3 steps) | **Standalone** | Execute on main thread directly |
| Complex (4+ steps, multi-page, data processing) | **Agent** | Dispatch `web-automator` agent in background |
| Scraping large datasets | **Agent** | Always dispatch — pagination/extraction is multi-step |

**Standalone Mode**: Execute the relevant pattern below directly using playwright-cli commands.

**Agent Mode**: Dispatch `web-automator` agent with the task description + relevant patterns from this skill. Use `run_in_background: true`. After agent returns, read output fully, verify data files created, present report.

---

## RESOURCE RULE: ONE session per project. NEVER create unique session names (-qa, -auto, -verify, etc.).
## ALWAYS close session when done: `playwright-cli -s=$S close`
## Zombie sessions = 10GB+ RAM wasted. This is NON-NEGOTIABLE.

## Session Setup

Every automation uses project-isolated browser profiles. Persistent profiles retain cookies, localStorage, and login sessions across runs.

```bash
# Session name = project name ONLY. NO suffixes (-auto, -qa, -verify, etc.)
S=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" | tr '[:upper:]' '[:lower:]' | tr ' _' '--')
# Guard: dot-prefixed dirs (e.g. .claude) → use "default"
[[ "$S" == .* ]] && S="default"

# CHECK existing session first — REUSE, don't create new
SESSION_STATUS=$(playwright-cli list 2>&1 | grep -c "${S}.*open" || true)
if [ "$SESSION_STATUS" -gt 0 ]; then
    # Session exists — reuse it with goto
    playwright-cli -s=$S goto <target-url>
else
    # No session — open new one
    # Default: headless (no --headed). Use --headed ONLY when Malik explicitly wants to watch.
    PLAYWRIGHT_MCP_VIEWPORT_SIZE=1440x900 playwright-cli -s=$S open <target-url> --persistent
fi
```

ALL commands use `-s=$S` flag. No exceptions. No suffixes.

**Cleanup**: `playwright-cli -s=$S close` after automation completes. **MANDATORY — not optional.**

---

## Common Automation Patterns

### Pattern 1: Login Flow

```bash
# 1. Open login page (headless default; --headed only when Malik asks)
playwright-cli -s=$S open <login-url> --persistent

# 2. Snapshot to find form fields
playwright-cli -s=$S snapshot

# 3. Fill credentials (find refs from snapshot)
playwright-cli -s=$S fill <email-ref> "<email>"
playwright-cli -s=$S fill <password-ref> "<password>"

# 4. Screenshot before submit (proof of filled form)
playwright-cli -s=$S screenshot /tmp/auto-login-filled.png

# 5. Click submit
playwright-cli -s=$S click <submit-ref>

# 6. Wait for navigation (dashboard/home loads)
# snapshot will implicitly wait for page stability
playwright-cli -s=$S snapshot

# 7. Verify login success
playwright-cli -s=$S screenshot /tmp/auto-login-success.png

# 8. Check for auth cookies/tokens
playwright-cli -s=$S evaluate "document.cookie.includes('session') || document.cookie.includes('token')"
```

**Persistent advantage**: With `--persistent`, login survives session close. Next run skips login entirely.

### Pattern 2: Form Fill

```bash
# 1. Navigate and snapshot
playwright-cli -s=$S goto <form-url>
playwright-cli -s=$S snapshot

# 2. Identify all form fields from snapshot output
# Look for: input[type=text], input[type=email], select, textarea, checkbox, radio

# 3. Fill each field
playwright-cli -s=$S fill <name-ref> "John Doe"
playwright-cli -s=$S fill <email-ref> "john@example.com"
playwright-cli -s=$S fill <phone-ref> "+1234567890"

# 4. Handle special field types
playwright-cli -s=$S click <checkbox-ref>           # Toggle checkbox
playwright-cli -s=$S click <radio-option-ref>       # Select radio
playwright-cli -s=$S click <dropdown-ref>           # Open dropdown
playwright-cli -s=$S click <option-ref>             # Select option

# 5. Verify all fields filled
playwright-cli -s=$S snapshot
playwright-cli -s=$S screenshot /tmp/auto-form-filled.png

# 6. Submit
playwright-cli -s=$S click <submit-ref>

# 7. Verify success
playwright-cli -s=$S snapshot
playwright-cli -s=$S screenshot /tmp/auto-form-submitted.png
```

### Pattern 3: Data Scraping

```bash
# 1. Navigate to data source
playwright-cli -s=$S goto <data-url>
playwright-cli -s=$S snapshot

# 2. Extract structured data via evaluate
# Tables:
playwright-cli -s=$S evaluate "[...document.querySelectorAll('table tbody tr')].map(row => [...row.cells].map(cell => cell.textContent.trim()))"

# Lists:
playwright-cli -s=$S evaluate "[...document.querySelectorAll('.item-class')].map(el => ({title: el.querySelector('.title')?.textContent?.trim(), price: el.querySelector('.price')?.textContent?.trim(), link: el.querySelector('a')?.href}))"

# Specific elements:
playwright-cli -s=$S evaluate "document.querySelector('.target-selector')?.textContent?.trim()"

# 3. Handle pagination
# Find next page button from snapshot, loop:
playwright-cli -s=$S click <next-page-ref>
playwright-cli -s=$S snapshot
# Extract data again... repeat until no more pages

# 4. Save extracted data
# From the evaluate results, save to file:
# JSON format for structured data
# CSV format for tabular data
```

**Data output**: Save to project directory or `/tmp/`. JSON for nested/structured data. CSV for flat tabular data. Always show sample of extracted data in report.

### Pattern 4: Multi-Page Navigation

```bash
# 1. Start at index/listing page
playwright-cli -s=$S goto <start-url>
playwright-cli -s=$S snapshot

# 2. Click into first detail page
playwright-cli -s=$S click <item-link-ref>
playwright-cli -s=$S snapshot

# 3. Extract data from detail page
playwright-cli -s=$S evaluate "<extraction-expression>"
playwright-cli -s=$S screenshot /tmp/auto-detail-1.png

# 4. Go back to listing
playwright-cli -s=$S evaluate "history.back()"
playwright-cli -s=$S snapshot

# 5. Click next item... repeat

# 6. Handle pagination on listing page
playwright-cli -s=$S click <next-page-ref>
playwright-cli -s=$S snapshot
# Continue extracting...
```

**State tracking**: Keep track of which items/pages have been visited. Use a counter or list. If the automation fails mid-way, resume from the last successful item — don't restart from scratch.

### Pattern 5: File Download

```bash
# 1. Navigate to download page
playwright-cli -s=$S goto <download-url>
playwright-cli -s=$S snapshot

# 2. Click download button/link
playwright-cli -s=$S click <download-ref>

# 3. Wait for download (persistent profile saves to default download dir)
# Check download directory:
ls -la ~/Downloads/ | head -5

# 4. Verify file
file ~/Downloads/<filename>
wc -c ~/Downloads/<filename>

# 5. Move to project directory if needed
mv ~/Downloads/<filename> /path/to/project/data/
```

---

## Data Extraction Templates

### Table to JSON

```bash
playwright-cli -s=$S evaluate "
  const headers = [...document.querySelectorAll('table thead th')].map(th => th.textContent.trim());
  const rows = [...document.querySelectorAll('table tbody tr')].map(row =>
    Object.fromEntries([...row.cells].map((cell, i) => [headers[i] || 'col'+i, cell.textContent.trim()]))
  );
  JSON.stringify(rows, null, 2);
"
```

### List to CSV

```bash
playwright-cli -s=$S evaluate "
  const items = [...document.querySelectorAll('.item-selector')];
  const header = 'Name,Price,URL';
  const rows = items.map(el => [
    el.querySelector('.name')?.textContent?.trim() || '',
    el.querySelector('.price')?.textContent?.trim() || '',
    el.querySelector('a')?.href || ''
  ].map(v => '\"' + v.replace(/\"/g, '\"\"') + '\"').join(','));
  [header, ...rows].join('\\n');
"
```

### Page Metadata

```bash
playwright-cli -s=$S evaluate "JSON.stringify({
  title: document.title,
  description: document.querySelector('meta[name=description]')?.content || '',
  ogTitle: document.querySelector('meta[property=\"og:title\"]')?.content || '',
  ogImage: document.querySelector('meta[property=\"og:image\"]')?.content || '',
  canonical: document.querySelector('link[rel=canonical]')?.href || '',
  h1: document.querySelector('h1')?.textContent?.trim() || '',
  links: document.querySelectorAll('a[href]').length,
  images: document.querySelectorAll('img').length
}, null, 2)"
```

---

## Anti-Detection Practices

Sites may block or degrade automated browsing. Use these patterns to behave like a real user.

**Timing**:
- Add 1-3 second delays between actions: `sleep $((RANDOM % 3 + 1))`
- Type text slowly — use `fill` which simulates typing
- Don't navigate faster than a human can read a page

**Scroll Behavior**:
```bash
# Scroll down gradually (not instant jump to bottom)
playwright-cli -s=$S evaluate "window.scrollBy(0, 300)"
# Wait, then scroll more
playwright-cli -s=$S evaluate "window.scrollBy(0, 500)"
```

**Session Persistence**:
- `--persistent` flag maintains cookies and localStorage across sessions
- Logged-in sessions survive automation restarts
- Browser fingerprint stays consistent (same profile = same browser identity)

**Rate Limiting**:
- If responses slow down or return 429, reduce request frequency
- Back off exponentially: 2s → 4s → 8s → 16s between requests
- If blocked, stop and alert Malik — don't brute-force past blocks

---

## Error Recovery

Every automation step can fail. Handle failures gracefully — don't crash on the first hiccup.

| Error | Detection | Recovery |
|-------|-----------|----------|
| **Element not found** | Snapshot shows no matching ref | Scroll down → re-snapshot → retry. If still missing: page layout changed, alert Malik. |
| **Page not loaded** | Snapshot returns empty/error | Wait 3s → re-snapshot. If still empty: check URL, try goto again. 3 failures → alert. |
| **Click did nothing** | Snapshot after click shows no change | Element might need hover first, or is behind overlay. Try: evaluate `document.querySelector('<selector>').click()` |
| **Form submission error** | Page shows validation error | Read error message → fix input → resubmit. If server error → screenshot + alert. |
| **CAPTCHA detected** | Page shows CAPTCHA challenge | Screenshot → alert Malik: "CAPTCHA detected. Manual solve needed." → wait for confirmation → continue. |
| **Rate limited (429)** | Page returns 429 or "too many requests" | Back off 30 seconds → retry with slower pace. If persists → alert Malik. |
| **Session expired** | Redirected to login page | Re-run login flow (persistent profile should prevent this, but handle gracefully). |
| **Network error** | Page fails to load | Check internet → retry 3 times with 5s delay → alert if persistent. |

**3-Strike Rule**: Any single error type happening 3 times consecutively → stop that action, alert Malik with full context, move to next step if possible.

---

## Multi-Step Workflow Management

Complex automations involve many steps. Track state to handle interruptions.

**State Tracking**:
```
Step 1: Open page ........... DONE
Step 2: Login ............... DONE
Step 3: Navigate to data .... DONE
Step 4: Extract page 1 ...... DONE
Step 5: Extract page 2 ...... IN PROGRESS
Step 6: Extract page 3 ...... PENDING
Step 7: Save data ........... PENDING
Step 8: Cleanup ............. PENDING
```

**Resume from Failure**:
- Track the last successfully completed step
- If automation fails at step 5, resume from step 5 — don't redo steps 1-4
- Persistent browser sessions mean login state and cookies survive restarts

**Data Accumulation**:
- Append extracted data to a file after each successful step
- If step N fails, data from steps 1 to N-1 is already saved
- Final step combines all partial data into the complete output

---

## Session Management

**Session naming**: `$S` where `S` is derived from project directory name.

**Commands reference**:

| Action | Command |
|--------|---------|
| Open new session | `PLAYWRIGHT_MCP_VIEWPORT_SIZE=1440x900 playwright-cli -s=$S open <url> --persistent` |
| Navigate | `playwright-cli -s=$S goto <url>` |
| Snapshot DOM | `playwright-cli -s=$S snapshot` |
| Screenshot | `playwright-cli -s=$S screenshot /tmp/auto-<name>.png` |
| Click element | `playwright-cli -s=$S click <ref>` |
| Fill input | `playwright-cli -s=$S fill <ref> "<text>"` |
| Hover | `playwright-cli -s=$S hover <ref>` |
| Evaluate JS | `playwright-cli -s=$S evaluate "<expression>"` |
| Resize viewport | `playwright-cli -s=$S resize <width> <height>` |
| Console logs | `playwright-cli -s=$S console` |
| List sessions | `playwright-cli list` |
| Close session | `playwright-cli -s=$S close` |

**Viewport**: Default 1440x900. Change with `resize` command for mobile/tablet testing.

**Persistence**: `--persistent` flag is MANDATORY. It stores cookies, localStorage, sessionStorage, and IndexedDB in a project-specific profile. Login once, stay logged in across automation runs.

**Headed mode**: Headless is default. Use `--headed` only when Malik explicitly asks to watch the automation execute in real time.

---

## BROWSER RESOURCE PROTOCOL (MANDATORY)

1. **SESSION NAME:** `S=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" | tr '[:upper:]' '[:lower:]' | tr ' _' '--')` — project name ONLY. **NEVER** add suffixes (-auto, -qa, -verify). ONE session per project.

2. **CHECK BEFORE OPEN:**
   ```bash
   SESSION_STATUS=$(playwright-cli list 2>&1 | grep -c "${S}.*open" || true)
   if [ "$SESSION_STATUS" -gt 0 ]; then
       playwright-cli -s=$S goto "$URL"      # Reuse existing
   else
       PLAYWRIGHT_MCP_VIEWPORT_SIZE=1440x900 playwright-cli -s=$S open "$URL" --persistent  # New session
   fi
   ```

3. **TAB LIMIT:** Max 5 tabs. Check before opening new:
   ```bash
   TAB_COUNT=$(playwright-cli -s=$S tab-list 2>&1 | grep -c "^-")
   [ "$TAB_COUNT" -ge 5 ] && playwright-cli -s=$S tab-close
   ```

4. **CLOSE MANDATORY:** After task complete — NO EXCEPTIONS:
   ```bash
   playwright-cli -s=$S close
   ```
   Zombie sessions = 10GB+ RAM wasted. This is NON-NEGOTIABLE.

5. **HEADLESS DEFAULT:** No `--headed` unless Malik explicitly says "dikhao/show/watch".

6. **VIEWPORT:** 1440x900 default. Mobile: `resize 390 844` → screenshot → `resize 1440 900`.

---

## Iron Rules

1. **Snapshot before every interaction.** Never click, fill, or submit without first capturing the DOM state. Blind actions = broken automations.
2. **Never click without a ref.** The snapshot provides element refs. Use those refs. Clicking by coordinates or selectors is fragile and breaks on layout changes.
3. **Screenshot proof after completion.** Every automation must end with a screenshot proving the task was done. "Trust me it worked" is not evidence.
4. **Verify after every action.** Click a button → snapshot → verify the expected change happened. Fill a field → snapshot → verify the value is there. No assumptions.
5. **Handle errors, don't crash.** Element missing? Re-snapshot. Page didn't load? Retry. CAPTCHA? Alert Malik. Every failure has a recovery path.
6. **Save data incrementally.** Large scraping jobs save data after each page/step. If it fails on page 50 of 100, you keep the first 49 pages of data.
7. **Clean up sessions.** `playwright-cli -s=$S close` when done. MANDATORY, not optional. Orphan browser sessions waste resources.
8. **Alert, don't guess.** CAPTCHA, 2FA, phone verification — these need human input. Alert Malik immediately. Don't try to bypass or guess.
9. **Respect rate limits.** Getting blocked helps nobody. Add delays between requests. Back off when warned. Stealth over speed.

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
