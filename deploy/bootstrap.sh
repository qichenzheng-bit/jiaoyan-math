#!/usr/bin/env bash
# Run once from a trusted checkout as root. No sudo permissions are granted to the runner.
set -euo pipefail
umask 077
[[ $(id -u) -eq 0 ]] || { echo "Run with sudo"; exit 1; }
id jiaoyan >/dev/null
origin=${1:-}
[[ "$origin" =~ ^https://[a-zA-Z0-9.-]+(:[0-9]+)?$ ]] || { echo "Usage: sudo bash deploy/bootstrap.sh https://your-domain"; exit 1; }
home_dir=$(getent passwd jiaoyan | cut -d: -f6)
base="$home_dir/jiaoyan-app"
[[ ! -e "$base/config/app.env" ]] || { echo "Existing configuration: refusing to overwrite"; exit 1; }
apt-get update
apt-get install -y postgresql postgresql-client python3 python3-venv nginx curl rsync
systemctl enable --now postgresql
runuser -u postgres -- psql -v ON_ERROR_STOP=1 -tAc "SELECT 1 FROM pg_roles WHERE rolname='jiaoyan'" | grep -qx 1 || runuser -u postgres -- createuser --no-superuser --no-createdb --no-createrole jiaoyan
runuser -u postgres -- psql -v ON_ERROR_STOP=1 -tAc "SELECT 1 FROM pg_database WHERE datname='jiaoyan'" | grep -qx 1 || runuser -u postgres -- createdb -O jiaoyan jiaoyan
install -d -m 0700 -o jiaoyan -g "$(id -gn jiaoyan)" "$base" "$base/config" "$base/data" "$base/data/files" "$base/releases" "$base/backups"
printf 'DATABASE_URL=postgresql+psycopg:///jiaoyan\nAPP_ORIGIN=%s\nCOOKIE_SECURE=true\nSTORAGE_ROOT=%s/data/files\n' "$origin" "$base" > "$base/config/app.env"
chown jiaoyan:"$(id -gn jiaoyan)" "$base/config/app.env"
install -d -m 0755 -o jiaoyan -g "$(id -gn jiaoyan)" "$home_dir/.config" "$home_dir/.config/systemd" "$home_dir/.config/systemd/user"
install -m 0644 -o jiaoyan -g "$(id -gn jiaoyan)" "$(dirname "$0")/jiaoyan.service" "$home_dir/.config/systemd/user/jiaoyan.service"
loginctl enable-linger jiaoyan
uid=$(id -u jiaoyan)
systemctl start "user@$uid.service"
runuser -u jiaoyan -- env XDG_RUNTIME_DIR="/run/user/$uid" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$uid/bus" systemctl --user daemon-reload
runuser -u jiaoyan -- env XDG_RUNTIME_DIR="/run/user/$uid" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$uid/bus" systemctl --user enable jiaoyan.service
echo "Bootstrap complete. Configure TLS/Nginx separately, enable deployment, then initialize admin."
