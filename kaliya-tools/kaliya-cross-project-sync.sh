#!/usr/bin/env bash
set -uo pipefail

# KALIYA Cross-Project Brain Sync v1.0
# Syncs learnings from project-specific mistakes files to global brain.
# Human subconscious transfers lessons across experiences — KALIYA should too.
#
# Usage: kaliya-cross-project-sync.sh [--dry-run] [--verbose]

GLOBAL_BRAIN="$HOME/.claude_2/projects/-Users-niwash/memory/mistakes-learnings.md"
MEMORY_ROOT="$HOME/.claude_2/projects"
SYNC_LOG="/tmp/kaliya-brain-sync.log"
DRY_RUN=false
VERBOSE=false

# Parse args
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        --verbose) VERBOSE=true ;;
        --force) ;; # Skip confirmation (no interactive prompt in this script, flag accepted for compatibility)
    esac
done

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log() { echo -e "${CYAN}[BRAIN]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
added() { echo -e "${GREEN}[+NEW]${NC} $1"; }
skip() { $VERBOSE && echo -e "${YELLOW}[SKIP]${NC} $1"; }

# Ensure global brain exists
if [ ! -f "$GLOBAL_BRAIN" ]; then
    warn "Global brain not found at $GLOBAL_BRAIN"
    exit 1
fi

# Read global brain content for dedup checking
GLOBAL_CONTENT=$(cat "$GLOBAL_BRAIN")
GLOBAL_HEADERS=$(grep "^## " "$GLOBAL_BRAIN" | sed 's/^## //' | tr '[:upper:]' '[:lower:]')

synced=0
skipped=0
files_checked=0

log "Cross-Project Brain Sync starting..."
log "Global brain: $GLOBAL_BRAIN ($(wc -l < "$GLOBAL_BRAIN") lines)"

# Find all project mistake files (excluding the global one itself)
while IFS= read -r project_file; do
    # Skip the global file itself
    [ "$project_file" = "$GLOBAL_BRAIN" ] && continue

    files_checked=$((files_checked + 1))
    project_name=$(echo "$project_file" | sed "s|$MEMORY_ROOT/||" | cut -d'/' -f1 | sed 's/-Users-niwash-//' | sed 's/-Users-niwash/global/')

    $VERBOSE && log "Scanning: $project_name ($(wc -l < "$project_file") lines)"

    # Extract sections (## headers and their content until next ## or EOF)
    current_header=""
    current_content=""

    while IFS= read -r line; do
        if [[ "$line" =~ ^##\  ]]; then
            # Process previous section if exists
            if [ -n "$current_header" ] && [ -n "$current_content" ]; then
                header_lower=$(echo "$current_header" | tr '[:upper:]' '[:lower:]')

                # Check if this header (or similar) exists in global
                # Use first 20 chars of header for fuzzy match
                header_key=$(echo "$header_lower" | cut -c1-25)

                if echo "$GLOBAL_HEADERS" | grep -qi "$header_key" 2>/dev/null; then
                    skip "Already in global: $current_header [$project_name]"
                    skipped=$((skipped + 1))
                else
                    # Check content similarity — if key phrases exist in global
                    key_phrase=$(echo "$current_content" | head -1 | sed 's/[*_#]//g' | cut -c1-40)

                    if [ -n "$key_phrase" ] && echo "$GLOBAL_CONTENT" | grep -qi "$key_phrase" 2>/dev/null; then
                        skip "Content overlap: $current_header [$project_name]"
                        skipped=$((skipped + 1))
                    else
                        added "NEW learning: $current_header [$project_name]"

                        if ! $DRY_RUN; then
                            # Append to global brain
                            {
                                echo ""
                                echo "## $current_header"
                                echo "$current_content"
                            } >> "$GLOBAL_BRAIN"
                        fi

                        synced=$((synced + 1))

                        # Log sync
                        echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) | SYNCED | $project_name | $current_header" >> "$SYNC_LOG"
                    fi
                fi
            fi

            # Start new section
            current_header="${line#\#\# }"
            current_content=""
        else
            # Accumulate content
            if [ -n "$current_header" ]; then
                current_content="${current_content}${line}
"
            fi
        fi
    done < "$project_file"

    # Process last section
    if [ -n "$current_header" ] && [ -n "$current_content" ]; then
        header_lower=$(echo "$current_header" | tr '[:upper:]' '[:lower:]')
        header_key=$(echo "$header_lower" | cut -c1-25)

        if ! echo "$GLOBAL_HEADERS" | grep -qi "$header_key" 2>/dev/null; then
            key_phrase=$(echo "$current_content" | head -1 | sed 's/[*_#]//g' | cut -c1-40)

            if [ -z "$key_phrase" ] || ! echo "$GLOBAL_CONTENT" | grep -qi "$key_phrase" 2>/dev/null; then
                added "NEW learning: $current_header [$project_name]"

                if ! $DRY_RUN; then
                    {
                        echo ""
                        echo "## $current_header"
                        echo "$current_content"
                    } >> "$GLOBAL_BRAIN"
                fi

                synced=$((synced + 1))
                echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) | SYNCED | $project_name | $current_header" >> "$SYNC_LOG"
            else
                skip "Content overlap: $current_header"
                skipped=$((skipped + 1))
            fi
        else
            skip "Already in global: $current_header"
            skipped=$((skipped + 1))
        fi
    fi

done < <(ls "$MEMORY_ROOT"/*/memory/mistakes-learnings.md "$MEMORY_ROOT"/*/*/memory/mistakes-learnings.md 2>/dev/null || true)

# Summary
echo ""
log "========================================="
log "Files checked: $files_checked"
added "New learnings synced: $synced"
skip "Already present: $skipped" || true
if $DRY_RUN; then
    warn "DRY RUN — nothing was written"
fi
log "Global brain now: $(wc -l < "$GLOBAL_BRAIN") lines"
log "========================================="
