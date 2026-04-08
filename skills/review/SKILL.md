---
name: review
description: "Deep code review — security vulns, performance bottlenecks, logic bugs, code quality, maintainability. Use when user wants code reviewed, PR reviewed, security audit, architecture review, code quality check, or diff analysis."
argument-hint: "[file/directory/PR-url/PR-number]"
---

# Code Review — 5-Layer Deep Analysis

Review target: `$ARGUMENTS`

If no argument provided, ask what to review. Accept: file paths, directories, PR URLs, PR numbers, git diff ranges.

---

## Mode Selection

Determine scope first:

| Scope | Mode | Action |
|-------|------|--------|
| 1-3 files | **Standalone** | Review on main thread, no agent |
| 4+ files | **Agent** | Dispatch `code-reviewer` agent in background |
| PR URL/number | **PR Mode** | Fetch diff via `gh pr diff`, then review |
| Directory | **Agent** | Always dispatch — too many files for main thread |

**Standalone Mode**: Execute the full methodology below directly.

**Agent Mode**: Dispatch `code-reviewer` agent with the full methodology below as the prompt. Use `run_in_background: true`. After agent returns, read output fully, verify completeness, present report.

---

## PR Review Workflow

When target is a PR URL or number:

```bash
# Fetch PR diff
gh pr diff <number> > /tmp/pr-<number>.diff

# Get PR metadata
gh pr view <number> --json title,body,files,additions,deletions

# Get list of changed files
gh pr view <number> --json files --jq '.files[].path'
```

Read each changed file FULLY (not just the diff) to understand context. The diff shows WHAT changed — the full file shows WHY it matters.

After review, post inline comments:

```bash
# Comment on specific line
gh pr review <number> --comment --body "**[SEVERITY]** Issue description

\`\`\`suggestion
fixed code here
\`\`\`"

# Approve or request changes
gh pr review <number> --approve --body "Review summary"
gh pr review <number> --request-changes --body "Blocking issues listed"
```

**Approval Criteria**: Zero CRITICAL issues. Zero HIGH issues. MEDIUM issues acknowledged with timeline. All security findings addressed.

---

## 5-Layer Review Methodology

Execute ALL 5 layers. No shortcuts. No skipping. Order matters — correctness first because nothing else matters if the logic is wrong.

### Layer 1: Correctness

Find logic bugs, edge cases, type errors, null safety issues.

**Check**:
- Off-by-one errors in loops and array indexing
- Null/undefined/None dereferences — every `.` access on a possibly-null value
- Type coercion bugs (implicit conversions, wrong type assumptions)
- Race conditions in concurrent/async code
- Boundary conditions: empty input, single element, max size, negative values
- Error handling: are all error paths covered? Do catches re-throw or swallow?
- State management: stale state, mutation of shared state, missing state transitions
- Return values: are all code paths returning? Correct types?
- Integer overflow/underflow in arithmetic
- String encoding issues (UTF-8, emoji, RTL text)

**Evidence required**: For each bug found, show the exact code path that triggers it. No hypotheticals — prove it breaks.

### Layer 2: Security

OWASP Top 10 + language-specific attack vectors.

**Check**:
- **Injection**: SQL injection (string concatenation in queries), command injection (unsanitized shell args), LDAP injection, XPath injection
- **Broken Auth**: Hardcoded credentials, weak password policy, session fixation, JWT without expiry, missing rate limiting on auth endpoints
- **Data Exposure**: Secrets in code (API keys, tokens, passwords), PII in logs, sensitive data in error messages, missing encryption at rest
- **XXE**: XML parsing with external entities enabled
- **Broken Access Control**: Missing authorization checks, IDOR (direct object reference), privilege escalation paths, missing CORS validation
- **Misconfig**: Debug mode in production, default credentials, verbose error pages, unnecessary open ports
- **XSS**: Unescaped user input in HTML/JS, innerHTML usage, dangerouslySetInnerHTML without sanitization, template injection
- **Deserialization**: Pickle/marshal/eval on untrusted data, JSON parse of user input without schema validation
- **Dependency Vulns**: Known CVEs in dependencies (check versions), outdated packages with security patches available
- **Logging**: Missing audit trail for sensitive operations, log injection

**Evidence required**: Show the vulnerable code AND a proof-of-concept exploit scenario. Theoretical vulns without a trigger path = LOW, not CRITICAL.

### Layer 3: Performance

N+1 queries, algorithmic complexity, memory leaks, blocking I/O.

**Check**:
- **Database**: N+1 queries (loop with individual queries), missing indexes on WHERE/JOIN columns, SELECT * when few columns needed, unbounded queries without LIMIT, missing connection pooling
- **Algorithms**: O(n^2) or worse in hot paths, nested loops on large datasets, repeated computation (missing memoization), inefficient string concatenation in loops
- **Memory**: Unbounded caches/lists, event listener leaks (addEventListener without removeEventListener), closures holding references to large objects, streams not closed
- **I/O**: Synchronous file/network operations blocking event loop, missing connection timeouts, no retry with backoff, unbounded concurrent requests
- **Bundle/Asset**: Importing entire libraries for one function, unoptimized images, missing code splitting, unused CSS/JS shipped to client
- **Caching**: Missing caching on expensive computations, cache invalidation bugs, no TTL on cached data

**Evidence required**: Quantify the impact. "This is O(n^2)" is not enough — "This is O(n^2) where n = number of users, at 10K users = 100M operations per request" is.

### Layer 4: Code Quality

Naming, DRY, SOLID, dead code, complexity.

**Check**:
- **Naming**: Variables/functions that don't describe their purpose, single-letter names outside tight loops, inconsistent naming conventions (camelCase mixed with snake_case)
- **DRY**: Duplicated logic (3+ lines repeated = extract), copy-pasted code with minor variations, repeated magic numbers/strings without constants
- **SOLID Violations**: Classes with too many responsibilities (>5 public methods doing unrelated things), tight coupling between modules, violations of dependency inversion
- **Dead Code**: Unreachable branches, unused imports, commented-out code, functions never called (grep callers to verify), unused variables
- **Complexity**: Cyclomatic complexity >10 = flag for refactor. Deeply nested conditionals (>3 levels). Functions >50 lines. Files >500 lines.
- **Error Messages**: Generic "Something went wrong" instead of actionable messages. Missing context in errors (which input? which step?).
- **Consistency**: Mixed patterns for same operation (some places use async/await, others use callbacks). Inconsistent error handling strategy.

**Evidence required**: For each issue, provide the refactored code. Never just say "rename this" — show the new name and why it's better.

### Layer 5: Maintainability

Test coverage, documentation, dependency freshness, API surface.

**Check**:
- **Tests**: Are critical paths tested? Edge cases covered? Are tests actually asserting the right things (not just "runs without error")? Missing test for each bug found in Layer 1.
- **Documentation**: Public API without docs? Complex algorithms without comments explaining WHY? Missing README for setup? Outdated docs that contradict code?
- **Dependencies**: Outdated packages (major versions behind)? Abandoned dependencies (no commits in 2+ years)? Too many dependencies for simple tasks?
- **API Surface**: Breaking changes without version bump? Missing input validation on public API? Inconsistent error response format? Missing rate limiting on public endpoints?
- **Configuration**: Hardcoded values that should be configurable? Missing environment variable validation at startup? No sensible defaults?
- **Migration Path**: Database schema changes without migration? Breaking API changes without deprecation notice?

**Evidence required**: Suggest specific improvements with code. "Add tests" is useless — "Add test for X scenario: [test code]" is actionable.

---

## Severity Definitions

| Severity | Definition | Examples | Action |
|----------|-----------|----------|--------|
| **CRITICAL** | Data loss, security breach, system crash in production | SQL injection, auth bypass, unhandled OOM, data corruption | Block merge. Fix immediately. |
| **HIGH** | Broken feature, significant data integrity issue | Logic bug causing wrong calculations, race condition on write path, missing authorization check | Block merge. Fix before release. |
| **MEDIUM** | Degraded UX, performance regression, maintainability concern | N+1 query on non-critical path, missing input validation on internal API, cyclomatic complexity >15 | Fix within sprint. Can merge with ticket. |
| **LOW** | Style, naming, minor improvements | Inconsistent naming, missing JSDoc on internal function, TODO comment | Fix when touching the file. Non-blocking. |

---

## Language-Specific Checklists

### Python
- [ ] **Bare except**: `except:` catches `SystemExit` and `KeyboardInterrupt` — ALWAYS use `except Exception:`
- [ ] **Mutable defaults**: `def f(items=[])` — shared across calls. Use `def f(items=None): items = items or []`
- [ ] **F-string injection**: `eval(f"func_{user_input}()")` — user controls code execution
- [ ] **Late binding closures**: `[lambda: i for i in range(5)]` — all return 4. Use `lambda i=i: i`
- [ ] **Datetime traps**: `datetime.now()` is local time (no timezone). Use `datetime.now(timezone.utc)`. `.isoformat()` gives `+00:00` not `Z` — use `.strftime('%Y-%m-%dT%H:%M:%SZ')`
- [ ] **String concatenation in loops**: Use `''.join(parts)` instead of `result += string`
- [ ] **`is` vs `==`**: `is` checks identity, `==` checks equality. `x is True` fails for truthy non-bool values
- [ ] **Global state**: Module-level mutable state shared across threads without locks
- [ ] **`__init__` side effects**: Network calls or file I/O in constructors make testing impossible

### JavaScript / TypeScript
- [ ] **`==` vs `===`**: `==` coerces types — `"0" == false` is `true`. Always use `===`
- [ ] **Prototype pollution**: `obj[userInput] = value` — attacker can set `__proto__` properties
- [ ] **XSS via innerHTML**: `element.innerHTML = userInput` — use `textContent` or sanitize
- [ ] **Floating point**: `0.1 + 0.2 !== 0.3` — use integer math for money (cents, not dollars)
- [ ] **`this` binding**: Arrow functions vs regular functions in class methods and callbacks
- [ ] **Unhandled promise rejection**: Missing `.catch()` or try/catch around `await` — crashes Node.js
- [ ] **RegExp DoS (ReDoS)**: User-supplied regex or backtracking-heavy patterns on user input
- [ ] **`JSON.parse` without try**: Crashes on malformed input. Always wrap.
- [ ] **Node.js `require` of user input**: `require(userInput)` = arbitrary code execution
- [ ] **Event listener memory leaks**: `addEventListener` without corresponding `removeEventListener` on cleanup

### Go
- [ ] **Goroutine leaks**: Goroutine blocked on channel with no reader/writer. Use `context.WithCancel`.
- [ ] **Defer ordering**: Defers execute LIFO — resource cleanup order matters. Defer in loop = resource accumulation.
- [ ] **Nil pointer on interface**: Interface holding nil concrete value is not `== nil`. Check concrete type.
- [ ] **Error swallowing**: `val, _ := someFunc()` — silently ignoring errors. Every error must be handled or explicitly discarded with comment.
- [ ] **Data race**: Shared state across goroutines without mutex or channels. Run `go test -race`.
- [ ] **Slice gotchas**: `append()` may or may not allocate new backing array — aliasing bugs. Slice header vs underlying array.
- [ ] **String to byte slice**: `[]byte(s)` copies — expensive in hot loops. Use `unsafe.Slice` only if profiled.
- [ ] **Context propagation**: Missing `ctx` parameter in function chains — cancellation doesn't propagate.

---

## Output Format

Structure the review report exactly as follows:

```markdown
# Code Review: [target]

**Reviewer**: KALIYA | **Date**: [date] | **Scope**: [files reviewed] | **Mode**: [Standalone/Agent]

## Summary

| Category | Score | Issues |
|----------|-------|--------|
| Correctness | X/10 | N issues |
| Security | X/10 | N issues |
| Performance | X/10 | N issues |
| Code Quality | X/10 | N issues |
| Maintainability | X/10 | N issues |
| **Overall** | **X/10** | **N total** |

## Critical & High Issues

[List CRITICAL and HIGH issues first — these block merge]

### [SEVERITY] Issue Title — `file:line`

**Problem**: [1-2 sentences explaining the bug/vuln]

**Current code**:
```[lang]
problematic code here
```

**Fix**:
```[lang]
fixed code here
```

**Impact**: [What happens if not fixed]

---

## Medium & Low Issues

[Table format for quicker scanning]

| # | Severity | File:Line | Issue | Fix |
|---|----------|-----------|-------|-----|
| 1 | MEDIUM | `file:42` | Description | `suggested fix` |
| 2 | LOW | `file:88` | Description | `suggested fix` |

## Positive Observations

[What's done well — acknowledge good patterns, clean architecture, solid test coverage]

## Recommendations

[Strategic improvements beyond individual issues — architecture suggestions, tooling, process]
```

---

## Iron Rules

1. **Read before judge.** Read every file in scope FULLY. Read imports. Grep callers before changing signatures. No review without full context.
2. **Never suggest without fix code.** Every issue MUST include the exact code to fix it. "Consider refactoring" = useless. Show the refactored code.
3. **Verify your findings.** Before reporting a bug, trace the code path. Is it actually reachable? Is the input actually user-controlled? False positives destroy credibility.
4. **Grep callers before flagging dead code.** `grep -r "functionName"` across the codebase. It might be called from tests, scripts, or dynamic imports.
5. **Quantify performance claims.** "This is slow" = worthless. "This is O(n^2) where n = users table size, ~50K rows = 2.5B comparisons" = actionable.
6. **Check the test.** A function with a test that doesn't assert the right thing is worse than no test — it gives false confidence.
7. **Language-specific checklist is mandatory.** Run the relevant checklist for every file. These are the bugs that slip through generic reviews.
8. **Severity must be justified.** CRITICAL means production is at risk RIGHT NOW. Don't inflate severity for attention. Don't deflate it to avoid confrontation.

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
