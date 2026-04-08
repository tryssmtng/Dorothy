---
name: debug
description: "Military-grade structured debugging — reproduce, analyze root cause, fix, validate, save learnings. Anti-loop protection, memory integration, zero band-aids. Use when: debug, bug, error, crash, broken, not working, fix, issue, problem, failing, exception, traceback, stack trace, TypeError, undefined, null, 500, 404, segfault, ENOENT, ECONNREFUSED."
argument-hint: "[error description, file path, or error message]"
---

# KALIYA Debug Protocol — Military Grade

Structured 5-phase debugging. ZERO guessing. ZERO band-aids. Root cause or nothing.

## Target: `$ARGUMENTS`

If no arguments provided, ask: "Kya error aa rha hai? File path, error message, ya description de."

---

## PHASE 1: REPRODUCE — Capture the Crime Scene

**Objective:** See the error yourself. Don't trust descriptions alone.

### Steps:
1. **Get Error Context:**
   - If file path given → Read the file FULLY
   - If error message given → parse: error type, file, line number, stack trace
   - If description given → identify likely files, read them

2. **Reproduce the Error:**
   - If build error → run the build command yourself (`npm run build`, `python -c`, etc.)
   - If runtime error → run the command/script yourself
   - If browser error → use playwright-cli: open page, check console
   - If test failure → run the specific test
   - CAPTURE full error output — don't truncate

3. **Crime Scene Documentation:**
   ```
   ERROR CAPTURED
   ==============
   Type: [build/runtime/browser/test/type error/etc.]
   Message: [exact error message]
   File: [file:line]
   Stack Trace: [key frames]
   Reproducible: [YES/NO + how]
   ```

4. **Memory Check — MANDATORY:**
   ```
   Grep(pattern="<error-keyword>", path="~/.claude/projects/-Users-niwash/memory/mistakes-learnings.md")
   Grep(pattern="<error-keyword>", path="~/.claude/projects/-Users-niwash/memory/")
   ```
   - Similar bug found in memory? → Read that entry → Apply known fix FIRST
   - No match? → Proceed to Phase 2

---

## PHASE 2: ANALYZE — Root Cause Investigation

**Objective:** Find WHY, not just WHAT. Root cause, not symptom.

### Analysis Protocol:

1. **Stack Trace Analysis (if available):**
   - Read TOP to BOTTOM — root cause usually at the BOTTOM
   - Identify: originating file, function, line number
   - Read that exact code section

2. **Code Path Tracing:**
   - Read the failing function/file FULLY
   - Grep for ALL callers of the failing function
   - Grep for ALL imports/dependencies
   - Trace the data flow: where does the bad value come from?

3. **Pattern Recognition:**
   - Is this a NULL/undefined check missing?
   - Is this a type mismatch?
   - Is this an import/path resolution issue?
   - Is this a race condition / timing issue?
   - Is this an environment/config issue?
   - Is this a dependency version conflict?

4. **Differential Analysis:**
   - What changed recently? (`git diff`, `git log --oneline -10`)
   - Did it work before? What's different now?
   - Other files with same pattern — do they work? Why?

5. **External Knowledge (if stuck after code analysis):**
   - WebSearch the EXACT error message (copy-paste, don't paraphrase)
   - Check if it's a known bug in the library/framework
   - Check library docs for correct usage

6. **Root Cause Declaration:**
   ```
   ROOT CAUSE IDENTIFIED
   =====================
   What: [exact technical cause]
   Where: [file:line]
   Why: [underlying reason — not "it's broken" but WHY it's broken]
   Evidence: [code snippet, log line, or test that proves this is the cause]
   Confidence: [HIGH/MEDIUM — if MEDIUM, explain what else to check]
   ```

### ANTI-PATTERN DETECTION:
- "Let me try removing this line" → BANNED. Understand FIRST.
- "Let me add a try/catch" → BANNED unless the root cause IS an unhandled exception.
- "It works if I change this" → WHY does that fix it? Understand mechanism.

---

## PHASE 2B: SYSTEM-LEVEL DEBUGGING — Variable Isolation Protocol

**WHEN TO USE:** Problem is NOT a simple code bug but:
- Build pipeline breaks after code changes
- Detection triggered (Play Protect, antivirus, WAF) after changes
- Multi-component system breaks (server + client + build + deploy)
- "It was working before, now it isn't" — regression

**This phase saved 11.5 hours in session c013d181. USE IT.**

### Step 1: ESTABLISH KNOWN-GOOD BASELINE

```
Q1: Was this working before?
  YES → Find the exact working state:
    - git log: which commit was last known-good?
    - backup: is there a V2/backup that still works?
    - memory: was working state documented?
  NO → This is a new feature, not a regression. Skip to Phase 3.

Q2: Can I build + test the baseline RIGHT NOW?
  YES → DO IT. Build baseline → test → PROVE it works.
  NO → Find out why not. Fix baseline accessibility first.

Q3: Baseline still works?
  YES → Proceed to Step 2 (diff analysis)
  NO → Problem is NOT your changes. It's environment/external.
       Debug the environment instead.
```

### Step 2: DIFF — What EXACTLY Changed?

```bash
# For git-tracked projects:
git diff <last-good-commit> HEAD --stat
git diff <last-good-commit> HEAD -- <specific-file>

# For non-git / backup comparison:
diff -rq <baseline-dir>/ <current-dir>/ | grep -v '.git'

# For build artifacts:
unzip -l baseline.apk > /tmp/base.txt
unzip -l current.apk > /tmp/curr.txt
diff /tmp/base.txt /tmp/curr.txt
```

**OUTPUT: Complete list of changed files/components.**
**Categorize changes into INDEPENDENT groups:**
```
Group A: [Feature X files — e.g., SmsReceiver.kt, EventService.kt]
Group B: [Config changes — e.g., string_protector.py, builder.py]
Group C: [Cleanup changes — e.g., native lib removal, class renames]
Group D: [Infrastructure — e.g., build scripts, deployment config]
```

### Step 3: INCREMENTAL ISOLATION (The Scientific Method)

```
START: Baseline (known-good)

TEST 1: Baseline + Group A → Build → Test
  PASS → Group A is safe. Continue.
  FAIL → Group A is the root cause. Drill into individual files.

TEST 2: Baseline + Group A + Group B → Build → Test
  PASS → Group B is safe. Continue.
  FAIL → Group B is the root cause. Drill into individual files.

...continue until FAIL found...

DRILL DOWN: If Group X fails, split into individual changes:
  Baseline + single file from Group X → test
  Repeat until EXACT file/change identified.
```

**RULES:**
- ONE group at a time. NEVER add multiple groups simultaneously.
- Build + test AFTER EVERY addition. No exceptions.
- Document each test result in TaskList or assistant text.
- If you can't build locally, prepare the change and document what needs testing.

### Step 4: HYPOTHESIS-DRIVEN FIXING

Before EVERY change, document:
```
HYPOTHESIS
==========
Suspect: [file:change]
Theory: [why this would cause the problem]
Test: [I will apply X and expect Y]
If wrong: [I will try Z instead]
```

After testing:
```
RESULT
======
Hypothesis: [CONFIRMED / REJECTED]
Evidence: [build output, test result, detection scan]
Next: [apply next group / drill down / escalate]
```

### Step 5: RED-TEAM THINKING (for detection/bypass problems)

**When the problem is detection (Play Protect, AV, WAF, etc.):**
```
Think like the DETECTOR, not the developer:
1. What does the detector scan for? (strings, permissions, behaviors, signatures)
2. What changed that the detector NOW sees? (new strings, new permissions, etc.)
3. Scan the diff output: which changes are VISIBLE to static analysis?
4. Run the SAME tools the detector uses (aapt dump, dex2jar, strings, etc.)
5. Compare: detector input from baseline vs detector input from current
6. The DIFF in detector input = root cause of detection
```

### BUILD-DEPLOY INTELLIGENCE

```
LOCAL validation BEFORE deploy:
  1. Code compiles? (python -c "import py_compile;...", javac, tsc, etc.)
  2. Unit tests pass? (if available)
  3. Lint/static analysis clean? (if available)
  4. Diff review: do changes make sense together?

DEPLOY only when ALL local validation passes.
NEVER deploy hope. Deploy VERIFIED code.

Post-deploy validation:
  1. Service starts? (systemctl status, health check)
  2. Logs clean? (journalctl -u service -n 50)
  3. End-to-end test passes?
  4. If ANY fails → DON'T fix forward. REVERT to last working deploy.
```

---

## PHASE 3: FIX — Surgical Strike

**Objective:** Fix the ROOT CAUSE. Minimal blast radius. No collateral damage.

### Fix Protocol:

1. **Read Before Edit — MANDATORY:**
   - Read the file to be modified (FULL or relevant section)
   - Understand surrounding code context
   - Check: will this fix break anything else?

2. **Implement Fix:**
   - Fix the ROOT CAUSE, not the symptom
   - Minimal change — don't refactor unrelated code during a bugfix
   - Preserve existing code style and conventions
   - Add error handling ONLY if that's the root cause (missing error handling)

3. **Collateral Check:**
   - Grep ALL callers of the modified function → do they still work?
   - Check imports — anything broken?
   - If function signature changed → update ALL call sites

4. **Build Verification — IMMEDIATE:**
   - Run build/compile IMMEDIATELY after fix
   - Must pass. If fails → go back, don't stack fixes on broken code.

5. **Fix Documentation:**
   ```
   FIX APPLIED
   ============
   File: [file:line]
   Change: [what was changed]
   Root Cause: [brief — linking back to Phase 2]
   Blast Radius: [what's affected by this change]
   Build: [PASS/FAIL]
   ```

---

## PHASE 4: VALIDATE — Prove It Works

**Objective:** PROVE the fix works. Not "should work" — DOES work.

### Validation Protocol:

1. **Reproduce Original Error:**
   - Run the EXACT same command/test that triggered the error
   - Must NOT reproduce the error anymore
   - Capture output as proof

2. **Regression Check:**
   - Run related tests (if test suite exists)
   - Check adjacent functionality — did the fix break anything nearby?
   - If UI change → playwright-cli: open, click, screenshot, console check

3. **Edge Case Verification:**
   - NULL/empty input → still works?
   - Large/overflow input → still works?
   - Concurrent/rapid input → still works?
   - Error conditions → graceful handling?

4. **Cross-Check:**
   - Grep for same bug pattern in OTHER files → fix those too (JARVIS brain)
   - Same anti-pattern elsewhere? → Fix ALL instances, not just the reported one

5. **Validation Report:**
   ```
   VALIDATION
   ==========
   Original Error: [FIXED - no longer reproduces]
   Regression: [PASS - no new failures]
   Edge Cases: [PASS/PARTIAL - details]
   Pattern Scan: [X other instances found and fixed / No other instances]
   Evidence: [build output, test output, screenshot]
   ```

---

## PHASE 5: LEARN — Save to Memory

**Objective:** Never hit this bug again. Evolve.

### Learning Protocol:

1. **Is This Worth Saving?**
   - New bug pattern? → YES, save
   - Tricky root cause? → YES, save
   - Common mistake? → YES, save
   - Simple typo? → NO, skip
   - Environment-specific quirk? → YES, save

2. **Save to mistakes-learnings.md:**
   - Use Edit tool to append to appropriate section
   - Format:
     ```
     - **[Bug Type]**: [one-line description of root cause + fix]
       - Symptom: [what the error looked like]
       - Root cause: [actual cause]
       - Fix: [what fixed it]
       - Prevention: [how to avoid in future]
     ```

3. **Update Relevant Topic Files:**
   - If it's a workflow improvement → save to workflow-patterns.md
   - If it's a tool gotcha → save to appropriate topic file
   - If it reveals a Malik preference → save to malik-preferences.md

4. **Final Report:**
   ```
   DEBUG COMPLETE
   ==============
   Bug: [one-line summary]
   Root Cause: [technical cause]
   Fix: [file:line — what changed]
   Validated: [YES + evidence]
   Saved to Memory: [YES/NO — file if yes]
   Time: [phases completed]

   Pattern Alert: [if same pattern found elsewhere, list locations]
   ```

---

## ANTI-LOOP PROTOCOL

```
ATTEMPT 1: Standard analysis → fix → validate
ATTEMPT 2: Different angle — check dependencies, environment, config
ATTEMPT 3: External knowledge — WebSearch exact error, check GitHub issues

IF 3 ATTEMPTS SAME APPROACH → HARD STOP
  - Report to Malik: what was tried, what failed, what's unclear
  - Suggest: different approach, expert review, or more context needed
  - DO NOT keep retrying the same thing

BUILD-DEPLOY-FAIL LOOP DETECTION:
  Deploy → fail → fix → deploy → fail = DEATH SPIRAL
  After 3rd deploy-fail → STOP DEPLOYING
  → Go to Phase 2B (system-level debugging)
  → Establish baseline → isolate variable → test incrementally
  → NEVER deploy again until variable is isolated

FRUSTRATION ESCALATION:
  1 gaali = specific gap. Find it, fix it.
  2+ gaali same topic = FUNDAMENTAL approach is wrong.
    → STOP current approach entirely
    → Phase 2B: baseline, diff, isolate, test
    → Report: "Approach change — here's what I found"
  3+ gaali = YOU are the problem. Ask Malik for direction.
```

## ESCALATION

If after Phase 2 the root cause is unclear:
```
ESCALATE: "Malik, root cause 100% clear nahi hai.
  Tried: [1, 2, 3]
  Suspects: [A, B, C]
  Need: [more context / different approach / specific input]"
```

If after Phase 2B variable isolation is done:
```
REPORT: "Malik, isolated the root cause:
  Baseline: [works — proved via X]
  Root cause: [Group/file Y — broke when added]
  Evidence: [test result showing break]
  Fix options: [A or B]
  Recommendation: [preferred option + why]"
```

## EXECUTION RULES

- NEVER guess the fix — understand first, then fix
- NEVER add try/catch to hide errors — fix the actual cause
- NEVER skip Memory Check in Phase 1 — past bugs are GOLD
- ALWAYS build/test after fix — broken fix = no fix
- ALWAYS check for same pattern elsewhere — JARVIS brain
- ALWAYS save non-trivial learnings — evolution = intelligence
- Root cause fix ONLY — band-aids = REDO
- Minimal blast radius — don't refactor during bugfix
- If it's in memory already, USE the known fix — re-discovering = gaddari

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
