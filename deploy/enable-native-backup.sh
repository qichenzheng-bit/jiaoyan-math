#!/usr/bin/env bash
# Admin-only installation; no login or production service restart.
set -euo pipefail
umask 077
[[ $(id -u) == 0 ]] || { echo "Run as root"; exit 1; }
src="$(cd -- "$(dirname -- "$0")" && pwd)"
for name in age flock python3 runuser; do command -v "$name" >/dev/null; done
recipient=$(runuser -u jiaoyan -- python3 -c 'import json; from pathlib import Path; print(json.loads((Path.home()/"jiaoyan-app/config/backup.json").read_text())["recipient"])')
[[ "$recipient" =~ ^age1[0-9a-z]{20,100}$ ]] || exit 1
group=$(id -gn jiaoyan)
base=/var/lib/jiaoyan-native-backup
[[ ! -L "$base" && ! -L /opt/jiaoyan-qoder ]] || exit 1
install -d -m 0750 -o root -g "$group" "$base"
install -m 0644 -o root -g root "$src/snapshot-native-state.py" /opt/jiaoyan-qoder/
install -m 0755 -o root -g root "$src/publish-native-snapshot.sh" /opt/jiaoyan-qoder/
# If the recipient changes, refuse to label an old archive with the new key.
if [[ -f "$base/recipient" && "$(cat "$base/recipient")" != "$recipient" ]]; then
  echo "Native backup recipient changed; administrator must verify key rotation before continuing."; exit 1
fi
printf '%s\n' "$recipient" >/opt/jiaoyan-qoder/native-backup-recipient
chmod 0600 /opt/jiaoyan-qoder/native-backup-recipient
printf '%s\n' "$recipient" >"$base/recipient"
chown root:"$group" "$base/recipient"; chmod 0640 "$base/recipient"
install -m 0644 -o root -g root "$src/jiaoyan-native-backup.service" /etc/systemd/system/
install -m 0644 -o root -g root "$src/jiaoyan-native-backup.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl start jiaoyan-native-backup.service
systemctl enable --now jiaoyan-native-backup.timer
systemctl list-timers jiaoyan-native-backup.timer --no-pager
