---
name: agent-commander
description: "Agent lifecycle commander — selection intelligence, 7-step dispatch protocol, wave execution, fleet health monitoring, failure recovery, automatic dispatch triggers. Use when: agent, dispatch, spawn, delegate, fleet, wave, orchestrate, parallel, builder, explorer, too many edits, too many reads."
argument-hint: "[task to delegate or fleet operation]"
---

# Agent Commander — Fleet Operations

Master controller for all agent operations. Selection, dispatch, monitoring, verification, integration. Every agent spawned = your responsibility from birth to completion.

## Agent Selection Intelligence

### Quick Select (memorize this):
```
Need to BUILD code?          → builder (per-file scope)
Need to REVIEW code?         → code-reviewer (READ-ONLY)
Need to DEPLOY?              → deployer (build+deploy)
Need DOCUMENTATION?          → documenter (docs/README)
Need to EXPLORE/FIND?        → explorer (codebase navigation)
Need to TEST?                → qa-tester (writes+runs tests)
Need REVERSE ENGINEERING?    → re-specialist (binary/RE)
Need RESEARCH?               → researcher (deep investigation)
Need SITE AUDIT?             → site-auditor (web analysis)
Need SYSTEM OPS?             → system-guardian (infra/ops)
Need UI/FRONTEND work?       → ui-builder (frontend-only)
Need WEB AUTOMATION?         → web-automator (browser tasks)
```

### Size-Based Strategy:
```
SMALL  (1-2 files, <50 lines)   → Main thread direct. No agent overhead.
MEDIUM (3-5 files, <300 lines)  → 2-3 builders parallel
LARGE  (6-15 files)             → 4-6 agents, dependency-ordered waves
MEGA   (15+ files)              → 6-10 agents, multi-wave + integration checks
```

---

## Automatic Dispatch Triggers (MANDATORY)

These are NON-NEGOTIABLE. When these conditions are met, dispatch an agent IMMEDIATELY.

- **3+ sequential main thread Edits** → dispatch builder for remaining edits
- **5+ sequential main thread Reads** → dispatch explorer for bulk reading
- **5+ files to read for a task** → dispatch explorer (NOT main thread sequential reads)
- **Any task taking >10 tool calls on main thread** → RE-EVALUATE: should this be an agent?
- **Research/exploration needed** → ALWAYS agent (explorer), NEVER 10+ main thread Reads
- **3+ files to change** → ALWAYS use builder (not main thread)
- **Multi-file implementation** → ALWAYS parallel builders with explicit file boundaries
- **Post multi-agent work** → ALWAYS spawn qa-tester before claiming "done"

### Dispatch Threshold Table:
```
Sequential Edits >= 3          → STOP → dispatch builder
Sequential Reads >= 5          → STOP → dispatch explorer
Sequential Greps >= 5          → STOP → dispatch explorer
Delegation ratio > 50% at 25+  → ALL remaining work via agents
Delegation ratio > 70% at 50+  → EMERGENCY: agents ONLY, zero main thread implementation
```

---

## Pre-Dispatch Checklist (BEFORE any agent spawn)

```
BEFORE dispatching ANY agent:
  □ STEP 0 done? Memory grepped for task keywords?
  □ Credentials needed? → Read credentials-secrets.md FIRST
  □ NEVER hardcode passwords/API keys in agent prompts
  □ Credentials go as: "SSH details are in credentials-secrets.md — read it first"
```

**Session 08d65c07 failure:** SSH password hardcoded directly in agent prompt.
Should have: Read credentials-secrets.md → told agent to read it too.

---

## 7-Step Dispatch Protocol

Every agent dispatch follows this EXACTLY:

```
STEP 1 — TASK:     TaskCreate with clear description, status: pending
STEP 2 — SCOPE:    Define EXACT file boundaries (MODIFY / READ / DO NOT TOUCH)
STEP 3 — PROMPT:   Use T-BUILD/T-DEBUG/T-REVIEW/T-SCOUT template from auto-dispatch.md
STEP 4 — DISPATCH: TaskUpdate status: in_progress → spawn with run_in_background: true
STEP 5 — MONITOR:  Track agent ID, main thread stays free for other work
STEP 6 — VERIFY:   Read FULL output, check for TODOs/placeholders, verify files on disk
STEP 7 — REPORT:   TaskUpdate status: completed → TaskList → report to Malik → auto-dispatch next
```

**Shortcut for simple tasks:** Steps 1+2+3+4 can happen in one action. But NEVER skip 6+7.

---

## Prompt Quality Standard

Every agent prompt MUST include:

1. **Clear 1-line objective** — what to build/fix/find
2. **Scope boundaries** — MODIFY, READ, DO NOT TOUCH file lists
3. **Specific requirements** — numbered, unambiguous
4. **Expected output** — what success looks like
5. **Efficiency rules** — "Batch Bash with &&. Read files once. Parallel independent tool calls. Target <50% maxTurns."

### Anti-patterns in prompts:
```
WRONG: "Fix the bug"                    → No context, no file, no error
WRONG: "Update the docs"               → Which docs? What to update?
WRONG: "Make it better"                → Better HOW? Be specific.
RIGHT: "Fix TypeError in server.ts:45 — null check missing on user.id before DB query"
RIGHT: "Add /api/health endpoint to server.ts returning {status, uptime, version}"
```

---

## Wave Execution (3+ agents)

When multiple agents are needed, organize in waves:

```
WAVE 1: Independent agents (no file overlap)
  - Builder A: files X, Y
  - Builder B: files Z, W
  - Scout C: explore directory D
  → ALL dispatch in parallel, background

WAVE 2: Dependent on Wave 1 results
  - Builder D: needs Scout C output
  - Integration: needs Builder A + B complete
  → Dispatch as Wave 1 agents complete

WAVE 3: Verification
  - Integration-tester: verify all imports, types, build
  - Playwright-validator: UI verification if applicable
```

### Wave Rules:
- Same file = ONE agent only (no conflicts)
- Different files = PARALLEL (maximize speed)
- Dependent = SEQUENTIAL (wait for input)
- Always end with qa-tester for multi-agent work

---

## Fleet Health Monitoring

While agents run:
```
1. Track ALL active agents — IDs, tasks, expected completion
2. If agent silent >3 min → TaskOutput(block=false) to check status
3. If agent fails → read output, understand why, re-dispatch or fix manually
4. If agent quality score < 70 → review output manually, re-dispatch if needed
5. Prepare NEXT wave while current wave runs — idle main thread = waste
```

---

## Failure Recovery

```
Agent fails (API error):
  1. Retry dispatch ONCE with simpler prompt
  2. If still fails → dispatch different agent type
  3. ONLY after 2 agent failures → do manual work

Agent returns garbage (TODOs, placeholders, incomplete):
  1. Identify what's missing/wrong
  2. Re-dispatch with MORE SPECIFIC prompt + error context
  3. If 2nd attempt also garbage → do it manually but LOG the agent failure

Agent hits wrong files:
  1. Revert changes (git checkout specific files)
  2. Re-dispatch with STRICTER scope boundaries
  3. Add "DO NOT TOUCH" list explicitly

Agent quality score < 70:
  1. Read the output — what went wrong?
  2. Check: waste patterns? (re-reads, separate compiles)
  3. Re-dispatch with efficiency emphasis OR accept if code is correct
```

---

## What WRONG Looks Like (Session 65fca7dd)

This is the anti-pattern to NEVER repeat:

- Main thread did 45 Edits, 58 Reads, 129 Bash calls — **328 total main thread calls**
- Only 5 agent calls total — **98.5% main thread ratio**
- 309 budget warnings from hooks — **ALL IGNORED**
- Peak 19 sequential Edits — never once stopped to dispatch builder
- Should have been: 3 builder agents (parallel), each handling ~15 Edits
- Result: **22/100 quality score**, Malik's trust damaged

### What went wrong:
1. Never self-assessed delegation ratio during the session
2. Ignored all 309 hook warnings
3. Treated main thread as a worker instead of a commander
4. No automatic dispatch triggers fired (because they were advisory, not acted on)
5. No mid-session course correction despite clear signals

---

## What RIGHT Looks Like

A well-executed session with proper delegation:

```
Main Thread (20-30 calls):
  - TaskCreate for all work items
  - Dispatch 3-4 builders (parallel, background)
  - Monitor progress, prepare next wave
  - Verify agent outputs (read full, check disk)
  - Integration-tester dispatch
  - Report to Malik

Agents (70-80% of all calls):
  - Builder A: files X, Y (15-20 calls)
  - Builder B: files Z, W (15-20 calls)
  - Builder C: files V, U (15-20 calls)
  - Integration-tester: verify all (10-15 calls)

Result:
  - Main thread ratio: <30%
  - Agent ratio: >70%
  - Quality score: 80+
  - Malik happy, work done efficiently
```

---

## Decomposition Rules

**NEVER send broad scope to a single agent.** These phrases = DECOMPOSE FIRST:
- "full upgrade", "full redesign", "complete rewrite"
- "entire app", "all pages", "everything"
- "complete overhaul", "whole app"

### Decomposition algorithm:
```
1. Break broad task into 3-5 specific sub-tasks
2. Each sub-task = 1 agent with SPECIFIC file scope
3. Size check: if sub-task needs >30 tool calls, break it further
4. Map dependencies: which sub-tasks need others to complete first?
5. Assign to waves: independent = Wave 1 (parallel), dependent = Wave 2+
6. Dispatch ALL Wave 1 agents in parallel (background)
```

### Scope sizing:
```
1-2 files, <100 lines   → 10-15 turns  → 1 agent
3-5 files, <300 lines   → 15-25 turns  → 1 agent
5-10 files, mixed        → 25-40 turns  → 2-3 agents (split by file)
10+ files, major feature → 40+ turns    → 3-5 agents via coordinator
```

---

## Execution Rules

- DISPATCH within 5 seconds — use templates, don't write prompts from scratch
- **BACKGROUND is MANDATORY** — `run_in_background: true` for ALL agents. ZERO exceptions.
- Foreground agents = main thread BLOCKED = Malik can't interact = UNACCEPTABLE
- VERIFY FULLY — "agent done" is NOT "task done" until you verify on disk
- AUTO-NEXT — don't wait for Malik to say "next", dispatch automatically
- TRACK ALL — never lose track of a spawned agent, every agent has a lifecycle
- PARALLEL when independent — sequential only when there's a real dependency
- INTEGRATION-TEST after multi-agent — always, no exceptions
- REPORT SHORT — Malik wants results, not process descriptions
- NEVER spawn and forget — that's the cardinal sin of agent management

## Foreground Agent BAN — Session 73fb9fcd Lesson

**CRITICAL FAILURE:** Session 73fb9fcd ran Explore agents in FOREGROUND. Result:
- 5+ minutes idle per agent (37% of session WASTED)
- Malik couldn't interact during agent execution
- No parallel work happened — pure dead time

**THE FIX — HARDCODED:**
```
EVERY Agent() call MUST include: run_in_background=true

ONLY exception: result needed for LITERALLY the next line of code
  (e.g., agent returns a value you pass to the next function)
  This exception applies to <5% of dispatches.

Research/exploration agents → ALWAYS background
Builder agents → ALWAYS background
Review/audit agents → ALWAYS background
```

**While background agents run, main thread MUST:**
1. Prepare next task context (read files, draft prompts)
2. Check TaskList for unblocked work
3. Ask Malik if anything else needed
4. Update memory/daily log with progress
5. NEVER sit idle — idle = kamchori

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
