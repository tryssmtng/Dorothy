# Code Quality & Verification — Zero Tolerance

## Code Quality
- Production-grade. Error handling. Edge cases. Security. No dead code.
- No TODOs, placeholders, empty functions, fake returns. Ever.
- Every function called. Every import resolves. Orphan code = delete.
- Root cause fix, not band-aid.
- Build passes before claiming "done."

## Verification Protocol
1. Read file fully before modifying. Grep callers before changing signatures.
2. After edit → build/compile → verify syntax → test if applicable.
3. "Done" = build passes + tested + all features present + evidence shown.

### Grep Verification Patterns
- Grep for content words, NOT markdown syntax (`"Section Name"` not `"## Section Name"`).
- Avoid backslashes in grep patterns. Use literal strings.
- Zero matches ≠ missing. Read the file manually before claiming "missing."

## Error Recovery
- Build fail → read full error → root cause → fix → verify.
- Unknown error → WebSearch exact error text.
- Anti-loop + adaptation strategies → see CLAUDE.md "Anti-Loop" section (ONE place, no duplicate).

## Debugging Intelligence (Session c013d181 Lesson)
- "Was working, now broken" → CLAUDE.md Scientific Debugging Protocol. MANDATORY.
- Build-deploy-fail 3x → STOP deploying. Establish baseline. Isolate variable.
- NEVER make multiple changes then test all at once. ONE change → test → next.
- NEVER deploy without local validation (compile, syntax check, import check).
- Hypothesis BEFORE fix with evidence. "I think" without evidence = PREDICTION = BANNED.
- Detection problems (Play Protect, AV, WAF) → think like the DETECTOR. What does it see?
- File edited 3+ times in one session → STOP. You don't understand the file. Read it FULLY first.

## "Verify" Means Different Things Per Domain

**Xposed/Android hooks:**
- Verify = grep CALLING CODE (who calls this method? what does caller do with return value?)
- Verify = check 3 OPEN-SOURCE implementations (JustTrustMe, TrustMeAlready, SSLUnpinning — do they use same pattern?)
- Verify = device test (install → reboot → logcat → target app behavior)
- Static code review ALONE = NOT enough to call something a "bug"
- `param.result = null` for void methods = INTENTIONAL in Xposed. Don't "fix" it.

**Web/Backend code:**
- Verify = build passes + curl/API test + error handling tested
- Verify = screenshot for UI changes (playwright-cli)

**General code:**
- Verify = build/compile + run tests + grep for callers before changing signatures
- "Bug found in code review" = HYPOTHESIS, not fact. Reproduce it FIRST.

## Confidence Levels for Code Changes
- **HIGH** = reproduced on device/test, error log shows exact failure → FIX immediately
- **MEDIUM** = code pattern looks wrong but no reproduction yet → REPORT to Malik, ask before fixing
- **LOW** = theoretical concern from static analysis, no evidence → REPORT only, suggest investigation

## UI/UX — Apple Grade
- Zero emoji in UI. Custom inline SVG icons, stroke 1.5-2px.
- Micro-interactions (0.2-0.3s hover), generous whitespace, smooth animations.
- Responsive: desktop + tablet (768px) + mobile (480px). Always.
- Skeleton loading. Designed error/empty states.

## Playwright Verification — UI Tasks

**Any UI/visual change = playwright-cli screenshot BEFORE claiming "done".**

```
Session: S=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" | tr '[:upper:]' '[:lower:]' | tr ' _' '--')
Check:   playwright-cli list | grep "$S"
Open:    playwright-cli -s=$S open <url> --persistent
Shot:    playwright-cli -s=$S screenshot
Mobile:  playwright-cli -s=$S resize 390 844 → screenshot
Close:   playwright-cli -s=$S close
```

Required for: CSS/styling, layout/component changes, new UI elements, redesigns.
NOT required for: backend, config, CLI tools, non-visual code.
