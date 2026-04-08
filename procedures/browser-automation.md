# Browser Automation — Procedural Memory

> playwright-cli usage rules. ONLY browser tool allowed.

## Rules
- **ONLY playwright-cli via Bash.** Chrome DevTools MCP = BANNED. Puppeteer MCP = BANNED.
- Session name: `S=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" | tr '[:upper:]' '[:lower:]' | tr ' _' '--')`
- Check before open: `playwright-cli list | grep "$S"` → Open = `goto`, Closed = `open --persistent`
- Max 5 tabs. Close oldest before new.
- Close after EVERY task — zero exceptions. Zombie browsers = RAM killer.

## Stale Ref Rule (CRITICAL)
- After ANY DOM-changing click → MUST take fresh `snapshot` → use ONLY new refs
- Old refs = "not found". NEVER reuse refs across DOM mutations.
- Pattern: snapshot → act → (DOM changed?) → snapshot → act

## Commands
- Open: `playwright-cli -s=$S open <url> --persistent`
- Snapshot: `playwright-cli -s=$S snapshot`
- Screenshot: `playwright-cli -s=$S screenshot`
- Click: `playwright-cli -s=$S click <ref>`
- Fill: `playwright-cli -s=$S fill <ref> <text>`
- Mobile: `playwright-cli -s=$S resize 390 844` → screenshot
- Close: `playwright-cli -s=$S close`

## UI Verification
- Any UI/visual change = screenshot BEFORE claiming "done"
- Test BOTH desktop AND mobile viewport (390x844)
- No emoji in UI. Custom inline SVG icons, stroke 1.5-2px.
