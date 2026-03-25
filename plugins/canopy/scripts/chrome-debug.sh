#!/bin/bash
# Ensure a Chrome debug instance is running with remote debugging enabled.
# NEVER quits or interferes with the user's main Chrome.
#
# Uses a dedicated debug profile (~/.chrome-debug-profile) so the debug
# instance is completely isolated. Logins/cookies persist across restarts.
#
# NOTE: macOS treats both Chrome instances as one app in Spotlight/dock.
# If new windows open in the debug instance, Cmd+W to close the window
# (Chrome stays running with CDP active in the background).

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

# Create debug profile dir if it doesn't exist (first-time only).
if [ ! -d "$DEBUG_PROFILE" ]; then
    echo "First run: creating debug profile at $DEBUG_PROFILE"
    echo "You'll need to log into your accounts once — they'll persist after that."
    mkdir -p "$DEBUG_PROFILE"
fi

# Launch Chrome with the debug profile.
echo "Starting Chrome debug instance on port $PORT..."
"$CHROME_BIN" \
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
echo "  \"$CHROME_BIN\" --remote-debugging-port=$PORT --user-data-dir=$DEBUG_PROFILE"
exit 1
