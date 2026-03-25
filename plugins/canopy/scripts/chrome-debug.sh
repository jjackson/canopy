#!/bin/bash
# Ensure Chrome is running with remote debugging enabled.
# If Chrome is already debuggable, does nothing.
# If Chrome is running without debugging, gracefully restarts it.
#
# Uses a persistent debug profile at ~/.chrome-debug-profile. This is
# separate from your main Chrome profile. On first run you'll get a
# fresh Chrome — log into your accounts once and it persists across
# restarts. Your main Chrome profile is never touched.
#
# KEY INSIGHT: Newer Chrome on macOS requires --user-data-dir to be
# a non-default path for --remote-debugging-port to work.

PORT="${1:-9222}"
DEBUG_PROFILE="$HOME/.chrome-debug-profile"

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

# If Chrome is running (without debugging), quit it first
if pgrep -x "Google Chrome" > /dev/null 2>&1; then
    echo "Chrome is running without debugging. Quitting to restart with CDP on port $PORT..."

    osascript -e 'tell application "Google Chrome" to quit' 2>/dev/null

    for i in $(seq 1 15); do
        if ! pgrep -x "Google Chrome" > /dev/null 2>&1; then
            break
        fi
        sleep 1
    done

    if pgrep -x "Google Chrome" > /dev/null 2>&1; then
        echo "Error: Chrome didn't quit cleanly. Close it manually and try again."
        exit 1
    fi

    sleep 2
else
    echo "Chrome is not running. Starting with debugging on port $PORT..."
fi

# Create debug profile dir if it doesn't exist (first-time only).
# This profile is persistent — logins, tabs, and cookies survive across restarts.
if [ ! -d "$DEBUG_PROFILE" ]; then
    echo "  First run: creating debug profile at $DEBUG_PROFILE"
    echo "  You'll need to log into your accounts once — they'll persist after that."
    mkdir -p "$DEBUG_PROFILE"
fi

# Launch Chrome with debugging.
"$CHROME_BIN" \
    --remote-debugging-port="$PORT" \
    --user-data-dir="$DEBUG_PROFILE" > /dev/null 2>&1 &

# Wait for debugging to become available
echo "Waiting for Chrome to start..."
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
echo "  $CHROME_BIN --remote-debugging-port=$PORT --user-data-dir=$DEBUG_PROFILE"
exit 1
