#!/usr/bin/env bash
# Run explicitly as administrator from a trusted current release, with AI/video work idle.
# Install encrypted native backup; optionally enable/test SDK inference for video with rollback.
set -euo pipefail
umask 077
[[ $(id -u) == 0 ]] || { echo "Run as root"; exit 1; }
[[ $# == 0 || ($# == 1 && $1 == --video) ]] || { echo "Usage: $0 [--video]"; exit 2; }
base=/home/jiaoyan/jiaoyan-app
release=$(readlink -f "$base/current")
[[ "$release" == "$base/releases/"* ]] || { echo "Unexpected release"; exit 1; }
src="$release/deploy"
[[ "$(cd -- "$(dirname -- "$0")" && pwd)" == "$src" ]] || { echo "Run from current deployed release"; exit 1; }
userctl() {
  runuser -u jiaoyan -- env XDG_RUNTIME_DIR="/run/user/$(id -u jiaoyan)" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$(id -u jiaoyan)/bus" systemctl --user "$@"
}
worker_status() {
  curl --silent --show-error --fail --max-time 5 --unix-socket /run/jiaoyan-qoder/worker.sock http://localhost/status
}
check_idle() {
  worker_status | python3 -c 'import json,sys;s=json.load(sys.stdin);assert s.get("worker_version",0)>=23 and s.get("native_agent") and s.get("chat_available"),"QODER_NOT_READY";assert not s.get("busy") and not s.get("waiting_count") and s.get("login",{}).get("state") not in ("starting","waiting"),"QODER_BUSY"'
}
check_idle
bash "$src/enable-native-backup.sh"
# Publish the first actual encrypted archive through the already configured daily backup.
userctl start jiaoyan-backup.service
runuser -u jiaoyan -- python3 -c 'import json;from pathlib import Path;s=json.loads((Path.home()/"jiaoyan-app/backup-state/last-success.json").read_text());assert s.get("native_state")=="included","NATIVE_BACKUP_NOT_INCLUDED";print("NATIVE_BACKUP_PUBLISHED")'
if [[ $# == 0 ]]; then
  echo "BACKUP_SETUP_PASSED; video inference unchanged"
  exit 0
fi
# Video SDK is a separate switch. Do not alter prompts, renderer, TTS or the video database.
check_idle
dropdir=/etc/systemd/system/jiaoyan-qoder.service.d
drop="$dropdir/90-jiaoyan-native-video.conf"
install -d -m 0755 "$dropdir"
[[ ! -L "$drop" ]] || { echo "Unsafe video configuration"; exit 1; }
saved=$(mktemp /opt/jiaoyan-qoder/.native-video-config.XXXXXX)
had=0
if [[ -f "$drop" ]]; then cp -p -- "$drop" "$saved"; had=1; fi
ok=0
finish() {
  code=$?
  trap - EXIT
  if [[ "$ok" != 1 ]]; then
    if [[ "$had" == 1 ]]; then install -m 0644 -o root -g root "$saved" "$drop"; else rm -f -- "$drop"; fi
    systemctl daemon-reload
    systemctl restart jiaoyan-qoder.service || true
    echo "VIDEO_NATIVE_TEST_FAILED; prior worker configuration restored" >&2
  fi
  rm -f -- "$saved"
  exit "$code"
}
trap finish EXIT
printf '[Service]\nEnvironment=WG_NATIVE_VIDEO=1\n' > "$drop"
chmod 0644 "$drop"
systemctl daemon-reload
systemctl restart jiaoyan-qoder.service
ready=0
for _ in $(seq 1 20); do
  if worker_status 2>/dev/null | python3 -c 'import json,sys;s=json.load(sys.stdin);assert s.get("native_agent") and s.get("native_video") and not s.get("busy")' 2>/dev/null; then ready=1; break; fi
  sleep 1
done
[[ "$ready" == 1 ]]
runuser -u jiaoyan -- "$release/venv/bin/python" "$src/native-video-smoke.py" --model Auto
ok=1
echo "ADMIN_FINALIZATION_PASSED; native video inference enabled, real generation/render/edit acceptance still required"
