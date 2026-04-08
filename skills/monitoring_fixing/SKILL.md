---
name: monitoring_fixing
description: "KALIYA Deep Session Monitor — Analyzes any session by ID. Deep analysis of agent behavior, work quality, error handling, time waste, rule compliance, hallucinations, request-delivery gaps. Every finding backed by parser data. Use when: monitor session, audit session, check quality, session review, analyze session, check agent work."
argument-hint: "<session_id>"
---

# KALIYA Deep Session Monitor — /monitoring_fixing

> Run parser. Read data. Analyze deeply. Report findings with evidence.
> Every finding = parser line reference. No guessing. No hallucination.
> Monitoring is PRIMARY. Fixing is OPTIONAL (only when Malik asks or CRITICAL gaps found).

---

## JSONL TRANSCRIPT SCHEMA (Reference — DO NOT GUESS fields)

```
type: "progress"    -> {sessionId, cwd, version, gitBranch, type:"progress"}
type: "user"        -> {type:"user", message: {role:"user", content: STRING}}
type: "assistant"   -> {type:"assistant", message: {role:"assistant", content: LIST}}
type: "tool_result" -> {type:"tool_result", toolResult: {content: LIST[{type:"text", text:STRING}]}}

assistant content LIST items:
  {type: "text", text: "..."}           -> assistant text output
  {type: "tool_use", name: "Read"}      -> file read
  {type: "tool_use", name: "Agent"}     -> agent dispatch (has: subagent_type, description, prompt, run_in_background)
  {type: "tool_use", name: "Edit"}      -> file edit
  {type: "tool_use", name: "Bash"}      -> bash command
  {type: "tool_use", name: "TaskCreate"} -> task creation
  {type: "tool_use", name: "TaskUpdate"} -> task update

CRITICAL: user content = STRING. assistant content = LIST. NEVER assume type.
```

---

## PHASE 0 — LOCATE & PARSE (mandatory first step, no exceptions)

### Step 1: Find transcript file

```bash
find ~/.claude/projects/ -name "${SESSION_ID}*.jsonl" -type f 2>/dev/null
```

Not found? Try partial match:
```bash
find ~/.claude/projects/ -name "*${SESSION_ID:0:8}*" -type f 2>/dev/null | head -5
```

Still not found? Check alternate location:
```bash
find ~/.claude_2/projects/ -name "${SESSION_ID}*.jsonl" -type f 2>/dev/null | head -5
```

### Step 2: Run parser (MANDATORY — NEVER write your own parser)

```bash
# Quick overview first
python3 ~/.claude/tools/session-analyzer.py <JSONL_PATH> --mode summary 2>&1 | tail -80

# Then full analysis
python3 ~/.claude/tools/session-analyzer.py <JSONL_PATH> --mode full 2>&1
```

Parser returns structured JSON with: metadata, scores, compliance, lifecycle_checks, tool_calls, agent_dispatches, error_events, recommendations, corporate_violations, next_steps_violations.

**USE THIS DATA for ALL analysis.** Do not re-parse JSONL manually.

If parser output exceeds context, save to file and read sections:
```bash
python3 ~/.claude/tools/session-analyzer.py <JSONL_PATH> --mode full > /tmp/session-audit.json 2>&1
```

### Step 3: Identify project context

- Path contains project name -> Read that project's CLAUDE.md for project-specific rules
- ALWAYS cross-reference with global rules (already loaded via ~/.claude/CLAUDE.md)

### Step 4: Anchor to parser data

Before proceeding to Phase 1, confirm you have:
- [ ] Parser JSON loaded (summary or full mode)
- [ ] Session metadata: ID, project, line count, duration
- [ ] Compliance scores available
- [ ] Agent dispatch list available
- [ ] Error events list available

If any missing -> re-run parser. Do NOT proceed without parser data.

---

## PHASE 1 — DEEP ANALYSIS (the core — spend 80% of effort here)

### 1A. Session Overview

From parser metadata, extract:
- **Project:** directory path and project name
- **Goal:** what was the session about? (from first user message)
- **Duration:** session length (first to last event timestamp if available)
- **Scale:** total user messages, total tool calls, agents dispatched, tasks created
- **Efficiency ratio:** (tasks completed / tool calls used) — lower = more waste

### 1B. Request-Delivery Gap Analysis (MOST IMPORTANT)

For EACH user message in the session:

1. **Extract requirements:** List every specific item Malik asked for
   - Count them: "Malik asked for N things"
   - Be precise — "fix CSS" counts as 1, "fix CSS + add animation + mobile responsive" = 3

2. **Track delivery:** For each requirement, check:
   - Was an agent dispatched for it?
   - Did the agent return with results?
   - Was the result verified? (Read/Bash after agent return)
   - Was evidence provided to Malik?

3. **Gap identification:**
   - Items asked but NOT delivered = CRITICAL gap
   - Items delivered but NOT verified = HIGH gap
   - Items delivered without evidence = MEDIUM gap
   - 4/5 delivered = FAIL (Malik's rule: 5 asked = 5 delivered)

4. **Frustration correlation:**
   - Was gaali received? Map it to the specific gap that caused it
   - Gaali WITHOUT preceding gap analysis = system failed to self-correct

### 1C. Per-Agent Effectiveness Analysis

For EACH agent dispatched (from parser's agent_dispatches):

| Field | Check | Source |
|-------|-------|--------|
| Prompt quality | Has file paths? Has numbered requirements? Has rules? | agent dispatch input |
| Configuration | run_in_background=True? | agent dispatch input |
| Task scope | 1 agent = 1 task? Or overloaded with multiple jobs? | prompt content |
| Return status | Did it return? What did it report? | tool_result after agent |
| Output verification | Was Read/Bash called AFTER agent returned? | tool calls sequence |
| Quality score | A/B/C/D/F based on delivery vs prompt requirements | manual assessment |

Scoring: **A** all met + verified | **B** 90%+ minor gaps | **C** 50-89% major gaps | **D** <50% wrong approach | **F** crashed/no output

### 1D. Error & Failure Analysis

From parser's error_events, analyze EACH error:

1. **What happened:** exact error message and context
2. **How was it handled:**
   - Fixed immediately? (GOOD)
   - Ignored and moved on? (BAD — flag as gap)
   - Caused cascading failure? (CRITICAL — trace the chain)
   - Retried same approach 3+ times? (LOOP — flag as waste)
3. **Build/compile failures:** were they resolved before claiming "done"?
4. **Agent failures:** was the agent re-dispatched? With what changes?

### 1E. Waste & Inefficiency Analysis

Check for these waste patterns:

| Pattern | How to Detect | Severity |
|---------|--------------|----------|
| Loop detected | Same command/file accessed 3+ times | HIGH |
| Unnecessary reads | File read but never edited or used | MEDIUM |
| Agent rework | Same task dispatched to 2+ agents | HIGH |
| Approach churn | Approach tried, failed, same approach retried | HIGH |
| Per-message limit violations | >10 Reads, >3 Edits, >15 Bash, >20 total per user msg | CRITICAL |
| Worker work on main thread | Manager doing code edits, multi-file reads | HIGH |
| Monitoring loops | tail/grep/log polling same file | CRITICAL |
| Idle time | Agent dispatched but no other productive work done while waiting | MEDIUM |

Count total wasted calls. Calculate: (wasted calls / total calls) * 100 = waste percentage.

### 1F. Rule Compliance (25 Checks)

Parser provides compliance data. Present as single table grouped by category:

| # | Category | Check | Parser Field |
|---|----------|-------|-------------|
| 1 | Memory | memory_search first? | `compliance.step0_memory_first` |
| 2 | Memory | Memory before Edit/Write/Agent? | `compliance.memory_before_edit` |
| 3 | Memory | memory_daily logged? | `compliance.memory_daily_logged` |
| 4 | Tasks | TaskCreate within first 5 calls? | `compliance.task_create_early` |
| 5 | Tasks | All subtasks created upfront? | `compliance.task_create_count` |
| 6 | Tasks | TaskList after completion? | `compliance.task_list_after_complete` |
| 7 | Tasks | Proper status transitions? | `task_operations` |
| 8 | Agents | All agents background? | `compliance.all_agents_background` |
| 10 | Agents | Zero hardcoded credentials? | `compliance.agents_with_credentials` |
| 11 | Agents | Prompts have file paths? | `compliance.agents_with_file_paths` |
| 12 | Agents | Prompts have requirements? | `compliance.agents_with_requirements` |
| 13 | Manager | Read calls <= 10 per msg? | `compliance.read_count` |
| 14 | Manager | Edit calls <= 3 per msg? | `compliance.edit_count` |
| 15 | Manager | Total calls <= 30? | `compliance.total_tool_calls` |
| 16 | Manager | No worker-work on main thread? | Edit + code-Read count |
| 17 | Quality | Build/compile passed? | Bash results for build cmd |
| 18 | Quality | Agent output verified? | Read/Bash AFTER agent return |
| 19 | Quality | Evidence before "done"? | Last assistant text has proof |
| 20 | Lifecycle | Full lifecycle executed? | `lifecycle_checks` |
| 21 | Lifecycle | No "next steps for user"? | `next_steps_violations` |
| 22 | Lifecycle | Project-specific steps done? | `lifecycle_checks` by type |
| 23 | Autonomy | No unnecessary questions? | `compliance.ask_user_count` |
| 24 | Autonomy | No monitoring loops? | `compliance.loops_detected` |
| 25 | Comms | No corporate English? | `corporate_violations` |

For each FAIL: one-line explanation of what rule was violated and what happened.

### 1G. Hallucination Detection

Check session for these patterns:

| Pattern | Detection Method | Severity |
|---------|-----------------|----------|
| Fake file path | Read/Edit tool_result returned error (file not found) | CRITICAL |
| Wrong function name | Edit failed (old_string not found) or build broke | CRITICAL |
| False API response | Agent claims result X but tool_result shows Y | CRITICAL |
| Invented metrics | "5 tests passed" but no test runner in Bash output | HIGH |
| False completion | "done" but file unchanged (no Edit/Write in sequence) | HIGH |
| Wrong identifiers | Wrong package name, version, class name used | MEDIUM |
| Phantom dependencies | Import/require for library not in project | MEDIUM |

For each hallucination found: document what was claimed vs what actually happened.

---

## PHASE 2 — SCORING & REPORT

### Scoring Display

```
>> SESSION AUDIT ━━━━━━━━━━━━━━━━━━━━━━
   Session: <id> | Project: <name> | <lines> lines

   Rule Compliance    ▶ X% (N/25 passed)
   Agent Efficiency   ▶ X% (returned/dispatched, verified/returned)
   Request Delivery   ▶ X% (delivered/asked across all user messages)
   Lifecycle          ▶ X% (steps completed/total)
   Autonomy           ▶ X%
   Context Efficiency ▶ X% (productive calls / total calls)
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   OVERALL ▶ X% ■■■■■■■■□□

   Weights: Rules 25% | Agents 20% | Delivery 20% | Lifecycle 15% | Autonomy 10% | Context 10%
```

Scores: **90-100%** excellent | **75-89%** good, specific gaps | **60-74%** needs work | **<60%** critical problems

### Findings (prioritized by severity)

```
>> FINDINGS ━━━━━━━━━━━━━━━━━━━━━━━━━━━
   #1 [CRITICAL] <finding title>
      Evidence: <parser data reference — what happened>
      Impact: <why this matters — what it caused>

   #2 [HIGH] <finding title>
      Evidence: <parser data reference>
      Impact: <consequence>

   #3 [MEDIUM] <finding title>
      ...
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Severity: **CRITICAL** task failure/frustration | **HIGH** will fail in future | **MEDIUM** suboptimal | **LOW** style/format

### Recommendations

From parser's recommendations section + your own analysis findings.
Each recommendation: specific, actionable, references the finding it addresses.

---

## PHASE 3 — PERMANENT FIXES (OPTIONAL)

> This phase runs ONLY when:
> 1. Malik explicitly asks for fixes ("fix it", "patch it", "upgrade")
> 2. CRITICAL findings that need immediate system-level fix
> Otherwise: report findings and stop. Monitoring != fixing.

### Fix Targets (priority order)

| # | Target | File | When to Fix |
|---|--------|------|-------------|
| 1 | Agent injection rules | `~/.claude/hooks/agent-context-inject.sh` | Agent behavior gap |
| 2 | Global CLAUDE.md | `~/.claude/CLAUDE.md` (MAX 40KB!) | Main thread behavior gap |
| 3 | Project CLAUDE.md | `~/project/CLAUDE.md` | Project-specific gap |
| 4 | Quality rules | `~/.claude/rules/quality.md` | Quality standard gap |
| 5 | Output format | `~/.claude/rules/output-format.md` | Format/communication gap |
| 6 | Hook logic | `~/.claude/hooks/<hook>.sh` | Hook missed something |
| 7 | Parser | `~/.claude/tools/session-analyzer.py` | Parser missed data |
| 8 | Memory | Memory topic files | Learning to persist |

### Fix Protocol (for EACH fix)

1. **Read** target file — understand current state and existing rules
2. **Locate** exact section — find where fix belongs (line number)
3. **Deduplicate** — check if similar rule already exists. EXTEND, never duplicate
4. **Write** the fix — SPECIFIC rule text, not vague guidance
   - BAD: "Be more autonomous"
   - GOOD: "Android task = code + build + adb install + reboot + logcat verify"
5. **Verify syntax:**
   - Shell: `bash -n <file>`
   - Python: `python3 -c "import py_compile; py_compile.compile('<file>')"`
6. **Size check:**
   - CLAUDE.md < 40KB (`wc -c`)
   - agent-context-inject.sh injection < 5KB
   - Hooks < 200 lines (`wc -l`)

### Known Fix Patterns

- **Agent lifecycle gap** -> agent-context-inject.sh LIFECYCLE: add specific steps for project type
- **Agent listed next steps** -> agent-context-inject.sh AUTONOMY: strengthen "BANNED: listing TODO"
- **No memory_search** -> step0-enforcer.py + settings.json: verify hook registration
- **Too many main thread reads** -> CLAUDE.md Manager Role limits: lower limit or add trigger
- **Agent hallucinated path** -> agent-context-inject.sh QUALITY: add "verify file exists"
- **Agent skipped build** -> agent-context-inject.sh LIFECYCLE: add "build MUST pass"
- **Corporate English** -> agent-context-inject.sh IDENTITY: add specific banned phrase
- **Unnecessary questions** -> agent-context-inject.sh AUTONOMY: add "WebSearch FIRST"

### Verification After ALL Fixes

```bash
bash -n ~/.claude/hooks/agent-context-inject.sh && echo "SHELL OK"
echo '{}' | bash ~/.claude/hooks/agent-context-inject.sh 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print('OK' if 'hookSpecificOutput' in d else 'BROKEN')"
wc -c ~/.claude/CLAUDE.md  # must be < 40960
python3 -c "import py_compile; py_compile.compile('$HOME/.claude/tools/session-analyzer.py')" && echo "PYTHON OK"
python3 ~/.claude/tools/session-analyzer.py <JSONL_PATH> --mode summary > /dev/null 2>&1 && echo "PARSER OK"
```

---

## EXECUTION RULES (IRON LAW — ZERO EXCEPTIONS)

1. **Parser FIRST.** Run `session-analyzer.py` before ANY analysis. Never re-invent parsing.
2. **Data ONLY.** Report ONLY what parser data and transcript show. "Probably did X" = BANNED.
3. **Every finding = evidence.** Reference parser fields, line numbers, or tool results. No vague claims.
4. **UNKNOWN > WRONG.** Cannot verify a check? Mark UNKNOWN, never mark PASS by default.
5. **Anti-hallucination obsession.** Before reporting ANY finding, verify it exists in parser output. Fabricating audit findings = catastrophic — broken fixes applied to working system.
6. **Dispatch agent for heavy work.** Parser output too large? Dispatch general-purpose agent to analyze.
7. **Hinglish in report text.** Technical terms, file paths, code = English. Commentary = Hinglish.
8. **Thorough analysis.** Every error, every agent, every user request analyzed. Nothing skipped.
9. **Score honestly.** Inflating scores = lying to Malik. Deflating = wasting time on non-issues.
10. **Monitoring != Fixing.** Default: analyze and report. Fix only when explicitly asked or CRITICAL.
11. **Context protection.** Large parser output -> save to /tmp file, read in sections. Don't overflow context.
12. **Log to memory after audit.** Save session audit result to memory for pattern tracking across sessions.
