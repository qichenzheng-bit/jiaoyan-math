#!/usr/bin/env bash
set -euo pipefail
umask 077
[[ $(id -un) == jiaoyan ]] || { echo "Run as jiaoyan"; exit 1; }
base="$HOME/jiaoyan-app"
for binary in age git ssh pg_dump psql flock; do command -v "$binary" >/dev/null || { echo "Missing: $binary"; exit 1; }; done
test -f "$base/config/backup.json"
test -f "$base/config/app.env"
test -x "$base/current/venv/bin/python"
install -d -m 0700 "$base/backup-state"
install -d -m 0755 "$HOME/.config/systemd/user"
install -m 0644 "$base/current/deploy/jiaoyan-backup.service" "$HOME/.config/systemd/user/"
install -m 0644 "$base/current/deploy/jiaoyan-backup.timer" "$HOME/.config/systemd/user/"
systemctl --user daemon-reload
# Require a verified real backup before enabling the recurring timer.
systemctl --user start jiaoyan-backup.service
systemctl --user enable --now jiaoyan-backup.timer
systemctl --user list-timers jiaoyan-backup.timer --no-pager
