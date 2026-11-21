"""Fase 3 — metrik PER-POST Instagram → sum/agregat per member.

Pakai instagrapi + sesi login akun CADANGAN (bukan akun pribadi!). Robust: library
menangani device-id/signing yang bikin requests mentah kena 403.

Yang BISA ditarik per post (scalable, 1 panggilan feed/member + paginasi):
  likes ✓   komentar ✓   views Reel (play_count) ✓
TIDAK bisa (dikonfirmasi tak ada di API feed maupun media_info):
  repost (🔁) & share (✈️) — angka itu owner-only/UI; kolomnya tetap ada tapi None.

Siapkan cookie (sekali):
  instagram/.env →  IG_SESSIONID=...   (devtools akun cadangan → Cookies → sessionid)
Jalan (LOKAL saja — IP datacenter/Railway langsung di-flag IG):
  set -a; . ./.env; set +a
  python ig_posts.py --max 36                 # semua member → snapshots/posts_<today>.csv
  python ig_posts.py --only jkt48.christy      # uji 1 member
  python ig_posts.py --sample                  # uji parser tanpa login

ToS IG melarang scraping otomatis — akun khusus, tempo pelan, sadar risiko rate-limit/flag.
"""
import argparse
import csv
import json
import os
import statistics
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote

import ig_fetch  # resolve pk member via crawler publik (hemat panggilan ber-auth)

HERE = Path(__file__).resolve().parent
WIB = timezone(timedelta(hours=7))
SETTINGS = HERE / ".ig_settings.json"  # device instagrapi (gitignored) → konsisten antar-run


def make_client():
    sid = unquote(os.environ.get("IG_SESSIONID", "").strip())
    if not sid:
        return None
    try:
        from instagrapi import Client
    except ImportError:
        sys.exit("pip install instagrapi")
    cl = Client()
    cl.delay_range = [2, 5]  # jeda acak antar-panggilan (sopan ke IG)
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
        "is_reel": is_reel,
        "likes": int(lk) if isinstance(lk, int) and lk >= 0 else None,
        "comments": int(cm) if isinstance(cm, int) and cm >= 0 else None,
        "views": int(views) if isinstance(views, int) and views > 0 else None,
        "reshares": None,  # tak tersedia di API
        "shares": None,    # tak tersedia di API
    }


def summarize(handle, posts, followers=None):
    def nz(key):
        return [p[key] for p in posts if isinstance(p.get(key), int)]
    likes, comments = nz("likes"), nz("comments")
    views = [p["views"] for p in posts if p.get("is_reel") and isinstance(p.get("views"), int)]
    reels = sum(1 for p in posts if p.get("is_reel"))
    avg_eng = (statistics.mean(likes) + statistics.mean(comments)) if likes and comments else None
    er = round(avg_eng / followers * 100, 2) if avg_eng and followers else None
    return {
        "handle": handle, "n_posts": len(posts), "n_reels": reels,
        "sum_likes": sum(likes) or None, "avg_likes": round(statistics.mean(likes)) if likes else None,
        "med_likes": round(statistics.median(likes)) if likes else None,
        "sum_comments": sum(comments) or None,
        "avg_comments": round(statistics.mean(comments)) if comments else None,
        "avg_views_reel": round(statistics.mean(views)) if views else None,
        "sum_views_reel": sum(views) or None,
        "sum_reshares": None, "sum_shares": None, "er": er,
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
        out.append({"panggilan": m["panggilan"], "nama": nama, "tim": tim,
                    "ig_username": u, "followers": m.get("followers")})
    return out


COLS = ["date", "panggilan", "nama", "tim", "ig_username", "n_posts", "n_reels",
        "sum_likes", "avg_likes", "med_likes", "sum_comments", "avg_comments",
        "avg_views_reel", "sum_views_reel", "sum_reshares", "sum_shares", "er"]


def run(date=None, only=None, out_dir=None, max_posts=36, pause=3.0):
    cl = make_client()
    if cl is None:
        sys.exit("IG_SESSIONID belum di-set. Isi instagram/.env lalu: set -a; . ./.env; set +a")
    print("login OK sebagai user_id:", cl.user_id)
    date = date or datetime.now(WIB).strftime("%Y-%m-%d")
    out_dir = Path(out_dir) if out_dir else (HERE / "snapshots")
    out_dir.mkdir(parents=True, exist_ok=True)
    only = set(only.split(",")) if only else None
    targets = load_targets(only)
    pub = __import__("requests").Session()
    rows, ok = [], 0
    for i, t in enumerate(targets, 1):
        try:
            pk = (ig_fetch.fetch_one(t["ig_username"], pub, pause=0.5) or {}).get("pk")
            if not pk:
                pk = cl.user_id_from_username(t["ig_username"])
            medias = cl.user_medias_v1(int(pk), amount=max_posts)
            posts = [parse_media(m) for m in medias]
        except Exception as e:  # noqa: BLE001
            print(f"  {i}/{len(targets)} {t['ig_username']:<18} GAGAL: {str(e)[:70]}", flush=True)
            posts = []
        summ = summarize(t["ig_username"], posts, t.get("followers"))
        if summ["n_posts"]:
            ok += 1
        rows.append([date, t["panggilan"], t["nama"], t["tim"], t["ig_username"],
                     summ["n_posts"], summ["n_reels"], summ["sum_likes"], summ["avg_likes"],
                     summ["med_likes"], summ["sum_comments"], summ["avg_comments"],
                     summ["avg_views_reel"], summ["sum_views_reel"], summ["sum_reshares"],
                     summ["sum_shares"], summ["er"]])
        print(f"  {i}/{len(targets)} {t['ig_username']:<18} posts={summ['n_posts']} "
              f"avgL={summ['avg_likes']} avgC={summ['avg_comments']} "
              f"viewsReel={summ['avg_views_reel']} ER={summ['er']}", flush=True)
        time.sleep(pause)
    path = out_dir / f"posts_{date}.csv"
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLS)
        w.writerows(rows)
    print(f"\nOK {ok}/{len(targets)} member ada data post → {path}")
    return path


class _M:  # objek contoh utk --sample (tanpa login)
    def __init__(self, **k):
        self.__dict__.update(k)


SAMPLE = [
    _M(code="C1", taken_at=None, media_type=8, product_type="carousel_container", like_count=82179, comment_count=377),
    _M(code="C2", taken_at=None, media_type=2, product_type="clips", like_count=39871, comment_count=72, play_count=755082),
    _M(code="C3", taken_at=None, media_type=1, product_type="feed", like_count=17364, comment_count=84),
]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--only")
    ap.add_argument("--out")
    ap.add_argument("--max", type=int, default=36)
    ap.add_argument("--pause", type=float, default=3.0)
    ap.add_argument("--sample", action="store_true")
    a = ap.parse_args()
    if a.sample:
        parsed = [parse_media(m) for m in SAMPLE]
        for p in parsed:
            print(" ", p)
        print("\nsummarize (followers=1.740.761):")
        print(" ", json.dumps(summarize("jkt48.christy", parsed, 1740761), indent=1))
    else:
        run(date=a.date, only=a.only, out_dir=a.out, max_posts=a.max, pause=a.pause)
