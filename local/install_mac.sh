#!/bin/bash
# Schedules local/tracking_mac.py to run every morning on this Mac.
#
#   bash local/install_mac.sh            install (or update) the daily run at 9:20am
#   bash local/install_mac.sh 7 45       install at a different time (7:45am)
#   bash local/install_mac.sh --remove   stop the daily run
#
# Uses launchd, macOS's built-in scheduler. If the Mac is asleep at run time,
# the job runs when it wakes. If it is shut down, that day is skipped.
set -euo pipefail

LABEL="com.drilium.courtscript.tracking"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOGDIR="$HOME/Library/Logs/court-script"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$REPO/local/tracking_mac.py"
DOMAIN="gui/$(id -u)"

if [ "${1:-}" = "--remove" ]; then
  launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
  rm -f "$PLIST"
  echo "Removed the daily tracking run. Logs are still in $LOGDIR."
  exit 0
fi

HOUR="${1:-9}"
MINUTE="${2:-20}"

# macOS asks permission before background jobs can read Desktop, Documents or
# Downloads, and a scheduled job can't answer that prompt, so it fails quietly.
case "$REPO" in
  "$HOME/Desktop"*|"$HOME/Documents"*|"$HOME/Downloads"*)
    echo "The repo is in $REPO."
    echo "Scheduled jobs can't read Desktop, Documents or Downloads without extra permissions."
    echo "Move it somewhere like ~/code/court-script and run this again:"
    echo "  mkdir -p ~/code && mv \"$REPO\" ~/code/ && bash ~/code/court-script/local/install_mac.sh"
    exit 1;;
esac

PY="$(command -v python3 || true)"
if [ -z "$PY" ] || ! "$PY" -c 'import sys; sys.exit(sys.version_info < (3, 8))' 2>/dev/null; then
  echo "Python 3 isn't installed yet. Run:  xcode-select --install"
  echo "then run this script again."
  exit 1
fi
command -v git >/dev/null || { echo "git isn't installed. Run:  xcode-select --install"; exit 1; }

mkdir -p "$LOGDIR" "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PY</string>
    <string>$SCRIPT</string>
  </array>
  <key>WorkingDirectory</key><string>$REPO</string>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>$HOUR</integer>
    <key>Minute</key><integer>$MINUTE</integer>
  </dict>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
  <key>StandardOutPath</key><string>$LOGDIR/tracking.log</string>
  <key>StandardErrorPath</key><string>$LOGDIR/tracking.log</string>
  <key>ProcessType</key><string>Background</string>
</dict>
</plist>
EOF

launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
launchctl bootstrap "$DOMAIN" "$PLIST"

printf 'Installed: tracking stats will be pulled every day at %d:%02d.\n' "$HOUR" "$MINUTE"
echo "Log:        $LOGDIR/tracking.log"
echo "Run it now: launchctl kickstart $DOMAIN/$LABEL"
echo "Remove:     bash local/install_mac.sh --remove"
