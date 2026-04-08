#!/usr/bin/env python3
"""
KALIYA Perception Engine v1.0 — The Brain
Event: UserPromptSubmit

Human Mind System #1: PERCEPTION
Processes ALL input BEFORE the commander acts.

REPLACES: gaali-detector.sh + agent-dashboard-inject.sh (merged)

Pipeline:
  1. Parse message → count actionable items
  2. Extract keywords → auto memory search
  3. Check mistakes-learnings.md for similar past failures
  4. Detect frustration (gaali/tone patterns)
  5. Check agent dashboard (if agents running)
  6. Inject structured context

OUTPUT:
  [PERCEPTION] Items: N | Intent: fix/build/deploy
  [MEMORY] Relevant findings
  [PAST ISSUES] Similar failures
  [FRUSTRATION — LEVEL] if detected
  [AGENTS] Dashboard if running
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════
MEMORY_ENGINE_VENV = Path.home() / ".claude" / "memory-engine" / ".venv" / "bin" / "python3"
MEMORY_ENGINE_CLI = Path.home() / ".claude" / "memory-engine" / "cli.py"
MISTAKES_FILE = Path.home() / ".claude" / "projects" / "-Users-niwash--claude" / "memory" / "mistakes-learnings.md"
GLOBAL_MISTAKES = Path.home() / ".claude_2" / "projects" / "-Users-niwash" / "memory" / "mistakes-learnings.md"
TRACKER_FILE = Path("/tmp/kaliya-frustration-tracker.json")
PERCEPTION_STATE = Path("/tmp/kaliya-perception-state.json")
HOME = str(Path.home())


def read_input():
    """Read hook input from stdin."""
    try:
        raw = sys.stdin.read() if not sys.stdin.isatty() else ""
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


# ═══════════════════════════════════════════════════════════════
# 1. ITEM COUNTER — Parse actionable items from message
# ═══════════════════════════════════════════════════════════════
def count_items(text):
    """Count actionable items in Malik's message.

    Detects:
    - Numbered lists (1. 2. 3.)
    - Comma-separated actions
    - Imperative verbs (karo, fix, ban, create, check, deploy, etc.)
    - Hinglish action words
    """
    if not text or len(text.strip()) < 5:
        return 0, "conversation"

    lower = text.lower()

    # Check if this is a pure conversational message (no action verbs)
    conversation_patterns = [
        r'^(hi|hello|hey|haan|ok|theek|sahi|good|nice|thanks|shukriya|hmm|accha)\b',
    ]
    for pat in conversation_patterns:
        if re.match(pat, lower.strip()):
            # If no action verbs embedded, it's just conversation
            if not re.search(r'\b(fix|build|create|deploy|test|check|add|remove|karo|banao|hatao)\b', lower):
                return 0, "conversation"

    # Method 1: Numbered items (1. 2. 3. or 1) 2) 3))
    numbered = re.findall(r'(?:^|\n)\s*\d+[\.\)]\s+\S', text)
    if len(numbered) >= 2:
        return len(numbered), "build/fix"

    # Method 2: Action verbs — compound Hinglish FIRST (most specific → least)
    # ORDER MATTERS: "fix karo" before "karo" to get correct intent classification
    action_verbs_compound = [
        # fix/debug
        'fix karo', 'debug karo', 'fix kar', 'theek karo', 'repair karo',
        # build/create
        'build karo', 'create karo', 'bana do', 'banao', 'bana de',
        'implement karo', 'likh do', 'likho', 'write karo',
        # deploy/push
        'deploy karo', 'push karo', 'send karo', 'bhejo', 'bhej do',
        'upload karo', 'release karo',
        # test/verify
        'test karo', 'check karo', 'verify karo', 'audit karo',
        'scan karo', 'review karo', 'inspect karo',
        # research
        'research karo', 'analyze karo', 'compare karo', 'study karo',
        # other compound
        'update karo', 'upgrade karo', 'downgrade karo', 'patch karo',
        'install karo', 'remove karo', 'delete karo', 'add karo',
        'set karo', 'configure karo', 'setup karo', 'change karo',
        'move karo', 'copy karo', 'run karo', 'start karo', 'stop karo',
        'restart karo', 'clean karo', 'trace karo', 'bypass karo',
        'hook karo', 'profile karo', 'merge karo', 'show karo',
        'open karo', 'shuru karo', 'band karo', 'chalu karo',
        'hata do', 'hatao', 'dikhao', 'dekhao',
    ]
    action_verbs_en = [
        'fix', 'build', 'create', 'deploy', 'test', 'verify', 'check',
        'add', 'remove', 'delete', 'update', 'write', 'send', 'show',
        'install', 'run', 'push', 'merge', 'implement', 'change',
        'move', 'copy', 'open', 'start', 'stop', 'restart', 'clean',
        'upgrade', 'downgrade', 'patch', 'audit', 'scan', 'trace',
        'bypass', 'hook', 'configure', 'setup', 'debug', 'profile',
        'research', 'analyze', 'compare', 'refactor', 'redesign',
        'migrate', 'optimize', 'monitor', 'review', 'rewrite',
    ]
    # Generic Hinglish LAST (least specific)
    action_verbs_generic = ['karo', 'kar do', 'kar de', 'bana', 'hata', 'likh']

    # Count unique action clauses (split on . ! ? \n AND commas for multi-action sentences)
    # First split on sentence boundaries, then split each sentence on commas/aur/and
    raw_sentences = re.split(r'[.!?\n]', text)
    clauses = []
    for sent in raw_sentences:
        # Split compound sentences: "X karo, Y karo, aur Z karo"
        sub_clauses = re.split(r',|\baur\b|\band\b|\b\+\b', sent)
        clauses.extend(sub_clauses)

    action_count = 0
    intent_words = set()

    def classify_verb(verb):
        if any(w in verb for w in ['fix', 'debug', 'bug']):
            intent_words.add('fix')
        elif any(w in verb for w in ['build', 'create', 'bana', 'implement', 'write', 'likh']):
            intent_words.add('build')
        elif any(w in verb for w in ['deploy', 'push', 'send', 'bhej']):
            intent_words.add('deploy')
        elif any(w in verb for w in ['test', 'check', 'verify', 'audit', 'scan']):
            intent_words.add('verify')
        elif any(w in verb for w in ['research', 'analyze', 'compare']):
            intent_words.add('research')
        else:
            intent_words.add('execute')

    for clause in clauses:
        clause_lower = clause.lower().strip()
        if len(clause_lower) < 3:
            continue

        for verb in action_verbs_compound + action_verbs_en + action_verbs_generic:
            if verb in clause_lower:
                action_count += 1
                classify_verb(verb)
                break  # One action per clause

    # At minimum 1 if message has substance
    if action_count == 0 and len(text.strip()) > 20:
        action_count = 1
        intent_words.add('execute')

    intent = '/'.join(sorted(intent_words)) if intent_words else 'conversation'
    return max(action_count, 1), intent


# ═══════════════════════════════════════════════════════════════
# 2. KEYWORD EXTRACTOR — For memory search
# ═══════════════════════════════════════════════════════════════
def extract_keywords(text):
    """Extract meaningful keywords for memory search."""
    if not text:
        return []

    # Remove common stop words (Hinglish + English)
    stop_words = {
        'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
        'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
        'should', 'may', 'might', 'shall', 'can', 'need', 'dare', 'ought',
        'used', 'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by', 'from',
        'as', 'into', 'through', 'during', 'before', 'after', 'above',
        'below', 'between', 'out', 'off', 'over', 'under', 'again',
        'further', 'then', 'once', 'here', 'there', 'when', 'where',
        'why', 'how', 'all', 'both', 'each', 'few', 'more', 'most',
        'other', 'some', 'such', 'no', 'nor', 'not', 'only', 'own',
        'same', 'so', 'than', 'too', 'very', 'just', 'because', 'but',
        'and', 'or', 'if', 'while', 'this', 'that', 'these', 'those',
        'i', 'me', 'my', 'we', 'our', 'you', 'your', 'he', 'him', 'his',
        'she', 'her', 'it', 'its', 'they', 'them', 'their', 'what', 'which',
        'who', 'whom', 'up', 'about', 'also',
        # Hinglish
        'hai', 'hain', 'ho', 'tha', 'thi', 'the', 'ka', 'ki', 'ke',
        'ko', 'se', 'mein', 'pe', 'par', 'ne', 'ye', 'wo', 'yeh', 'woh',
        'aur', 'ya', 'bhi', 'toh', 'na', 'nahi', 'nhi', 'mat', 'haan',
        'ji', 'abhi', 'ab', 'tab', 'jab', 'kab', 'kya', 'kaise', 'kyun',
        'kahan', 'kaun', 'kitna', 'bahut', 'zyada', 'kam', 'sab', 'kuch',
        'mere', 'mera', 'meri', 'tera', 'teri', 'tere', 'uska', 'uski',
        'apna', 'apni', 'apne', 'ek', 'do', 'teen', 'chaar', 'paanch',
        'pehle', 'baad', 'wala', 'wali', 'wale',
        'karo', 'kar', 'karna', 'dekh', 'dekho', 'bata', 'batao',
        'matlab', 'isliye', 'lekin', 'phir', 'fir',
    }

    words = re.findall(r'[a-zA-Z0-9_\-]+', text.lower())
    keywords = []
    seen = set()
    for w in words:
        if w not in stop_words and len(w) > 2 and w not in seen:
            seen.add(w)
            keywords.append(w)

    # Return top 8 most relevant (longer words = more specific)
    keywords.sort(key=lambda x: len(x), reverse=True)
    return keywords[:8]


# ═══════════════════════════════════════════════════════════════
# 3. AUTO MEMORY SEARCH — Via memory engine CLI
# ═══════════════════════════════════════════════════════════════
def auto_memory_search(keywords):
    """Search memory engine for relevant context."""
    if not keywords:
        return ""

    query = " ".join(keywords[:5])

    # Try memory engine CLI first
    if MEMORY_ENGINE_VENV.exists() and MEMORY_ENGINE_CLI.exists():
        try:
            result = subprocess.run(
                [str(MEMORY_ENGINE_VENV), str(MEMORY_ENGINE_CLI), "search",
                 "--query", query, "--top-k", "3", "--scope", "all"],
                capture_output=True, text=True, timeout=3
            )
            if result.returncode == 0 and result.stdout.strip():
                # Extract just the content, not scores
                lines = result.stdout.strip().split('\n')
                relevant = []
                for line in lines[:6]:
                    line = line.strip()
                    if line and not line.startswith('Found') and not line.startswith('---'):
                        relevant.append(line)
                if relevant:
                    return ' | '.join(relevant)[:300]
        except (subprocess.TimeoutExpired, Exception):
            pass

    return ""


# ═══════════════════════════════════════════════════════════════
# 4. MISTAKES CHECKER — Search past failures
# ═══════════════════════════════════════════════════════════════
def check_mistakes(keywords):
    """Search mistakes-learnings.md for similar past failures."""
    results = []

    for mistakes_file in [MISTAKES_FILE, GLOBAL_MISTAKES]:
        if not mistakes_file.exists():
            continue
        try:
            content = mistakes_file.read_text(encoding='utf-8')
            sections = re.split(r'\n## ', content)

            for section in sections:
                section_lower = section.lower()
                matches = sum(1 for kw in keywords if kw in section_lower)
                if matches >= 2:
                    # Extract section title
                    title = section.split('\n')[0].strip()
                    if title:
                        results.append(title[:80])
        except Exception:
            continue

    return results[:3]


# ═══════════════════════════════════════════════════════════════
# 5. FRUSTRATION DETECTOR — Ported from gaali-detector.sh
# ═══════════════════════════════════════════════════════════════

# Gaali patterns (CRITICAL)
CRIT_WORDS = re.compile(
    r'\b(bsdk|bhosdk|bhosadike|gandu|ganduon|chutiya|chutiye|chutiyon|chutiyap|'
    r'chutiyapa|madarchod|madarjaat|bhenchod|bhosdike|lodu|laude|laudu|lavde|'
    r'randi|randikhana|haramkhor|harami|kutiya|kuttiya|jhant|jhaant|gaand|'
    r'tattiya|tatti|dalla|dalal|bhadwa|bhadve)\b', re.IGNORECASE
)

# HIGH patterns
HIGH_SINGLE = re.compile(
    r'\b(kamchori|bakwas|timepass|bekar|bekaar|kachra|faltu|ghatiya|wahiyat|'
    r'wahiyaat|pagal|stupid|useless|pathetic|terrible|horrible|disgusting|'
    r'incompetent|crap|trash|garbage|worthless|hopeless|nikamma|nikammi|'
    r'nautanki|natak|bawaseer|fazool|bewakoof|bewkoof|nalayak|kamina|kamine|'
    r'kaminey|gadha|gadhe|suar|kutte|kuttey|sala|saale)\b', re.IGNORECASE
)

HIGH_PHRASES = [
    'tujhse nahi hoga', 'kuch nahi aata', 'dimag nahi hai', 'akal nahi',
    'sochta nahi', 'tameez nahi', 'kaam ka nahi', 'band kar de', 'chup kar',
    'hat ja', 'kuch bhi karta', 'time pass', 'brain dead', 'no brain',
    'kya kar raha hai', 'sense nahi', 'tera se nhi hoga', 'tere se nahi',
    'bewakoofi', 'chutiyap',
]

# MEDIUM patterns
MED_PHRASES = [
    'kyu nahi', 'kyu nhi', 'kyun nahi', 'kyun nhi', 'phir se', 'dobara',
    'sahi nahi', 'sahi nhi', 'theek nahi', 'theek nhi', 'thik nahi',
    'thik nhi', 'kab hoga', 'kitna time', 'abhi tak', 'still not',
    'not working', 'nahi ho rha', 'nhi ho rha', 'kaam nhi', 'fix nahi',
    'fix nhi', 'wrong again', 'same mistake', 'already told', 'pehle bola tha',
    'bola tha na', 'bataya tha', 'nahi chala', 'nhi chala', 'error aa rha',
    'crash ho rha', 'toot gaya', 'kharab ho gaya', 'wahi galti',
    'repeat mistake', 'fir wahi', 'kuch aur bola tha', 'ye nahi bola',
    'maine ye nahi kaha', 'samajh nahi aata', 'samajhta nahi', 'sun nahi rha',
    'dhyan se kar', 'concentrate kar', 'focus kar', 'ye kya kiya',
    'kya kar diya', 'bigaad diya', 'barbaad kar', 'galat kar', 'galat kiya',
    'pehle bhi bola', 'already said', 'i told you', 'said before',
    'firse', 'fir se wahi',
]

# LOW patterns
LOW_PHRASES = [
    'ok but', 'lekin ye', 'par ye nahi', 'are you sure', 'sach mein',
    'ye alag hai', 'different hai', 'aisa nahi chahiye', 'not what i',
    'half done', 'adha reh gaya', 'ye bhi nahi', 'still pending',
    'abhi bhi nahi', 'check properly', 'ache se check', 'ache se dekh',
    'dhang se kar', 'sahi se kar', 'bhool gaya', 'forgot to', 'miss kiya',
    'miss ho gaya', 'missing hai', 'nahi kiya', 'nhi kiya',
]

# WARNING patterns
SARCASM = [
    'wah wah', 'great job', 'nice work', 'well done', 'bahut accha',
    'slow clap', 'bravo', 'kya baat hai', 'wonderful', 'amazing work',
    'perfect', 'fantastic', 'superb', 'taaliyaan', 'waah', 'bohot badiya',
    'mast kaam', 'what a genius', 'so smart', 'very intelligent',
]

REPEAT_PHRASES = [
    'fir se bol', 'phir bata', 'ek aur baar', 'once more', 'i said',
    'maine kaha', 'bola na', 'already said', 'pehle bhi bola',
    'kitni baar', 'how many times', 'again and again', 'baar baar',
    'dobara bol', 'repeat kar',
]

# Tech terms to exclude from CAPS detection
TECH_TERMS = {
    'API', 'SSH', 'SSL', 'TLS', 'URL', 'CSS', 'HTML', 'JSON', 'XML', 'YAML',
    'HTTP', 'HTTPS', 'DNS', 'TCP', 'UDP', 'IP', 'SQL', 'JWT', 'CLI', 'GUI',
    'IDE', 'SDK', 'MCP', 'APK', 'DEX', 'ARM', 'CPU', 'GPU', 'RAM', 'SSD',
    'HDD', 'USB', 'MAC', 'LAN', 'WAN', 'VPN', 'PIN', 'OTP', 'PDF', 'PNG',
    'JPG', 'SVG', 'GIT', 'NPM', 'ENV', 'AWS', 'GCP', 'PID', 'EOF', 'CORS',
    'SMTP', 'IMAP', 'FTP', 'SFTP', 'REST', 'CRUD', 'CSRF', 'XSS', 'DOM',
    'CDN', 'CMS', 'CIN', 'GST', 'UDYAM', 'BSV', 'NFC', 'GPS', 'ADB', 'OEM',
    'ROM', 'BIOS', 'UEFI', 'ISO', 'ZIP', 'TAR', 'SCP', 'RSA', 'AES', 'SHA',
    'MD5', 'HEX', 'DEC', 'OCT', 'BIN', 'ASCII', 'UTF', 'OTA', 'TODO', 'ASAP',
    'IMHO', 'TBD', 'TLDR', 'ETA', 'FYI', 'BTW', 'DIY', 'FAQ', 'FIFO', 'LIFO',
    'KALIYA', 'JARVIS', 'CLAUDE', 'DNA', 'TTS',
}


def detect_frustration(text):
    """Detect frustration level and signal. Returns (level, signal) or (None, None)."""
    if not text or len(text.strip()) < 2:
        return None, None

    lower = text.lower()

    # CRITICAL — explicit gaali
    m = CRIT_WORDS.search(lower)
    if m:
        return "CRITICAL", m.group(0)

    # HIGH — strong words
    m = HIGH_SINGLE.search(lower)
    if m:
        return "HIGH", m.group(0)
    for phrase in HIGH_PHRASES:
        if phrase in lower:
            return "HIGH", phrase

    # MEDIUM — annoyance
    for phrase in MED_PHRASES:
        if phrase in lower:
            return "MEDIUM", phrase

    # LOW — subtle dissatisfaction
    if re.search(r'\b(incomplete|mismatch)\b', lower):
        return "LOW", re.search(r'\b(incomplete|mismatch)\b', lower).group(0)
    for phrase in LOW_PHRASES:
        if phrase in lower:
            return "LOW", phrase

    # WARNING patterns
    # 3+ question marks
    qm_count = text.count('?')
    if qm_count >= 3:
        return "WARNING", f"excessive-?? ({qm_count}x)"

    # ALL-CAPS words (excluding tech terms)
    caps_words = [w for w in re.findall(r'\b[A-Z]{3,}\b', text) if w not in TECH_TERMS]
    if len(caps_words) >= 2:
        return "WARNING", f"CAPS-detected ({len(caps_words)} words)"

    # Short + exclamation = curt
    word_count = len(text.split())
    if word_count <= 3 and '!' in text:
        return "WARNING", f"curt-response ({word_count} words + !)"

    # Sarcasm
    if word_count <= 10:
        for phrase in SARCASM:
            if phrase in lower:
                return "WARNING", "possible-sarcasm"

    # Repeated request
    for phrase in REPEAT_PHRASES:
        if phrase in lower:
            return "WARNING", "repeated-request"

    # Ellipsis overuse
    ellipsis_count = text.count('...')
    if ellipsis_count >= 2:
        return "WARNING", f"ellipsis-overuse ({ellipsis_count}x ...)"

    return None, None


def escalate_frustration(level, signal, session_id):
    """Apply escalation rules based on session history."""
    tracker = load_tracker(session_id)

    total = tracker.get("total", 0)
    streak = tracker.get("streak", 0)
    last_level = tracker.get("last_level", "")

    # 3 MEDIUMs in a row → HIGH
    if level == "MEDIUM" and streak >= 2 and last_level == "medium":
        level = "HIGH"
        signal = f"{signal} [ESCALATED: {streak}x medium streak]"

    # 2 HIGHs in a row → CRITICAL
    if level == "HIGH" and last_level == "high":
        level = "CRITICAL"
        signal = f"{signal} [ESCALATED: consecutive HIGH]"

    # 5+ total → LOW/WARNING become MEDIUM
    if level in ("LOW", "WARNING") and total >= 5:
        level = "MEDIUM"
        signal = f"{signal} [ESCALATED: {total}x session total]"

    # Update tracker
    update_tracker(session_id, level, signal)

    return level, signal, total + 1


def load_tracker(session_id):
    """Load frustration tracker state."""
    if not TRACKER_FILE.exists():
        return {"total": 0, "streak": 0, "last_level": ""}
    try:
        data = json.loads(TRACKER_FILE.read_text())
        return data.get(session_id, {"total": 0, "streak": 0, "last_level": ""})
    except Exception:
        return {"total": 0, "streak": 0, "last_level": ""}


def update_tracker(session_id, level, signal):
    """Update frustration tracker."""
    try:
        data = {}
        if TRACKER_FILE.exists():
            data = json.loads(TRACKER_FILE.read_text())
    except Exception:
        data = {}

    entry = data.get(session_id, {
        "total": 0, "critical": 0, "high": 0, "medium": 0,
        "low": 0, "warning": 0, "streak": 0, "last_level": ""
    })

    ll = level.lower()
    entry["total"] = entry.get("total", 0) + 1
    entry[ll] = entry.get(ll, 0) + 1
    entry["streak"] = entry.get("streak", 0) + 1 if entry.get("last_level") == ll else 1
    entry["last_level"] = ll

    data[session_id] = entry
    try:
        TRACKER_FILE.write_text(json.dumps(data))
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════
# 6. AGENT DASHBOARD — Check running agents
# ═══════════════════════════════════════════════════════════════
def get_agent_dashboard(session_id):
    """Get current agent dashboard status."""
    dashboard_file = Path(f"/tmp/kaliya-dashboard-{session_id}.json")
    if not dashboard_file.exists():
        return ""

    try:
        data = json.loads(dashboard_file.read_text())
        agents = data.get("agents", [])
        if not agents:
            return ""

        running = [a for a in agents if a.get("status") == "running"]
        completed = [a for a in agents if a.get("status") == "completed"]

        if not running and not completed:
            return ""

        lines = []
        for a in running:
            name = a.get("name", a.get("type", "agent"))
            task = a.get("task", "working")[:40]
            lines.append(f"  * {name}: {task} (running)")
        for a in completed[-2:]:  # Last 2 completed
            name = a.get("name", a.get("type", "agent"))
            success = "done" if a.get("success") else "check"
            lines.append(f"  * {name}: {success}")

        return "\n".join(lines) if lines else ""
    except Exception:
        return ""


# ═══════════════════════════════════════════════════════════════
# 7. DOMAIN-AWARE PROCEDURE INJECTION — Load relevant how-to knowledge
# ═══════════════════════════════════════════════════════════════
PROCEDURES_DIR = Path.home() / ".claude" / "projects" / "-Users-niwash" / "memory" / "procedures"

# Domain keywords → procedure files to load
DOMAIN_MAP = {
    "android": ["android-device-testing.md", "xposed-development.md"],
    "cloak": ["xposed-development.md", "android-device-testing.md"],
    "xposed": ["xposed-development.md", "android-device-testing.md"],
    "lsposed": ["xposed-development.md", "android-device-testing.md"],
    "aghori-android": ["android-device-testing.md", "xposed-development.md", "frida-instrumentation.md"],
    "aghori-redteam": ["frida-instrumentation.md"],
    "frida": ["frida-instrumentation.md"],
    "careone": ["browser-automation.md"],
    "playwright": ["browser-automation.md"],
    "browser": ["browser-automation.md"],
}

# Always loaded (cross-domain)
ALWAYS_LOAD = ["general-coding.md"]


def detect_domain():
    """Detect project domain from CWD."""
    cwd = os.environ.get("CWD", os.getcwd()).lower()
    detected_files = set(ALWAYS_LOAD)

    for keyword, files in DOMAIN_MAP.items():
        if keyword in cwd:
            detected_files.update(files)

    return list(detected_files)


def load_procedures(proc_files):
    """Load procedure summaries for context injection. Keep it SHORT."""
    if not PROCEDURES_DIR.exists():
        return ""

    summaries = []
    for fname in proc_files:
        fpath = PROCEDURES_DIR / fname
        if not fpath.exists():
            continue
        try:
            content = fpath.read_text(encoding='utf-8')
            # Extract just the headers and first line under each — compact summary
            lines = content.split('\n')
            key_rules = []
            for line in lines:
                line = line.strip()
                # Grab lines starting with - ** (bold rules) — these are the critical ones
                if line.startswith('- **') and len(line) > 10:
                    key_rules.append(line[:120])
                if len(key_rules) >= 5:
                    break
            if key_rules:
                domain = fname.replace('.md', '').replace('-', ' ').title()
                summaries.append(f"{domain}: " + " | ".join(key_rules))
        except Exception:
            continue

    return " || ".join(summaries) if summaries else ""


# ═══════════════════════════════════════════════════════════════
# 8. AUTO-CAPTURE — Detect and save Malik's instructions automatically
# ═══════════════════════════════════════════════════════════════
PREFERENCES_FILE = Path.home() / ".claude" / "projects" / "-Users-niwash" / "memory" / "malik-preferences.md"

# Patterns that indicate a permanent instruction
PERMANENT_PATTERNS = [
    (r'\b(hamesha|always)\b.*\b(karo|kar|karna|use|do)\b', 'always'),
    (r'\b(kabhi nahi|kabhi mat|never)\b.*\b(karo|kar|karna|use|do)\b', 'never'),
    (r'\b(banned|ban hai|allowed nahi)\b', 'never'),
    (r'\b(har baar|every time|each time)\b', 'always'),
]

# Patterns that indicate a procedural instruction ("when X do Y")
PROCEDURAL_PATTERNS = [
    r'\bjab\b.*\btoh?\b.*\b(karo|kar|karna)\b',
    r'\bwhen\b.*\bthen\b.*\b(do|use|run)\b',
    r'\bafter\b.*\b(always|must|chahiye|zaroori)\b',
    r'\bbefore\b.*\b(always|must|chahiye|zaroori)\b',
    r'\b(zaroori|necessary|mandatory|chahiye)\b.*\b(hai|hota|hoti)\b',
]


def auto_capture_instructions(text):
    """Detect permanent instructions and save automatically.
    Returns list of captured instructions for injection."""
    if not text or len(text) < 20:
        return []

    lower = text.lower()
    captured = []

    # Check permanent patterns
    for pattern, ptype in PERMANENT_PATTERNS:
        if re.search(pattern, lower):
            # Extract the instruction (clean it up)
            instruction = text.strip()[:200]
            captured.append(f"[AUTO-CAPTURE: {ptype}] {instruction}")
            # Save to preferences file
            _append_to_preferences(instruction, ptype)
            break  # One capture per message

    # Check procedural patterns
    for pattern in PROCEDURAL_PATTERNS:
        if re.search(pattern, lower):
            instruction = text.strip()[:200]
            captured.append(f"[AUTO-CAPTURE: procedure] {instruction}")
            _save_procedure_learning(instruction)
            break

    return captured


def _append_to_preferences(instruction, ptype):
    """Append a preference to malik-preferences.md."""
    try:
        if not PREFERENCES_FILE.exists():
            return
        content = PREFERENCES_FILE.read_text(encoding='utf-8')
        # Check if similar instruction already exists (avoid duplicates)
        if instruction[:50] in content:
            return
        # Append under appropriate section
        timestamp = time.strftime("%Y-%m-%d")
        entry = f"\n- [{ptype.upper()}] ({timestamp}) {instruction}\n"
        with open(PREFERENCES_FILE, 'a', encoding='utf-8') as f:
            f.write(entry)
    except Exception:
        pass


def _save_procedure_learning(instruction):
    """Save a procedural learning to the appropriate procedure file."""
    try:
        learnings_file = PROCEDURES_DIR / "auto-captured.md"
        timestamp = time.strftime("%Y-%m-%d %H:%M")
        entry = f"- ({timestamp}) {instruction}\n"

        if learnings_file.exists():
            content = learnings_file.read_text(encoding='utf-8')
            if instruction[:50] in content:
                return  # Duplicate

        with open(learnings_file, 'a', encoding='utf-8') as f:
            if not learnings_file.exists() or learnings_file.stat().st_size == 0:
                f.write("# Auto-Captured Procedures\n\n> Auto-captured from Malik's instructions. Review and move to domain-specific files.\n\n")
            f.write(entry)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════
# 9. PERCEPTION STATE — Save for other hooks to read
# ═══════════════════════════════════════════════════════════════
def save_perception_state(item_count, intent, keywords):
    """Save perception state for discipline-engine and done-gate to read."""
    state = {
        "item_count": item_count,
        "intent": intent,
        "keywords": keywords,
        "timestamp": time.time(),
        "items_completed": 0,
    }
    try:
        PERCEPTION_STATE.write_text(json.dumps(state))
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════
# MAIN — Pipeline
# ═══════════════════════════════════════════════════════════════
def main():
    data = read_input()
    user_text = data.get("prompt", data.get("message", ""))

    if not user_text or len(user_text.strip()) < 2:
        print(json.dumps({"suppressOutput": True}))
        return

    session_id = os.environ.get("CLAUDE_SESSION_ID", "")
    if not session_id:
        try:
            with open("/tmp/claude-current-session/id") as f:
                session_id = f.read().strip() or "default"
        except (OSError, IOError):
            session_id = "default"

    # ── Pipeline Step 1: Count items ──
    item_count, intent = count_items(user_text)

    # ── Pipeline Step 2: Extract keywords ──
    keywords = extract_keywords(user_text)

    # ── Pipeline Step 3: Auto memory search ──
    memory_context = ""
    if keywords and len(user_text) > 30:
        memory_context = auto_memory_search(keywords)

    # ── Pipeline Step 4: Check past mistakes ──
    past_issues = []
    if keywords and len(user_text) > 30:
        past_issues = check_mistakes(keywords)

    # ── Pipeline Step 5: Detect frustration ──
    frust_level, frust_signal = detect_frustration(user_text)

    # ── Pipeline Step 6: Agent dashboard ──
    agent_status = get_agent_dashboard(session_id)

    # ── Pipeline Step 7: Domain-aware procedure loading ──
    proc_files = detect_domain()
    proc_context = load_procedures(proc_files)

    # ── Pipeline Step 8: Auto-capture permanent instructions ──
    auto_captured = auto_capture_instructions(user_text)

    # ── Pipeline Step 9: Save state for other hooks ──
    save_perception_state(item_count, intent, keywords)

    # ── Build injection context ──
    ctx_parts = []

    # Perception header (always)
    ctx_parts.append(f"[PERCEPTION] Items: {item_count} | Intent: {intent}")

    # Procedure reminders (domain-specific, HIGH priority)
    if proc_context:
        ctx_parts.append(f"[PROCEDURES] {proc_context}")

    # Memory recall (if found)
    if memory_context:
        ctx_parts.append(f"[MEMORY RECALL] {memory_context}")

    # Past issues (if found)
    if past_issues:
        issues_str = "; ".join(past_issues)
        ctx_parts.append(f"[PAST ISSUES] Similar: {issues_str}")

    # Frustration (if detected)
    if frust_level:
        frust_level, frust_signal, frust_total = escalate_frustration(
            frust_level, frust_signal, session_id
        )
        fctx = f" [Session: {frust_total}x frustrations]" if frust_total > 1 else ""

        protocols = {
            "CRITICAL": f"[GAALI — CRITICAL] Signal: '{frust_signal}'.{fctx}\nPROTOCOL: Show '>> GAALI PROTOCOL [CRITICAL]' block. Then: 1) 'Meri galti.' 2) Re-read ORIGINAL request 3) Find SPECIFIC gap 4) Fix NOW with TaskCreate/agent 5) PROVE with Read/Bash 6) Report gap+fix+evidence. Running agents CONTINUE.",
            "HIGH": f"[FRUSTRATION — HIGH] Signal: '{frust_signal}'.{fctx}\nPROTOCOL: Show '>> FRUSTRATION PROTOCOL [HIGH]' block. 1-line acknowledge. Re-read request. Course-correct NOW. 2x verify. Results first.",
            "MEDIUM": f"[FRUSTRATION — MEDIUM] Signal: '{frust_signal}'.{fctx}\nShow '>> ALERT [MEDIUM]'. Fix issue. Check original request. Be precise.",
            "LOW": f"[DISSATISFACTION — LOW] Signal: '{frust_signal}'.{fctx}\nShow '>> NOTE [LOW]'. Re-read last response. Be more thorough. Verify.",
            "WARNING": f"[TONE SHIFT — WARNING] Signal: '{frust_signal}'.{fctx}\nShow '>> WARN — tone shift'. Extra precision. Match what was asked. Zero fluff.",
        }
        ctx_parts.append(protocols.get(frust_level, ""))

    # Agent dashboard (if running)
    if agent_status:
        ctx_parts.append(f"[AGENTS]\n{agent_status}")

    # Combine
    injection = "\n".join(p for p in ctx_parts if p)

    # Trim to stay within budget (max 3000 chars — expanded for procedures)
    if len(injection) > 3000:
        injection = injection[:2997] + "..."

    # Output
    output = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": injection,
        },
        "suppressOutput": True,
    }
    print(json.dumps(output))


if __name__ == "__main__":
    main()
