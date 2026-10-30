#!/usr/bin/env bash
# Dijalankan di VPS dari folder ~/jkt48-x-metrics: buat venv, pasang dependensi, siapkan .env & unit systemd.
set -euo pipefail
cd "$(dirname "$0")/.."
if ! python3 -m venv --help >/dev/null 2>&1 || ! python3 -c "import ensurepip" 2>/dev/null; then
  sudo apt-get update -qq && sudo apt-get install -y -qq python3-venv
fi
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt
mkdir -p data
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Template .env dibuat; isi nilainya sebelum start."
fi
chmod 600 .env
sudo cp deploy/jkt48-x-worker.service /etc/systemd/system/jkt48-x-worker.service
sudo cp "deploy/jkt48-x-job@.service" "/etc/systemd/system/jkt48-x-job@.service"
sudo cp "deploy/jkt48-x-stress@.service" "/etc/systemd/system/jkt48-x-stress@.service"
sudo systemctl daemon-reload
.venv/bin/python -c "import twitter_cli, curl_cffi, openpyxl; print('dependensi OK')"
echo "Siap. Batch member: isi .env lalu sudo systemctl enable --now jkt48-x-worker"
echo "Job SSK: salin .env.job.example ke .env.job.<akun> (chmod 600), isi, lalu sudo systemctl enable --now jkt48-x-job@<akun>"
