#!/bin/zsh
set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"
LOG_DIR="$APP_DIR/data/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/desktop_console.log"
LAUNCHER_CONTRACT="touch_free_locus_v2"
echo "$(date '+%Y-%m-%d %H:%M:%S') launcher start" >> "$LOG_FILE"

is_current_console() {
  curl -fsS "$1/api/version" 2>/dev/null | grep -q "\"launcher_contract\": \"$LAUNCHER_CONTRACT\""
}

if [ ! -x ".venv/bin/python" ]; then
  osascript -e 'display dialog "The AI LinkedIn Python environment is missing. Ask Codex to run setup once, then open this app again." buttons {"OK"} default button "OK"'
  exit 1
fi

for PORT in 8766 8767 8768 8769 8770; do
  URL="http://127.0.0.1:$PORT/"
  if is_current_console "$URL"; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') reusing console at $URL" >> "$LOG_FILE"
    open "$URL"
    exit 0
  fi

  echo "$(date '+%Y-%m-%d %H:%M:%S') starting console at $URL" >> "$LOG_FILE"
  nohup "$APP_DIR/.venv/bin/python" -m ai_linkedin_automation.ui_server --host 127.0.0.1 --port "$PORT" >> "$LOG_FILE" 2>&1 &
  SERVER_PID=$!
  disown "$SERVER_PID" 2>/dev/null || true

  for ATTEMPT in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24; do
    if is_current_console "$URL"; then
      echo "$(date '+%Y-%m-%d %H:%M:%S') console ready at $URL" >> "$LOG_FILE"
      open "$URL"
      exit 0
    fi
    if ! kill -0 "$SERVER_PID" >/dev/null 2>&1; then
      break
    fi
    sleep 0.25
  done
done

osascript -e 'display dialog "The AI LinkedIn Console could not start. Ask Codex to inspect data/logs/desktop_console.log." buttons {"OK"} default button "OK"'
exit 1
