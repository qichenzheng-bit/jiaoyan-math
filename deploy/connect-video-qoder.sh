#!/usr/bin/env bash
# Explicit administrator step. No credentials are copied between service accounts.
set -euo pipefail
[[ $(id -u) == 0 ]] || { echo "Run as root"; exit 1; }
base="$(getent passwd jiaoyan | cut -d: -f6)/jiaoyan-app"
release="$(readlink -f "$base/current")"
test -f "$release/deploy/video_qoder_adapter.py"
test -f "$release/deploy/qoder_worker.py"
test -f /opt/jiaoyan-video/runtime-fec8a4f/SOURCE_REVISION
systemctl is-active --quiet jiaoyan-video
# Check shared Qoder is idle before restarting its worker.
python3 - <<'PY'
import http.client,json,socket
class C(http.client.HTTPConnection):
    def connect(self):
        self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.sock.settimeout(5)
        self.sock.connect("/run/jiaoyan-qoder/worker.sock")
c=C("localhost")
c.request("GET","/status")
r=c.getresponse()
s=json.loads(r.read())
if r.status!=200 or not s.get("available"):
    raise SystemExit("QODER_NOT_READY")
if s.get("login",{}).get("state") in ("starting","waiting") or s.get("busy"):
    raise SystemExit("QODER_BUSY")
PY
install -m 644 -o root -g root "$release/deploy/video_qoder_adapter.py" /opt/jiaoyan-video/runtime-fec8a4f/video_qoder_adapter.py
install -m 644 -o root -g root "$release/deploy/qoder_worker.py" /opt/jiaoyan-qoder/qoder_worker.py
install -d -m 755 /etc/systemd/system/jiaoyan-video.service.d
cat > /etc/systemd/system/jiaoyan-video.service.d/qoder.conf <<'CONF'
[Unit]
After=jiaoyan-qoder.service
Requires=jiaoyan-qoder.service

[Service]
SupplementaryGroups=jiaoyan
ExecStart=
ExecStart=/opt/jiaoyan-video/venv/bin/python -m uvicorn video_qoder_adapter:create_app --factory --host 127.0.0.1 --port 8766
CONF
systemctl daemon-reload
systemctl restart jiaoyan-qoder
systemctl restart jiaoyan-video
for n in $(seq 1 20); do
  if curl -fsS --max-time 2 http://127.0.0.1:8766/health >/dev/null; then
    echo "VIDEO_QODER_READY"
    exit 0
  fi
  sleep 1
done
systemctl status jiaoyan-video --no-pager -l || true
exit 1
