---
name: context
description: "Military-grade context management — status, save state, pre-compact preparation, load state, efficiency analysis. Prevents context overflow disasters. Use when: context, memory usage, how much context, token, compact, save state, load state, running out, overflow, what's loaded, system prompt, efficiency, optimize context, too much context, context window."
argument-hint: "[command] — commands: status, save, prepare, load, efficiency, reset"
---

# KALIYA Context Management — Military Grade

Full control over context window. Prevent overflow disasters. Optimize token usage. Never lose work.

## Command: `$ARGUMENTS`

Parse command from arguments. If no command given, default to `status`.

---

## OPERATIONS

### `status` — Context Window Intelligence Report

Analyze current context state and report.

#### Steps:

1. **Estimate Context Usage:**
   - System prompt (CLAUDE.md + MEMORY.md + hooks): ~20-40K tokens estimated
   - Conversation history: estimate from message count and length
   - Tool results cached: estimate from recent tool calls
   - Total capacity: ~1M tokens

2. **What's Currently Loaded (System Prompt):**
   - `~/.claude/CLAUDE.md` — size via `wc -c ~/.claude/CLAUDE.md`
   - `MEMORY.md` (auto-loaded, first 200 lines) — identify which one
   - Project CLAUDE.md (if exists) — size
   - Hook injections (SessionStart) — estimated size
   - Plugins active — list from settings

3. **Session Activity:**
   - Estimate messages exchanged (from conversation flow)
   - Large tool outputs received (file reads, search results, agent outputs)
   - Files read this session (from track-reads hook if available)

4. **Compact Risk Assessment:**
   ```
   IF estimated usage > 60% capacity → GREEN (safe)
   IF estimated usage > 75% capacity → YELLOW (save state soon)
   IF estimated usage > 85% capacity → ORANGE (save state NOW)
   IF estimated usage > 90% capacity → RED (compact IMMINENT — emergency save)
   ```

5. **Output Format:**
   ```
   CONTEXT STATUS
   ==============
   Capacity: ~1M tokens
   Estimated Usage: [X]K tokens ([Y]%)
   Risk Level: [GREEN/YELLOW/ORANGE/RED]

   System Prompt:
     CLAUDE.md (global): [size] ([est tokens])
     CLAUDE.md (project): [size or N/A] ([est tokens])
     MEMORY.md: [lines]/200 lines ([est tokens])
     Hook injections: ~[est] tokens
     Plugins: [list]

   Session:
     Messages: ~[count]
     Tool calls: ~[count]
     Large outputs: [list of big reads/searches]
     Files read: [count from hook or estimate]

   Recommendation:
     [Based on risk level — specific action to take]
   ```

---

### `save` — Save Current State to Memory

Save everything important from current session to persistent storage.

#### Steps:

1. **Update Last Session in MEMORY.md:**
   ```
   ## Last Session
   - Date: [today]
   - Dir: [CWD]
   - Work: [summary of what was done this session]
   - Completed: [list of completed items]
   - Pending: [list of unfinished items]
   - Blockers: [any blockers]
   - Key Learning: [most important thing learned]
   ```

2. **Save Pending TaskList:**
   - Check TaskList for any in-progress or pending tasks
   - Ensure descriptions are detailed enough to resume
   - Include file paths, approach details, what's left

3. **Save Session Findings:**
   - Any new patterns → workflow-patterns.md
   - Any bugs/gotchas → mistakes-learnings.md
   - Any preference discovered → malik-preferences.md
   - Any device/env info → device-environment.md

4. **Save Working Context:**
   - Which files were being actively edited
   - Which approach was being used
   - Any partial work that needs resuming

5. **Update state.json:**
   ```json
   {
     "timestamp": "[ISO timestamp]",
     "cwd": "[current working directory]",
     "trigger": "manual-save",
     "active_files": ["list of files being worked on"],
     "pending_tasks": ["list from TaskList"],
     "approach": "brief description of current approach"
   }
   ```
   Write to: `~/.claude/projects/<CWD-hash>/memory/state.json`

6. **Confirmation:**
   ```
   STATE SAVED
   ===========
   MEMORY.md Last Session: UPDATED
   TaskList: [X] pending tasks preserved
   Findings: [N] new entries saved to topic files
   state.json: UPDATED at [path]
   Recovery: Next session will auto-load this state
   ```

---

### `prepare` — Pre-Compact Emergency Protocol

**CRITICAL: Run this when context is getting full or before expected compact.**

#### Steps (ALL mandatory, in order):

1. **Save EVERYTHING from `save` command above** — run full save protocol

2. **Verify TaskList Accuracy:**
   - TaskList → are all tasks up to date?
   - Any stale tasks? → update or delete
   - Any missing tasks? → create them
   - Each task has enough description to resume without prior context

3. **Save Critical Working State:**
   - Currently open files and their modification state
   - Current debugging/investigation state
   - Any approach decisions made but not yet saved
   - Any agent results collected but not yet integrated

4. **Verify Recovery Path:**
   - state.json exists and is current
   - MEMORY.md Last Session is current
   - Post-compact hook will fire and inject recovery protocol
   - CLAUDE.md snapshot will be injected

5. **Confirmation:**
   ```
   PRE-COMPACT PREPARATION COMPLETE
   =================================
   State: SAVED (MEMORY.md + state.json + TaskList)
   Findings: [N] entries saved to topic files
   TaskList: [X] tasks with full descriptions
   Recovery: Post-compact hook will inject recovery protocol
   SAFE TO COMPACT: YES

   After compact, I will:
   1. Read CLAUDE.md (identity restoration)
   2. Read Last Session (context recovery)
   3. Check TaskList (work continuation)
   4. Resume from: [current task/state]
   ```

---

### `load` — Load Specific Context

Manually load context that might not be auto-loaded.

#### Steps:

1. **Parse what to load:**
   - `load project` → Read project CLAUDE.md + project MEMORY.md
   - `load global` → Read all global memory topic files
   - `load state` → Read state.json + Last Session
   - `load all` → Load everything (global + project + state)
   - `load <file>` → Read specific memory file

2. **Execute Reads:**
   - Read requested files
   - Parse and internalize the content
   - Report what was loaded

3. **Output:**
   ```
   CONTEXT LOADED
   ==============
   Loaded: [list of files read]
   Key Info:
     - [summary of important points from loaded files]
   Active Rules: [from MEMORY.md if loaded]
   Last Session: [brief if loaded]
   ```

---

### `efficiency` — Context Optimization Analysis

Analyze what's consuming context and suggest optimizations.

#### Steps:

1. **System Prompt Analysis:**
   - CLAUDE.md size → is it under 40KB? Any bloat?
   - MEMORY.md lines → is it under 200? Any overflow needed?
   - Hook injections → session-start-new.sh output size
   - Duplicate content between CLAUDE.md and MEMORY.md?

2. **Conversation Analysis:**
   - Large file reads that could use offset/limit instead
   - Repeated reads of same file
   - Large tool outputs that could be summarized
   - Agent outputs that were unnecessarily verbose

3. **Optimization Suggestions:**
   ```
   CONTEXT EFFICIENCY REPORT
   =========================
   System Prompt: [X]K tokens
     - CLAUDE.md: [size] — [OK / OPTIMIZE: suggestion]
     - MEMORY.md: [lines] lines — [OK / OVERFLOW: specific sections to move]
     - Hooks: [size] — [OK / REDUCE: suggestion]

   Session Patterns:
     - [pattern 1]: [optimization suggestion]
     - [pattern 2]: [optimization suggestion]

   Recommendations:
     1. [Highest impact optimization]
     2. [Second highest]
     3. [Third]

   Estimated Savings: ~[X]K tokens ([Y]% improvement)
   ```

4. **Auto-Fix Offer:**
   - For safe optimizations (moving content to topic files, cleaning stale entries)
   - Ask Malik before executing changes

---

### `reset` — Clean Session State

Reset session-specific state (NOT memory — just working state).

1. **Clear state.json** working state (not timestamp/cwd)
2. **Clear stale TaskList entries** from previous sessions
3. **Verify MEMORY.md Last Session** reflects clean state
4. **Report:** what was reset, what was preserved

---

## CONTEXT MATH REFERENCE

```
Token Estimation (rough):
  1 token ≈ 4 characters (English)
  1 token ≈ 3 characters (code)
  1KB ≈ 250 tokens (text) / 330 tokens (code)

Claude Code Context Budget:
  Total: ~1M tokens (1,000,000)
  System prompt: 20-40K (CLAUDE.md + MEMORY.md + hooks + plugins)
  Available for conversation: ~960K tokens
  Safe zone: < 800K total
  Warning zone: 800-900K total
  Danger zone: > 900K total
  Auto-compact trigger: ~967K total

File Size → Token Estimates:
  CLAUDE.md (30KB) ≈ 8-10K tokens
  MEMORY.md (first 200 lines, ~8KB) ≈ 2-3K tokens
  Note: 1M context, auto-compact at ~967K tokens
  Hook injection (~6KB) ≈ 1.5-2K tokens
  Project CLAUDE.md (if exists) ≈ varies
```

## EXECUTION RULES

- ALWAYS estimate conservatively — better to save early than lose work
- state.json goes in PERSISTENT dir (~/.claude/projects/), NEVER /tmp/
- Pre-compact save is NON-NEGOTIABLE — losing unsaved work = disaster
- Token estimates are ROUGH — err on the side of caution
- Context status should be FAST — don't read files unnecessarily for estimates
- Malik ko CLEAR batao risk level — GREEN/YELLOW/ORANGE/RED with action items
- If ORANGE/RED → auto-trigger `prepare` without asking

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
