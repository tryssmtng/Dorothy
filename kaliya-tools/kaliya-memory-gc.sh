#!/usr/bin/env bash
set -uo pipefail
# NOTE: -e intentionally omitted. find returns non-zero on permission-denied
# dirs, and set -e + pipefail kills the script. We handle errors explicitly.

# KALIYA Memory Garbage Collection v1.0
# Cleans up stale session summaries and old daily logs
# from ~/.claude_2/projects/ directory tree.

# ──────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────
PROJECTS_DIR="$HOME/.claude_2/projects"
GC_TIMESTAMP_FILE="/tmp/kaliya-last-gc"
SESSION_MAX_AGE_DAYS=7
DAILY_MAX_AGE_DAYS=14

# Protected filenames (NEVER delete these from memory/)
PROTECTED_FILES="MEMORY.md mistakes-learnings.md credentials-secrets.md malik-preferences.md device-environment.md"

# UUID regex pattern (8-4-4-4-12 hex)
UUID_PATTERN='^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'

# ──────────────────────────────────────────────────────
# Colors
# ──────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# ──────────────────────────────────────────────────────
# Flags
# ──────────────────────────────────────────────────────
DRY_RUN=false
STATS_ONLY=false
FORCE=false

# ──────────────────────────────────────────────────────
# Global collection arrays (macOS bash 3.x compatible)
# ──────────────────────────────────────────────────────
SESSION_DIRS_TO_CLEAN=()
SESSION_SIZES=()
SESSION_CLEAN_COUNT=0

DAILY_FILES_TO_CLEAN=()
DAILY_SIZES=()
DAILY_CLEAN_COUNT=0

usage() {
    echo -e "${BOLD}KALIYA Memory GC v1.0${NC}"
    echo ""
    echo "Usage: $(basename "$0") [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --dry-run    Show what would be deleted without deleting"
    echo "  --stats      Show current memory stats and exit"
    echo "  --force      Skip confirmation prompt"
    echo "  --help       Show this help"
    echo ""
    echo "What gets cleaned:"
    echo "  - Session summaries (UUID dirs) older than ${SESSION_MAX_AGE_DAYS} days"
    echo "  - Daily log files older than ${DAILY_MAX_AGE_DAYS} days"
    echo ""
    echo "What is NEVER touched:"
    echo "  - MEMORY.md, mistakes-learnings.md, credentials-secrets.md"
    echo "  - malik-preferences.md, device-environment.md"
    echo "  - Topic-specific .md files in memory/ directories"
}

# Parse args
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)  DRY_RUN=true; shift ;;
        --stats)    STATS_ONLY=true; shift ;;
        --force)    FORCE=true; shift ;;
        --help|-h)  usage; exit 0 ;;
        *)          echo -e "${RED}Unknown option: $1${NC}"; usage; exit 1 ;;
    esac
done

# ──────────────────────────────────────────────────────
# Validation
# ──────────────────────────────────────────────────────
if [[ ! -d "$PROJECTS_DIR" ]]; then
    echo -e "${RED}Projects directory not found: ${PROJECTS_DIR}${NC}"
    exit 1
fi

# ──────────────────────────────────────────────────────
# Helper: safe find wrapper (handles permission errors)
# Writes results to a temp file, returns file path
# ──────────────────────────────────────────────────────
safe_find() {
    local tmpfile dir pattern
    tmpfile=$(mktemp /tmp/kaliya-gc-find.XXXXXX)
    dir="$1"; shift
    # Convert find patterns to ls globs (sandbox-safe)
    local args="$*"
    if echo "$args" | grep -q "session-memory/summary.md"; then
        ls "$dir"/*/*/session-memory/summary.md 2>/dev/null > "$tmpfile" || true
    elif echo "$args" | grep -q "memory/daily"; then
        ls "$dir"/*/memory/daily/*.md 2>/dev/null > "$tmpfile" || true
    elif echo "$args" | grep -q '\-name.*\.md'; then
        { ls "$dir"/*/memory/*.md "$dir"/*/memory/daily/*.md "$dir"/*/*/session-memory/summary.md 2>/dev/null || true; } > "$tmpfile"
    elif echo "$args" | grep -q "memory/\*.md.*not.*daily"; then
        ls "$dir"/*/memory/*.md 2>/dev/null | grep -v "/daily/" > "$tmpfile" 2>/dev/null || true
    else
        find "$dir" "$@" 2>/dev/null > "$tmpfile" || true
    fi
    echo "$tmpfile"
}

# ──────────────────────────────────────────────────────
# Helper: get file/dir modification time age in days
# ──────────────────────────────────────────────────────
get_age_days() {
    local filepath="$1"
    local now mtime
    now=$(date +%s)
    mtime=$(stat -f %m "$filepath" 2>/dev/null || echo "$now")
    echo $(( (now - mtime) / 86400 ))
}

# ──────────────────────────────────────────────────────
# Helper: get directory size in bytes
# ──────────────────────────────────────────────────────
get_dir_size() {
    local dirpath="$1"
    local kb
    kb=$(du -sk "$dirpath" 2>/dev/null | awk '{print $1}')
    echo $(( kb * 1024 ))
}

# ──────────────────────────────────────────────────────
# Helper: get file size in bytes
# ──────────────────────────────────────────────────────
get_file_size() {
    local filepath="$1"
    stat -f %z "$filepath" 2>/dev/null || echo 0
}

# ──────────────────────────────────────────────────────
# Helper: human readable size
# ──────────────────────────────────────────────────────
human_size() {
    local bytes=$1
    if (( bytes >= 1048576 )); then
        echo "$(( bytes / 1048576 )) MB"
    elif (( bytes >= 1024 )); then
        echo "$(( bytes / 1024 )) KB"
    else
        echo "${bytes} B"
    fi
}

# ──────────────────────────────────────────────────────
# Collect: session UUID directories to clean
# Populates global SESSION_DIRS_TO_CLEAN, SESSION_SIZES
# ──────────────────────────────────────────────────────
collect_session_dirs() {
    SESSION_DIRS_TO_CLEAN=()
    SESSION_SIZES=()
    SESSION_CLEAN_COUNT=0

    local tmpfile
    tmpfile=$(safe_find "$PROJECTS_DIR" -path "*/session-memory/summary.md" -type f)

    while IFS= read -r summary_file; do
        [[ -z "$summary_file" ]] && continue

        local session_memory_dir uuid_dir uuid_name age
        session_memory_dir=$(dirname "$summary_file")
        uuid_dir=$(dirname "$session_memory_dir")
        uuid_name=$(basename "$uuid_dir")

        # Verify it's actually a UUID directory
        if [[ ! "$uuid_name" =~ $UUID_PATTERN ]]; then
            continue
        fi

        age=$(get_age_days "$summary_file")

        if (( age > SESSION_MAX_AGE_DAYS )); then
            SESSION_DIRS_TO_CLEAN+=("$uuid_dir")
            SESSION_SIZES+=("$(get_dir_size "$uuid_dir")")
            SESSION_CLEAN_COUNT=$((SESSION_CLEAN_COUNT + 1))
        fi
    done < "$tmpfile"

    rm -f "$tmpfile"
}

# ──────────────────────────────────────────────────────
# Collect: daily files to clean
# Populates global DAILY_FILES_TO_CLEAN, DAILY_SIZES
# ──────────────────────────────────────────────────────
collect_daily_files() {
    DAILY_FILES_TO_CLEAN=()
    DAILY_SIZES=()
    DAILY_CLEAN_COUNT=0

    local tmpfile
    tmpfile=$(safe_find "$PROJECTS_DIR" -path "*/memory/daily/*.md" -type f)

    while IFS= read -r daily_file; do
        [[ -z "$daily_file" ]] && continue

        local filename file_date file_epoch now_ts age_days
        filename=$(basename "$daily_file")

        # Verify date pattern in filename
        if [[ ! "$filename" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}\.md$ ]]; then
            continue
        fi

        # Extract date from filename for accurate age calculation
        file_date="${filename%.md}"
        file_epoch=$(date -j -f "%Y-%m-%d" "$file_date" "+%s" 2>/dev/null || echo 0)

        if [[ "$file_epoch" -eq 0 ]]; then
            # Fallback to mtime if date parsing fails
            age_days=$(get_age_days "$daily_file")
        else
            now_ts=$(date +%s)
            age_days=$(( (now_ts - file_epoch) / 86400 ))
        fi

        if (( age_days > DAILY_MAX_AGE_DAYS )); then
            DAILY_FILES_TO_CLEAN+=("$daily_file")
            DAILY_SIZES+=("$(get_file_size "$daily_file")")
            DAILY_CLEAN_COUNT=$((DAILY_CLEAN_COUNT + 1))
        fi
    done < "$tmpfile"

    rm -f "$tmpfile"
}

# ──────────────────────────────────────────────────────
# Count helpers (use safe_find to avoid pipefail issues)
# ──────────────────────────────────────────────────────
count_total_files() {
    local tmpfile count
    tmpfile=$(safe_find "$PROJECTS_DIR" -name "*.md" -type f)
    count=$(wc -l < "$tmpfile" | tr -d ' ')
    rm -f "$tmpfile"
    echo "${count:-0}"
}

count_session_summaries() {
    local tmpfile count
    tmpfile=$(safe_find "$PROJECTS_DIR" -path "*/session-memory/summary.md" -type f)
    count=$(wc -l < "$tmpfile" | tr -d ' ')
    rm -f "$tmpfile"
    echo "${count:-0}"
}

count_daily_files_total() {
    local tmpfile count
    tmpfile=$(safe_find "$PROJECTS_DIR" -path "*/memory/daily/*.md" -type f)
    count=$(wc -l < "$tmpfile" | tr -d ' ')
    rm -f "$tmpfile"
    echo "${count:-0}"
}

# ──────────────────────────────────────────────────────
# Sum array of numbers
# ──────────────────────────────────────────────────────
sum_array() {
    local total=0
    local item
    for item in "$@"; do
        [[ -n "$item" ]] && total=$((total + item))
    done
    echo "$total"
}

# ──────────────────────────────────────────────────────
# STATS mode
# ──────────────────────────────────────────────────────
if [[ "$STATS_ONLY" == true ]]; then
    echo -e "${BOLD}${CYAN}>> KALIYA Memory Stats${NC}"
    echo ""

    total_files=$(count_total_files)
    session_count=$(count_session_summaries)
    daily_count=$(count_daily_files_total)
    protected_count=0
    topic_count=0

    # Count protected and topic files in memory/ (excluding daily/)
    local_tmpfile=$(safe_find "$PROJECTS_DIR" -path "*/memory/*.md" -not -path "*/daily/*" -type f)
    while IFS= read -r f; do
        [[ -z "$f" ]] && continue
        fname=$(basename "$f")
        parent_dir=$(basename "$(dirname "$f")")
        is_protected=false

        for pf in $PROTECTED_FILES; do
            if [[ "$fname" == "$pf" ]]; then
                is_protected=true
                break
            fi
        done

        if [[ "$is_protected" == true ]]; then
            protected_count=$((protected_count + 1))
        elif [[ "$parent_dir" == "memory" ]]; then
            topic_count=$((topic_count + 1))
        fi
    done < "$local_tmpfile"
    rm -f "$local_tmpfile"

    # Collect cleanable items
    collect_session_dirs
    collect_daily_files

    total_reclaimable=0
    if (( ${#SESSION_SIZES[@]} > 0 )); then
        total_reclaimable=$(sum_array "${SESSION_SIZES[@]}")
    fi
    if (( ${#DAILY_SIZES[@]} > 0 )); then
        daily_total=$(sum_array "${DAILY_SIZES[@]}")
        total_reclaimable=$((total_reclaimable + daily_total))
    fi

    total_to_clean=$((SESSION_CLEAN_COUNT + DAILY_CLEAN_COUNT))
    total_kept=$((total_files - total_to_clean))

    echo -e "  ${GREEN}Total .md files:${NC}          $total_files"
    echo -e "  ${GREEN}Session summaries:${NC}        $session_count (${SESSION_CLEAN_COUNT} stale, >${SESSION_MAX_AGE_DAYS}d)"
    echo -e "  ${GREEN}Daily logs:${NC}               $daily_count (${DAILY_CLEAN_COUNT} stale, >${DAILY_MAX_AGE_DAYS}d)"
    echo -e "  ${GREEN}Protected files:${NC}          $protected_count"
    echo -e "  ${GREEN}Topic files:${NC}              $topic_count"
    echo ""
    echo -e "  ${RED}Files to clean:${NC}           $total_to_clean"
    echo -e "  ${RED}Space to reclaim:${NC}         $(human_size $total_reclaimable)"
    echo -e "  ${GREEN}Files kept:${NC}               $total_kept"
    echo ""

    if [[ -f "$GC_TIMESTAMP_FILE" ]]; then
        last_gc=$(cat "$GC_TIMESTAMP_FILE")
        echo -e "  ${YELLOW}Last GC:${NC}                  $last_gc"
    else
        echo -e "  ${YELLOW}Last GC:${NC}                  never"
    fi

    exit 0
fi

# ──────────────────────────────────────────────────────
# Main GC flow
# ──────────────────────────────────────────────────────
echo -e "${BOLD}${CYAN}>> KALIYA Memory GC v1.0${NC}"
echo ""

# Collect items to clean
collect_session_dirs
collect_daily_files

total_to_clean=$((SESSION_CLEAN_COUNT + DAILY_CLEAN_COUNT))

# Nothing to clean?
if (( total_to_clean == 0 )); then
    echo -e "${GREEN}Nothing to clean. All files are within retention period.${NC}"
    echo ""
    echo -e "  Session summaries: >${SESSION_MAX_AGE_DAYS} days = 0 found"
    echo -e "  Daily logs: >${DAILY_MAX_AGE_DAYS} days = 0 found"
    date "+%Y-%m-%d %H:%M:%S" > "$GC_TIMESTAMP_FILE"
    exit 0
fi

# Calculate total reclaimable space
total_reclaimable=0
if (( ${#SESSION_SIZES[@]} > 0 )); then
    total_reclaimable=$(sum_array "${SESSION_SIZES[@]}")
fi
if (( ${#DAILY_SIZES[@]} > 0 )); then
    daily_total=$(sum_array "${DAILY_SIZES[@]}")
    total_reclaimable=$((total_reclaimable + daily_total))
fi

# Show what will be cleaned — sessions
echo -e "${BOLD}Session UUID directories (>${SESSION_MAX_AGE_DAYS} days):${NC} ${SESSION_CLEAN_COUNT} found"
for i in "${!SESSION_DIRS_TO_CLEAN[@]}"; do
    local_dir="${SESSION_DIRS_TO_CLEAN[$i]}"
    local_size="${SESSION_SIZES[$i]}"
    local_uuid=$(basename "$local_dir")
    local_project=$(basename "$(dirname "$local_dir")")
    local_age=$(get_age_days "$local_dir/session-memory/summary.md")
    echo -e "  ${RED}[DELETE]${NC} ${local_project}/${local_uuid} (${local_age}d, $(human_size "$local_size"))"
done

# Show what will be cleaned — dailies
echo ""
echo -e "${BOLD}Daily log files (>${DAILY_MAX_AGE_DAYS} days):${NC} ${DAILY_CLEAN_COUNT} found"
for i in "${!DAILY_FILES_TO_CLEAN[@]}"; do
    local_file="${DAILY_FILES_TO_CLEAN[$i]}"
    local_size="${DAILY_SIZES[$i]}"
    local_date=$(basename "$local_file" .md)
    # Walk up: file -> daily/ -> memory/ -> project/
    local_project=$(basename "$(dirname "$(dirname "$(dirname "$local_file")")")")
    echo -e "  ${RED}[DELETE]${NC} ${local_project}/daily/${local_date}.md ($(human_size "$local_size"))"
done

echo ""
echo -e "${BOLD}Summary:${NC} $total_to_clean items, $(human_size $total_reclaimable) to reclaim"

# Dry run stops here
if [[ "$DRY_RUN" == true ]]; then
    echo ""
    echo -e "${YELLOW}DRY RUN -- nothing was deleted.${NC}"
    exit 0
fi

# Confirmation prompt (unless --force)
if [[ "$FORCE" != true ]]; then
    echo ""
    echo -ne "${YELLOW}Proceed with deletion? [y/N]: ${NC}"
    read -r confirm
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        echo -e "${YELLOW}Aborted.${NC}"
        exit 0
    fi
fi

# ──────────────────────────────────────────────────────
# Execute deletions
# ──────────────────────────────────────────────────────
deleted_count=0
deleted_bytes=0
failed_count=0

# Delete session UUID directories
for i in "${!SESSION_DIRS_TO_CLEAN[@]}"; do
    dir="${SESSION_DIRS_TO_CLEAN[$i]}"
    size="${SESSION_SIZES[$i]}"
    uuid=$(basename "$dir")
    project=$(basename "$(dirname "$dir")")

    if rm -rf "$dir" 2>/dev/null; then
        deleted_count=$((deleted_count + 1))
        deleted_bytes=$((deleted_bytes + size))
        echo -e "  ${RED}Deleted${NC} ${project}/${uuid}"
    else
        failed_count=$((failed_count + 1))
        echo -e "  ${YELLOW}Failed${NC} ${project}/${uuid}"
    fi
done

# Delete daily files
for i in "${!DAILY_FILES_TO_CLEAN[@]}"; do
    file="${DAILY_FILES_TO_CLEAN[$i]}"
    size="${DAILY_SIZES[$i]}"
    date_name=$(basename "$file" .md)
    project=$(basename "$(dirname "$(dirname "$(dirname "$file")")")")

    if rm -f "$file" 2>/dev/null; then
        deleted_count=$((deleted_count + 1))
        deleted_bytes=$((deleted_bytes + size))
        echo -e "  ${RED}Deleted${NC} ${project}/daily/${date_name}.md"
    else
        failed_count=$((failed_count + 1))
        echo -e "  ${YELLOW}Failed${NC} ${project}/daily/${date_name}.md"
    fi
done

# Count remaining files
remaining=$(count_total_files)

# Save GC timestamp
date "+%Y-%m-%d %H:%M:%S" > "$GC_TIMESTAMP_FILE"

# ──────────────────────────────────────────────────────
# Final summary
# ──────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${CYAN}>> GC Complete${NC}"
echo -e "  ${RED}Deleted:${NC}    $deleted_count items"
echo -e "  ${RED}Reclaimed:${NC}  $(human_size $deleted_bytes)"
echo -e "  ${GREEN}Kept:${NC}       $remaining files"
if (( failed_count > 0 )); then
    echo -e "  ${YELLOW}Failed:${NC}     $failed_count items"
fi
echo -e "  ${CYAN}Timestamp:${NC}  $(cat "$GC_TIMESTAMP_FILE")"
