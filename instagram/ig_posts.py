"""Fase 3 — metrik PER-POST Instagram → sum/agregat per member.

Butuh SESI LOGIN akun CADANGAN (bukan akun pribadi!). Cookie `sessionid` dari devtools:
  Instagram (login akun cadangan) → DevTools → Application → Cookies → salin nilai `sessionid`.
  export IG_SESSIONID='...'            # (opsional) IG_DS_USER_ID, IG_CSRFTOKEN
Lalu:
  python ig_posts.py                   # semua member → snapshots/posts_<today>.csv
  python ig_posts.py --only jkt48.christy --max 24
  python ig_posts.py --sample          # uji parser tanpa login (data contoh)

Dari feed API tiap item: likes & komentar & views Reel (play_count) ANDAL; repost/share
best-effort (field IG baru — diisi bila ada, selain itu None). pk member diambil publik
(crawler) jadi tak perlu login untuk resolve id. HORMATI rate-limit: pace lambat, akun cadangan.
ToS IG melarang scraping otomatis — gunakan dengan sadar risiko, akun khusus.
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

try:
    import requests
except ImportError:
    sys.exit("pip install requests")

import ig_fetch  # resolve pk via crawler publik

HERE = Path(__file__).resolve().parent
WIB = timezone(timedelta(hours=7))
APP_ID = "936619743392459"
DESKTOP_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def make_session():
    sid = os.environ.get("IG_SESSIONID", "").strip()
    if not sid:
        return None
    s = requests.Session()
    csrf = os.environ.get("IG_CSRFTOKEN", "").strip()
    s.headers.update({
        "User-Agent": DESKTOP_UA, "x-ig-app-id": APP_ID,
        "x-requested-with": "XMLHttpRequest", "Referer": "https://www.instagram.com/",
        "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9",
    })
    if csrf:
        s.headers["x-csrftoken"] = csrf
        s.cookies.set("csrftoken", csrf, domain=".instagram.com")
    s.cookies.set("sessionid", sid, domain=".instagram.com")
    dsid = os.environ.get("IG_DS_USER_ID", "").strip()
    if dsid:
        s.cookies.set("ds_user_id", dsid, domain=".instagram.com")
    return s


def _first(d, *keys):
    """Ambil nilai integer pertama yang ada dari beberapa kandidat key (toleran skema)."""
    for k in keys:
        v = d.get(k)
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            return int(v)
        if isinstance(v, dict) and isinstance(v.get("count"), (int, float)):
            return int(v["count"])
    return None


def parse_item(it):
    """Satu item feed → metrik per-post (field tak tersedia = None)."""
    pt = (it.get("product_type") or "").lower()
    mt = it.get("media_type")
    return {
        "code": it.get("code"),
        "taken_at": it.get("taken_at"),
        "media_type": mt,
        "is_reel": pt == "clips",
        "likes": _first(it, "like_count"),
        "comments": _first(it, "comment_count"),
        # reel views: play_count / ig_play_count / view_count
        "views": _first(it, "play_count", "ig_play_count", "view_count"),
        # repost (fitur baru IG) — beberapa kandidat key
        "reshares": _first(it, "reshare_count", "repost_count", "reshares_count"),
        # share/send count — sering owner-only; best-effort
        "shares": _first(it, "share_count", "reshare_count") if it.get("share_count") is not None
        else (it.get("share_info") or {}).get("share_count") if isinstance(it.get("share_info"), dict) else None,
    }


def fetch_media(pk, s, max_posts=36, pause=2.5, log=print):
    """Ambil hingga max_posts item terbaru via feed/user API (paginasi max_id)."""
    items, max_id, pages = [], None, 0
    while len(items) < max_posts and pages < 12:
        url = f"https://www.instagram.com/api/v1/feed/user/{pk}/?count=12"
        if max_id:
            url += f"&max_id={max_id}"
        r = s.get(url, timeout=30)
        if r.status_code != 200:
            log(f"    feed HTTP {r.status_code} (pk {pk}) — sesi mungkin tak valid/expired")
            break
        try:
            j = r.json()
        except ValueError:
            log("    respons bukan JSON (kemungkinan login-wall) — cek IG_SESSIONID")
            break
        batch = j.get("items") or []
        items.extend(batch)
        pages += 1
        if not j.get("more_available"):
            break
        max_id = j.get("next_max_id")
        time.sleep(pause)
    return [parse_item(x) for x in items[:max_posts]]


def summarize(handle, posts, followers=None):
    def nz(key):
        return [p[key] for p in posts if isinstance(p.get(key), int)]
    likes, comments = nz("likes"), nz("comments")
    views = [p["views"] for p in posts if p.get("is_reel") and isinstance(p.get("views"), int)]
    reshares, shares = nz("reshares"), nz("shares")
    reels = sum(1 for p in posts if p.get("is_reel"))
    avg_eng = (statistics.mean(likes) + statistics.mean(comments)) if likes and comments else None
    er = round(avg_eng / followers * 100, 2) if avg_eng and followers else None
    return {
        "handle": handle, "n_posts": len(posts), "n_reels": reels,
        "sum_likes": sum(likes) or None, "avg_likes": round(statistics.mean(likes)) if likes else None,
        "med_likes": round(statistics.median(likes)) if likes else None,
        "sum_comments": sum(comments) or None, "avg_comments": round(statistics.mean(comments)) if comments else None,
        "avg_views_reel": round(statistics.mean(views)) if views else None,
        "sum_views_reel": sum(views) or None,
        "sum_reshares": sum(reshares) if reshares else None,
        "sum_shares": sum(shares) if shares else None,
        "er": er,
        "has_reshare": bool(reshares), "has_share": bool(shares),
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


def run(date=None, only=None, out_dir=None, max_posts=36, pause=2.5):
    s = make_session()
    if s is None:
        sys.exit("IG_SESSIONID belum di-set. Login akun CADANGAN, salin cookie sessionid, "
                 "lalu: export IG_SESSIONID='...'  (lihat header file ini).")
    date = date or datetime.now(WIB).strftime("%Y-%m-%d")
    out_dir = Path(out_dir) if out_dir else (HERE / "snapshots")
    out_dir.mkdir(parents=True, exist_ok=True)
    only = set(only.split(",")) if only else None
    targets = load_targets(only)
    pub = requests.Session()
    rows, ok = [], 0
    for i, t in enumerate(targets, 1):
        prof = ig_fetch.fetch_one(t["ig_username"], pub, pause=0.5)
        pk = prof.get("pk")
        if not pk:
            print(f"  {i}/{len(targets)} {t['ig_username']:<18} pk tak ketemu, lewati"); continue
        posts = fetch_media(pk, s, max_posts=max_posts, pause=pause)
        summ = summarize(t["ig_username"], posts, t.get("followers"))
        if summ["n_posts"]:
            ok += 1
        rows.append([date, t["panggilan"], t["nama"], t["tim"], t["ig_username"],
                     summ["n_posts"], summ["n_reels"], summ["sum_likes"], summ["avg_likes"],
                     summ["med_likes"], summ["sum_comments"], summ["avg_comments"],
                     summ["avg_views_reel"], summ["sum_views_reel"], summ["sum_reshares"],
                     summ["sum_shares"], summ["er"]])
        print(f"  {i}/{len(targets)} {t['ig_username']:<18} posts={summ['n_posts']} "
              f"avgL={summ['avg_likes']} avgC={summ['avg_comments']} ER={summ['er']} "
              f"reshare={'y' if summ['has_reshare'] else '-'} share={'y' if summ['has_share'] else '-'}", flush=True)
        time.sleep(pause)
    path = out_dir / f"posts_{date}.csv"
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLS)
        w.writerows(rows)
    print(f"\nOK {ok}/{len(targets)} member ada data post → {path}")
    return path


SAMPLE_ITEMS = [
    {"code": "C1", "taken_at": 1795200000, "media_type": 1, "product_type": "feed",
     "like_count": 52000, "comment_count": 480},
    {"code": "C2", "taken_at": 1795100000, "media_type": 2, "product_type": "clips",
     "like_count": 61000, "comment_count": 530, "play_count": 1200000, "reshare_count": 148},
    {"code": "C3", "taken_at": 1795000000, "media_type": 8, "product_type": "carousel_container",
     "like_count": 44000, "comment_count": 300, "share_count": 54},
]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--only")
    ap.add_argument("--out")
    ap.add_argument("--max", type=int, default=36)
    ap.add_argument("--pause", type=float, default=2.5)
    ap.add_argument("--sample", action="store_true", help="uji parser tanpa login")
    a = ap.parse_args()
    if a.sample:
        parsed = [parse_item(x) for x in SAMPLE_ITEMS]
        print("parse_item:")
        for p in parsed:
            print(" ", p)
        print("\nsummarize (followers=1.740.761):")
        print(" ", json.dumps(summarize("jkt48.christy", parsed, 1740761), indent=1))
    else:
        run(date=a.date, only=a.only, out_dir=a.out, max_posts=a.max, pause=a.pause)
