"""Penarikan harian: snapshot follower, tweet baru member, dan mention ke member untuk 1 hari (WIB).

Dipakai scheduler tiap 00:00 WIB. Memakai ulang infra akun/proxy/pace dari worker.py & fetch_v2.py.
Semua ditulis ke DATA_DIR/daily/ (JSONL append, aman restart) dan dicerminkan ke Google Sheets.
Hemat request: follower = 1 req/member; tweet member = 1 jendela/hari; mention = 1 jendela/hari.
"""
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import worker as w  # noqa: E402
from fetch_v2 import (TRANSIENT_WAITS, _call, fetch_member, fetch_query, count_unique,  # noqa: E402
                      read_jsonl, save_store)
from xraw import parse_raw_any  # noqa: E402
from data_rows import tweet_row  # noqa: E402

WIB = timezone(timedelta(hours=7))
DAILY = Path(os.environ.get("DATA_DIR", "/data")) / "daily"
MEMBERS = DAILY / "members"
# Tweet s.d. tanggal ini sudah ada di backfill Sheets → cron hanya append tanggal SETELAHnya (hindari dobel).
BACKFILL_UNTIL = os.environ.get("DATA_BACKFILL_UNTIL", "2026-10-24")
# Pematangan metrik: tiap malam tarik ulang N hari terakhir supaya views/like tweet matang (MIN_AGE_DAYS=7)
# sebelum dihitung dashboard. 9 = 7 hari gate + 2 hari buffer (tweet larut malam & jaga-jaga cron kelewat 1 malam).
MATURE_DAYS = int(os.environ.get("MATURE_DAYS", "9"))
# Umur (hari) tweet dianggap matang utk di-append ke tab Data (samakan dgn aggregate.MIN_AGE_DAYS=7).
# Syarat: MATURE_DAYS >= MIN_AGE_APPEND + 2, supaya hari-matang masih ikut di-refetch malam itu (metriknya segar).
MIN_AGE_APPEND = int(os.environ.get("MIN_AGE_APPEND", "7"))


def load_roster():
    import csv
    with open(ROOT / "members.csv", newline="") as f:
        return [r for r in csv.DictReader(f) if r["handle_x"]]


def classifier(roster):
    handles = {r["handle_x"].lower() for r in roster}
    official = {"officialjkt48", "jkt48_pm", "jkt48v_official"}

    def c(h):
        return "member" if h in handles else ("official" if h in official else "lain")
    return c


def append_jsonl(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def _last_follower_map():
    path = DAILY / "follower_history.jsonl"
    out = {}
    if path.exists():
        for line in open(path, encoding="utf-8"):
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            out[r["handle"]] = r["followers"]
    return out


def run_day(client, roster, day_wib, pace, guard, on_transient, sheets, log=print, on_member=None):
    """Tarik follower + tweet + mention untuk tanggal `day_wib` (date WIB). Return ringkasan.

    Tulis ke Sheets PER-MEMBER (bukan batch di akhir) supaya dataset keisi live.
    on_member(i, handle) dipanggil tiap member kelar → dipakai app.py utk rebuild dashboard live.
    """
    DAILY.mkdir(parents=True, exist_ok=True)
    MEMBERS.mkdir(parents=True, exist_ok=True)
    date_s = day_wib.strftime("%Y-%m-%d")
    start = datetime(day_wib.year, day_wib.month, day_wib.day, tzinfo=WIB)
    end = start + timedelta(days=1)
    tw_cutoff = end - timedelta(days=MATURE_DAYS)  # window rolling: re-fetch N hari terakhir utk pematangan metrik
    mature_start = start - timedelta(days=MIN_AGE_APPEND)  # hari yg tweet-nya BARU mencapai umur matang
    mature_end = mature_start + timedelta(days=1)
    mday_s = mature_start.strftime("%Y-%m-%d")
    prev_fol = _last_follower_map()
    classify = classifier(roster)
    salt = os.environ.get("HASH_SALT", "harian")
    hasher = lambda uid: "u_" + hashlib.sha256(f"{salt}:{uid}".encode()).hexdigest()[:16]
    handle_case = {r["handle_x"].lower(): r["handle_x"] for r in roster}

    fol_rows, men_rows, data_rows = [], [], []
    done_fol = {r["handle"] for r in _read_today("follower_history.jsonl", date_s)}
    done_men = {r["handle"] for r in _read_today("mentions_daily.jsonl", date_s)}
    done_data = {r["handle"] for r in _read_today("data_appended.jsonl", mday_s)}

    for i, m in enumerate(roster, 1):
        h = m["handle_x"]
        # 1) follower snapshot (1 request) — lewati kalau sudah tercatat hari ini (aman restart)
        if h not in done_fol:
            pace()
            prof = vars(_call(lambda: client.fetch_user(h), guard, on_transient))
            fol = prof.get("followers_count", 0)
            delta = fol - prev_fol[h] if h in prev_fol else 0
            rec = {"date": date_s, "handle": h, "nama": m["panggilan"], "followers": fol, "delta": delta}
            append_jsonl(DAILY / "follower_history.jsonl", rec)
            fol_rows.append([date_s, h, m["panggilan"], fol, delta])
            sheets.append_rows("follower_history", [[date_s, h, m["panggilan"], fol, delta]])  # live
            # simpan profil terbaru utk dashboard
            append_jsonl(DAILY / "profiles.jsonl", {"date": date_s, **prof})
        # 2) re-fetch N hari terakhir (pematangan metrik) -> merge/overwrite ke store _v2
        fetch_member(client, h, tw_cutoff.astimezone(timezone.utc), end.astimezone(timezone.utc),
                     MEMBERS / f"{h}_v2.json", pace=pace, on_rate_limit=guard, on_transient=on_transient,
                     log=lambda s: None, keep_prev=True)
        # 2b) append tweet yang BARU MATANG (umur ~7 hari) ke tab Data dgn metrik matang — bukan saat baru diposting.
        #     Tweet hari-matang baru saja di-refetch di langkah 2, jadi metriknya sudah final.
        if h not in done_data and mday_s > BACKFILL_UNTIL:
            drows, store_path = [], MEMBERS / f"{h}_v2.json"
            if store_path.exists():
                try:
                    store = json.loads(store_path.read_text(encoding="utf-8", errors="replace"))
                    for t in store.get("tweets", {}).values():
                        tw = datetime.fromisoformat(t["created_at"]).astimezone(WIB)
                        if mature_start <= tw < mature_end:
                            drows.append(tweet_row(h, m["panggilan"], m["tim"], t, handle_case))
                except Exception:
                    drows = []
            if drows:
                sheets.append_rows("Data", drows)  # metrik sudah matang (di-refetch tiap malam sampai umur 7 hari)
            data_rows.extend(drows)
            append_jsonl(DAILY / "data_appended.jsonl", {"date": mday_s, "handle": h, "n": len(drows)})
        # 3) mention ke member hari itu (tanpa reply/retweet)
        if h not in done_men:
            handles = [x for x in (h, (m.get("former_handle") or "").strip()) if x]
            q = f"({' OR '.join('@' + x for x in handles)}) {' '.join('-from:' + x for x in handles)} " \
                "-filter:replies -filter:nativeretweets"
            label = f"mention_{h}_{date_s}"
            fetch_query(client, label, q, lambda x: parse_raw_any(x, classify, hasher),
                        start.astimezone(timezone.utc), end.astimezone(timezone.utc), DAILY / "mentions",
                        timedelta(days=1), unit="time", pace=pace, on_rate_limit=guard,
                        on_transient=on_transient, log=lambda s: None)
            rows = read_jsonl(DAILY / "mentions" / f"{label}.jsonl")
            vals = [r for r in rows.values() if r.get("kind") != "Repost"]
            men = len(vals)
            uniq = len({r["author_key"] for r in vals})
            mv = sum(r["metrics"]["views"] for r in vals)
            rec = {"date": date_s, "handle": h, "nama": m["panggilan"], "mentions": men,
                   "unique_authors": uniq, "mention_views": mv}
            append_jsonl(DAILY / "mentions_daily.jsonl", rec)
            men_rows.append([date_s, h, m["panggilan"], men, uniq, mv])
            sheets.append_rows("mentions_daily", [[date_s, h, m["panggilan"], men, uniq, mv]])  # live
        log(f"  {i}/{len(roster)} {m['panggilan']}")
        if on_member:  # rebuild dashboard live per-member
            try:
                on_member(i, h)
            except Exception as e:
                log(f"   (update dashboard gagal: {type(e).__name__})")

    # Sheets sudah ditulis per-member di atas; ini hanya ringkasan.
    return {"date": date_s, "followers": len(fol_rows), "mentions": len(men_rows), "posts": len(data_rows)}


def _read_today(fname, date_s):
    path = DAILY / fname
    if not path.exists():
        return []
    out = []
    for line in open(path, encoding="utf-8"):
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("date") == date_s:
            out.append(r)
    return out
