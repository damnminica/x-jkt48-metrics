"""Reshape dashboard_data.json into flat row-based dataset files for the Dashboard artifact type.

Writes dash_ds/<id>.json (arrays of row objects) + dash_meta.json (totals/takeaway).
"""
import json
import statistics as st
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).parent
d = json.loads((BASE / "dashboard_data.json").read_text())
OUT = BASE / "dash_ds"
OUT.mkdir(exist_ok=True)
M = d["members"]

# 1. members — satu baris per member (sudah urut med_views desc, rank terisi)
members = [{
    "rank": m["rank"], "nama": m["nama"], "tim": m["tim"], "followers": m["followers"],
    "post_utama": m["post_utama"], "reply": m["reply"], "repost": m["repost"], "per_week": m["per_week"],
    "med_views": m["med_views"], "med_likes": m["med_likes"], "floor_likes": m["floor_likes"],
    "er": m["er"], "views_per_1k_fol": m["views_per_1k_fol"], "total_views": m["total_views"],
    "total_bookmarks": m["total_bookmarks"],
} for m in M]
(OUT / "members.json").write_text(json.dumps(members, ensure_ascii=False))

# 2. monthly — long: nama, month, med_views, n (untuk sparkline per baris & tren)
monthly = [{"nama": m["nama"], "month": mo["m"], "med_views": mo["v"], "n": mo["n"]}
           for m in M for mo in m["monthly"]]
(OUT / "monthly.json").write_text(json.dumps(monthly, ensure_ascii=False))

# 3. team — ringkasan per tim
by_team = defaultdict(list)
for m in M:
    by_team[m["tim"]].append(m)
order = {"Dream": 0, "Love": 1, "Passion": 2, "Trainee": 3}
team = [{
    "tim": t, "n_member": len(ms), "post_utama": sum(x["post_utama"] for x in ms),
    "med_views": round(st.median([x["med_views"] for x in ms])),
    "med_er": round(st.median([x["er"] for x in ms]), 2),
    "total_views": sum(x["total_views"] for x in ms),
} for t, ms in sorted(by_team.items(), key=lambda kv: order.get(kv[0], 9))]
(OUT / "team.json").write_text(json.dumps(team, ensure_ascii=False))

# 4. top_posts — 30 teratas
top = [{"rank": i, "nama": p["n"], "date": p["t"], "views": p["v"], "likes": p["l"],
        "media": p["media"], "txt": p["txt"]} for i, p in enumerate(d["top_posts"][:30], 1)]
(OUT / "top_posts.json").write_text(json.dumps(top, ensure_ascii=False))

# 5. network — siapa membalas siapa (antar member)
(OUT / "network.json").write_text(json.dumps(
    [{"dari": n["from"], "ke": n["to"], "jumlah": n["n"]} for n in d["network"][:25]], ensure_ascii=False))

# meta/takeaway
top3 = ", ".join(m["nama"] for m in M[:3])
meta = {
    "period": d["period"], "generated": d["generated"], "n_members": len(M),
    "total_post": d["totals"]["post_utama"], "total_views": d["totals"]["views"],
    "total_views_bn": round(d["totals"]["views"] / 1e9, 2),
    "med_of_med_views": round(st.median([m["med_views"] for m in M])),
    "takeaway": (f"{len(M)} member aktif, {d['totals']['post_utama']:,}".replace(",", ".")
                 + f" post utama setahun. Views per post tertinggi: {top3}."),
}
(OUT / "dash_meta.json").write_text(json.dumps(meta, ensure_ascii=False))

for f in sorted(OUT.glob("*.json")):
    rows = json.loads(f.read_text())
    print(f"{f.name}: {len(rows) if isinstance(rows, list) else '1 obj'} baris, {f.stat().st_size} B")
print("takeaway:", meta["takeaway"])
