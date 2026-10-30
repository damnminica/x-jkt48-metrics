"""Bangun file job (jobs/<name>.json) dari dataset SSK.

Pakai:
    python3 build_jobs.py [datasets/ssk2024.xlsx] [jobs/ssk2024.json]

Cakupan (keputusan user 2026-10-24): member Active + member Graduate yang berperingkat.
Tiap member menghasilkan task:
  - member  : metrik tweet member (from:handle), jendela mingguan
  - mention : tweet orang lain yang menyebut @member (handle sekarang + lama), tanpa reply, jendela harian
  - hashtag : tiap hashtag kampanye (#...), dibatasi konteks JKT48/member supaya tidak tercampur hashtag umum
  - tagline : tagline tanpa # (nonaktif default; terlalu umum untuk dicari sendirian)
Query di file JSON bisa diedit manual sebelum dijalankan.
"""
import csv
import json
import re
import sys
from pathlib import Path

from openpyxl import load_workbook

BASE = Path(__file__).parent
NAME = "ssk2024"
# periode analisis (WIB): pengumuman SSK 2024 (17 Des 2023, konser Flowerful) s.d. akhir 2024.
# fetch dimulai sehari lebih awal karena search memakai tanggal UTC.
ANALYSIS_START, ANALYSIS_END = "2023-12-17", "2024-12-31"
FETCH_START, FETCH_END = "2023-12-16", "2025-01-01"   # FETCH_END eksklusif
# handle X sekarang untuk member yang sudah lulus (dicocokkan dengan akun yang di-follow @officialJKT48)
GRADUATE_CURRENT = {"shania gracia": "_shaniagracia31", "indira seruni": "indiraseruni__",
                    "cathleen nixie": "cathleenixie8"}
GRADUATE_NICK = {"shania gracia": "Gracia", "indira seruni": "Indira", "cathleen nixie": "Cathy"}
OFFICIAL = ["officialjkt48", "jkt48_pm", "jkt48v_official", "jkt48tour", "_jkt48teamj", "_jkt48teamkiii",
            "_jkt48teamt", "yokosojkt48", "filmjkt48"]


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def read_dataset(path):
    ws = load_workbook(path, read_only=True).active
    rows = list(ws.iter_rows(values_only=True))
    head = [str(h).strip() for h in rows[0]]
    return [dict(zip(head, r)) for r in rows[1:] if r and r[0]]


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else BASE / "datasets" / "ssk2024.xlsx"
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else BASE / "jobs" / f"{NAME}.json"
    with open(BASE / "members.csv", newline="") as f:
        roster = {r["nama"].lower(): r for r in csv.DictReader(f)}
    data = read_dataset(src)

    tasks, members, fanbases, problems = [], [], [], []
    for r in data:
        name, status, rank = r["Member"].strip(), (r["Status"] or "").strip(), str(r["Rank"]).strip()
        ranked = rank.isdigit()
        if not (status == "Active" or (status == "Graduate" and ranked)):
            continue
        info = roster.get(name.lower(), {})
        handle = info.get("handle_x") or GRADUATE_CURRENT.get(name.lower(), "")
        if not handle:
            problems.append(f"{name}: handle X tidak ditemukan")
            continue
        former = (r.get("Former Username (Member)") or "").strip().lstrip("@")
        fanbase_url = (r.get("Fanbase") or "").strip()
        fanbase = fanbase_url.rstrip("/").split("/")[-1] if fanbase_url else ""
        nick = info.get("panggilan") or GRADUATE_NICK.get(name.lower()) or name.split()[0]
        handles = [h for h in dict.fromkeys([handle, former]) if h]
        key = slug(nick)
        members.append({"key": key, "nama": name, "panggilan": nick, "status": status,
                        "rank_2024": int(rank) if ranked else None, "tim": info.get("tim", "Graduate"),
                        "handle": handle, "former_handle": former, "fanbase": fanbase,
                        "tagline_raw": r.get("Hashtag/Tagline") or ""})
        if fanbase:
            fanbases.append(fanbase.lower())

        tasks.append({"id": f"member:{key}", "mode": "member", "member": key, "handle": handle,
                      "window_days": 7, "enabled": True})

        mention_or = " OR ".join(f"@{h}" for h in handles)
        not_from = " ".join(f"-from:{h}" for h in handles)
        tasks.append({"id": f"mention:{key}", "mode": "mention", "member": key,
                      # tanpa reply & tanpa retweet polos (RT membawa metrik tweet asli -> menggelembungkan angka)
                      "query": f"({mention_or}) {not_from} -filter:replies -filter:nativeretweets",
                      # uji batas 2026-10-24: jendela 1 hari selalu lengkap; jendela s.d. 180 tweet masih lengkap,
                      # kebocoran 1–3% baru di ~260–300 tweet. Simulasi data Feni/Jessi 2026-10-26: jendela 3 hari
                      # yang dipecah harian bila >=120 tweet = 61–76% request jendela harian, tetap lengkap.
                      "window_hours": 72, "split_hours": 24, "split_threshold": 120,
                      "unit": "time", "empty_retries": 2, "enabled": True})

        context = " OR ".join(dict.fromkeys(
            ["JKT48", nick] + [f"@{h}" for h in handles] + ([f"@{fanbase}"] if fanbase else [])))
        raw = str(r.get("Hashtag/Tagline") or "")
        for tag in dict.fromkeys(re.findall(r"#(\w+)", raw)):
            tasks.append({"id": f"hashtag:{key}:{slug(tag)}", "mode": "hashtag", "member": key, "tag": tag,
                          "query": f"#{tag} ({context}) -filter:nativeretweets",
                          "query_bare": f"#{tag} -filter:nativeretweets",
                          # volume hashtag+konteks kecil & banyak hari kosong -> jendela mingguan; minggu yang
                          # padat (>=80 tweet) otomatis ditarik ulang per hari supaya tidak ada yang hilang
                          "window_hours": 168, "unit": "time", "empty_retries": 2,
                          "split_hours": 24, "split_threshold": 80, "enabled": True})
        # tagline = bagian sebelum hashtag pertama yang bukan hashtag, mis. "GRATITUDE"
        for tl in [t.strip() for t in raw.split(",") if t.strip() and not t.strip().startswith("#")]:
            tl = re.sub(r"\s*\(.*\)$", "", tl).strip()
            if tl:
                tasks.append({"id": f"tagline:{key}:{slug(tl)[:40]}", "mode": "tagline", "member": key,
                              "tag": tl, "query": f'"{tl}" ({context}) -filter:nativeretweets',
                              "window_hours": 168, "unit": "time", "empty_retries": 2,
                              "split_hours": 24, "split_threshold": 80, "enabled": False})

    member_handles = sorted({h.lower() for m in members for h in (m["handle"], m["former_handle"]) if h}
                            | set(roster_h.lower() for roster_h in
                                  (r["handle_x"] for r in roster.values()) if roster_h))
    related = []
    if (BASE / "related_accounts.csv").exists():
        with open(BASE / "related_accounts.csv", newline="") as f:
            related = [r["handle"].lower() for r in csv.DictReader(f)]

    job = {
        "name": NAME,
        "description": "SSK 2024: metrik member, mention fans (tanpa reply) & hashtag kampanye",
        "analysis_start_wib": ANALYSIS_START, "analysis_end_wib": ANALYSIS_END,
        "fetch_start_utc": FETCH_START, "fetch_end_utc": FETCH_END,
        "source_dataset": str(src.name),
        # fase kampanye (tanggal WIB, inklusif) & tanggal penting untuk analisis
        "phases": [{"name": "Pra-voting", "start": "2023-12-17", "end": "2024-08-31"},
                   {"name": "Voting", "start": "2024-09-01", "end": "2024-12-09"},
                   {"name": "Pasca-voting", "start": "2024-12-10", "end": "2024-12-31"}],
        "events": [{"date": "2023-12-17", "name": "Pengumuman SSK 2024 (konser Flowerful, Graha Unesa)"},
                   {"date": "2024-09-01", "name": "Voting dibuka"},
                   {"date": "2024-09-28", "name": "Hasil sementara 1 (Road to Sousenkyo, ICE BSD)"},
                   {"date": "2024-10-31", "name": "Hasil sementara 2"},
                   {"date": "2024-12-09", "name": "Voting ditutup"},
                   {"date": "2024-12-15", "name": "Hasil akhir (konser Wonderland, Indonesia Arena)"}],
        "members": members,
        "known_accounts": {"member": sorted(set(member_handles) | set(related)),
                           "fanbase": sorted(set(fanbases)), "official": OFFICIAL},
        "tasks": tasks,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(job, ensure_ascii=False, indent=1), encoding="utf-8")
    by_mode = {}
    for t in tasks:
        by_mode.setdefault(t["mode"], [0, 0])
        by_mode[t["mode"]][0 if t["enabled"] else 1] += 1
    print(f"{out}: {len(members)} member; task aktif/nonaktif per mode: {by_mode}")
    for p in problems:
        print("PERINGATAN:", p)


if __name__ == "__main__":
    main()
