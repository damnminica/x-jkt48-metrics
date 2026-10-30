"""Web dashboard harian JKT48 (Flask + scheduler). Satu service Railway.

- Menyajikan dashboard di / dan datanya di /data.json (dibaca dari DATA_DIR/daily_data.json).
- Scheduler menjalankan penarikan tiap 00:00 WIB: snapshot follower, tweet baru, mention hari kemarin,
  lalu memperbarui Google Sheets dan membangun ulang daily_data.json. Tombol /refresh?key=... untuk uji manual.
- Boot pertama: seed store member dari seed.tgz (data full1) supaya dashboard langsung tampil.

Env: DATA_DIR, lalu env X/Telegram/Proxy (lihat fetch). FETCH_ENABLED=0 untuk hanya menyajikan (tanpa narik X).
     REFRESH_KEY untuk /refresh. TZ scheduler = Asia/Jakarta.
"""
import logging
import os
import sys
import tarfile
import threading
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import worker as w  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
import aggregate as agg  # noqa: E402
import fetch_daily as fd  # noqa: E402
from sheets import Sheets  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("app")
WIB = timezone(timedelta(hours=7))
DATA = Path(os.environ.get("DATA_DIR", "/data"))
DAILY = DATA / "daily"
DATA_JSON = DATA / "daily_data.json"
SEED = Path(__file__).resolve().parent / "seed.tgz"
HERE = Path(__file__).resolve().parent
CUTOFF = os.environ.get("CUTOFF", "2025-10-22")
_lock = threading.Lock()

app = Flask(__name__)


def seed_if_empty():
    members = DAILY / "members"
    if members.exists() and any(p for p in members.glob("*_v2.json") if not p.name.startswith(".")):
        return
    if SEED.exists():
        log.info("Seed store member dari %s", SEED.name)
        members.mkdir(parents=True, exist_ok=True)
        with tarfile.open(SEED) as t:
            for mem in t.getmembers():
                base = Path(mem.name).name
                if mem.isfile() and base.endswith("_v2.json") and not base.startswith("."):
                    mem.name = Path(mem.name).name
                    t.extract(mem, members)


def rebuild():
    """Bangun ulang daily_data.json dari store + riwayat. Aman dipanggil kapan saja."""
    with _lock:
        agg.write(DATA, DATA_JSON, CUTOFF)
    log.info("daily_data.json diperbarui")


def run_fetch():
    """Penarikan harian untuk tanggal kemarin (WIB). Dipanggil scheduler / /refresh."""
    if os.environ.get("FETCH_ENABLED", "1") != "1":
        log.info("FETCH_ENABLED=0, lewati penarikan.")
        return
    missing = [k for k in w.REQUIRED_ENV if not os.environ.get(k)]
    if not os.environ.get("TWITTER_PROXY") and os.environ.get("ALLOW_DIRECT") != "1":
        missing.append("TWITTER_PROXY")
    if missing:
        log.warning("Env belum lengkap: %s; lewati penarikan.", ", ".join(missing))
        return
    if not _lock.acquire(blocking=False):
        log.warning("Penarikan lain masih jalan; lewati.")
        return
    try:
        from twitter_cli.client import TwitterClient
        roster = fd.load_roster()
        day = (datetime.now(WIB) - timedelta(days=1)).date()
        day_wib = datetime(day.year, day.month, day.day, tzinfo=WIB)
        proxy, ip = w.choose_proxy()
        if proxy:
            os.environ["TWITTER_PROXY"] = proxy
        client = TwitterClient(os.environ["TWITTER_AUTH_TOKEN"], os.environ["TWITTER_CT0"],
                               {"maxRetries": 0, "requestDelay": 0})
        pacer, guard = w.Pacer(w.REQ_PER_WINDOW), w.RateLimitGuard()

        def pace():
            pacer()
            guard.ok()

        def on_transient(attempt, wait, e):
            log.warning("gangguan (%s), tunggu %ss", e.status_code, wait)
            import time
            time.sleep(wait)

        w.notify(f"🌙 Mulai update harian {day_wib:%d %b %Y} WIB. Exit IP: {ip}. {w.now_wib()} WIB")
        sheets = Sheets()

        import time as _t
        _last_rebuild = [0.0]

        def on_member(i, h):
            # rebuild dashboard live tiap member; TANPA _lock (run_fetch sudah memegangnya di sini).
            if _t.monotonic() - _last_rebuild[0] < 8:  # kolaps burst saat member di-skip (restart)
                return
            try:
                agg.write(DATA, DATA_JSON, CUTOFF)
                _last_rebuild[0] = _t.monotonic()
            except Exception as e:
                log.warning("rebuild dashboard per-member gagal: %s", e)

        summ = fd.run_day(client, roster, day_wib, pace, guard, on_transient, sheets,
                          log=lambda s: log.info(s), on_member=on_member)
        _lock.release()
        rebuild()
        _snapshot_to_sheets(sheets)
        w.notify(f"✅ Update harian {summ['date']}: {summ['followers']} follower, {summ['mentions']} mention. "
                 f"{pacer.count} request. {w.now_wib()} WIB")
        return
    except Exception as e:
        traceback.print_exc()
        try:
            w.notify(f"🛑 Update harian gagal: {type(e).__name__}: {str(e)[:200]}. {w.now_wib()} WIB")
        except Exception:
            pass
    finally:
        if _lock.locked():
            _lock.release()


def _snapshot_to_sheets(sheets):
    import json
    if not DATA_JSON.exists():
        return
    d = json.loads(DATA_JSON.read_text())
    date_s = datetime.now(WIB).strftime("%Y-%m-%d")
    rows = [[date_s, m["rank"], m["handle"], m["nama"], m["tim"], m["followers"], m["post_utama"],
             m["med_views"], m["med_likes"], m["er"], m["views_per_1k_fol"]] for m in d["members"]]
    sheets.replace("members_snapshot",
                   ["date", "rank", "handle", "nama", "tim", "followers", "post_utama", "med_views",
                    "med_likes", "er", "views_per_1k_fol"], rows)


@app.route("/")
def index():
    return send_from_directory(HERE, "dashboard.html")


@app.route("/data.json")
def data_json():
    if not DATA_JSON.exists():
        rebuild()
    return Response(DATA_JSON.read_text(), mimetype="application/json")


@app.route("/refresh")
def refresh():
    key = os.environ.get("REFRESH_KEY", "")
    if not key or request.args.get("key") != key:
        return jsonify({"error": "key salah"}), 403
    threading.Thread(target=run_fetch, daemon=True).start()
    return jsonify({"ok": True, "msg": "penarikan harian dimulai di latar belakang"})


@app.route("/health")
def health():
    return jsonify({"ok": True, "data_exists": DATA_JSON.exists(), "at": w.now_wib()})


def start_scheduler():
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        sched = BackgroundScheduler(timezone="Asia/Jakarta")
        sched.add_job(run_fetch, "cron", hour=0, minute=0, id="daily", misfire_grace_time=3600)
        sched.start()
        log.info("Scheduler aktif: tiap 00:00 WIB.")
    except Exception as e:
        log.warning("Scheduler gagal: %s", e)


seed_if_empty()
try:
    rebuild()  # selalu rebuild saat boot → format daily_data.json selalu ikut versi aggregate terbaru
except Exception as e:
    log.warning("rebuild saat boot gagal: %s", e)
start_scheduler()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
