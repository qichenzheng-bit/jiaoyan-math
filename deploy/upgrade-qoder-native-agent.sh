#!/usr/bin/env bash
# Administrator-only upgrade of the independently installed Qoder worker for native Agent pilot.
# Run from a trusted, reviewed checkout, not an untrusted PR or runner job.
set -euo pipefail
[[ $(id -u) == 0 ]] || { echo "Run with sudo from a trusted checkout"; exit 1; }
src="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/qoder_worker.py"
dest=/opt/jiaoyan-qoder/qoder_worker.py
[[ -f "$dest" && ! -L "$dest" ]] || { echo "Qoder worker is not installed"; exit 1; }
systemctl is-active --quiet jiaoyan-qoder.service
# No access to or modification of the existing CLI login files.
python3 - "$src" <<'PY'
import ast,sys
from pathlib import Path
source=Path(sys.argv[1]).read_text()
ast.parse(source)
assert '"/agent/start"' in source and 'native_agent' in source
PY
sdk=/opt/jiaoyan-qoder/sdk-venv/bin/python
if ! "$sdk" -c 'from qodercn_agent_sdk import QoderSDKClient, QoderAgentOptions, qodercli_auth, tool, create_sdk_mcp_server, ResultMessage, SystemMessage, AgentDefinition, AssistantMessage, TextBlock; from mcp.types import ToolAnnotations; import inspect; assert callable(getattr(QoderSDKClient,"receive_response",None)); assert "session_store" in inspect.signature(QoderAgentOptions).parameters' 2>/dev/null; then
  echo "Install or upgrade the official qodercn-agent-sdk in /opt/jiaoyan-qoder/sdk-venv first; no login changes are required."
  exit 1
fi
status() {
  curl --silent --show-error --fail --max-time 5 --unix-socket /run/jiaoyan-qoder/worker.sock http://localhost/status
}
status | python3 -c 'import json,sys; s=json.load(sys.stdin); assert not s.get("busy") and s.get("login",{}).get("state") not in ("starting","waiting"), "QODER_BUSY"'
backup=$(mktemp /opt/jiaoyan-qoder/.worker-backup.XXXXXX)
cp -p -- "$dest" "$backup"
cleanup() { rm -f -- "$backup"; }
trap cleanup EXIT
rollback() {
  install -m 644 -o root -g root "$backup" "$dest"
  systemctl restart jiaoyan-qoder.service
  echo "Worker upgrade failed; previous worker restored." >&2
  exit 1
}
install -m 644 -o root -g root "$src" "$dest" || rollback
systemctl restart jiaoyan-qoder.service || rollback
for _ in $(seq 1 20); do
  if status 2>/dev/null | python3 -c 'import json,sys; s=json.load(sys.stdin); assert s.get("native_agent") and s.get("worker_version",0)>=22' 2>/dev/null; then
    echo "QODER_NATIVE_AGENT_READY (live SDK/MCP/vision smoke tests still required)"
    exit 0
  fi
  sleep 1
done
rollback
