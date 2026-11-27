#!/usr/bin/env bash
# Only the administrator can change the actual Nginx and system-wide video service.
set -euo pipefail
[[ $(id -u) == 0 ]] || { echo "Run as root"; exit 1; }
here="$(cd "$(dirname "$0")" && pwd)"
site=""
if [[ $# == 1 ]]; then
  site="$1"
else
  declare -A candidates=()
  shopt -s nullglob
  for file in /etc/nginx/sites-enabled/* /etc/nginx/conf.d/*.conf; do
    [[ -f "$file" ]] || continue
    if grep -Eq 'proxy_pass[[:space:]]+http://127\.0\.0\.1:8765;' "$file" &&
       grep -Eq '^[[:space:]]*client_max_body_size[[:space:]]+(20|200)m;' "$file"; then
      candidates["$(realpath "$file")"]=1
    fi
  done
  [[ ${#candidates[@]} == 1 ]] || { echo "Jiaoyan HTTPS site could not be uniquely detected; pass its exact config as the only argument."; exit 1; }
  for file in "${!candidates[@]}"; do site="$file"; done
fi
bash "$here/upgrade-upload-limit.sh" "$site"
bash "$here/install-video-backup.sh"
uid=$(id -u jiaoyan)
runuser -u jiaoyan -- env XDG_RUNTIME_DIR="/run/user/$uid" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$uid/bus" systemctl --user start --no-block jiaoyan-backup.service
echo "V1 activation requested. Verify repository backup and video coverage in System Settings."
