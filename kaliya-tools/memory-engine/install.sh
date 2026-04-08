#!/bin/bash
# KALIYA Memory Engine — One-shot Installer
set -e

ENGINE_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="/opt/homebrew/bin/python3"

echo "=== KALIYA Memory Engine Installer ==="
echo "Engine dir: $ENGINE_DIR"

# 1. Install Python dependencies
echo "[1/4] Installing Python dependencies..."
$PYTHON -m pip install --quiet sentence-transformers fastmcp numpy 2>&1 | tail -3

# 2. Create directories
echo "[2/4] Creating directories..."
mkdir -p "$ENGINE_DIR/index" "$ENGINE_DIR/models" "$ENGINE_DIR/core"

# 3. Verify imports
echo "[3/4] Verifying imports..."
$PYTHON -c "
from sentence_transformers import SentenceTransformer
from fastmcp import FastMCP
import numpy as np
import sqlite3
print(f'  sentence-transformers: OK')
print(f'  fastmcp: OK')
print(f'  numpy: {np.__version__}')
print(f'  sqlite3: {sqlite3.sqlite_version}')
"

# 4. Initialize database
echo "[4/4] Initializing database..."
$PYTHON -c "
import sys
sys.path.insert(0, '$ENGINE_DIR')
from core.database import MemoryDB
db = MemoryDB('$ENGINE_DIR/index/memory.db')
db.initialize()
print(f'  Database initialized: $ENGINE_DIR/index/memory.db')
db.close()
"

echo ""
echo "=== Installation complete ==="
echo "Next: Add MCP server to ~/.claude/settings.json"
echo "Then: python3 $ENGINE_DIR/cli.py index --all-projects"
