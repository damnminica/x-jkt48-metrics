"""Web dashboard Instagram JKT48 (Flask + scheduler). Satu service Railway.

- Dashboard di /  ·  data di /ig_data.json
- Scheduler menarik snapshot og-tag/crawler tiap 00:00 WIB (follower EKSAK + post),
  menyimpan ke SNAP_DIR, lalu membangun ulang ig_data.json.
- /refresh?key=REFRESH_KEY untuk tarik manual.
- Boot: seed snapshot dari repo bila volume kosong, lalu rebuild ig_data.json.

Env: DATA_DIR (volume persist; default = folder repo), REFRESH_KEY,
     FETCH_ENABLED=0 (hanya menyajikan, tak menarik), IG_PAUSE (jeda antar-akun detik).
"""
import logging
import os
import shutil
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import aggregate_ig  # noqa: E402
import ig_fetch  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("ig-app")
WIB = timezone(timedelta(hours=7))

DATA = Path(os.environ.get("DATA_DIR", HERE))
SNAP = Path(os.environ.get("IG_SNAP_DIR", DATA / "snapshots"))
DATA_JSON = Path(os.environ.get("IG_DATA_OUT", DATA / "ig_data.json"))
REFRESH_KEY = os.environ.get("REFRESH_KEY", "")
FETCH_ENABLED = os.environ.get("FETCH_ENABLED", "1") != "0"
PAUSE = float(os.environ.get("IG_PAUSE", "1.2"))

app = Flask(__name__)
_lock = threading.Lock()


def seed_snapshots():
    SNAP.mkdir(parents=True, exist_ok=True)
    if not any(SNAP.glob("ig_*.csv")):
        repo = HERE / "snapshots"
        if repo.exists():
            for p in repo.glob("ig_*.csv"):
                shutil.copy(p, SNAP / p.name)
            log.info("Seed %d snapshot dari repo", len(list(SNAP.glob('ig_*.csv'))))


def rebuild():
    try:
        aggregate_ig.build(snap_dir=SNAP, out=DATA_JSON)
    except SystemExit as e:
        log.warning("rebuild dilewati: %s", e)


def do_fetch():
    with _lock:
        date = datetime.now(WIB).strftime("%Y-%m-%d")
        log.info("Mulai tarik IG %s", date)
        ig_fetch.run(date=date, out_dir=SNAP, pause=PAUSE)
        rebuild()
        log.info("Selesai tarik IG %s", date)


@app.route("/")
def index():
    return send_from_directory(HERE, "dashboard.html")


@app.route("/ig_data.json")
def data_json():
    if DATA_JSON.exists():
        return send_from_directory(DATA_JSON.parent, DATA_JSON.name, mimetype="application/json")
    return jsonify({"error": "belum ada data"}), 404


@app.route("/health")
def health():
    snaps = sorted(p.stem.replace("ig_", "") for p in SNAP.glob("ig_*.csv"))
    return jsonify({"ok": True, "snapshots": snaps, "data_json": DATA_JSON.exists(),
                    "fetch_enabled": FETCH_ENABLED})


@app.route("/refresh")
def refresh():
    if not REFRESH_KEY or request.args.get("key") != REFRESH_KEY:
        return jsonify({"error": "unauthorized"}), 403
    if not FETCH_ENABLED:
        return jsonify({"error": "fetch dimatikan"}), 400
    threading.Thread(target=do_fetch, daemon=True).start()
    return jsonify({"ok": True, "msg": "tarik IG dimulai di latar belakang"})


def start_scheduler():
    if not FETCH_ENABLED:
        log.info("FETCH_ENABLED=0 → scheduler tidak dijalankan")
        return
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
        sch = BackgroundScheduler(timezone="Asia/Jakarta")
        sch.add_job(do_fetch, CronTrigger(hour=0, minute=0), id="ig_daily",
                    misfire_grace_time=3600, coalesce=True)
        sch.start()
        log.info("Scheduler aktif: tarik IG tiap 00:00 WIB")
    except Exception as e:  # noqa: BLE001
        log.warning("Scheduler gagal start: %s", e)


# boot
seed_snapshots()
if not DATA_JSON.exists():
    rebuild()
start_scheduler()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
