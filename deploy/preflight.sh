#!/usr/bin/env bash
# Read-only diagnostic; does not print secrets, install packages or modify services.
set -euo pipefail
[[ $(id -un) == jiaoyan && $(id -u) -ne 0 ]] || { echo "FAIL: runner must use non-root jiaoyan account"; exit 1; }
report() {
  if "$@" >/dev/null 2>&1; then printf 'OK: %s\n' "$label"; else printf 'PENDING: %s\n' "$label"; fi
}
printf 'Runner account: %s\n' "$(id -un)"
printf 'Architecture: %s\n' "$(uname -m)"
printf 'Disk free (MiB): %s\n' "$(df -Pm "$HOME" | awk 'END {print $4}')"
for tool in python3 psql pg_dump pg_restore nginx curl rsync flock tar; do
  label="command $tool"; report command -v "$tool"
done
base="$HOME/jiaoyan-app"
label="Python virtual environment support"; report python3 -c 'import venv'
label="server environment file"; report test -r "$base/config/app.env"
label="persistent file directory"; report test -w "$base/data/files"
label="backup directory"; report test -w "$base/backups"
label="PostgreSQL local peer connection"; report timeout 5 psql -X -w -d jiaoyan -tAc 'SELECT 1'
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
label="systemd user manager"; report systemctl --user show-environment
label="application service enabled"; report systemctl --user is-enabled --quiet jiaoyan.service
label="application service active"; report systemctl --user is-active --quiet jiaoyan.service
label="local application health"; report curl -fsS --max-time 3 http://127.0.0.1:8765/api/health
label="local application readiness"; report curl -fsS --max-time 3 http://127.0.0.1:8765/api/ready
echo "PENDING entries require configuration or inspection. This workflow does not deploy."

label="pinned video source delivered"; report test -f "$base/current/video-engine-source/SOURCE_REVISION"
label="independent video service active"; report systemctl is-active --quiet jiaoyan-video.service
