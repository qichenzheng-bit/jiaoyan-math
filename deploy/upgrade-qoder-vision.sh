#!/usr/bin/env bash
# Run as administrator only from the trusted deployed release.
set -euo pipefail
[[ $(id -u) == 0 ]] || { echo "Run with sudo from the trusted release"; exit 1; }
src="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/qoder_worker.py"
dest=/opt/jiaoyan-qoder/qoder_worker.py
[[ -f "$dest" && ! -L "$dest" ]] || { echo "Qoder worker not installed"; exit 1; }
python3 - "$src" <<'PY'
import ast,sys
from pathlib import Path
source=Path(sys.argv[1]).read_text()
ast.parse(source)
assert '"/vision/start"' in source and 'vision_attachment' in source
PY
status() { curl -fsS --max-time 5 --unix-socket /run/jiaoyan-qoder/worker.sock http://localhost/status; }
status | python3 -c 'import json,sys; s=json.load(sys.stdin); assert not s.get("busy") and s.get("login",{}).get("state") not in ("starting","waiting"), "QODER_BUSY"'
backup=$(mktemp /opt/jiaoyan-qoder/.worker-backup.XXXXXX)
cp -p -- "$dest" "$backup"
trap 'rm -f -- "$backup"' EXIT
rollback() {
  install -m 644 -o root -g root "$backup" "$dest"
  systemctl restart jiaoyan-qoder.service
  echo "Previous worker restored." >&2
  exit 1
}
install -m 644 -o root -g root "$src" "$dest" || rollback
systemctl restart jiaoyan-qoder.service || rollback
for _ in $(seq 1 20); do
  if status 2>/dev/null | python3 -c 'import json,sys; s=json.load(sys.stdin); assert s.get("vision_attachment") and s.get("worker_version",0)>=13' 2>/dev/null; then
    echo "QODER_VISION_INTERFACE_READY (real model recognition still needs testing)"
    exit 0
  fi
  sleep 1
done
rollback
