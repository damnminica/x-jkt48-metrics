"""Fase 3 — metrik PER-POST Instagram → store per-post + maturity model.

Model: simpan tiap post (by shortcode) dgn likes/komentar/views + taken_at + last_fetched,
UPSERT tiap run → nilai post ter-update sampai "matang". Agregat per member dihitung dari
store (lihat aggregate_ig): post MATANG (umur ≥ IG_MATURE_DAYS) dalam IG_RECENCY_DAYS terakhir.

Dua mode:
  --backfill  : SEKALI di awal — tarik SEMUA post tiap member (atau --max N) → isi store historis.
  (default)   : rolling — tarik post < IG_REFETCH_DAYS hari → upsert (hemat panggilan).

Engine: instagrapi (github.com/subzeroid/instagrapi), login via sessionid akun CADANGAN.
Hanya likes/komentar/views Reel (repost & share TIDAK ada di API IG).

  instagram/.env → IG_SESSIONID=...   (devtools akun cadangan → Cookies → sessionid)
  IG_PROXY=...  (WAJIB bila dari IP datacenter/Railway)
  set -a; . ./.env; set +a
  python ig_posts.py --backfill        # sekali: semua post → snapshots/posts_store.csv
  python ig_posts.py                   # rolling: post 14 hari terakhir → upsert
  python ig_posts.py --sample          # uji parser tanpa login

ToS IG melarang scraping otomatis — akun khusus, tempo pelan, sadar risiko.
"""
import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote

import ig_fetch  # resolve pk member via crawler publik (hemat panggilan ber-auth)

HERE = Path(__file__).resolve().parent
WIB = timezone(timedelta(hours=7))
SETTINGS = HERE / ".ig_settings.json"  # device instagrapi (gitignored) → konsisten antar-run
REFETCH_DAYS = int(os.environ.get("IG_REFETCH_DAYS", "14"))
ROLLING_SCAN = 40  # berapa post terbaru dipindai saat rolling (cukup utk menutup window)

STORE_COLS = ["code", "handle", "panggilan", "tim", "taken_at", "media_type", "is_reel",
              "likes", "comments", "views", "first_seen", "last_fetched"]


def make_client():
    sid = unquote(os.environ.get("IG_SESSIONID", "").strip())
    if not sid:
        return None
    try:
        from instagrapi import Client
    except ImportError:
        sys.exit("pip install instagrapi")
    cl = Client()
    cl.delay_range = [2, 5]
    proxy = os.environ.get("IG_PROXY", "").strip()  # WAJIB bila IP datacenter (Railway)
    if proxy:
        try:
            cl.set_proxy(proxy)
        except Exception:  # noqa: BLE001
            pass
    if SETTINGS.exists():
        try:
            cl.load_settings(SETTINGS)
        except Exception:  # noqa: BLE001
            pass
    cl.login_by_sessionid(sid)
    try:
        cl.dump_settings(SETTINGS)
    except Exception:  # noqa: BLE001
        pass
    return cl


def parse_media(m):
    """Media instagrapi → metrik per-post (field tak tersedia = None)."""
    pt = (getattr(m, "product_type", "") or "").lower()
    is_reel = pt == "clips"
    lk = getattr(m, "like_count", None)
    cm = getattr(m, "comment_count", None)
    views = None
    if is_reel:
        views = getattr(m, "play_count", None) or getattr(m, "view_count", None) or None
    ta = getattr(m, "taken_at", None)
    return {
        "code": getattr(m, "code", None),
        "taken_at": int(ta.timestamp()) if ta else None,
        "media_type": getattr(m, "media_type", None),
        "is_reel": 1 if is_reel else 0,
        "likes": int(lk) if isinstance(lk, int) and lk >= 0 else None,
        "comments": int(cm) if isinstance(cm, int) and cm >= 0 else None,
        "views": int(views) if isinstance(views, int) and views > 0 else None,
    }


def store_path(out_dir):
    return Path(out_dir) / "posts_store.csv"


def load_store(out_dir):
    p = store_path(out_dir)
    store = {}
    if p.exists():
        with p.open() as f:
            for r in csv.DictReader(f):
                store[r["code"]] = r
    return store


def save_store(out_dir, store):
    p = store_path(out_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(store.values(), key=lambda r: -(int(r["taken_at"]) if r.get("taken_at") else 0))
    with p.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=STORE_COLS)
        w.writeheader()
        w.writerows(rows)


def upsert(store, target, p, now):
    """Masukkan/update satu post ke store (preserve first_seen)."""
    code = p.get("code")
    if not code:
        return
    cur = store.get(code, {})
    store[code] = {
        "code": code, "handle": target["ig_username"], "panggilan": target["panggilan"],
        "tim": target["tim"], "taken_at": p.get("taken_at"), "media_type": p.get("media_type"),
        "is_reel": p.get("is_reel"),
        "likes": p.get("likes"), "comments": p.get("comments"), "views": p.get("views"),
        "first_seen": cur.get("first_seen") or now, "last_fetched": now,
    }


def load_targets(only=None):
    members = json.loads((HERE / "members_ig.json").read_text())
    meta = {}
    with (HERE.parent / "members.csv").open() as f:
        for row in csv.DictReader(f):
            meta[row["panggilan"]] = (row["nama"], row["tim"])
    out, seen = [], set()
    for m in members:
        u = m.get("ig_username")
        if not u or u in seen or m.get("status_akun") == "shared":
            continue
        if only and u not in only:
            continue
        seen.add(u)
        nama, tim = meta.get(m["panggilan"], (m.get("nama", ""), m.get("tim", "Trainee")))
        out.append({"panggilan": m["panggilan"], "nama": nama, "tim": tim, "ig_username": u})
    return out


MARKER = ".ig_backfilled"


def run(mode="rolling", only=None, out_dir=None, backfill_max=0, refetch_days=None, pause=3.0,
        on_member=None):
    cl = make_client()
    if cl is None:
        sys.exit("IG_SESSIONID belum di-set. Isi instagram/.env lalu: set -a; . ./.env; set +a")
    print("login OK sebagai user_id:", cl.user_id)
    out_dir = Path(out_dir) if out_dir else (HERE / "snapshots")
    out_dir.mkdir(parents=True, exist_ok=True)
    refetch_days = refetch_days if refetch_days is not None else REFETCH_DAYS
    only = set(only.split(",")) if only else None
    targets = load_targets(only)
    store = load_store(out_dir)
    pub = __import__("requests").Session()
    now = int(time.time())
    cutoff = now - refetch_days * 86400
    new, upd = 0, 0
    for i, t in enumerate(targets, 1):
        try:
            pk = (ig_fetch.fetch_one(t["ig_username"], pub, pause=0.4) or {}).get("pk")
            if not pk:
                pk = cl.user_id_from_username(t["ig_username"])
            amount = (backfill_max if backfill_max and backfill_max > 0 else 0) if mode == "backfill" else ROLLING_SCAN
            medias = cl.user_medias_v1(int(pk), amount=amount)
            cnt = 0
            for m in medias:
                p = parse_media(m)
                if mode != "backfill" and p.get("taken_at") and p["taken_at"] < cutoff:
                    break  # newest-first → sisanya lebih tua dari window
                before = p["code"] in store
                upsert(store, t, p, now)
                cnt += 1
                if before:
                    upd += 1
                else:
                    new += 1
            print(f"  {i}/{len(targets)} {t['ig_username']:<18} {mode}: {cnt} post", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"  {i}/{len(targets)} {t['ig_username']:<18} GAGAL: {str(e)[:70]}", flush=True)
        save_store(out_dir, store)      # simpan tiap member → data langsung tersedia (live)
        if on_member:
            try:
                on_member(i, t["ig_username"])  # mis. rebuild ig_data.json → muncul di dashboard
            except Exception:  # noqa: BLE001
                pass
        time.sleep(pause)
    save_store(out_dir, store)
    if mode == "backfill":
        (out_dir / MARKER).write_text(datetime.now(WIB).isoformat())
    print(f"\nstore: {len(store)} post total (+{new} baru, {upd} update) → {store_path(out_dir)}")
    return store_path(out_dir)


class _M:
    def __init__(self, **k):
        self.__dict__.update(k)


SAMPLE = [
    _M(code="C1", taken_at=datetime.now(timezone.utc), media_type=8, product_type="carousel", like_count=82179, comment_count=377),
    _M(code="C2", taken_at=datetime.now(timezone.utc), media_type=2, product_type="clips", like_count=39871, comment_count=72, play_count=755082),
]

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", action="store_true", help="SEKALI: tarik semua post")
    ap.add_argument("--only")
    ap.add_argument("--out")
    ap.add_argument("--max", type=int, default=0, help="batas post saat backfill (0=semua)")
    ap.add_argument("--refetch-days", type=int, default=None)
    ap.add_argument("--pause", type=float, default=3.0)
    ap.add_argument("--sample", action="store_true")
    a = ap.parse_args()
    if a.sample:
        for m in SAMPLE:
            print(" ", parse_media(m))
    else:
        run(mode="backfill" if a.backfill else "rolling", only=a.only, out_dir=a.out,
            backfill_max=a.max, refetch_days=a.refetch_days, pause=a.pause)
