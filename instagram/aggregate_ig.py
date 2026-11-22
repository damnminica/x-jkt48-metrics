"""Bangun ig_data.json untuk dashboard IG dari snapshots/ig_*.csv.

- Membaca semua snapshot harian (toleran beda skema: og lama vs crawler eksak).
- Time-series per member, delta follower/post (follower-delta hanya antar snapshot EKSAK
  supaya batas metode og->eksak tak bikin lonjakan palsu).
- Agregat tim, leaderboard, dan perbandingan lintas-platform IG vs X (dash_ds/members.json).
"""
import csv
import json
import os
import statistics
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
WIB = timezone(timedelta(hours=7))
TEAM_COLOR = {"Love": "#f43f5e", "Dream": "#38bdf8", "Passion": "#a855f7", "Trainee": "#94a3b8"}
MATURE_DAYS = int(os.environ.get("IG_MATURE_DAYS", "3"))     # post < ini dianggap belum matang
RECENCY_DAYS = int(os.environ.get("IG_RECENCY_DAYS", "30"))  # jendela post utk agregat "terkini"
# bucket umur (hari) utk kurva pematangan
AGE_BUCKETS = [(0, 1), (1, 3), (3, 7), (7, 14), (14, 30), (30, 90)]


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _float(v):
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return None


def read_post_store(snap_dir):
    """Baca posts_store.csv (per-post, by shortcode) → list post dgn umur. [] bila belum ada."""
    p = Path(snap_dir) / "posts_store.csv"
    if not p.exists():
        return [], None
    now = int(time.time())
    posts, latest = [], 0
    with p.open() as f:
        for r in csv.DictReader(f):
            ta = _int(r.get("taken_at"))
            if ta is None:
                continue
            latest = max(latest, _int(r.get("last_fetched")) or 0)
            posts.append({
                "handle": r.get("handle"), "taken_at": ta, "age_d": (now - ta) / 86400.0,
                "is_reel": str(r.get("is_reel")) in ("1", "True", "true"),
                "likes": _int(r.get("likes")), "comments": _int(r.get("comments")),
                "views": _int(r.get("views")),
            })
    date = datetime.fromtimestamp(latest, WIB).strftime("%Y-%m-%d") if latest else None
    return posts, date


def agg_engagement(posts):
    """Agregat per handle: post MATANG (umur≥MATURE_DAYS) dalam RECENCY_DAYS terakhir."""
    by = {}
    for p in posts:
        if p["age_d"] < MATURE_DAYS or p["age_d"] > RECENCY_DAYS:
            continue
        by.setdefault(p["handle"], []).append(p)
    out = {}
    for h, ps in by.items():
        lk = [x["likes"] for x in ps if isinstance(x["likes"], int)]
        cm = [x["comments"] for x in ps if isinstance(x["comments"], int)]
        vw = [x["views"] for x in ps if x["is_reel"] and isinstance(x["views"], int)]
        if not lk:
            continue
        out[h] = {
            "n_posts": len(ps), "n_reels": sum(1 for x in ps if x["is_reel"]),
            "avg_likes": round(statistics.mean(lk)), "med_likes": round(statistics.median(lk)),
            "avg_comments": round(statistics.mean(cm)) if cm else None,
            "med_comments": round(statistics.median(cm)) if cm else None,
            "avg_views_reel": round(statistics.mean(vw)) if vw else None,
        }
    return out


def maturity_curve(posts, folmap):
    """Kurva pematangan JKT48: per bucket umur → median like-per-1k-follower + median views Reel.
    Normalisasi per follower supaya ukuran member tak mendominasi kurva."""
    out = []
    for lo, hi in AGE_BUCKETS:
        lr, vr = [], []
        for p in posts:
            if not (lo <= p["age_d"] < hi):
                continue
            fol = folmap.get(p["handle"])
            if isinstance(p["likes"], int) and fol:
                lr.append(p["likes"] / fol * 1000)
            if p["is_reel"] and isinstance(p["views"], int) and fol:
                vr.append(p["views"] / fol * 1000)
        out.append({
            "lo": lo, "hi": hi, "label": f"{lo}-{hi}hr",
            "n": len(lr),
            "med_like_per1k": round(statistics.median(lr), 1) if lr else None,
            "med_view_per1k": round(statistics.median(vr)) if vr else None,
        })
    return out


def read_snapshots(snap_dir):
    """-> {date: {handle: row}} + urutan tanggal. row dinormalisasi + 'method'."""
    days = {}
    for p in sorted(Path(snap_dir).glob("ig_*.csv")):
        date = p.stem.replace("ig_", "")
        rows = {}
        with p.open() as f:
            rd = csv.DictReader(f)
            method = "exact" if "is_verified" in (rd.fieldnames or []) else "og"
            for r in rd:
                h = r.get("ig_username")
                if not h:
                    continue
                rows[h] = {
                    "panggilan": r.get("panggilan", ""),
                    "nama": r.get("nama", ""),
                    "tim": r.get("tim", ""),
                    "handle": h,
                    "status_akun": r.get("status_akun", ""),
                    "followers": _int(r.get("followers")),
                    "following": _int(r.get("following")),
                    "posts": _int(r.get("posts")),
                    "is_verified": (r.get("is_verified") in ("True", "true", "1")),
                    "method": method,
                }
        if rows:
            days[date] = rows
    return days


def x_followers():
    """panggilan -> follower X (dari dashboard proyek X), untuk perbandingan lintas-platform."""
    out = {}
    for cand in (ROOT / "dash_ds" / "members.json", ROOT / "dashboard_data.json"):
        if cand.exists():
            try:
                data = json.loads(cand.read_text())
                arr = data if isinstance(data, list) else data.get("members", [])
                for m in arr:
                    nm = m.get("nama") or m.get("panggilan")
                    fol = m.get("followers") or m.get("follower")
                    if nm and fol:
                        out[nm] = _int(fol)
                if out:
                    return out
            except Exception:  # noqa: BLE001
                continue
    return out


def build(snap_dir=None, out=None, x_followers_map=None):
    snap_dir = Path(snap_dir) if snap_dir else (HERE / "snapshots")
    out = Path(out) if out else (HERE / "ig_data.json")
    days = read_snapshots(snap_dir)
    dates = sorted(days)
    if not dates:
        raise SystemExit(f"Belum ada snapshot di {snap_dir}")
    latest = dates[-1]
    cur = days[latest]
    xf = x_followers_map if x_followers_map is not None else x_followers()

    # time-series per handle (hanya akun, bukan baris shared)
    series = {}
    for d in dates:
        for h, r in days[d].items():
            series.setdefault(h, []).append({"d": d, "f": r["followers"], "p": r["posts"], "m": r["method"]})

    def delta(h, field):
        """Delta terbaru vs snapshot sebelumnya; follower hanya antar metode 'exact'."""
        s = series.get(h, [])
        if len(s) < 2:
            return None
        a, b = s[-2], s[-1]
        if field == "f" and (a["m"] != "exact" or b["m"] != "exact"):
            return None
        if a[field] is None or b[field] is None:
            return None
        return b[field] - a[field]

    members = []
    for h, r in cur.items():
        if r["status_akun"] == "shared_hub":
            continue  # u16 ditangani terpisah
        members.append({
            **r,
            "color": TEAM_COLOR.get(r["tim"], "#94a3b8"),
            "d_fol": delta(h, "f"),
            "d_post": delta(h, "p"),
            "x_fol": xf.get(r["panggilan"]),
            "ig_x_ratio": (round(r["followers"] / xf[r["panggilan"]], 2)
                           if r["followers"] and xf.get(r["panggilan"]) else None),
        })
    members.sort(key=lambda m: (m["followers"] is None, -(m["followers"] or 0)))
    for i, m in enumerate(members, 1):
        m["rank"] = i

    # engagement per-post (fase 3): dari posts_store, agregat MATANG & terkini + kurva maturity
    posts_all, eng_date = read_post_store(snap_dir)
    eng = agg_engagement(posts_all)
    folmap = {m["handle"]: m["followers"] for m in members if m.get("followers")}
    for m in members:
        if m["handle"] in eng:
            e = eng[m["handle"]]
            m["eng"] = e
            m["avg_likes"] = e.get("avg_likes")
            m["avg_comments"] = e.get("avg_comments")
            m["avg_views"] = e.get("avg_views_reel")
            fol = m.get("followers")
            if fol and e.get("avg_likes") is not None:
                m["er"] = round((e["avg_likes"] + (e.get("avg_comments") or 0)) / fol * 100, 2)
    maturity = maturity_curve(posts_all, folmap) if posts_all else []

    # agregat tim
    teams = {}
    for m in members:
        t = teams.setdefault(m["tim"], {"tim": m["tim"], "members": 0, "followers": 0,
                                        "posts": 0, "color": TEAM_COLOR.get(m["tim"], "#94a3b8")})
        t["members"] += 1
        t["followers"] += m["followers"] or 0
        t["posts"] += m["posts"] or 0
    teams = sorted(teams.values(), key=lambda t: -t["followers"])

    hub = cur.get("jkt48.u16")
    tot_fol = sum(m["followers"] or 0 for m in members)
    payload = out  # path output
    data_obj = {
        "generated": datetime.now(WIB).strftime("%Y-%m-%d %H:%M WIB"),
        "latest_date": latest, "dates": dates, "n_members": len(members),
        "total_followers": tot_fol, "total_posts": sum(m["posts"] or 0 for m in members),
        "avg_followers": round(tot_fol / len(members)) if members else 0,
        "u16": ({"followers": hub["followers"], "posts": hub["posts"]} if hub else None),
        "members": members, "teams": teams, "series": series, "has_x": bool(xf),
        "has_posts": bool(eng), "posts_date": eng_date,
        "maturity": maturity, "mature_days": MATURE_DAYS, "recency_days": RECENCY_DAYS,
        "n_posts_store": len(posts_all),
    }
    payload.write_text(json.dumps(data_obj, ensure_ascii=False))
    print(f"{payload.name}: {len(members)} member, {len(dates)} hari ({dates[0]}..{latest}), "
          f"total {tot_fol:,} follower, X-compare={'ya' if xf else 'tidak'}")
    return data_obj


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--snap")
    ap.add_argument("--out")
    a = ap.parse_args()
    build(snap_dir=a.snap, out=a.out)
