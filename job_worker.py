"""Worker job (Docker di Railway / systemd di VPS): jalankan task dari jobs/<name>.json, lalu kirim Excel ke Telegram.

Mode task: member (metrik tweet member), mention (tweet orang lain yang menyebut member, tanpa reply),
hashtag/tagline (tweet kampanye). Satu akun X = satu proses.

Koordinasi beberapa akun:
  - ANTREAN (default, SHARD tidak diisi): semua worker di DATA_DIR yang sama mengambil task dari antrean
    bersama (taskqueue.py). Task yang sudah diklaim/diselesaikan satu akun tidak dikerjakan akun lain; akun
    yang lebih cepat otomatis mengambil task berikutnya. Butuh disk bersama (mis. beberapa instance di 1 VPS).
  - SHARD k/n: pembagian tetap (task ke-i untuk shard i mod n). Untuk worker di disk berbeda (Railway).

Env wajib : TWITTER_AUTH_TOKEN, TWITTER_CT0, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TWITTER_PROXY
            (proxy boleh kosong hanya dengan ALLOW_DIRECT=1, untuk tes di IP residensial)
Env opsi  : JOB_FILE (default jobs/ssk2024.json), MODES (urutan & filter mode, default member,hashtag,mention)
            TASKS (daftar id task dipisah koma; menimpa MODES), SHARD (k/n; kosong = mode antrean)
            WORKER_ID (nama worker; default turunan hash cookie), RUN_ID (default nama job; SAMA untuk semua akun)
            DATA_DIR (default /data), REQ_PER_WINDOW (default 35), QUEUE_POLL_S (default 300)
            HASH_SALT (mode antrean: opsional, dibagi lewat file; mode shard n>1: wajib & sama)
            EXIT_WHEN_DONE=1 (tes lokal)
Aman di-restart: progres per jendela tersimpan; klaim milik worker yang sama dilanjutkan.
"""
import hashlib
import json
import os
import random
import secrets
import sys
import threading
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

from twitter_cli.client import TwitterClient
from twitter_cli.exceptions import NotFoundError, TwitterAPIError

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))
import worker as w  # noqa: E402  (Pacer, RateLimitGuard, Stop, notify, choose_proxy, send_excel, idle)
from fetch_v2 import TRANSIENT_WAITS, classify, count_unique, fetch_member, fetch_query, save_store  # noqa: E402
from xraw import parse_raw_any  # noqa: E402
from export_jobs import build_job_workbook, job_summary_text  # noqa: E402
from taskqueue import TaskQueue  # noqa: E402

WIB = timezone(timedelta(hours=7))
DEFAULT_MODES = ["member", "hashtag", "mention"]


def wib_midnight(day):
    return datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=WIB)


def load_job():
    path = Path(os.environ.get("JOB_FILE", BASE / "jobs" / "ssk2024.json"))
    if not path.is_absolute():
        path = BASE / path
    return json.loads(path.read_text(encoding="utf-8"))


def shard_spec():
    raw = os.environ.get("SHARD", "").strip()
    if not raw:
        return None
    k, n = (int(x) for x in raw.split("/"))
    if not 1 <= k <= n:
        raise w.Stop(f"SHARD tidak valid: {k}/{n}")
    return k, n


def select_tasks(job):
    """Task aktif yang dipilih env, diurutkan per mode; di mode shard diambil bagian shard ini.
    Return (tasks, nama_state)."""
    ids = [x.strip() for x in os.environ.get("TASKS", "").split(",") if x.strip()]
    if ids:
        by_id = {t["id"]: t for t in job["tasks"]}
        missing = [i for i in ids if i not in by_id]
        if missing:
            raise w.Stop(f"TASKS tidak dikenal: {', '.join(missing)}")
        tasks = [by_id[i] for i in ids]  # TASKS eksplisit boleh menjalankan task nonaktif
    else:
        modes = [m.strip() for m in os.environ.get("MODES", ",".join(DEFAULT_MODES)).split(",") if m.strip()]
        tasks = [t for m in modes for t in job["tasks"] if t["mode"] == m and t.get("enabled", True)]
    spec = shard_spec()
    if spec:
        k, n = spec
        tasks = [t for i, t in enumerate(tasks) if i % n == k - 1]
    # nama state memuat sidik daftar task: dua konfigurasi berbeda di disk yang sama tidak saling menimpa
    sig = hashlib.sha1(",".join(t["id"] for t in tasks).encode()).hexdigest()[:8]
    return tasks, (f"shard{spec[0]}of{spec[1]}_{sig}" if spec else f"antrean_{sig}")


def worker_id():
    """Nama worker yang stabil antar restart (dipakai untuk melanjutkan klaim sendiri)."""
    wid = os.environ.get("WORKER_ID", "").strip()
    if wid:
        return wid
    return "akun_" + hashlib.sha256(os.environ.get("TWITTER_AUTH_TOKEN", "").encode()).hexdigest()[:8]


def hash_salt(root):
    """Salt anonimisasi fans: harus sama untuk semua worker & restart dalam satu job, dan tidak boleh berubah."""
    env = os.environ.get("HASH_SALT", "").strip()
    path = root / ".hash_salt"
    if path.exists():
        saved = path.read_text().strip()
        if not saved:
            raise w.Stop(f"{path} kosong; isi ulang dengan salt job ini atau hapus file & data job")
        if env and env != saved:
            raise w.Stop("HASH_SALT berbeda dari salt yang sudah dipakai job ini; hash fans akan tidak konsisten")
        return saved
    spec = shard_spec()
    if not env and spec and spec[1] > 1:
        raise w.Stop("HASH_SALT wajib diisi (sama untuk semua akun) kalau job dibagi ke beberapa shard")
    salt = env or secrets.token_hex(16)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:  # dibuat worker lain di saat yang sama
        return hash_salt(root)
    with os.fdopen(fd, "w") as fh:
        fh.write(salt)
    return salt


def make_classifier(job):
    known = job.get("known_accounts", {})
    member, fanbase = set(known.get("member", [])), set(known.get("fanbase", []))
    official = set(known.get("official", []))

    def classify_author(handle):
        if handle in member:
            return "member"
        if handle in fanbase:
            return "fanbase"
        if handle in official:
            return "official"
        return "lain"
    return classify_author


def run_task(t, job, client, root, pace, guard, on_transient):
    """Jalankan satu task; return ringkasan untuk notifikasi."""
    log = lambda s: print(s, flush=True)
    if t["mode"] == "member":
        start = datetime.strptime(job["fetch_start_utc"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end = datetime.strptime(job["fetch_end_utc"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        (root / "member").mkdir(parents=True, exist_ok=True)
        store = fetch_member(client, t["handle"], start, end, root / "member" / f"{t['handle']}_v2.json",
                             pace=pace, on_rate_limit=guard, on_transient=on_transient, log=log)
        return f"{len(store['tweets'])} tweet"
    salt = hash_salt(root)
    hasher = lambda uid: "u_" + hashlib.sha256(f"{salt}:{uid}".encode()).hexdigest()[:16]
    classify_author = make_classifier(job)
    start = wib_midnight(job["analysis_start_wib"])
    end = wib_midnight(job["analysis_end_wib"]) + timedelta(days=1)
    label = t["id"].replace(":", "__")
    split_h = t.get("split_hours")
    state = fetch_query(client, label, t["query"], lambda x: parse_raw_any(x, classify_author, hasher), start, end,
                        root / t["mode"], timedelta(hours=t.get("window_hours", 24)), unit=t.get("unit", "time"),
                        pace=pace, on_rate_limit=guard, on_transient=on_transient, log=log,
                        empty_retries=t.get("empty_retries", 3),
                        split_window=timedelta(hours=split_h) if split_h else None,
                        split_threshold=t.get("split_threshold"))
    wins = state["windows"].values()
    trunc = sum(1 for x in wins if x["truncated"])
    n = count_unique(root / t["mode"] / f"{label}.jsonl")
    return (f"{n:,} tweet unik dari {len(state['windows'])} jendela".replace(",", ".")
            + (f", {trunc} jendela TERPOTONG" if trunc else ""))


def missing_env():
    """Env wajib yang kosong. Proxy wajib kecuali ALLOW_DIRECT=1 (tes lokal di IP residensial)."""
    missing = [k for k in w.REQUIRED_ENV if not os.environ.get(k)]
    if not os.environ.get("TWITTER_PROXY") and os.environ.get("ALLOW_DIRECT") != "1":
        missing.append("TWITTER_PROXY (wajib; set ALLOW_DIRECT=1 hanya untuk tes di IP residensial)")
    return missing


def main():
    missing = missing_env()
    if missing:
        print(f"Env belum lengkap: {', '.join(missing)}. Worker diam, tidak menyentuh X.", flush=True)
        if os.environ.get("EXIT_WHEN_DONE"):
            return
        while True:
            time.sleep(3600)

    job = load_job()
    run_id = os.environ.get("RUN_ID") or job["name"]
    root = w.DATA / run_id
    root.mkdir(parents=True, exist_ok=True)
    wid = worker_id()
    try:
        tasks, set_name = select_tasks(job)
        if any(t["mode"] != "member" for t in tasks):
            hash_salt(root)  # validasi salt sebelum menyentuh X
    except w.Stop as e:
        w.notify(f"🛑 Konfigurasi job salah ({wid}): {e}")
        return w.idle({}, root / "state_invalid.json", run_id)
    queue = None if shard_spec() else TaskQueue(root, wid)
    label = f"{set_name}" if queue is None else f"antrean · {wid}"
    state_path = root / (f"state_{set_name}.json" if queue is None else f"state_{set_name}_{wid}.json")
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    if state.get("built") and not state.get("sent"):
        w.send_excel(state, state_path, f"📊 (kirim ulang) Excel job '{run_id}' ({label}). {w.now_wib()} WIB")
    if state.get("built") or state.get("finished_all"):
        print(f"Job {run_id} ({label}) sudah selesai. Ganti RUN_ID untuk menjalankan ulang. Diam.", flush=True)
        return w.idle(state, state_path, run_id)
    state.setdefault("finished", [])
    state.setdefault("skipped", [])
    state["tasks"] = [t["id"] for t in tasks]
    save_store(state_path, state)

    current = {"task": None}
    try:
        proxy, ip = w.choose_proxy()
        if proxy:
            os.environ["TWITTER_PROXY"] = proxy  # dibaca twitter-cli saat membuat sesi
        client = TwitterClient(os.environ["TWITTER_AUTH_TOKEN"], os.environ["TWITTER_CT0"],
                               {"maxRetries": 0, "requestDelay": 0})
        if queue:
            todo = queue.remaining(tasks)
        else:
            todo = [t for t in tasks if t["id"] not in state["finished"]]
        counts = {}
        for t in todo:
            counts[t["mode"]] = counts.get(t["mode"], 0) + 1
        w.notify(f"▶️ Mulai job '{run_id}' ({label}): {len(todo)} dari {len(tasks)} task belum selesai "
                 f"({', '.join(f'{m} {c}' for m, c in counts.items())}). Periode {job['analysis_start_wib']} – "
                 f"{job['analysis_end_wib']} WIB. Exit IP: {ip}{' (proxy)' if proxy else ' (langsung)'}. "
                 f"Tempo {w.REQ_PER_WINDOW} req/15 menit. {w.now_wib()} WIB")

        pacer, guard = w.Pacer(w.REQ_PER_WINDOW), w.RateLimitGuard()

        def pace():
            pacer()
            guard.ok()

        def on_transient(attempt, wait, e):
            w.notify(f"⚠️ [{wid}] Gangguan jaringan/X (HTTP {e.status_code}: {str(e)[:120]}). Coba lagi "
                     f"{wait // 60} menit ({attempt + 1}/{len(TRANSIENT_WAITS)}). {w.now_wib()} WIB")
            time.sleep(wait)

        poll_s = float(os.environ.get("QUEUE_POLL_S", "300"))
        waiting_noted = False
        mine = 0
        while True:
            if queue:
                t = queue.next_task(tasks)
                if t is None:
                    left = queue.remaining(tasks)
                    if not left:
                        break
                    if not waiting_noted:
                        holders = sorted({(queue.claim_info(x["id"]) or {}).get("worker", "?") for x in left})
                        w.notify(f"⏳ [{wid}] Tidak ada task bebas; {len(left)} task masih dikerjakan "
                                 f"{', '.join(holders)}. Menunggu (ambil alih otomatis kalau worker itu mati). "
                                 f"{w.now_wib()} WIB")
                        waiting_noted = True
                    threading.Event().wait(poll_s)  # tidak memakai time.sleep supaya tes bisa mempercepatnya
                    continue
                queue.heartbeat_start(t["id"])
            else:
                pending = [x for x in tasks if x["id"] not in state["finished"]]
                if not pending:
                    break
                t = pending[0]
            current["task"] = t["id"]
            t0, c0 = time.time(), pacer.count
            try:
                info = run_task(t, job, client, root, pace, guard, on_transient)
            except NotFoundError as e:  # akun member hilang/berganti nama: lewati task ini saja
                info = None
                state["skipped"].append(t["id"])
                w.notify(f"⏭️ [{wid}] {t['id']} dilewati: {str(e)[:150]}. {w.now_wib()} WIB")
            state["finished"].append(t["id"])
            save_store(state_path, state)
            if queue:
                queue.heartbeat_stop()
                queue.finish(t["id"])
            current["task"] = None
            mine += 1
            if info is not None:
                done_all = len(tasks) - (len(queue.remaining(tasks)) if queue else len(tasks) - len(state["finished"]))
                w.notify(f"✅ [{wid}] {t['id']}: {info}, {pacer.count - c0} request, "
                         f"{(time.time() - t0) / 60:.0f} menit. Total job {done_all}/{len(tasks)}. {w.now_wib()} WIB")
            time.sleep(random.uniform(60, 180))  # jeda antar task

        if queue and not queue.take_export():
            state["finished_all"] = w.now_wib()
            save_store(state_path, state)
            w.notify(f"🏁 [{wid}] Semua task job '{run_id}' selesai ({mine} dikerjakan worker ini). Excel dibuat "
                     f"oleh worker {queue.export_owner()}. {w.now_wib()} WIB")
        else:
            ids = [t["id"] for t in tasks]
            out = root / f"JKT48_{run_id}_{set_name}_{datetime.now(WIB):%Y%m%d}.xlsx"
            build_job_workbook(job, root, out, task_ids=ids)
            state["built"] = str(out)
            save_store(state_path, state)
            w.notify(job_summary_text(job, root, task_ids=ids))
            if not w.send_excel(state, state_path, f"📊 Job '{run_id}' selesai: {len(tasks)} task "
                                                   f"({mine} oleh {wid}). {w.now_wib()} WIB"):
                print("Kirim Excel gagal; dicoba ulang tiap jam.", flush=True)
    except w.Stop as e:
        w.notify(f"🛑 [{wid}] Berhenti: {e}. Progres tersimpan; cek akun di browser sebelum lanjut. {w.now_wib()} WIB")
    except TwitterAPIError as e:
        kind = classify(e)
        why = {"account": "Kemungkinan cookie kedaluwarsa atau akun cadangan terkunci; cek di browser.",
               "transient": "Gangguan jaringan/proxy/X berlanjut ~1,4 jam walau sudah dicoba ulang.",
               }.get(kind, "Respons X tidak dikenal (mungkin endpoint/operator query berubah).")
        w.notify(f"🛑 [{wid}] Berhenti: X membalas HTTP {e.status_code} ({str(e)[:200]}). {why} Progres tersimpan; "
                 f"restart worker untuk melanjutkan. {w.now_wib()} WIB")
    except Exception as e:
        traceback.print_exc()
        w.notify(f"🛑 [{wid}] Error tak terduga: {type(e).__name__}: {str(e)[:300]}. Progres tersimpan. "
                 f"{w.now_wib()} WIB")
    finally:
        if queue:
            queue.heartbeat_stop()
            if current["task"]:  # lepas klaim supaya akun lain bisa langsung melanjutkan task ini
                queue.release(current["task"])
    w.idle(state, state_path, run_id)


if __name__ == "__main__":
    main()
