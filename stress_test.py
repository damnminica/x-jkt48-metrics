"""Uji batas penarikan mention/hashtag: apakah jendela besar kehilangan tweet dibanding jendela kecil?

Untuk tiap task & rentang tanggal, tarik hasil yang sama dengan beberapa ukuran jendela (mis. 24, 6, 1 jam),
lalu bandingkan jumlah tweet unik, irisan, dan biaya request. Untuk hashtag bisa juga membandingkan query
berkonteks vs query polos (--bare). Hasil: <DATA_DIR>/stress/<RUN_ID>/report.json + ringkasan ke Telegram.

Pakai (env sama dengan job_worker):
    STRESS_TASKS=mention:feni,mention:indah STRESS_START=2024-09-01 STRESS_DAYS=1 STRESS_HOURS=24,6,1 \
    STRESS_BARE=1 python stress_test.py
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from twitter_cli.client import TwitterClient
from twitter_cli.exceptions import TwitterAPIError

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))
import worker as w  # noqa: E402
from fetch_v2 import classify, fetch_query, read_jsonl  # noqa: E402
from job_worker import hash_salt, load_job, make_classifier, missing_env, wib_midnight  # noqa: E402
from xraw import parse_raw_any  # noqa: E402
import hashlib  # noqa: E402


def main():
    """Jalankan uji; semua kegagalan dilaporkan ke Telegram lalu keluar normal (exit 0) supaya platform
    tidak me-restart dan terus menembak akun yang sedang bermasalah."""
    try:
        run()
    except w.Stop as e:
        w.notify(f"🛑 Uji batas berhenti: {e}. Cek akun cadangan sebelum mengulang. {w.now_wib()} WIB")
    except TwitterAPIError as e:
        w.notify(f"🛑 Uji batas berhenti: X membalas HTTP {e.status_code} [{classify(e)}] ({str(e)[:200]}). "
                 f"{w.now_wib()} WIB")
    except Exception as e:  # noqa: BLE001
        w.notify(f"🛑 Uji batas error tak terduga: {type(e).__name__}: {str(e)[:300]}. {w.now_wib()} WIB")


def run():
    missing = missing_env()
    if missing:
        print(f"Env belum lengkap: {', '.join(missing)}. Tidak menyentuh X.", flush=True)
        return
    job = load_job()
    by_id = {t["id"]: t for t in job["tasks"]}
    task_ids = [x.strip() for x in os.environ.get("STRESS_TASKS", "").split(",") if x.strip()]
    if not task_ids or any(i not in by_id for i in task_ids):
        print(f"STRESS_TASKS kosong atau tidak dikenal: {task_ids}", flush=True)
        return
    start = wib_midnight(os.environ.get("STRESS_START", "2024-09-01"))
    end = start + timedelta(days=int(os.environ.get("STRESS_DAYS", "1")))
    hours = [int(h) for h in os.environ.get("STRESS_HOURS", "24,6").split(",")]
    variants = [("konteks", "query")] + ([("polos", "query_bare")] if os.environ.get("STRESS_BARE") else [])
    run_id = os.environ.get("RUN_ID", "stress")
    root = w.DATA / "stress" / run_id
    root.mkdir(parents=True, exist_ok=True)
    salt = hash_salt(root)
    hasher = lambda uid: "u_" + hashlib.sha256(f"{salt}:{uid}".encode()).hexdigest()[:16]
    classify_author = make_classifier(job)

    proxy, ip = w.choose_proxy()
    if proxy:
        os.environ["TWITTER_PROXY"] = proxy
    client = TwitterClient(os.environ["TWITTER_AUTH_TOKEN"], os.environ["TWITTER_CT0"],
                           {"maxRetries": 0, "requestDelay": 0})
    pacer, guard = w.Pacer(w.REQ_PER_WINDOW), w.RateLimitGuard()

    def pace():
        pacer()
        guard.ok()

    w.notify(f"🧪 Mulai uji batas {run_id}: {', '.join(task_ids)}, {start:%Y-%m-%d} +{(end - start).days} hari, "
             f"jendela {hours} jam. Exit IP: {ip}. {w.now_wib()} WIB")
    report = []
    for tid in task_ids:
        t = by_id[tid]
        for vname, qkey in variants:
            if qkey not in t:
                continue
            ids_by_h = {}
            for h in hours:
                # periode masuk label supaya uji dengan tanggal berbeda tidak tercampur di file yang sama
                label = f"{tid.replace(':', '__')}__{vname}__{h}h__{start:%Y%m%d}_{(end - start).days}d"
                c0, t0 = pacer.count, time.time()
                st = fetch_query(client, label, t[qkey], lambda x: parse_raw_any(x, classify_author, hasher),
                                 start, end, root, timedelta(hours=h), unit="time", pace=pace,
                                 on_rate_limit=guard, log=lambda s: print(s, flush=True))
                ids = {i for i, r in read_jsonl(root / f"{label}.jsonl").items()
                       if start <= datetime.fromisoformat(r["created_at"]) < end}
                ids_by_h[h] = ids
                report.append({"task": tid, "varian": vname, "jendela_jam": h, "tweet_unik": len(ids),
                               "request": pacer.count - c0, "menit": round((time.time() - t0) / 60, 1),
                               "jendela_terpotong": sum(x["truncated"] for x in st["windows"].values())})
            union = set().union(*ids_by_h.values())
            for r in report:
                if r["task"] == tid and r["varian"] == vname:
                    r["cakupan_vs_gabungan"] = round(len(ids_by_h[r["jendela_jam"]]) / max(1, len(union)), 3)
    (root / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    lines = [f"🧪 Hasil uji batas {run_id} ({start:%Y-%m-%d} +{(end - start).days} hari):"]
    for r in report:
        lines.append(f"{r['task']} [{r['varian']}, {r['jendela_jam']} jam]: {r['tweet_unik']} tweet, "
                     f"{r['request']} req, cakupan {r['cakupan_vs_gabungan']:.0%}"
                     + (f", {r['jendela_terpotong']} terpotong" if r["jendela_terpotong"] else ""))
    w.notify("\n".join(lines)[:4000])
    print(f"laporan: {root / 'report.json'}", flush=True)


if __name__ == "__main__":
    main()
