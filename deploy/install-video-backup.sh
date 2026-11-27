#!/usr/bin/env bash
# Run explicitly as administrator from a reviewed release; never grant sudo to the runner.
set -euo pipefail
[[ $(id -u) == 0 ]] || { echo "Run as root"; exit 1; }
here="$(cd "$(dirname "$0")" && pwd)"
test -x /opt/jiaoyan-video/venv/bin/python
test -f /etc/jiaoyan-video/engine.env
getent group jiaoyan >/dev/null
install -d -o jiaoyan-video -g jiaoyan -m 2750 /var/lib/jiaoyan-video-backup
if [[ ! -e /var/lib/jiaoyan-video-backup/publish.lock ]]; then
  install -o jiaoyan-video -g jiaoyan -m 0640 /dev/null /var/lib/jiaoyan-video-backup/publish.lock
fi
install -m 0755 -o root -g root "$here/video_backup_snapshot.py" /opt/jiaoyan-video/backup_snapshot.py
cat > /etc/systemd/system/jiaoyan-video-backup.service <<'UNIT'
[Unit]
Description=Isolated video business snapshot for encrypted repository backup
After=postgresql.service
[Service]
Type=oneshot
User=jiaoyan-video
Group=jiaoyan
SupplementaryGroups=jiaoyan-video
EnvironmentFile=/etc/jiaoyan-video/engine.env
Environment=WEIGUANG_STORAGE=/var/lib/jiaoyan-video
ExecStart=/opt/jiaoyan-video/venv/bin/python /opt/jiaoyan-video/backup_snapshot.py
UMask=0027
NoNewPrivileges=true
PrivateTmp=true
Nice=10
TimeoutStartSec=1800
UNIT
cat > /etc/systemd/system/jiaoyan-video-backup.timer <<'UNIT'
[Unit]
Description=Daily video snapshot before encrypted repository backup
[Timer]
OnCalendar=*-*-* 23:15:00 Asia/Shanghai
Persistent=true
Unit=jiaoyan-video-backup.service
[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
# A busy video engine must not be interrupted; retry this installation when idle.
systemctl start jiaoyan-video-backup.service
systemctl enable --now jiaoyan-video-backup.timer
echo "Video snapshot timer enabled; trigger the existing main repository backup from system settings."
