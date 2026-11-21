"""Bangun ig_data.json untuk dashboard IG dari snapshots/ig_*.csv.

- Membaca semua snapshot harian (toleran beda skema: og lama vs crawler eksak).
- Time-series per member, delta follower/post (follower-delta hanya antar snapshot EKSAK
  supaya batas metode og->eksak tak bikin lonjakan palsu).
- Agregat tim, leaderboard, dan perbandingan lintas-platform IG vs X (dash_ds/members.json).
"""
import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
WIB = timezone(timedelta(hours=7))
TEAM_COLOR = {"Love": "#f43f5e", "Dream": "#38bdf8", "Passion": "#a855f7", "Trainee": "#94a3b8"}


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


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


def build(snap_dir=None, out=None):
    snap_dir = Path(snap_dir) if snap_dir else (HERE / "snapshots")
    out = Path(out) if out else (HERE / "ig_data.json")
    days = read_snapshots(snap_dir)
    dates = sorted(days)
    if not dates:
        raise SystemExit(f"Belum ada snapshot di {snap_dir}")
    latest = dates[-1]
    cur = days[latest]
    xf = x_followers()

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
