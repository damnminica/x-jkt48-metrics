"""Fetcher metrik Instagram member JKT48 — server-side, headless, tanpa login.

Trik: UA crawler (Googlebot) membuat instagram.com menyajikan HTML SSR penuh yang
menanam JSON profil EKSAK ("follower_count", "following_count", is_verified, dll),
plus og:description untuk jumlah post. Jalan di server headless (Railway/cron) —
tak butuh browser, Playwright, cookie, atau akun cadangan.

Pakai:
    python ig_fetch.py                 # tarik semua akun -> snapshots/ig_<today>.csv
    python ig_fetch.py --date 2026-11-22
    python ig_fetch.py --only jkt48.christy,jkt48.freya
"""
import argparse
import csv
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("pip install requests")

HERE = Path(__file__).resolve().parent
WIB = timezone(timedelta(hours=7))

# UA crawler: memicu IG mengirim HTML SSR dengan JSON profil eksak + og tags.
UA = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
HEADERS = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9",
           "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
PROFILE_URL = "https://www.instagram.com/{}/"


def parse_num(s):
    """'2M' / '932K' / '1,196' / '355' -> int (fallback utk angka og yang dibulatkan)."""
    if s is None:
        return None
    s = s.replace(",", "").strip()
    m = re.match(r"^([\d.]+)\s*([KMB]?)", s, re.I)
    if not m:
        return None
    n = float(m.group(1))
    mul = {"K": 1e3, "M": 1e6, "B": 1e9}.get(m.group(2).upper(), 1)
    return int(round(n * mul))


def parse_profile(html, handle):
    """Ekstrak metrik eksak dari HTML SSR crawler. Return dict (field None jika tak ketemu).

    Anchor: profil utama = kemunculan "follower_count" pertama (IG merender profil
    target paling awal; akun terkait menyusul). Field lain diambil dari jendela di
    sekitar anchor itu (objek JSON yang sama)."""
    # posts: dari og:description (eksak); og ada di <head>, cari di seluruh html
    posts = None
    mog = re.search(r'og:description"\s+content="([^"]*)"', html)
    if mog:
        mp = re.search(r"([\d.,KMB]+)\s+Posts", mog.group(1), re.I)
        posts = parse_num(mp.group(1)) if mp else None

    mfc = re.search(r'"follower_count":(\d+)', html)
    fol = int(mfc.group(1)) if mfc else None
    win = html[max(0, mfc.start() - 4000): mfc.end() + 4000] if mfc else ""

    def gi(key):
        m = re.search(rf'"{key}":(\d+)', win)
        return int(m.group(1)) if m else None

    def gb(key):
        m = re.search(rf'"{key}":(true|false)', win)
        return (m.group(1) == "true") if m else None

    def gs(key):
        m = re.search(rf'"{key}":"((?:[^"\\]|\\.)*)"', win)
        return json.loads(f'"{m.group(1)}"') if m else None

    avail = "Page Not Found" not in html and "isn't available" not in html
    return {
        "handle": handle,
        "username_check": gs("username"),   # sanity: harus == handle
        "available": bool(avail and (fol is not None or posts is not None)),
        "follower": fol,                    # EKSAK
        "following": gi("following_count"),  # EKSAK
        "posts": posts,                     # eksak (dari og)
        "full_name": gs("full_name"),
        "is_verified": gb("is_verified"),
        "is_private": gb("is_private"),
        "pk": (re.search(r'"pk":"(\d+)"', win) or [None, None])[1],
    }


def fetch_one(handle, session, tries=3, pause=1.2):
    last = None
    for t in range(tries):
        try:
            r = session.get(PROFILE_URL.format(handle), headers=HEADERS, timeout=30)
            if r.status_code == 200 and ("follower_count" in r.text or "og:description" in r.text):
                p = parse_profile(r.text, handle)
                p["status"] = 200
                return p
            last = f"HTTP {r.status_code}"
        except Exception as e:  # noqa: BLE001
            last = str(e)[:60]
        time.sleep(pause * (t + 1))
    return {"handle": handle, "available": False, "status": last,
            "follower": None, "following": None, "posts": None,
            "full_name": None, "is_verified": None, "is_private": None, "pk": None}


def load_targets(only=None):
    """Daftar (panggilan, nama, tim, handle, status_akun) akun yang ditarik.
    Lewati status 'shared' (metriknya = u16, diwakili baris hub)."""
    members = json.loads((HERE / "members_ig.json").read_text())
    # nama/tim dari members.csv
    meta = {}
    with (HERE.parent / "members.csv").open() as f:
        for row in csv.DictReader(f):
            meta[row["panggilan"]] = (row["nama"], row["tim"])
    out, seen = [], set()
    for m in members:
        u = m.get("ig_username")
        if not u or u in seen:
            continue
        if m.get("status_akun") == "shared":
            continue
        if only and u not in only:
            continue
        seen.add(u)
        nama, tim = meta.get(m["panggilan"], (m.get("nama", ""), m.get("tim", "Trainee")))
        out.append({"panggilan": m["panggilan"], "nama": nama, "tim": tim,
                    "ig_username": u, "status_akun": m.get("status_akun", "")})
    return out


COLS = ["date", "panggilan", "nama", "tim", "ig_username", "status_akun",
        "followers", "following", "posts", "is_verified", "is_private", "status"]


def run(date=None, only=None, out_dir=None, pause=1.2):
    date = date or datetime.now(WIB).strftime("%Y-%m-%d")
    out_dir = Path(out_dir) if out_dir else (HERE / "snapshots")
    out_dir.mkdir(parents=True, exist_ok=True)
    only = set(only.split(",")) if only else None
    targets = load_targets(only)
    s = requests.Session()
    rows, ok = [], 0
    for i, t in enumerate(targets, 1):
        p = fetch_one(t["ig_username"], s, pause=pause)
        if p.get("follower") is not None:
            ok += 1
        rows.append([date, t["panggilan"], t["nama"], t["tim"], t["ig_username"],
                     t["status_akun"], p.get("follower"), p.get("following"),
                     p.get("posts"), p.get("is_verified"), p.get("is_private"), p.get("status")])
        print(f"  {i:>2}/{len(targets)} {t['ig_username']:<20} fol={p.get('follower')} post={p.get('posts')} ({p.get('status')})",
              flush=True)
        time.sleep(pause)
    path = out_dir / f"ig_{date}.csv"
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLS)
        w.writerows(rows)
    print(f"\nOK {ok}/{len(targets)} akun -> {path}")
    return path, rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--only", help="daftar handle dipisah koma")
    ap.add_argument("--out")
    ap.add_argument("--pause", type=float, default=1.2)
    a = ap.parse_args()
    run(date=a.date, only=a.only, out_dir=a.out, pause=a.pause)
