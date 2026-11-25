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
python3 -m venv "$release/venv"
"$release/venv/bin/python" -m pip install -r "$release/backend/requirements.txt"
(cd "$release/frontend" && npm install --no-audit --no-fund && npm run build && rm -rf node_modules)
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
# Validate DB connectivity and schema before stopping service. No database or
# user-file snapshot is created, as requested by the administrator.
before=$(psql -X -d jiaoyan -tAc "SELECT to_regclass('public.alembic_version')" )
if [[ -n "$before" ]]; then before=$(psql -X -d jiaoyan -tAc 'SELECT version_num FROM alembic_version'); fi
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
