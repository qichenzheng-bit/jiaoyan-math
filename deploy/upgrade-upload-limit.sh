#!/usr/bin/env bash
# Explicit administrator operation: select only the actual Jiaoyan HTTPS site config.
set -euo pipefail
[[ $(id -u) == 0 && $# == 1 ]] || { echo "Usage: sudo bash upgrade-upload-limit.sh /etc/nginx/sites-available/JIAOYAN_SITE"; exit 1; }
path="$(realpath "$1")"
[[ "$path" == /etc/nginx/* && -f "$path" ]] || { echo "Invalid site configuration"; exit 1; }
grep -Eq 'proxy_pass[[:space:]]+http://127\.0\.0\.1:8765;' "$path" || { echo "Not the Jiaoyan site"; exit 1; }
count=$(grep -Ec '^[[:space:]]*client_max_body_size[[:space:]]+20m;' "$path" || true)
if [[ "$count" == 0 ]] && grep -Eq '^[[:space:]]*client_max_body_size[[:space:]]+200m;' "$path"; then
  nginx -t
  systemctl reload nginx
  exit 0
fi
[[ "$count" == 1 ]] || { echo "Expected exactly one existing 20m directive; review site manually"; exit 1; }
tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT
cp -p "$path" "$tmp"
sed -i -E 's/^([[:space:]]*client_max_body_size[[:space:]]+)20m;/\1200m;/' "$path"
if ! nginx -t || ! systemctl reload nginx; then
  cat "$tmp" > "$path"
  nginx -t && systemctl reload nginx
  exit 1
fi
echo "Jiaoyan upload limit: 200 MiB"
