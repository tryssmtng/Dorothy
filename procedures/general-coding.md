# General Coding — Procedural Memory

> Cross-project coding procedures. Har session mein applicable.

## Python
- After editing: `python3 -c "import py_compile; py_compile.compile('file.py')"` — syntax verify
- `except:` catches SystemExit — ALWAYS use `except Exception:`
- datetime: `.isoformat()` gives `+00:00` NOT `Z` → use `.strftime('%Y-%m-%dT%H:%M:%SZ')`
- Grep for 3 patterns: `datetime.now(`, `datetime.utcnow(`, `datetime.now(timezone.utc)`

## JSON Files
- settings.json: Multiple Edit operations → invisible chars/trailing commas → JSON breaks. **Fresh Write safer** for critical config.
- Always verify: `python3 -c "import json; json.load(open('file.json'))"` after editing

## Shell
- Check `.zshrc`, `.bashrc`, `.bash_profile` ALL THREE for aliases — cleanup teeno mein karo
- `find` broken in Claude Code sandbox → ALWAYS use `ls` with glob patterns
- npx cache cleanup: `~/.npm/_npx/*/node_modules/` — old MCP servers leave cache

## File Operations
- Large files (>5000 lines) → dedicated agent, self mein mat karo
- File edited 3+ times in one session → STOP. Read FULL file first, understand structure.
- Edit tool `replace_all` = powerful for bulk renames across file

## Deployment
- Fly.io: `flyctl deploy --ha=false` for single machine apps
- SSH batch: `ssh server "cmd1 && cmd2 && cmd3"` — NOT separate calls (fail2ban)
- Max 3 SSH calls/minute — beyond = ban risk

## MongoDB
- N+1 query problem → Use aggregation pipeline + batch `$in` queries
- Connection string from credentials-secrets.md, NEVER hardcode

## Git
- `git push` = ONLY when Malik EXPLICITLY says. Auto-push = BANNED.
- Commit after task = OK. Push after commit = WAIT for Malik.
