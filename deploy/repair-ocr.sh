#!/usr/bin/env bash
# One-time repair for an already provisioned Debian/Ubuntu host.
# Run as root; this does not alter application data or deployment configuration.
set -euo pipefail
umask 022
[[ "$(id -u)" -eq 0 ]] || { echo "Run with sudo: sudo bash deploy/repair-ocr.sh"; exit 1; }
command -v apt-get >/dev/null || { echo "This repair script requires Debian/Ubuntu apt-get."; exit 1; }
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends util-linux tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-eng poppler-utils
for tool in prlimit tesseract pdftotext pdftoppm; do
  command -v "$tool" >/dev/null || { echo "Missing executable after installation: $tool"; exit 1; }
done
languages="$(tesseract --list-langs 2>/dev/null)"
for language in chi_sim eng; do
  grep -qx "$language" <<<"$languages" || { echo "Tesseract language data is still missing: $language"; exit 1; }
done
if id jiaoyan >/dev/null 2>&1; then
  runuser -u jiaoyan -- bash -c 'tesseract --list-langs 2>/dev/null | grep -qx chi_sim && tesseract --list-langs 2>/dev/null | grep -qx eng'
fi
echo "OCR environment is ready: prlimit, Tesseract chi_sim+eng, pdftotext and pdftoppm."
echo "No application restart is required; OCR capabilities are checked on each request."
