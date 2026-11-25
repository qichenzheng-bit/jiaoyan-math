#!/usr/bin/env bash
# Trusted main only. Tests never source production configuration or use its DB.
set -euo pipefail
umask 077
[[ "$(id -un)" == jiaoyan && "$(id -u)" != 0 ]] || { echo "Requires the existing non-root jiaoyan runner"; exit 1; }
root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"
scratch=$(mktemp -d /tmp/jy-ci.XXXXXX)
pgbin=$(pg_config --bindir 2>/dev/null || true)
if [[ -z "$pgbin" || ! -x "$pgbin/initdb" ]]; then
  pgbin=$(find /usr/lib/postgresql -path '*/bin/initdb' -type f 2>/dev/null | sort -V | tail -n1 | xargs -r dirname)
fi
pg_started=0
preview_pid=
cleanup(){
  if [[ -n "$preview_pid" ]]; then kill "$preview_pid" 2>/dev/null || true; wait "$preview_pid" 2>/dev/null || true; fi
  if [[ "$pg_started" == 1 ]]; then "$pgbin/pg_ctl" -D "$scratch/pg" -m fast -w stop >/dev/null 2>&1 || return; fi
  rm -rf -- "$scratch"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
[[ -n "$pgbin" && -x "$pgbin/initdb" && -x "$pgbin/pg_ctl" ]] || { echo "PostgreSQL server binaries unavailable"; exit 1; }
mkdir "$scratch/socket" "$scratch/files"
"$pgbin/initdb" -D "$scratch/pg" --username=jiaoyan_ci --auth=trust --no-locale --encoding=UTF8 >/dev/null
# Private Unix socket only; never expose the test database via TCP.
"$pgbin/pg_ctl" -D "$scratch/pg" -l "$scratch/postgres.log" -o "-c listen_addresses='' -c unix_socket_directories=$scratch/socket -c port=55432 -c shared_buffers=32MB -c max_connections=15" -w start
pg_started=1
"$pgbin/createdb" -h "$scratch/socket" -p 55432 -U jiaoyan_ci jiaoyan_ci
python3 -m venv "$scratch/venv"
py="$scratch/venv/bin/python"
"$py" -m pip install -r "$root/backend/requirements-dev.txt"
echo "=== Isolated backend $(python3 --version) ==="
(
  cd "$root/backend"
  # Explicit connection and storage, no production env or real engine token.
  env -u VIDEO_ENGINE_TOKEN -u VIDEO_ENGINE_PORT \
    DATABASE_URL="postgresql+psycopg://jiaoyan_ci@/jiaoyan_ci?host=$scratch/socket&port=55432" \
    RUN_POSTGRES_INTEGRATION=1 APP_ORIGIN=https://testserver COOKIE_SECURE=true \
    STORAGE_ROOT="$scratch/files" JIAOYAN_CI_ISOLATION=1 \
    "$py" -m pytest -q
)
"$pgbin/pg_ctl" -D "$scratch/pg" -m fast -w stop
pg_started=0
echo "=== Frontend build ==="
(cd "$root/frontend" && npm install --no-audit --no-fund && npm run build)
echo "=== Browser acceptance (synthetic API fixtures) ==="
"$py" -m pip install playwright
export PLAYWRIGHT_BROWSERS_PATH="$HOME/.cache/jiaoyan-ci-playwright"
"$py" -m playwright install chromium
# Browser dependencies are installed by administrator if required. Runner never uses sudo.
"$py" - <<'PY'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    browser.close()
PY
rm -rf -- "$root/ui-screenshots"
# Use the installed executable directly so the trap terminates the preview server.
(cd "$root/frontend" && exec node node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port 4173 --strictPort) >"$scratch/preview.log" 2>&1 &
preview_pid=$!
for _ in $(seq 1 30); do
  kill -0 "$preview_pid" || { cat "$scratch/preview.log"; exit 1; }
  if curl -fsS --max-time 2 http://127.0.0.1:4173/ >/dev/null; then break; fi
  sleep 1
done
kill -0 "$preview_pid"
curl -fsS --max-time 2 http://127.0.0.1:4173/ >/dev/null
"$py" "$root/tests/ui_preview.py"
echo "All isolated server checks passed."
