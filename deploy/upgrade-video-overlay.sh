#!/usr/bin/env bash
# Explicit administrator action after main release. Only replace source files,
# not venv, databases, data, systemd credentials, or user video artifacts.
set -euo pipefail
umask 077
[[ $(id -u) == 0 ]] || { echo "Run as root"; exit 1; }
mode="${1:---check}"
[[ "$mode" == --check || "$mode" == --apply ]] || { echo "usage: $0 [--check|--apply]"; exit 1; }
base="$(getent passwd jiaoyan | cut -d: -f6)/jiaoyan-app"
release="$(readlink -f "$base/current")"
runtime=/opt/jiaoyan-video/runtime-fec8a4f
python=/opt/jiaoyan-video/venv/bin/python
test -x "$python"
test "$(cat "$runtime/SOURCE_REVISION")" = fec8a4f8c21b829a8f043a2c3538aff4cc48ea08
test -d "$release/vendor/video-overlay"
exec 9>/run/jiaoyan-video-overlay-upgrade.lock
flock -n 9
stage=$(mktemp -d /opt/jiaoyan-video/overlay-check.XXXXXX)
trap 'rm -rf "$stage"' EXIT
bash "$release/deploy/unpack-video-source.sh" "$stage/source"
# Existing installed environment, explicitly select new staged modules.
# No credentials or live data passed to the check.
chmod 755 "$stage"
chmod -R a+rX "$stage/source"
install -m 644 "$release/deploy/video-engine-overlay-check.py" "$stage/check.py"
env PYTHONPATH="$stage/source/app/backend/src:$stage/source/app/animation_engine/src" "$python" -m compileall -q "$stage/source/app/backend/src" "$stage/source/app/animation_engine/src"
runuser -u jiaoyan-video -- env PYTHONPATH="$stage/source/app/backend/src:$stage/source/app/animation_engine/src" "$python" "$stage/check.py"
if [[ "$mode" == --check ]]; then echo VIDEO_OVERLAY_PRECHECK_PASSED; exit 0; fi
# Prevent racing live inference. Apply only during a user-confirmed idle window.
python3 - <<'PY'
import http.client,json,socket
class C(http.client.HTTPConnection):
    def connect(self):
        self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.sock.settimeout(5)
        self.sock.connect("/run/jiaoyan-qoder/worker.sock")
c=C("localhost");c.request("GET","/status");r=c.getresponse();s=json.loads(r.read())
if r.status!=200 or s.get("busy") or s.get("waiting_count") or s.get("login",{}).get("state") in ("starting","waiting"):
    raise SystemExit("QODER_BUSY_OR_UNAVAILABLE")
PY
# Explicitly require an idle engine: check DB using the existing service environment
# outside this script before applying; stop services gracefully here.
echo "Apply only after confirming no queued/running generation, render, or edit jobs."
test "${VIDEO_OVERLAY_IDLE_CONFIRMED:-}" = yes || { echo "Set VIDEO_OVERLAY_IDLE_CONFIRMED=yes after checking tasks"; exit 1; }
backup="$stage/rollback"
mkdir -p "$backup"
mapfile -t paths < <(cd "$release/vendor/video-overlay" && find . -type f -printf '%P\n' | LC_ALL=C sort)
for f in "${paths[@]}"; do
  [[ "$f" == app/backend/src/* || "$f" == app/animation_engine/src/* ]] || exit 1
  [[ ! -L "$runtime/$f" ]] || exit 1
  if [[ -f "$runtime/$f" ]]; then install -D -m 644 "$runtime/$f" "$backup/$f"; fi
done
install -m 644 "$runtime/video_qoder_adapter.py" "$backup/video_qoder_adapter.py"
install -m 644 /opt/jiaoyan-qoder/qoder_worker.py "$backup/qoder_worker.py"
rollback(){
  set +e
  systemctl stop jiaoyan-video jiaoyan-qoder
  for f in "${paths[@]}"; do
    if [[ -f "$backup/$f" ]]; then install -D -m 644 "$backup/$f" "$runtime/$f"; else rm -f "$runtime/$f"; fi
  done
  install -m 644 "$backup/video_qoder_adapter.py" "$runtime/video_qoder_adapter.py"
  install -m 644 "$backup/qoder_worker.py" /opt/jiaoyan-qoder/qoder_worker.py
  systemctl start jiaoyan-qoder
  systemctl start jiaoyan-video
  echo VIDEO_OVERLAY_ROLLED_BACK
}
trap 'rollback; rm -rf "$stage"' EXIT
systemctl stop jiaoyan-video
systemctl stop jiaoyan-qoder
for f in "${paths[@]}"; do install -D -m 644 "$stage/source/$f" "$runtime/$f"; done
install -m 644 "$release/deploy/video_qoder_adapter.py" "$runtime/video_qoder_adapter.py"
install -m 644 "$release/deploy/qoder_worker.py" /opt/jiaoyan-qoder/qoder_worker.py
systemctl start jiaoyan-qoder
systemctl start jiaoyan-video
ok=no
for n in $(seq 1 20); do
  if curl -fsS --max-time 2 http://127.0.0.1:8766/health >/dev/null; then ok=yes;break;fi
  sleep 1
done
[[ "$ok" == yes ]]
runuser -u jiaoyan-video -g jiaoyan-video -G jiaoyan -- env PYTHONPATH="$runtime:$runtime/app/backend/src:$runtime/app/animation_engine/src" "$python" -c "from video_qoder_adapter import target; assert target('qoder_cli')['installed']"
printf '%s\n' video-prompt-v1 > "$runtime/PROMPT_OVERLAY_REVISION"
trap 'rm -rf "$stage"' EXIT
echo VIDEO_OVERLAY_UPGRADE_PASSED
