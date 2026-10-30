"""Backfill satu kali: muat SEMUA dataset level-tweet (data_vps/*_v2.json) ke tab "Data" di Google Sheet.

Setelah ini, cron harian tinggal append baris tweet baru. Jalankan dengan env GOOGLE_SA_JSON + SHEET_ID
(mis. via `railway run`). Idempoten-kasar: tab "Data" di-CLEAR dulu lalu ditulis ulang.

  python backfill_sheets.py [data_dir] [cutoff YYYY-MM-DD]
"""
import csv
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_rows import HEADER, WIB, tweet_row  # noqa: E402

try:
    import orjson as _json
    def loads(b): return _json.loads(b)
except Exception:
    import json as _json
    def loads(b): return _json.loads(b)


def build_rows(data_dir, cutoff_wib):
    with open(ROOT / "members.csv", newline="", encoding="utf-8") as f:
        roster = {r["handle_x"].lower(): r for r in csv.DictReader(f) if r["handle_x"]}
    handle_case = {h: r["handle_x"] for h, r in roster.items()}
    triples = []  # (handle_lower, wib_iso, row) untuk sorting seperti Excel
    for p in sorted(Path(data_dir).glob("*_v2.json")):
        if p.name.startswith("."):
            continue
        raw = loads(p.read_bytes())
        prof = raw.get("profile") or {}
        h = prof.get("screen_name")
        info = roster.get((h or "").lower(), {})
        pang, tim = info.get("panggilan", h or "?"), info.get("tim", "?")
        for t in raw["tweets"].values():
            w = datetime.fromisoformat(t["created_at"]).astimezone(WIB)
            if w < cutoff_wib:
                continue
            triples.append(((h or "").lower(), w, tweet_row(h, pang, tim, t, handle_case)))
    triples.sort(key=lambda x: (x[0], x[1]))
    return [r for _, _, r in triples]


def main():
    data_dir = sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "data_vps")
    cutoff = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("CUTOFF", "2025-10-22")
    cutoff_wib = datetime.strptime(cutoff, "%Y-%m-%d").replace(tzinfo=WIB)
    rows = build_rows(data_dir, cutoff_wib)
    print(f"baris dibangun: {len(rows)} (cutoff {cutoff})")

    import gspread
    from google.oauth2.service_account import Credentials
    import json
    sa = os.environ["GOOGLE_SA_JSON"].strip()
    sa = json.loads(sa) if sa.startswith("{") else json.loads(Path(sa).read_text())
    creds = Credentials.from_service_account_info(sa, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    sh = gspread.authorize(creds).open_by_key(os.environ["SHEET_ID"].strip())
    print("sheet:", sh.title)

    try:
        ws = sh.worksheet("Data")
        ws.clear()
        print('tab "Data" ada → dibersihkan')
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title="Data", rows=len(rows) + 10, cols=len(HEADER))
        print('tab "Data" dibuat')
    ws.resize(rows=len(rows) + 1, cols=len(HEADER))

    ws.update(range_name="A1", values=[HEADER], value_input_option="RAW")
    CH = 5000
    for i in range(0, len(rows), CH):
        chunk = rows[i:i + CH]
        ws.append_rows(chunk, value_input_option="RAW")
        print(f"  ditulis {min(i + CH, len(rows))}/{len(rows)}")
    ws.resize(rows=len(rows) + 1, cols=len(HEADER))  # pangkas baris kosong trailing dari INSERT_ROWS
    print(f">>> SELESAI: {len(rows)} baris di tab 'Data'. Baris sheet sekarang: {ws.row_count}")


if __name__ == "__main__":
    main()
