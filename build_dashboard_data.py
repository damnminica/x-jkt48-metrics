"""Hitung dataset agregat (JSON ringkas) untuk dashboard dari data_vps/<HANDLE>_v2.json.

Semua angka dari post utama (Original + Quote) kecuali disebut lain. Repost tidak dihitung di metrik.
Tweet < MIN_AGE_DAYS hari saat diambil dikeluarkan (belum matang). Waktu dikonversi ke WIB.
Output: dashboard_data.json (di-embed ke dashboard.html).
"""
import csv
import json
import statistics as st
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).parent
DATA = BASE / "data_vps"
WIB = timezone(timedelta(hours=7))
CUTOFF = datetime(2025, 10, 22, tzinfo=WIB)
MAIN = ("Original", "Quote")
MIN_AGE_DAYS = 7
HARI = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"]


def wib(iso):
    return datetime.fromisoformat(iso).astimezone(WIB)


def main():
    roster = {r["handle_x"].lower(): r for r in csv.DictReader(open(BASE / "members.csv")) if r["handle_x"]}
    members, pairs, top_posts = [], Counter(), []
    name_by_handle = {h: r["panggilan"] for h, r in roster.items()}

    for path in sorted(DATA.glob("*_v2.json")):
        raw = json.loads(path.read_text())
        prof = raw["profile"]
        handle = prof["screen_name"]
        info = roster.get(handle.lower(), {})
        fetched = datetime.fromisoformat(raw["fetched_at"])
        kinds = Counter()
        main_rows, monthly, media, hours, weekdays = [], defaultdict(list), Counter(), Counter(), Counter()
        for t in raw["tweets"].values():
            w = wib(t["created_at"])
            if w < CUTOFF:
                continue
            kinds[t["kind"]] += 1
            # reply antar member (untuk jaringan)
            if t["kind"] == "Reply" and (t["reply_to"] or "").lower() in roster:
                pairs[(handle.lower(), t["reply_to"].lower())] += 1
            if t["kind"] not in MAIN:
                continue
            age = (fetched - datetime.fromisoformat(t["created_at"])).total_seconds() / 86400
            if age < MIN_AGE_DAYS:
                continue
            m = t["metrics"]
            main_rows.append((w, m))
            monthly[w.strftime("%Y-%m")].append(m["views"])
            media[(t["media"][0] if t["media"] else "teks").replace("animated_gif", "gif")] += 1
            hours[w.hour] += 1
            weekdays[w.weekday()] += 1
            top_posts.append({"h": handle, "n": info.get("panggilan", handle), "t": w.strftime("%Y-%m-%d"),
                              "v": m["views"], "l": m["likes"], "id": t["id"], "media": t["media"][0] if t["media"] else "teks",
                              "txt": t["text"].replace("\n", " ")[:90]})
        if not main_rows:
            continue
        views = [m["views"] for _, m in main_rows]
        likes = [m["likes"] for _, m in main_rows]
        er = [(m["likes"] + m["retweets"] + m["replies"] + m["quotes"]) / m["views"]
              for _, m in main_rows if m["views"] > 0]
        days = (max(w for w, _ in main_rows) - CUTOFF).days + 1
        months = sorted(monthly)
        members.append({
            "handle": handle, "nama": info.get("panggilan", handle), "fullname": prof.get("name", ""),
            "tim": info.get("tim", "?"), "followers": prof.get("followers_count", 0),
            "post_utama": len(main_rows), "reply": kinds["Reply"], "thread": kinds["Reply (thread sendiri)"],
            "repost": kinds["Repost"],
            "med_views": round(st.median(views)), "avg_views": round(st.mean(views)),
            "med_likes": round(st.median(likes)), "avg_likes": round(st.mean(likes)),
            "floor_likes": round(st.quantiles(likes, n=10)[0]) if len(likes) >= 10 else min(likes),
            "total_views": sum(views), "total_likes": sum(likes),
            "total_bookmarks": sum(m["bookmarks"] for _, m in main_rows),
            "er": round(st.median(er) * 100, 2) if er else 0,
            "per_week": round(7 * len(main_rows) / days, 1),
            "views_per_1k_fol": round(1000 * st.median(views) / max(1, prof.get("followers_count", 1)), 1),
            "monthly": [{"m": mo, "v": round(st.median(monthly[mo])), "n": len(monthly[mo])} for mo in months],
            "media": dict(media), "hours": {str(h): hours.get(h, 0) for h in range(24)},
            "weekdays": {HARI[d]: weekdays.get(d, 0) for d in range(7)},
        })

    members.sort(key=lambda m: -m["med_views"])
    for i, m in enumerate(members, 1):
        m["rank"] = i
    top_posts.sort(key=lambda p: -p["v"])
    net = [{"from": name_by_handle.get(a, a), "to": name_by_handle.get(b, b), "n": n}
           for (a, b), n in pairs.most_common(40)]

    out = {
        "generated": datetime.now(WIB).strftime("%d %b %Y %H:%M WIB"),
        "period": f"{CUTOFF:%d %b %Y} – {max(m['monthly'][-1]['m'] for m in members)}",
        "cutoff": CUTOFF.strftime("%Y-%m-%d"),
        "n_members": len(members), "members": members, "top_posts": top_posts[:40], "network": net,
        "totals": {"post_utama": sum(m["post_utama"] for m in members),
                   "views": sum(m["total_views"] for m in members),
                   "likes": sum(m["total_likes"] for m in members)},
    }
    (BASE / "dashboard_data.json").write_text(json.dumps(out, ensure_ascii=False))
    kb = (BASE / "dashboard_data.json").stat().st_size / 1024
    print(f"{len(members)} member, {out['totals']['post_utama']} post utama, {out['totals']['views']:,} views")
    print(f"dashboard_data.json: {kb:.0f} KB")
    print("top 5 med views:", [(m["nama"], m["med_views"]) for m in members[:5]])
    print("bulan:", members[0]["monthly"][0]["m"], "..", members[0]["monthly"][-1]["m"],
          "(", len(members[0]["monthly"]), "bulan )")


if __name__ == "__main__":
    main()
