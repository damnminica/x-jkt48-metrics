"""Baris dataset level-tweet untuk Google Sheets (tab "Data"), meniru sheet Data di Excel full1.

Dipakai bersama oleh backfill_sheets.py (muat 1 tahun sekaligus) dan fetch_daily.py
(tiap hari append tweet baru). Satu sumber kolom supaya backfill & harian konsisten.
"""
from datetime import datetime, timedelta, timezone

WIB = timezone(timedelta(hours=7))
HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]

# Kolom = persis sheet "Data" di Excel full1.
HEADER = ["Handle", "Panggilan", "Tim", "Tanggal (WIB)", "Bulan", "Hari", "Jam", "Kategori", "Grup",
          "Membalas / akun asli", "Like", "Retweet", "Reply", "Quote", "Views", "Bookmark", "Interaksi",
          "Teks", "Link"]


def group_of(kind):
    return "Post utama" if kind in ("Original", "Quote") else "Repost" if kind == "Repost" else "Reply"


def tweet_row(handle, panggilan, tim, t, handle_case=None):
    """Satu baris dataset dari sebuah tweet store (_v2). handle_case: map lower->handle member utk normalisasi target."""
    w = datetime.fromisoformat(t["created_at"]).astimezone(WIB)
    kind = t["kind"]
    met = t["metrics"]
    target = (t.get("reply_to") or t.get("orig_author") or "")
    if handle_case and target.lower() in handle_case:
        target = handle_case[target.lower()]
    if kind == "Repost" and t.get("orig_author") and t.get("orig_id"):
        link = f"https://x.com/{t['orig_author']}/status/{t['orig_id']}"
    else:
        link = f"https://x.com/{handle}/status/{t['id']}"
    inter = met["likes"] + met["retweets"] + met["replies"] + met["quotes"]
    return [handle, panggilan, tim, w.strftime("%Y-%m-%d %H:%M"), w.strftime("%Y-%m"),
            HARI[w.weekday()], w.hour, kind, group_of(kind), target,
            met["likes"], met["retweets"], met["replies"], met["quotes"], met["views"],
            met.get("bookmarks", 0), inter, t.get("text", ""), link]
