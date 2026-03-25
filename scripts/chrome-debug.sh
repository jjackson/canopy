#!/bin/bash
# Ensure a Chrome debug instance is running with remote debugging enabled.
# NEVER quits or interferes with the user's main Chrome.
#
# Runs HEADLESS by default so it doesn't steal the dock icon, Spotlight,
# or new-window focus from the user's main Chrome. Claude interacts via
# CDP only — no visible window needed for screenshots or content.
#
# For first-time login or manual interaction, use: chrome-debug.sh --visible
# This launches a visible window so you can log into accounts. Those
# logins persist in the debug profile for future headless runs.

PORT="${1:-9222}"
DEBUG_PROFILE="$HOME/.chrome-debug-profile"
HEADLESS="--headless=new"

# Parse flags
for arg in "$@"; do
    case "$arg" in
        --visible) HEADLESS="" ;;
        [0-9]*) PORT="$arg" ;;
    esac
done

# Check if debugging is already on
if curl -s "http://localhost:$PORT/json/version" > /dev/null 2>&1; then
    echo "Chrome debugging already active on port $PORT"
    curl -s "http://localhost:$PORT/json/version" | python3 -c "import sys,json; v=json.load(sys.stdin); print(f\"  Browser: {v.get('Browser','?')}\")" 2>/dev/null
    exit 0
fi

CHROME_APP="/Applications/Google Chrome.app"
CHROME_BIN="$CHROME_APP/Contents/MacOS/Google Chrome"

if ! [ -x "$CHROME_BIN" ]; then
    echo "Error: Chrome not found at $CHROME_APP"
    exit 1
fi

# Create debug profile dir if it doesn't exist (first-time only).
if [ ! -d "$DEBUG_PROFILE" ]; then
    echo "First run: creating debug profile at $DEBUG_PROFILE"
    if [ -z "$HEADLESS" ]; then
        echo "Log into your accounts in the debug window — they'll persist for future runs."
    else
        echo "Run with --visible to log into accounts: chrome-debug.sh --visible"
    fi
    mkdir -p "$DEBUG_PROFILE"
fi

# Launch Chrome with the debug profile.
if [ -n "$HEADLESS" ]; then
    echo "Starting headless Chrome debug instance on port $PORT..."
else
    echo "Starting visible Chrome debug instance on port $PORT..."
fi
"$CHROME_BIN" \
    $HEADLESS \
    --remote-debugging-port="$PORT" \
    --user-data-dir="$DEBUG_PROFILE" > /dev/null 2>&1 &

# Wait for debugging to become available
for i in $(seq 1 30); do
    if curl -s "http://localhost:$PORT/json/version" > /dev/null 2>&1; then
        echo "Chrome debugging active on port $PORT"
        curl -s "http://localhost:$PORT/json/version" | python3 -c "import sys,json; v=json.load(sys.stdin); print(f\"  Browser: {v.get('Browser','?')}\")" 2>/dev/null
        exit 0
    fi
    sleep 1
done

echo "Warning: Chrome started but debugging port not responding."
echo "Try running manually:"
echo "  \"$CHROME_BIN\" $HEADLESS --remote-debugging-port=$PORT --user-data-dir=$DEBUG_PROFILE"
exit 1
