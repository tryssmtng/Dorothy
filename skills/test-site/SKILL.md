---
name: test-site
description: "Full QA website testing — functional, responsive, performance, accessibility, security. Use when user wants a website tested, app tested, bugs found, site health checked, UX audit, mobile test, page speed check, or accessibility review."
argument-hint: "[url]"
---

# Live Site Testing — 5-Phase QA Protocol

Test target: `$ARGUMENTS`

If no URL provided, ask for the URL to test.

---

## Mode Selection

| Scope | Mode | Action |
|-------|------|--------|
| Quick smoke test (1 page, specific check) | **Standalone** | Test on main thread directly |
| Full site audit (multi-page, all phases) | **Agent** | Dispatch `live-site-tester` agent in background |
| Specific phase only (e.g., "test mobile") | **Standalone** | Run that phase on main thread |

**Standalone Mode**: Execute relevant phases below directly using playwright-cli commands.

**Agent Mode**: Dispatch `live-site-tester` agent with the full protocol below. Use `run_in_background: true`. After agent returns, read output fully, verify screenshots captured, present report.

---

## RESOURCE RULE: ONE session per project. NEVER create unique session names (-qa, -auto, -verify, etc.).
## ALWAYS close session when done: `playwright-cli -s=$S close`
## Zombie sessions = 10GB+ RAM wasted. This is NON-NEGOTIABLE.

## Session Setup

Every test session uses project-isolated browser profiles via playwright-cli.

```bash
# Session name = project name ONLY. NO suffixes (-qa, -auto, -verify, etc.)
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

ALL commands in this skill use `-s=$S` flag. No exceptions. No suffixes.

**Cleanup**: `playwright-cli -s=$S close` after testing completes. **MANDATORY — not optional.**

---

## 5-Phase Test Protocol

Execute all phases in order. Each phase builds on the previous. Skip nothing.

### Phase 1: Functional Testing

Test every interactive element. Buttons that don't work = broken product.

**Navigation**:
- Click every nav link — verify correct page loads, URL updates, no 404s
- Test browser back/forward — state preserved correctly?
- Test deep links — paste URL directly, does the page load correctly?
- Check breadcrumbs if present — accurate path? Clickable?

**Buttons & CTAs**:
- Click every button — does it perform its action?
- Disabled states — are they visually distinct? Do they prevent clicks?
- Loading states — spinner/skeleton shown during async operations?
- Double-click protection — does rapid clicking cause duplicate submissions?

**Forms**:
- Fill every form field with valid data — submit succeeds?
- Empty submission — proper validation errors shown?
- Invalid data (wrong email format, too short password) — field-level errors?
- Special characters in text fields — `<script>alert(1)</script>`, `'; DROP TABLE`, unicode emoji
- Required field indicators — clear which fields are mandatory?
- Auto-complete behavior — does it interfere with custom inputs?

**Error States**:
- 404 page — custom or default? Links back to home?
- Server error page — informative or generic? Leaks stack traces?
- Network offline — graceful degradation? Error message shown?
- Empty states — what shows when lists/search results are empty?

**Media**:
- All images load — no broken image icons
- Videos play — controls work, no autoplay unless intended
- SVGs render — no missing icons

**Evidence**: `snapshot` before interaction, `screenshot` after. Console errors checked after every page load.

### Phase 2: Responsive Testing

Test at three breakpoints. Resize and screenshot at each.

**Breakpoints Table**:

| Device | Width x Height | What to Verify |
|--------|---------------|----------------|
| **Desktop** | 1440 x 900 | Full layout, sidebar visible, multi-column grids, hover states, large images crisp |
| **Tablet** | 768 x 1024 | Nav collapses to hamburger/condensed, grid reflows to 2-col, touch targets ≥44px, no horizontal scroll |
| **Mobile** | 390 x 844 | Single column, hamburger menu works, text readable without zoom, buttons full-width, no content overflow, sticky header/footer don't overlap content |

**Resize commands**:
```bash
playwright-cli -s=$S resize 1440 900    # Desktop
playwright-cli -s=$S screenshot /tmp/qa-desktop-<page>.png
playwright-cli -s=$S resize 768 1024     # Tablet
playwright-cli -s=$S screenshot /tmp/qa-tablet-<page>.png
playwright-cli -s=$S resize 390 844      # Mobile
playwright-cli -s=$S screenshot /tmp/qa-mobile-<page>.png
```

**Check at every breakpoint**:
- No horizontal scrollbar (content fits viewport width)
- Text readable without zooming (min 14px on mobile)
- Touch targets minimum 44x44px (iOS HIG requirement)
- Images scale properly (no pixelation, no overflow)
- Modals/dropdowns don't overflow viewport
- Fixed/sticky elements don't overlap content
- Navigation accessible (hamburger menu opens/closes correctly)
- Forms usable (inputs not cut off, keyboard doesn't obscure fields)

**Evidence**: Screenshot at each breakpoint for every key page. Side-by-side comparison in report.

### Phase 3: Performance Testing

Measure Core Web Vitals. Fast site = good UX = better SEO.

**Metrics & Thresholds**:

| Metric | Good | Needs Work | Poor | What It Measures |
|--------|------|-----------|------|-----------------|
| **LCP** (Largest Contentful Paint) | < 2.5s | 2.5-4.0s | > 4.0s | When main content is visible |
| **FID** (First Input Delay) | < 100ms | 100-300ms | > 300ms | Time to respond to first interaction |
| **CLS** (Cumulative Layout Shift) | < 0.1 | 0.1-0.25 | > 0.25 | Visual stability (elements jumping around) |
| **TTFB** (Time to First Byte) | < 800ms | 800-1800ms | > 1800ms | Server response speed |
| **FCP** (First Contentful Paint) | < 1.8s | 1.8-3.0s | > 3.0s | When first content appears |

**How to measure via playwright-cli**:

```bash
# Page load timing via console
playwright-cli -s=$S console

# Execute performance measurement in browser
playwright-cli -s=$S evaluate "JSON.stringify(performance.getEntriesByType('navigation')[0])"

# Get LCP
playwright-cli -s=$S evaluate "new Promise(r => new PerformanceObserver(l => { const e = l.getEntries(); r(e[e.length-1].startTime); }).observe({type:'largest-contentful-paint',buffered:true}))"

# Get CLS
playwright-cli -s=$S evaluate "new Promise(r => { let c=0; new PerformanceObserver(l => { for(const e of l.getEntries()) { if(!e.hadRecentInput) c+=e.value; } r(c); }).observe({type:'layout-shift',buffered:true}); setTimeout(()=>r(c),3000); })"

# Resource sizes
playwright-cli -s=$S evaluate "performance.getEntriesByType('resource').map(r=>({name:r.name.split('/').pop(),size:r.transferSize,duration:r.duration})).filter(r=>r.size>50000)"
```

**Also check**:
- Total page weight (target: < 3MB for initial load)
- Number of HTTP requests (target: < 50 for initial load)
- Render-blocking resources (CSS/JS in head without async/defer)
- Unoptimized images (large images served without compression or responsive srcset)
- Missing compression (gzip/brotli on text resources)
- Console errors during load (JS errors that might block rendering)

### Phase 4: Accessibility Testing

WCAG 2.1 Level AA compliance. Not optional — it's the law in many jurisdictions.

**Images & Media**:
- Every `<img>` has meaningful `alt` text (not "image", not filename)
- Decorative images use `alt=""` or `role="presentation"`
- Videos have captions/transcripts
- Audio has transcripts

**Color & Contrast**:
- Text contrast ratio ≥ 4.5:1 for normal text, ≥ 3:1 for large text (18px+ or 14px+ bold)
- Information not conveyed by color alone (error states use icons + text, not just red)
- Check via: `playwright-cli -s=$S evaluate "getComputedStyle(document.querySelector('<selector>')).color"`
- Focus indicators visible — not removed via `outline: none` without replacement

**Keyboard Navigation**:
- Tab through entire page — logical order? All interactive elements reachable?
- Enter/Space activates buttons and links
- Escape closes modals and dropdowns
- Arrow keys work in menus, tabs, sliders
- No keyboard traps (can tab into AND out of every component)
- Skip navigation link present for screen reader users

**Semantic HTML & ARIA**:
- Heading hierarchy: one `<h1>`, sequential `<h2>`→`<h3>` (no skipping levels)
- Landmarks: `<main>`, `<nav>`, `<header>`, `<footer>` present and correct
- Form inputs have associated `<label>` elements (not just placeholder text)
- ARIA roles used correctly (not `role="button"` on a `<div>` when `<button>` works)
- `aria-live` regions for dynamic content updates
- `aria-expanded` on toggles, `aria-hidden` on decorative elements

**Check via playwright-cli**:
```bash
# Count images without alt
playwright-cli -s=$S evaluate "document.querySelectorAll('img:not([alt])').length"

# Check heading hierarchy
playwright-cli -s=$S evaluate "[...document.querySelectorAll('h1,h2,h3,h4,h5,h6')].map(h=>h.tagName+': '+h.textContent.trim().slice(0,50))"

# Check form labels
playwright-cli -s=$S evaluate "[...document.querySelectorAll('input:not([type=hidden]):not([type=submit])')].map(i=>({id:i.id,hasLabel:!!document.querySelector('label[for=\"'+i.id+'\"]'),placeholder:i.placeholder}))"

# Check link text
playwright-cli -s=$S evaluate "[...document.querySelectorAll('a')].filter(a=>!a.textContent.trim()&&!a.getAttribute('aria-label')).length + ' links without text'"
```

### Phase 5: Security Quick Scan

Surface-level security checks. Not a pentest — a quick health check.

**Transport Security**:
- HTTPS enforced — HTTP redirects to HTTPS?
- HSTS header present: `Strict-Transport-Security: max-age=31536000; includeSubDomains`
- No mixed content (HTTP resources loaded on HTTPS page)

**Headers**:
```bash
# Check security headers via evaluate
playwright-cli -s=$S evaluate "fetch(window.location.href).then(r=>Object.fromEntries(r.headers))"
```
- `Content-Security-Policy` — present and not `unsafe-inline unsafe-eval *`
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY` or `SAMEORIGIN`
- `Referrer-Policy` — not `unsafe-url`
- `Permissions-Policy` — restricts camera, microphone, geolocation

**Cookies**:
```bash
playwright-cli -s=$S evaluate "document.cookie"
```
- Session cookies have `Secure` flag (HTTPS only)
- Session cookies have `HttpOnly` flag (no JS access)
- `SameSite=Lax` or `Strict` (CSRF protection)

**XSS Quick Check**:
- Try `<script>alert(1)</script>` in search fields, URL params, form inputs
- Check if input is reflected unescaped in the page source
- Test URL parameters: `?q=<img onerror=alert(1) src=x>`

**Open Redirects**:
- Test: `?redirect=https://evil.com`, `?next=//evil.com`, `?url=javascript:alert(1)`
- Does the site redirect without validation?

**Information Disclosure**:
- Check `/robots.txt`, `/.env`, `/wp-admin`, `/api/docs`, `/.git/HEAD`
- Console errors leaking stack traces or internal paths
- Server header revealing software version

---

## Test Case Library

### E-Commerce Sites
- Product listing: filters work, sort works, pagination works
- Product detail: images zoom, variants selectable, add to cart works
- Cart: quantity update, remove item, price calculation correct
- Checkout: form validation, payment flow, error handling
- Search: returns relevant results, handles typos, empty results page
- User account: login, register, password reset, order history

### SaaS Dashboards
- Auth flow: login, logout, session expiry, password reset
- Dashboard: data loads, charts render, filters work
- CRUD operations: create, read, update, delete for main entities
- Settings: profile update, notification preferences, billing
- Permissions: restricted pages show 403, not broken UI
- Real-time: WebSocket updates if applicable

### Landing Pages
- Hero section: CTA visible above fold, loads fast
- Scroll behavior: smooth scroll to sections, lazy loading works
- Lead capture forms: validation, success message, no duplicate submission
- Social proof: testimonials load, logos display
- Footer: all links work, legal pages exist

### Blog / Content Sites
- Article rendering: formatting, code blocks, images, embeds
- Navigation: categories, tags, search, pagination
- Comments: submit, display, validation
- Share buttons: correct URLs, correct metadata (OG tags)
- RSS feed: valid XML, all posts included

---

## Bug Report Template

Every bug found MUST follow this format:

```markdown
### BUG-[number]: [Short descriptive title]

**Severity**: CRITICAL / HIGH / MEDIUM / LOW
**Phase**: Functional / Responsive / Performance / Accessibility / Security
**Page**: [URL of affected page]
**Device**: Desktop 1440px / Tablet 768px / Mobile 390px

**Steps to Reproduce**:
1. Navigate to [URL]
2. [Action]
3. [Action]
4. Observe [problem]

**Expected**: [What should happen]
**Actual**: [What actually happens]

**Screenshot**: `/tmp/qa-bug-[number].png`

**Console Errors** (if any):
```
error text here
```

**Suggested Fix**: [Specific fix — CSS change, HTML fix, JS correction. Not vague.]
```

---

## Report Scoring System

Score each category 0-10. Weight them for the final health score.

| Category | Weight | Score Range |
|----------|--------|-------------|
| Functional | 30% | 0-10 |
| Responsive | 20% | 0-10 |
| Performance | 20% | 0-10 |
| Accessibility | 15% | 0-10 |
| Security | 15% | 0-10 |

**Scoring Guide**:
- **10**: No issues found. Exemplary implementation.
- **8-9**: Minor issues only (LOW severity). Production-ready.
- **6-7**: Some MEDIUM issues. Needs attention but functional.
- **4-5**: HIGH issues present. Significant problems affecting UX.
- **2-3**: CRITICAL issues. Major functionality broken.
- **0-1**: Site is non-functional or severely compromised.

**Final Health Score**: Weighted average of all categories.

**Health Rating**:
- 9.0-10.0: Excellent — ship it
- 7.0-8.9: Good — minor fixes needed
- 5.0-6.9: Fair — needs work before launch
- 3.0-4.9: Poor — significant issues
- 0.0-2.9: Critical — do not launch

---

## Output Format

Structure the test report exactly as follows:

```markdown
# Site Test Report: [URL]

**Tester**: KALIYA | **Date**: [date] | **Mode**: [Standalone/Agent]

## Health Score: [X.X/10] — [Rating]

| Category | Score | Weight | Weighted | Issues |
|----------|-------|--------|----------|--------|
| Functional | X/10 | 30% | X.X | N bugs |
| Responsive | X/10 | 20% | X.X | N bugs |
| Performance | X/10 | 20% | X.X | N metrics failed |
| Accessibility | X/10 | 15% | X.X | N violations |
| Security | X/10 | 15% | X.X | N findings |
| **Total** | | **100%** | **X.X** | **N total** |

## Critical & High Issues

[Bug reports for CRITICAL and HIGH severity — fix these first]

## Performance Metrics

| Metric | Value | Threshold | Status |
|--------|-------|-----------|--------|
| LCP | X.Xs | < 2.5s | PASS/FAIL |
| FID | Xms | < 100ms | PASS/FAIL |
| CLS | X.XX | < 0.1 | PASS/FAIL |
| TTFB | Xms | < 800ms | PASS/FAIL |
| FCP | X.Xs | < 1.8s | PASS/FAIL |

## Responsive Screenshots

| Page | Desktop | Tablet | Mobile |
|------|---------|--------|--------|
| Home | [path] | [path] | [path] |

## All Issues

| # | Severity | Phase | Page | Issue | Fix |
|---|----------|-------|------|-------|-----|
| 1 | HIGH | Functional | /page | Description | Fix |
| 2 | MEDIUM | Responsive | /page | Description | Fix |

## Positive Observations

[What's done well]

## Recommendations

[Priority-ordered action items]
```

---

## BROWSER RESOURCE PROTOCOL (MANDATORY)

1. **SESSION NAME:** `S=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" | tr '[:upper:]' '[:lower:]' | tr ' _' '--')` — project name ONLY. **NEVER** add suffixes (-qa, -auto, -verify). ONE session per project.

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

1. **Snapshot before every interaction.** DOM state must be captured before clicking, filling, or navigating. No blind actions.
2. **Screenshot as evidence.** Every bug needs a screenshot. Every breakpoint needs a screenshot. No claims without visual proof.
3. **Console check after every page.** `playwright-cli -s=$S console` — zero errors is the target. Every error is logged.
4. **Test the unhappy path.** Empty inputs, wrong formats, network errors, edge cases. Happy path testing = useless testing.
5. **Quantify performance.** Numbers, not feelings. "Feels slow" is not a bug report. "LCP 4.2s (threshold 2.5s)" is.
6. **Clean up after yourself.** `playwright-cli -s=$S close` when done. No orphan browser sessions. MANDATORY, not optional.
7. **Every bug gets a fix suggestion.** "This is broken" without a fix = incomplete report. Show the specific CSS/HTML/JS change needed.
8. **Responsive is not optional.** 60%+ of web traffic is mobile. Skip responsive testing = skip majority of users.

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
