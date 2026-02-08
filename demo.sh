#!/bin/bash
# wayr demo script - shows example usage

set -e

WAYR="./wayr.py"

echo "========================================"
echo "wayr - Why Are You Running? - Demo"
echo "========================================"
echo ""

# Check if wayr exists
if [ ! -f "$WAYR" ]; then
    echo "Error: wayr.py not found in current directory"
    exit 1
fi

chmod +x "$WAYR"

echo "1. Finding all Python processes:"
echo "   $ wayr python"
echo ""
$WAYR python 2>&1 | head -20 || true
echo ""

echo "========================================"
echo ""

echo "2. Checking systemd (PID 1):"
echo "   $ wayr --pid 1"
echo ""
$WAYR --pid 1 2>&1 || true
echo ""

echo "========================================"
echo ""

echo "3. Short ancestry format:"
echo "   $ wayr --pid 1 --short"
echo ""
$WAYR --pid 1 --short 2>&1 || true
echo ""

echo "========================================"
echo ""

echo "4. Process tree view:"
echo "   $ wayr --pid 1 --tree"
echo ""
$WAYR --pid 1 --tree 2>&1 | head -20 || true
echo ""

echo "========================================"
echo ""

echo "5. JSON output:"
echo "   $ wayr --pid 1 --json"
echo ""
$WAYR --pid 1 --json 2>&1 | head -30 || true
echo ""

echo "========================================"
echo ""

echo "6. Current shell process:"
echo "   $ wayr --pid $$"
echo ""
$WAYR --pid $$ 2>&1 || true
echo ""

echo "========================================"
echo ""

echo "7. Help output:"
echo "   $ wayr --help"
echo ""
$WAYR --help 2>&1
echo ""

echo "========================================"
echo "Demo complete!"
echo ""
echo "Try these commands yourself:"
echo "  - wayr <process_name>    # Find process by name"
echo "  - wayr --pid <pid>       # Analyze specific PID"
echo "  - wayr --port <port>     # Find what's listening on a port"
echo "  - wayr --tree            # Show process tree"
echo "  - wayr --json            # Get JSON output"
echo ""
