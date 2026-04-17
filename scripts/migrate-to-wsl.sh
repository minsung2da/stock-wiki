#!/usr/bin/env bash
# scripts/migrate-to-wsl.sh
# Migrates vault from /mnt/c/.../stock to ~/stock (WSL-native filesystem)
# Provides significant I/O performance improvement (5-10x) over /mnt/c/ paths.
#
# Usage: bash scripts/migrate-to-wsl.sh
#
# After migration:
# 1. cd ~/stock && git remote -v (verify remotes)
# 2. In Obsidian (Windows): Open vault at \\wsl$\<distro>\home\<user>\stock
# 3. Verify .obsidian/ settings intact
# 4. Remove old location when confirmed: rm -rf "$STOCK_SRC"

set -euo pipefail

SRC="${STOCK_SRC:?Set STOCK_SRC to your Windows vault path, e.g. /mnt/c/Users/yourname/workspace/stock}"
DST="$HOME/stock"

# Auto-detect WSL distro name for Obsidian path
if command -v wsl.exe &>/dev/null; then
    DISTRO=$(wsl.exe -l -q 2>/dev/null | head -1 | tr -d '\r' | tr -d '\000' || echo "Ubuntu")
else
    DISTRO=$(hostname)
fi

echo "=== Stock Wiki WSL Migration ==="
echo "Source: $SRC"
echo "Destination: $DST"
echo "Detected distro: $DISTRO"
echo ""

# Safety checks
if [ ! -d "$SRC" ]; then
    echo "ERROR: Source directory $SRC does not exist."
    exit 1
fi

if [ -d "$DST" ]; then
    echo "ERROR: Destination $DST already exists. Aborting to prevent data loss."
    echo "If this is intentional, remove $DST first."
    exit 1
fi

# Confirm
read -p "Proceed with migration? [y/N] " confirm
if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

echo ""
echo "Step 1: Copying files (preserving permissions and timestamps)..."
cp -a "$SRC" "$DST"

echo "Step 2: Verifying copy..."
SRC_COUNT=$(find "$SRC" -type f | wc -l)
DST_COUNT=$(find "$DST" -type f | wc -l)
echo "  Source files: $SRC_COUNT"
echo "  Destination files: $DST_COUNT"

if [ "$SRC_COUNT" -ne "$DST_COUNT" ]; then
    echo "WARNING: File counts differ. Please verify manually."
fi

echo ""
echo "=== Migration complete ==="
echo ""
echo "Next steps:"
echo "1. cd $DST && git remote -v  (verify remotes)"
echo "2. In Obsidian (Windows), open vault at:"
echo "   \\\\wsl\$\\${DISTRO}\\home\\$(whoami)\\stock"
echo "3. Verify .obsidian/ settings are intact"
echo "4. Test: cd $DST && docker compose up -d && uv run pytest tests/ -x"
echo "5. When confirmed working, remove old location:"
echo "   rm -rf $SRC"
