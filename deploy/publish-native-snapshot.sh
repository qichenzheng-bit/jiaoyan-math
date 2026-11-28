#!/usr/bin/env bash
# Installed root-owned by enable-native-backup.sh. Never returns plaintext.
set -euo pipefail
umask 077
[[ $(id -u) == 0 ]] || exit 1
worker=$(systemctl show -p User --value jiaoyan-qoder.service)
[[ -n "$worker" && "$worker" != root ]] || exit 1
home=$(getent passwd "$worker" | cut -d: -f6)
[[ "$home" == /* && "$home" != / ]] || exit 1
group=$(id -gn jiaoyan)
base=/var/lib/jiaoyan-native-backup
[[ -d "$base" && ! -L "$base" ]] || exit 1
recipient=$(cat /opt/jiaoyan-qoder/native-backup-recipient)
[[ "$recipient" =~ ^age1[0-9a-z]{20,100}$ ]] || exit 1
exec 9>"$base/.lock"
flock -n 9 || exit 1
tmp=$(mktemp "$base/.capture.XXXXXX")
trap 'rm -f -- "$tmp"' EXIT
runuser -u "$worker" -- env HOME="$home" python3 /opt/jiaoyan-qoder/snapshot-native-state.py --home "$home" --recipient "$recipient" > "$tmp"
[[ -s "$tmp" ]] || exit 1
chown root:"$group" "$tmp"; chmod 0640 "$tmp"
mv -Tf -- "$tmp" "$base/current.age"
echo "NATIVE_SNAPSHOT_PUBLISHED"
