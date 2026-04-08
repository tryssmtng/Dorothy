---
name: deploy
description: "Deployment operations — pre-deploy checklist, server deploy via SSH/Fly.io, health verification, rollback protocol. Use when: deploy, push, live, server, production, fly.io, ssh deploy, release."
argument-hint: "[target: server/fly.io/vercel] [project path]"
---

# /deploy — Deployment Skill

> Deploy karna hai to ye skill follow karo step-by-step. Skip = disaster.

---

## STEP 0 — Memory Check (NON-NEGOTIABLE)

Before touching ANYTHING:

```
Grep ~/.claude/projects/*/memory/credentials-secrets.md for target server/service
Read project CLAUDE.md for deploy-specific instructions
Read ~/.claude/projects/*/memory/device-environment.md for server IPs, ports
```

If credentials not found in memory → **STOP** → ask Malik. NEVER hardcode credentials.

---

## STEP 1 — Pre-Deploy Checklist (MANDATORY)

Every single item MUST pass before deploy. No exceptions.

| # | Check | Command | Pass Criteria |
|---|-------|---------|---------------|
| 1 | Build passes | `npm run build` / `python -m py_compile` / project-specific | Exit code 0, no errors |
| 2 | Tests pass | `npm test` / `pytest` / project-specific | All green |
| 3 | Git clean | `git status` | No uncommitted changes |
| 4 | Credentials loaded | Grep memory files | Found in credentials-secrets.md |
| 5 | SSH/connection test | `ssh <flags> <host> "echo OK"` | Returns "OK" |
| 6 | Backup plan | Document current version/image | Written down before proceeding |

**If ANY check fails → FIX IT FIRST. Do NOT proceed.**

Report to Malik:
```
Pre-deploy checklist:
- Build: PASS/FAIL
- Tests: PASS/FAIL
- Git: clean/dirty
- Credentials: loaded/missing
- Connection: OK/FAIL
- Backup: documented/missing
```

---

## STEP 2 — Deploy Method Selection

### Method A: SSH Deploy (Direct Server)

**SSH Connection Flags** (always use these):
```bash
SSH_FLAGS="-o PreferredAuthentications=password -o PubkeyAuthentication=no -o StrictHostKeyChecking=no"
```

**Password Auth:**
```bash
sshpass -p "$PASSWORD" ssh $SSH_FLAGS user@host "commands here"
```

**BATCH COMMANDS — IRON RULE:**
```bash
# CORRECT — single SSH call, multiple commands
sshpass -p "$PASS" ssh $SSH_FLAGS user@host "cd /app && git pull && npm install && pm2 restart all"

# WRONG — multiple SSH calls (session b7861387 learned this)
sshpass -p "$PASS" ssh $SSH_FLAGS user@host "cd /app"
sshpass -p "$PASS" ssh $SSH_FLAGS user@host "git pull"       # BANNED
sshpass -p "$PASS" ssh $SSH_FLAGS user@host "npm install"    # BANNED
```

**Max 3 SSH calls per minute.** Batch everything. One call for backup, one for deploy, one for verify.

**SSH Deploy Sequence:**
```bash
# Call 1: Backup current version
sshpass -p "$PASS" ssh $SSH_FLAGS user@host "cd /app && cp -r . ../app-backup-$(date +%Y%m%d%H%M)"

# Call 2: Deploy
sshpass -p "$PASS" ssh $SSH_FLAGS user@host "cd /app && git pull origin main && npm install --production && pm2 restart all"

# Call 3: Verify
sshpass -p "$PASS" ssh $SSH_FLAGS user@host "pm2 status && curl -s http://localhost:PORT/health"
```

### Method B: Fly.io Deploy

```bash
# Pre-check
flyctl status -a <app-name>

# Deploy (single machine apps)
flyctl deploy --ha=false

# Verify
flyctl status -a <app-name>
flyctl logs -a <app-name> --no-tail

# Check specific endpoint
curl -s https://<app-name>.fly.dev/health
```

**Fly.io Notes:**
- `--ha=false` for single machine apps (saves cost, avoids split-brain)
- Always check `flyctl status` before AND after deploy
- Read logs for first 30 seconds post-deploy

### Method C: Static Deploy (Vercel/Netlify)

```bash
# Vercel
npm run build && vercel --prod

# Netlify
npm run build && netlify deploy --prod --dir=dist

# Verify
curl -s https://<domain>/ | head -20
```

---

## STEP 3 — Post-Deploy Verification (MANDATORY)

Run ALL of these. No shortcuts.

### 3a. HTTP Health Check
```bash
# API server
curl -s -o /dev/null -w "%{http_code}" https://<domain>/health
# Expected: 200

# Web UI
curl -s -o /dev/null -w "%{http_code}" https://<domain>/
# Expected: 200
```

### 3b. Log Check
```bash
# SSH server
sshpass -p "$PASS" ssh $SSH_FLAGS user@host "pm2 logs --lines 30 --nostream"

# Fly.io
flyctl logs -a <app-name> --no-tail

# Look for: errors, exceptions, crashes, connection refused
```

### 3c. Functional Test
```bash
# API endpoint test
curl -s https://<domain>/api/status | jq .

# UI test (if applicable)
S="$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" | tr '[:upper:]' '[:lower:]' | tr ' _' '--')-deploy"

# Check-before-open — don't duplicate browser
SESSION_STATUS=$(playwright-cli list 2>&1 | grep -c "${S}.*open" || true)
if [ "$SESSION_STATUS" -gt 0 ]; then
    playwright-cli -s=$S goto "https://<domain>"
else
    # Default: headless (no --headed). Use --headed ONLY when Malik explicitly wants to watch.
    playwright-cli -s=$S open "https://<domain>" --persistent
fi
# Then: snapshot → screenshot → verify layout
```

### 3d. Mobile Check (if UI changed)
```bash
# In playwright session
playwright-cli -s=$S resize 390 844
playwright-cli -s=$S screenshot
# Verify responsive layout
```

### 3e. Cleanup — MANDATORY after verification
```bash
# ALWAYS close playwright after deploy verification is done
# Profile preserved — next deploy verification restores state
playwright-cli -s=$S close
```

**Verification Report:**
```
Post-deploy verification:
- Health check: 200 OK / FAIL
- Logs: clean / errors found
- Functional: working / broken
- Mobile: OK / issues
```

---

## STEP 4 — Rollback Protocol

**Trigger:** If health check fails within 2 minutes of deploy → ROLLBACK IMMEDIATELY. Don't debug in production.

### SSH Rollback
```bash
# Restore from backup
sshpass -p "$PASS" ssh $SSH_FLAGS user@host "cd / && rm -rf /app && mv /app-backup-TIMESTAMP /app && cd /app && pm2 restart all"
```

### Fly.io Rollback
```bash
# List releases
flyctl releases -a <app-name>

# Deploy previous image
flyctl deploy --image <previous-image-ref> -a <app-name> --ha=false

# Verify rollback
flyctl status -a <app-name>
```

### Git Rollback
```bash
git revert HEAD --no-edit
git push origin main
# Then redeploy using appropriate method
```

### Vercel/Netlify Rollback
```bash
# Vercel — promote previous deployment
vercel rollback

# Netlify — rollback from dashboard or redeploy previous commit
```

---

## Iron Rules — Violate = Session Failure

1. **NEVER deploy without build passing.** Local build broken = production broken. No exceptions.
2. **NEVER hardcode credentials.** Always read from `credentials-secrets.md` in memory. Hardcoded creds in code = immediate revert.
3. **ALWAYS verify after deploy.** "Deployed" without verification = not deployed. Health check + logs + functional test = minimum.
4. **ALWAYS have rollback plan.** Before deploy, know exactly how to undo. Backup taken. Previous version identified.
5. **SSH batch = mandatory.** One SSH call with `&&`-chained commands. Multiple calls = rate limit = banned = YOUR fault. Session b7861387 learned this.
6. **Max 3 SSH calls per minute.** Batch aggressively. Plan commands before executing.
7. **Credentials from memory ONLY.** `Grep credentials-secrets.md` before deploy. Not found = ask Malik. NEVER guess passwords.
8. **"Done" = deployed + verified + working.** Malik can hit the URL and it works. Otherwise it's NOT done.

---

## Quick Reference

| Target | Deploy Command | Verify Command |
|--------|---------------|----------------|
| SSH Server | `sshpass -p "$P" ssh $FLAGS host "cd /app && git pull && pm2 restart all"` | `curl -s host:port/health` |
| Fly.io | `flyctl deploy --ha=false` | `flyctl status && curl -s app.fly.dev/health` |
| Vercel | `vercel --prod` | `curl -s domain.com/` |
| Netlify | `netlify deploy --prod --dir=dist` | `curl -s domain.com/` |

---

## Error Recovery

| Error | Fix |
|-------|-----|
| SSH connection refused | Check IP, port, firewall. `telnet host 22` to test. |
| SSH auth failed | Re-read credentials-secrets.md. Check username/password. |
| Build fails on server | SSH in, check node/python version, check disk space. |
| Port already in use | `lsof -i :PORT` → kill old process → restart. |
| Fly.io deploy timeout | Check `flyctl logs`. Usually Dockerfile issue or health check path wrong. |
| 502 Bad Gateway | App crashed. Check logs immediately. Rollback if not fixable in 2 min. |
| SSL certificate error | Fly.io: auto-managed. SSH: check nginx/caddy config. |

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
