"""Bangun data.json untuk web dashboard dari store member + riwayat follower/mention.

5 seksi ala sheet Dashboard: (1) member & tim, (2) tren bulanan + heatmap jam×hari,
(3) efisiensi vs follower, (4) interaksi antar member, (5) komposisi post. Plus KPI tiles,
tren follower harian & tren mention harian.
"""
import csv
import json
import os
import statistics as st
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WIB = timezone(timedelta(hours=7))
MAIN = ("Original", "Quote")
MIN_AGE_DAYS = 7
HARI = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"]


def _wib(iso):
    return datetime.fromisoformat(iso).astimezone(WIB)


def _read_jsonl(path):
    out = []
    if path.exists():
        for line in open(path, encoding="utf-8", errors="replace"):
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def _load_member(path):
    """Baca satu store member; toleran byte rusak / json cacat (file bermasalah dilewati, bukan crash)."""
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:  # noqa: BLE001
        import logging
        logging.getLogger("aggregate").warning("lewati %s: %s", path.name, e)
        return None


def build(data_dir, cutoff_wib):
    data_dir = Path(data_dir)
    daily = data_dir / "daily"
    members_dir = daily / "members"
    roster = {r["handle_x"].lower(): r for r in csv.DictReader(open(ROOT / "members.csv", encoding="utf-8")) if r["handle_x"]}
    name_by = {h: r["panggilan"] for h, r in roster.items()}
    # fallback seed kalau store harian belum terisi
    seed = members_dir if any(p for p in members_dir.glob("*_v2.json") if not p.name.startswith(".")) else (ROOT / "data_vps")

    members, pairs, top_pool, young_posts = [], Counter(), [], []
    heat = defaultdict(int)          # (weekday, hour) -> count views-bearing posts
    media_tot, kind_tot = Counter(), Counter()
    for path in sorted(Path(seed).glob("*_v2.json")):
        if path.name.startswith("."):
            continue
        raw = _load_member(path)
        if not raw or "profile" not in raw or "tweets" not in raw:
            continue
        prof = raw["profile"]
        h = prof["screen_name"]
        info = roster.get(h.lower(), {})
        nama, tim = info.get("panggilan", h), info.get("tim", "?")
        gen = (info.get("generasi") or "").strip()
        fetched = datetime.fromisoformat(raw["fetched_at"])
        kinds, rows, media = Counter(), [], Counter()
        monthly, monthly_er, weekly, weekly_er = defaultdict(list), defaultdict(list), defaultdict(list), defaultdict(list)
        msum = defaultdict(lambda: {"views": 0, "replies": 0, "rt_quote": 0, "bookmarks": 0})
        wsum = defaultdict(lambda: {"views": 0, "replies": 0, "rt_quote": 0, "bookmarks": 0})
        hours, weekdays, mposts = [0] * 24, [0] * 7, []
        for t in raw["tweets"].values():
            ww = _wib(t["created_at"])
            if ww < cutoff_wib:
                continue
            kinds[t["kind"]] += 1
            kind_tot[t["kind"]] += 1
            if t["kind"] == "Reply" and (t.get("reply_to") or "").lower() in roster:
                pairs[(h.lower(), t["reply_to"].lower())] += 1
            if t["kind"] not in MAIN:
                continue
            tf = t.get("fetched_at")  # umur per-tweet saat metrik diambil; full1 lama pakai store-level
            ref = datetime.fromisoformat(tf) if tf else fetched
            if (ref - datetime.fromisoformat(t["created_at"])).total_seconds() / 86400 < MIN_AGE_DAYS:
                mtr = t["metrics"]; pv = (t.get("prev") or {}).get("views")  # post muda: tampil dgn Δ, tak dihitung di metrik matang
                young_posts.append({"h": h, "t": ww.strftime("%Y-%m-%d %H:%M"), "v": mtr["views"], "l": mtr["likes"],
                                    "rt": mtr["retweets"], "rp": mtr["replies"], "qt": mtr["quotes"], "bm": mtr.get("bookmarks", 0),
                                    "dv": (mtr["views"] - pv) if isinstance(pv, (int, float)) else None,
                                    "txt": t["text"].replace("\n", " ")[:90], "id": t["id"]})
                continue
            m = t["metrics"]
            rows.append(m)
            ym = ww.strftime("%Y-%m"); wk = ww.strftime("%G-W%V")
            rtq = m["retweets"] + m["quotes"]
            monthly[ym].append(m["views"]); weekly[wk].append(m["views"])
            if m["views"]:
                e = (m["likes"] + m["retweets"] + m["replies"] + m["quotes"]) / m["views"]
                monthly_er[ym].append(e); weekly_er[wk].append(e)
            for d in (msum[ym], wsum[wk]):
                d["views"] += m["views"]; d["replies"] += m["replies"]; d["rt_quote"] += rtq; d["bookmarks"] += m.get("bookmarks", 0)
            mt = (t["media"][0] if t["media"] else "teks").replace("animated_gif", "gif")
            media[mt] += 1
            media_tot[mt] += 1
            heat[(ww.weekday(), ww.hour)] += 1
            hours[ww.hour] += 1
            weekdays[ww.weekday()] += 1
            mposts.append({"h": h, "t": ww.strftime("%Y-%m-%d"), "v": m["views"], "l": m["likes"],
                           "media": mt, "txt": t["text"].replace("\n", " ")[:90], "id": t["id"]})
        if not rows:
            continue
        views = [m["views"] for m in rows]
        likes = [m["likes"] for m in rows]
        er = [(m["likes"] + m["retweets"] + m["replies"] + m["quotes"]) / m["views"] for m in rows if m["views"]]
        mposts.sort(key=lambda p: -p["v"])
        top_pool.extend(mposts[:50])     # top 50 post/member → cukup utk top-50 & detail top-10
        members.append({
            "handle": h, "nama": nama, "tim": tim, "gen": gen,
            "followers": prof.get("followers_count", 0), "post_utama": len(rows), "reply": kinds["Reply"],
            "repost": kinds["Repost"], "quote": kinds["Quote"],  # yang DILAKUKAN member (buat konteks lain)
            "total_bookmarks": sum(mm.get("bookmarks", 0) for mm in rows),
            # engagement yang DITERIMA member di post-nya sendiri:
            "recv_rt_quote": sum(mm["retweets"] + mm["quotes"] for mm in rows),
            "recv_replies": sum(mm["replies"] for mm in rows),
            "med_views": round(st.median(views)), "med_likes": round(st.median(likes)),
            "avg_views": round(st.mean(views)),
            "er": round(st.median(er) * 100, 2) if er else 0,
            "views_per_1k_fol": round(1000 * st.median(views) / max(1, prof.get("followers_count", 1)), 1),
            "total_views": sum(views),
            "monthly": [{"m": mo, "n": len(monthly[mo]), "med": round(st.median(monthly[mo])),
                         "avg": round(st.mean(monthly[mo])), "views": msum[mo]["views"],
                         "replies": msum[mo]["replies"], "rt_quote": msum[mo]["rt_quote"], "bookmarks": msum[mo]["bookmarks"],
                         "er": round(st.mean(monthly_er[mo]) * 100, 2) if monthly_er[mo] else 0}
                        for mo in sorted(monthly)],
            "weekly": [{"w": wkk, "n": len(weekly[wkk]), "med": round(st.median(weekly[wkk])),
                        "avg": round(st.mean(weekly[wkk])), "views": wsum[wkk]["views"],
                        "replies": wsum[wkk]["replies"], "rt_quote": wsum[wkk]["rt_quote"], "bookmarks": wsum[wkk]["bookmarks"],
                        "er": round(st.mean(weekly_er[wkk]) * 100, 2) if weekly_er[wkk] else 0}
                       for wkk in sorted(weekly)],
            "hours": hours, "weekdays": weekdays, "media": dict(media),
        })
    members.sort(key=lambda m: -m["med_views"])
    for i, m in enumerate(members, 1):
        m["rank"] = i
    top_pool.sort(key=lambda p: -p["v"])
    gens = sorted({m["gen"] for m in members if m["gen"]}, key=lambda g: (len(g), g))

    # tim
    by_team = defaultdict(list)
    for m in members:
        by_team[m["tim"]].append(m)
    order = {"Dream": 0, "Love": 1, "Passion": 2, "Trainee": 3}
    team = [{"tim": t, "n": len(ms), "med_views": round(st.median([x["med_views"] for x in ms])),
             "total_views": sum(x["total_views"] for x in ms), "post_utama": sum(x["post_utama"] for x in ms)}
            for t, ms in sorted(by_team.items(), key=lambda kv: order.get(kv[0], 9))]

    # riwayat follower & mention harian (dari store harian)
    fol_hist = _read_jsonl(daily / "follower_history.jsonl")
    men_hist = _read_jsonl(daily / "mentions_daily.jsonl")
    fol_by_day = defaultdict(lambda: {"followers": 0, "delta": 0})
    for r in fol_hist:
        fol_by_day[r["date"]]["followers"] += r["followers"]
        fol_by_day[r["date"]]["delta"] += r["delta"]
    men_by_day = defaultdict(lambda: {"mentions": 0, "authors": 0})
    for r in men_hist:
        men_by_day[r["date"]]["mentions"] += r["mentions"]
        men_by_day[r["date"]]["authors"] += r.get("unique_authors", 0)
    follower_trend = [{"date": d, **v} for d, v in sorted(fol_by_day.items())]
    mention_trend = [{"date": d, **v} for d, v in sorted(men_by_day.items())]
    # follower & delta terbaru per member
    latest_fol, latest_men = {}, {}
    fol_gain_by = defaultdict(int)
    for r in fol_hist:
        latest_fol[r["handle"]] = r
        fol_gain_by[r["handle"]] += r.get("delta", 0)  # total follower gain selama periode harian terkumpul
    for r in men_hist:
        latest_men.setdefault(r["handle"], []).append(r)
    for m in members:
        m["fol_gain"] = fol_gain_by.get(m["handle"], 0)
        fr = latest_fol.get(m["handle"])
        if fr:
            m["followers"] = fr["followers"]
            m["fol_delta"] = fr["delta"]
        mr = latest_men.get(m["handle"], [])
        m["mentions_today"] = mr[-1]["mentions"] if mr else None
        m["mention_total"] = sum(x["mentions"] for x in mr)
        m["mention_views"] = sum(x.get("mention_views", 0) for x in mr)
        m["mention_authors"] = mr[-1].get("unique_authors") if mr else None  # akun unik hari terbaru
        m["mention_days"] = len(mr)

    # leaderboard mention YANG DITERIMA member (member mana yang paling sering disebut fans)
    mention_members = sorted(
        [{"handle": m["handle"], "nama": m["nama"], "tim": m["tim"], "gen": m["gen"],
          "mentions": m["mention_total"], "views": m["mention_views"],
          "authors": m["mention_authors"], "today": m["mentions_today"], "days": m["mention_days"]}
         for m in members if m["mention_days"]],
        key=lambda x: (-x["mentions"], -x["views"]))

    total_fol = sum(m["followers"] for m in members)
    total_views = sum(m["total_views"] for m in members)
    total_post = sum(m["post_utama"] for m in members)
    avg_er = round(st.mean([m["er"] for m in members]), 2) if members else 0
    heatmap = [{"d": HARI[d], "h": hh, "n": heat.get((d, hh), 0)} for d in range(7) for hh in range(24)]

    return {
        "generated": datetime.now(WIB).strftime("%d %b %Y %H:%M WIB"),
        "cutoff": cutoff_wib.strftime("%Y-%m-%d"),
        "source": "harian" if seed == members_dir else "awal (full1)",
        "kpi": {"total_views": total_views, "total_post": total_post, "total_followers": total_fol,
                "avg_er": avg_er, "n_members": len(members)},
        "members": members, "team": team, "gens": gens, "teams": [t["tim"] for t in team],
        "top_pool": top_pool, "young_posts": sorted(young_posts, key=lambda p: p["t"], reverse=True)[:1000],
        "network": [{"dari": name_by.get(a, a), "ke": name_by.get(b, b), "n": n} for (a, b), n in pairs.most_common(25)],
        "heatmap": heatmap, "media_total": dict(media_tot), "kind_total": dict(kind_tot),
        "follower_trend": follower_trend, "mention_trend": mention_trend,
        "mention_members": mention_members,
        "mention_top": sorted(
            [{"nama": name_by.get(r["handle"], r["handle"]), "mentions": r["mentions"],
              "authors": r.get("unique_authors", 0), "date": r["date"]} for r in men_hist],
            key=lambda x: -x["mentions"])[:20],
    }


def write(data_dir, out_path, cutoff="2025-10-22"):
    cutoff_wib = datetime.strptime(cutoff, "%Y-%m-%d").replace(tzinfo=WIB)
    data = build(data_dir, cutoff_wib)
    out = Path(out_path)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, out)  # rename atomik → pembaca /data.json tak pernah lihat file separuh
    return data


if __name__ == "__main__":
    import sys
    d = write(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("DATA_DIR", "/data"),
              sys.argv[2] if len(sys.argv) > 2 else "daily_data.json")
    print("member:", len(d["members"]), "| KPI:", d["kpi"], "| hari follower:", len(d["follower_trend"]),
          "| hari mention:", len(d["mention_trend"]), "| sumber:", d["source"])
