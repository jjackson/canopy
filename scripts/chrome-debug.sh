#!/bin/bash
# Ensure Chrome is running with remote debugging enabled.
# If Chrome is already debuggable, does nothing.
# If Chrome is running without debugging, gracefully restarts it.
#
# KEY INSIGHT: Newer Chrome on macOS requires --user-data-dir to be
# a non-default path for --remote-debugging-port to work. We copy the
# real profile on first setup so tabs, extensions, and cookies carry over.

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

# Save tab URLs from the current Chrome session (if running)
TABS_FILE=""
if pgrep -x "Google Chrome" > /dev/null 2>&1; then
    echo "Chrome is running without debugging."
    echo "Saving tabs and restarting with debugging on port $PORT..."

    TABS_FILE=$(mktemp /tmp/chrome-tabs.XXXXXX)
    osascript -e '
    tell application "Google Chrome"
        set tabList to ""
        repeat with w in windows
            repeat with t in tabs of w
                set tabList to tabList & URL of t & linefeed
            end repeat
        end repeat
        return tabList
    end tell
    ' > "$TABS_FILE" 2>/dev/null

    TAB_COUNT=$(grep -c "http" "$TABS_FILE" 2>/dev/null || echo "0")
    echo "  Captured $TAB_COUNT tabs"

    # Graceful quit
    osascript -e 'tell application "Google Chrome" to quit' 2>/dev/null

    # Wait for Chrome to fully exit
    for i in $(seq 1 15); do
        if ! pgrep -x "Google Chrome" > /dev/null 2>&1; then
            break
        fi
        sleep 1
    done

    if pgrep -x "Google Chrome" > /dev/null 2>&1; then
        echo "Error: Chrome didn't quit cleanly. Close it manually and try again."
        rm -f "$TABS_FILE"
        exit 1
    fi

    sleep 2
else
    echo "Chrome is not running. Starting with debugging on port $PORT..."
fi

# Set up the debug profile (one-time: copy from real Chrome profile)
# Chrome requires a non-default --user-data-dir for remote debugging to work.
REAL_PROFILE="$HOME/Library/Application Support/Google/Chrome"
if [ ! -d "$DEBUG_PROFILE" ]; then
    if [ -d "$REAL_PROFILE" ]; then
        echo "  First-time setup: copying Chrome profile to debug profile..."
        echo "  (This may take a moment)"
        cp -R "$REAL_PROFILE" "$DEBUG_PROFILE"
        echo "  Debug profile created at $DEBUG_PROFILE"
    else
        echo "  Creating fresh debug profile..."
        mkdir -p "$DEBUG_PROFILE"
    fi
fi

# Launch Chrome with debugging.
# --user-data-dir is required on newer Chrome/macOS for the debug port to open.
"$CHROME_BIN" \
    --remote-debugging-port="$PORT" \
    --user-data-dir="$DEBUG_PROFILE" > /dev/null 2>&1 &

# Wait for debugging to become available
echo "Waiting for Chrome to start..."
for i in $(seq 1 30); do
    if curl -s "http://localhost:$PORT/json/version" > /dev/null 2>&1; then
        echo "Chrome debugging active on port $PORT"
        curl -s "http://localhost:$PORT/json/version" | python3 -c "import sys,json; v=json.load(sys.stdin); print(f\"  Browser: {v.get('Browser','?')}\")" 2>/dev/null

        # Restore tabs if we captured them and Chrome didn't auto-restore
        if [ -n "$TABS_FILE" ] && [ -s "$TABS_FILE" ]; then
            sleep 2
            CURRENT_TABS=$(curl -s "http://localhost:$PORT/json" 2>/dev/null | python3 -c "
import sys,json
tabs = json.load(sys.stdin)
urls = [t['url'] for t in tabs if not t['url'].startswith('chrome://')]
print(len(urls))
" 2>/dev/null || echo "0")

            if [ "$CURRENT_TABS" -le 1 ] && [ "$TAB_COUNT" -gt 1 ]; then
                echo "  Restoring $TAB_COUNT tabs..."
                while IFS= read -r url; do
                    [ -z "$url" ] && continue
                    [[ "$url" == chrome://* ]] && continue
                    curl -s "http://localhost:$PORT/json/new?$url" > /dev/null 2>&1
                done < "$TABS_FILE"
                echo "  Tabs restored."
            fi
        fi

        rm -f "$TABS_FILE"
        exit 0
    fi
    sleep 1
done

echo "Warning: Chrome started but debugging port not responding."
echo "Try running manually:"
echo "  $CHROME_BIN --remote-debugging-port=$PORT --user-data-dir=$DEBUG_PROFILE"
rm -f "$TABS_FILE"
exit 1
