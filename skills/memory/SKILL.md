---
name: memory
description: "Military-grade memory management — status, search, save, recall, cleanup, index, project, global, diff. Full control over KALIYA's subconscious mind. Use when: memory, remember, forget, recall, save, search memory, memory status, what do you know, brain, subconscious, cleanup memory, stale, project memory, global memory."
argument-hint: "[command] [args] — commands: status, search <keyword>, save <topic> <info>, recall <topic>, cleanup, index, project, global, diff"
---

# KALIYA Memory Operations — Powered by Memory Engine

Uses MCP `memory-engine` tools for semantic search + SQLite index. Falls back to Grep for direct file access.

## Command: `$ARGUMENTS`

Parse the command from arguments. If no command given, default to `status`.

## OPERATIONS MANUAL

### `status` — Full Memory System Health Report

1. **Call MCP tool `memory_status`** — gets index stats (chunks, embeddings, sessions, files)

2. **File-level details:**
   ```
   For EACH file in ~/.claude/projects/-Users-niwash/memory/:
     File name, size (wc -c), line count (wc -l), last modified
   Report: MEMORY.md line count vs 200-line limit
   ```

3. **Project memory check:**
   ```
   Detect current project from CWD
   Find: ~/.claude/projects/<CWD-with-dashes>/memory/
   List all files if exists
   ```

4. **Output Format:**
   ```
   MEMORY SYSTEM STATUS
   ====================
   Engine: [chunks] chunks | [embeddings] embeddings | [sessions] sessions | [files] indexed
   Model: [available/not installed]

   Global Brain: ~/.claude/projects/-Users-niwash/memory/
     MEMORY.md: [lines]/200 lines | [size] | Modified: [date]
     Topic Files:
       - malik-preferences.md: [lines] lines | [size] | [date]
       - mistakes-learnings.md: [lines] lines | [size] | [date]
       ...

   Project Brain: [path or "NOT INITIALIZED"]
     [file list or init instructions]

   Health: [OK / WARNING / CRITICAL]
   ```

---

### `search <keyword>` — Semantic + Keyword Search

**Uses MCP `memory_search` tool** — hybrid BM25 + vector search. Catches paraphrases.

1. Call `memory_search(query="<keyword>", scope="all", top_k=8)`
2. Display results with source file, section, score, preview

**Fallback:** If MCP unavailable, use Grep:
```
Grep(pattern="<keyword>", path="~/.claude/projects/", output_mode="content", -i=true, glob="*.md")
```

---

### `save <topic> <info>` — Smart Save to Correct File

Route information to the CORRECT topic file:

| Topic Keyword | Save To |
|---|---|
| preference, pref, rule, like, hate, style | `malik-preferences.md` |
| mistake, error, bug, gotcha, learning | `mistakes-learnings.md` |
| device, server, ip, ssh, adb, env | `device-environment.md` |
| workflow, pattern, process, template | `workflow-patterns.md` |
| project, current | Project's own MEMORY.md |
| note, daily, log | MCP `memory_daily(content, category)` |

**Before saving:** Read target file, grep for duplicates, find correct section.

---

### `recall <topic>` — Read Specific Memory

| Keyword | Action |
|---|---|
| preferences, prefs | Read `malik-preferences.md` |
| mistakes, errors, learnings | Read `mistakes-learnings.md` |
| devices, servers, ssh | Read `device-environment.md` |
| workflows, patterns | Read `workflow-patterns.md` |
| project | Current project's MEMORY.md |
| global, brain | Global MEMORY.md |
| all | MCP `memory_recall()` — budget-limited smart recall |

---

### `cleanup` — Find and Fix Memory Issues

1. **MEMORY.md line check** — warn if >180 lines
2. **Duplicate detection** — search similar entries across files
3. **Stale content** — files older than 7 days, outdated references
4. **Orphan files** — files in memory dir but not referenced

---

### `index` — Trigger Re-Index

Run: `~/.claude/memory-engine/.venv/bin/python3 ~/.claude/memory-engine/cli.py index --all-projects`

Reports: files scanned, chunks created, embeddings generated.

---

### `project [init|status]` — Project Memory Management

- `project status` — Show current project's memory
- `project init` — Create MEMORY.md template for current project

---

### `global` — Global Memory Overview

Read all files in `~/.claude/projects/-Users-niwash/memory/`, show section headers and sizes.

---

### `diff` — What Changed This Session

Show memory files modified today: `stat -f %Sm` on each .md file.

---

## EXECUTION RULES

- Use MCP `memory_search` for search (semantic), Grep for exact match only
- Use MCP `memory_daily` for daily log entries
- ALWAYS Read before Write — verify file exists before modifying
- NEVER duplicate — search before save
- NEVER save secrets to memory files
- MEMORY.md max 200 lines — overflow to topic files
- Global memory: `~/.claude/projects/-Users-niwash/memory/`
- Project memory: `~/.claude/projects/<CWD-with-dashes>/memory/`

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
