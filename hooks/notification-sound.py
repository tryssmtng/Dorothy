#!/usr/bin/env python3
# ═══════════════════════════════════════════════════════════════
# KALIYA Notification — Rich Info + Dedup
# PostToolUse[AskUserQuestion|TaskCreate|TaskUpdate] — registered in settings.json
# Hero = task done | Submarine = question waiting
# Format: "KALIYA | project | #N Done | actual task description"
# ═══════════════════════════════════════════════════════════════

import sys, json, subprocess, re, os, time

SUBJECTS_FILE = "/tmp/kaliya-task-subjects.json"
LOG_FILE = "/tmp/kaliya-notification.log"
DEDUP_FILE = "/tmp/kaliya-notif-dedup"


def log(msg):
    with open(LOG_FILE, "a") as f:
        f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")


def load_subjects():
    try:
        with open(SUBJECTS_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_subjects(data):
    try:
        with open(SUBJECTS_FILE, "w") as f:
            json.dump(data, f)
    except Exception:
        pass


def get_project(cwd):
    """Extract project name from CWD."""
    if not cwd:
        return "kaliya"
    path = cwd.rstrip("/")
    name = os.path.basename(path)
    if name == ".claude":
        return "kaliya-core"
    return name or "kaliya"


def dedup_check(key):
    """Block duplicate notifications within 5 seconds."""
    try:
        now = time.time()
        lines = []
        if os.path.exists(DEDUP_FILE):
            with open(DEDUP_FILE) as f:
                lines = f.readlines()
        recent = []
        for l in lines:
            l = l.strip()
            if not l or "|" not in l:
                continue
            try:
                ts = float(l.split("|")[0])
                if now - ts < 5:
                    recent.append(l)
            except ValueError:
                continue
        if any(key in l for l in recent):
            return True
        recent.append(f"{now}|{key}")
        with open(DEDUP_FILE, "w") as f:
            f.write("\n".join(recent[-50:]) + "\n")
        return False
    except Exception:
        return False


def notify(title, subtitle, message, sound):
    safe_msg = message.replace('"', "'").replace("\\", "")[:120]
    safe_sub = subtitle.replace('"', "'").replace("\\", "")[:80]
    log(f"NOTIFY: {safe_sub} | {safe_msg}")
    subprocess.Popen(
        ["afplay", f"/System/Library/Sounds/{sound}.aiff"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    script = f'display notification "{safe_msg}" with title "{title}" subtitle "{safe_sub}" sound name "{sound}"'
    subprocess.Popen(
        ["osascript", "-e", script],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def main():
    try:
        d = json.load(sys.stdin)
    except Exception:
        return

    tool = d.get("tool_name", "")
    inp = d.get("tool_input", {}) or {}
    result = d.get("tool_result", {}) or {}
    cwd = d.get("cwd", "")
    project = get_project(cwd)

    # ── Cache task subjects from TaskCreate ──
    if tool == "TaskCreate":
        subject = inp.get("subject", "")
        result_content = result.get("content", [])
        result_text = ""
        if isinstance(result_content, list):
            for item in result_content:
                if isinstance(item, dict) and item.get("type") == "text":
                    result_text += item.get("text", "")
        elif isinstance(result_content, str):
            result_text = result_content
        m = re.search(r"#(\d+)", result_text)
        if m and subject:
            data = load_subjects()
            data[m.group(1)] = subject
            save_subjects(data)
            log(f"Cached: #{m.group(1)} = {subject[:60]}")
        else:
            log(f"TaskCreate no-cache: subj='{subject[:40]}' res='{result_text[:60]}'")

    # ── Notify on task completion ──
    elif tool == "TaskUpdate":
        status = inp.get("status", "")
        task_id = str(inp.get("taskId", "?"))
        if status == "completed":
            key = f"done-{task_id}"
            if dedup_check(key):
                return
            data = load_subjects()
            subject = data.get(task_id, "")
            body = subject[:100] if subject else f"Task #{task_id} completed"
            subtitle = f"{project} | #{task_id} Done"
            notify("KALIYA", subtitle, body, "Hero")

    # ── Notify on question ──
    elif tool == "AskUserQuestion":
        questions = inp.get("questions", [])
        msg = "Input chahiye"
        if questions and isinstance(questions, list) and isinstance(questions[0], dict):
            msg = questions[0].get("question", msg)[:100]
        key = f"q-{msg[:20]}"
        if dedup_check(key):
            return
        subtitle = f"{project} | Question"
        notify("KALIYA", subtitle, msg, "Submarine")


if __name__ == "__main__":
    main()
