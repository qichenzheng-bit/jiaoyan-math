#!/usr/bin/env bash
# Executed only by the dedicated, non-root repository runner after CI.
set -euo pipefail
umask 077
[[ $(id -un) == jiaoyan ]] || { echo "Wrong deployment account"; exit 1; }
base="$HOME/jiaoyan-app"
[[ -f "$base/config/app.env" && -d "$base/releases" && -d "$base/backups" ]] || { echo "Server not provisioned; run bootstrap first"; exit 1; }
sha=${GITHUB_SHA:-}
[[ "$sha" =~ ^[0-9a-f]{40}$ ]] || { echo "Invalid release SHA"; exit 1; }
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
exec 9>"$base/deploy.lock"
flock -w 600 9 || { echo "Deployment busy"; exit 1; }
# Owner requested no local deployment backups. Never touch live data.
[[ -d "$base/backups" && ! -L "$base/backups" && "$(realpath "$base/backups")" == "$(realpath "$base")/backups" ]] || { echo "Unexpected backup directory"; exit 1; }
find "$base/backups" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
release="$base/releases/$sha-$(date +%s)"
mkdir "$release"
rsync -a --exclude=.git --exclude=node_modules --exclude=.venv --exclude=.env --exclude=data/ ./ "$release/"
printf '%s\n' "$sha" > "$release/RELEASE_SHA"
# Source delivery only: the non-root runner never installs privileged video services.
bash "$release/deploy/unpack-video-source.sh" "$release/video-engine-source"
# Cache completed dependency environments by Python version and requirements.
# The deployment lock above protects creation; existing environments are not modified.
dep_root="$base/dependency-envs"
mkdir -p "$dep_root"
[[ -d "$dep_root" && ! -L "$dep_root" ]] || { echo "Unexpected dependency cache"; exit 1; }
dep_key=$({
  printf '%s\n' 'jiaoyan-venv-v1'
  python3 -c 'import sys, sysconfig; print(sys.version, sys.executable, sysconfig.get_platform())'
  sha256sum < "$release/backend/requirements.txt"
} | sha256sum | cut -d' ' -f1)
[[ "$dep_key" =~ ^[0-9a-f]{64}$ ]] || { echo "Invalid dependency key"; exit 1; }
dep_link="$dep_root/$dep_key"
if [[ -L "$dep_link" ]]; then
  dep_env=$(readlink -f "$dep_link")
  [[ "$dep_env" == "$dep_root/env-$dep_key-"* && -f "$dep_env/.complete" && -x "$dep_env/bin/python" ]] || { echo "Invalid cached dependency environment"; exit 1; }
  echo "Reusing dependency environment: $dep_key"
  "$dep_env/bin/python" -m pip check
else
  [[ ! -e "$dep_link" ]] || { echo "Unexpected dependency cache entry"; exit 1; }
  dep_env=$(mktemp -d "$dep_root/env-$dep_key-XXXXXX")
  python3 -m venv "$dep_env"
  "$dep_env/bin/python" -m pip install --disable-pip-version-check -r "$release/backend/requirements.txt"
  "$dep_env/bin/python" -m pip check
  touch "$dep_env/.complete"
  ln -sT "$dep_env" "$dep_link"
fi
ln -sT "$dep_env" "$release/venv"
if [[ "${JIAOYAN_PREBUILT_FRONTEND:-0}" == 1 ]]; then
  python3 -c 'import sys; assert sys.version_info[:2] == (3, 10), "Production Python differs from CI"'
  test -s "$release/frontend/dist/index.html"
  test "$(cat "$release/frontend/dist/release-sha.txt")" = "$sha"
  echo "Using the exact frontend tested in CI."
else
  (cd "$release/frontend" && npm install --prefer-offline --no-audit --no-fund && npm run build)
fi
set -a
# File is provisioned by the administrator; never source repository .env.
source "$base/config/app.env"
set +a
old=$(readlink -f "$base/current" || true)
[[ -d "$old/backend" ]] || old=""
switch_to() {
  local link="$base/.current-$sha-$"
  ln -s "$1" "$link" && mv -Tf "$link" "$base/current"
}
# Check the schema before stopping service. No local deployment archive is retained.
before=$(psql -X -d jiaoyan -tAc "SELECT to_regclass('public.alembic_version')" )
if [[ -n "$before" ]]; then before=$(psql -X -d jiaoyan -tAc 'SELECT version_num FROM alembic_version'); fi
# Once configured, verify an encrypted remote backup before a schema change.
if [[ -n "$before" && -f "$base/config/backup.json" ]]; then
  target_heads=$(cd "$release/backend" && "$release/venv/bin/python" -m alembic heads | awk '{print $1}')
  if [[ "$before" != "$target_heads" ]]; then
    test -f "$old/deploy/backup.py" || { echo "Enable and verify backup service before migrating"; exit 1; }
    "$old/venv/bin/python" "$old/deploy/backup.py" backup
  fi
fi
systemctl --user stop jiaoyan.service
migrated=false
if (cd "$release/backend" && "$release/venv/bin/python" -m alembic upgrade head); then
  migrated=true
  if switch_to "$release" && systemctl --user start jiaoyan.service; then
    for _ in $(seq 1 20); do
      if curl -fsS --max-time 2 http://127.0.0.1:8765/api/health >/dev/null && curl -fsS --max-time 2 http://127.0.0.1:8765/ >/dev/null; then
        # First deployment deliberately permits admin initialization after migration.
        admins=$(psql -X -d jiaoyan -tAc 'SELECT count(*) FROM users WHERE id=1')
        if [[ "$admins" == 0 ]] || curl -fsS --max-time 2 http://127.0.0.1:8765/api/ready >/dev/null; then
          printf '%s\n' "$sha" > "$base/deployed-sha"
          echo "Local release health checks passed. HTTPS and browser acceptance remain separate."
          exit 0
        fi
      fi
      sleep 2
    done
  fi
fi
systemctl --user stop jiaoyan.service
after=$(psql -X -d jiaoyan -tAc "SELECT to_regclass('public.alembic_version')" )
if [[ -n "$after" ]]; then after=$(psql -X -d jiaoyan -tAc 'SELECT version_num FROM alembic_version'); fi
if [[ -n "$old" && "$before" == "$after" ]]; then
  switch_to "$old"
  systemctl --user start jiaoyan.service
  echo "Previous release restarted; verify its health."
else
  echo "Schema changed or no prior release; service remains stopped. No local deployment backup exists; administrator must review recovery options."
fi
echo "Deployment failed. Automatic backups disabled; migration command completed: $migrated"
exit 1
