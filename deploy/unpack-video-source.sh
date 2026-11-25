#!/usr/bin/env bash
# Reconstruct the byte-verified private upstream archive without cross-repository credentials.
set -euo pipefail
umask 077
repo="$(cd "$(dirname "$0")/.." && pwd)"
bundle="$repo/vendor/video-engine"
test "$#" -eq 1
target="$1"
pinned=fec8a4f8c21b829a8f043a2c3538aff4cc48ea08
expected=29c3bb41d260e91b77d735e82996cb3122470f5eb364349c35bafe074ca7f497
[[ $(cat "$bundle/SOURCE_REVISION") == "$pinned" && $(cat "$bundle/SHA256") == "$expected" ]] || { echo "Video source manifest mismatch"; exit 1; }
[[ ! -e "$target" ]] || { echo "Refusing to overwrite existing video source"; exit 1; }
archive=$(mktemp)
trap 'rm -f "$archive"' EXIT
cat "$bundle"/part-{000,001,002,003,004} > "$archive"
printf '%s  %s\n' "$expected" "$archive" | sha256sum --check --status
mkdir -p "$target"
tar --extract --gzip --file="$archive" --directory="$target" --strip-components=1 --no-same-owner --no-same-permissions
test -f "$target/app/backend/src/weiguang_backend/main.py"
test -f "$target/app/animation_engine/src/animation_engine/code/scene_contract.py"
test -f "$target/app/backend/src/weiguang_backend/ai/prompts/manim_teacher.md"
test -f "$target/app/backend/src/weiguang_backend/ai/prompts/manim_editor.md"
printf '%s\n' "$pinned" > "$target/SOURCE_REVISION"
echo "Verified upstream video source: $pinned"
