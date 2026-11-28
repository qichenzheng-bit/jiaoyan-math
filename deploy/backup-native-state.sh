#!/usr/bin/env bash
# Offline administrator backup of the native SDK mirror and app-scoped memory.
# Never includes ~/.qoder-cn, CLI authentication files or the login user's home.
set -euo pipefail
umask 077
[[ $(id -u) == 0 ]] || { echo "Run as root from the trusted deployment."; exit 1; }
[[ $# == 2 ]] || { echo "Usage: $0 AGE_PUBLIC_RECIPIENT OUTPUT.age"; exit 2; }
recipient=$1
output=$2
[[ "$recipient" =~ ^age1[0-9a-z]{20,100}$ && "$output" == *.age ]] || { echo "Invalid public recipient or output suffix."; exit 2; }
[[ "$(systemctl show -p ActiveState --value jiaoyan-qoder.service)" == inactive ]] || { echo "Stop jiaoyan-qoder.service before backup; it must remain stopped until backup ends."; exit 1; }
worker_user=$(systemctl show -p User --value jiaoyan-qoder.service)
[[ -n "$worker_user" && "$worker_user" != root ]] || { echo "Cannot determine isolated Worker user."; exit 1; }
worker_home=$(getent passwd "$worker_user" | cut -d: -f6)
[[ -n "$worker_home" && "$worker_home" == /* && "$worker_home" != / ]] || exit 1
command -v age >/dev/null
[[ ! -e "$output" && ! -L "$output" ]] || { echo "Output already exists; refusing overwrite."; exit 1; }
tmp=$(mktemp -- "$(dirname -- "$output")/.native-state.XXXXXX")
trap 'rm -f -- "$tmp"' EXIT
paths=()
for dir in .jiaoyan-native-workspaces .jiaoyan-native-memory; do
  [[ ! -L "$worker_home/$dir" ]] || { echo "Unexpected symlink in native state."; exit 1; }
  if [[ -d "$worker_home/$dir" ]]; then paths+=("$dir"); fi
done
(("${#paths[@]}")) || { echo "No native state exists yet."; exit 1; }
# Refuse symlinks, non-regular files and multiply linked files. Do not traverse other home directories.
for dir in "${paths[@]}"; do
  [[ -z "$(runuser -u "$worker_user" -- find "$worker_home/$dir" \( ! -type d ! -type f -o -type f -links +1 \) -print -quit)" ]] || { echo "Unexpected link or special file."; exit 1; }
done
runuser -u "$worker_user" -- tar --format=pax -C "$worker_home" -czf - -- "${paths[@]}" | age -r "$recipient" > "$tmp"
[[ "$(systemctl show -p ActiveState --value jiaoyan-qoder.service)" == inactive ]] || { echo "Worker became active during backup; discarding snapshot."; exit 1; }
[[ -s "$tmp" ]] || exit 1
# Hardlink creation fails atomically if output already exists.
ln -- "$tmp" "$output"
echo "NATIVE_STATE_BACKUP_CREATED (encrypted; restore verification still required)"
