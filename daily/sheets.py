"""Penyimpan dataset di Google Sheets (service account). Degil-aman: kalau kredensial tidak ada,
fungsi menjadi no-op yang mencatat peringatan, supaya worker & web tetap jalan tanpa Sheets.

Env:
  GOOGLE_SA_JSON   : isi JSON service account (satu baris) ATAU path ke file .json
  SHEET_ID         : id Google Sheet tujуan (bagikan sheet ke email service account sebagai Editor)

Worksheet yang dipakai (dibuat otomatis kalau belum ada), tiap baris = satu hari:
  follower_history : date, handle, nama, followers, delta
  mentions_daily   : date, handle, nama, mentions, unique_authors, mention_views
  members_snapshot : (ditimpa tiap hari) ringkasan member terbaru untuk dashboard
"""
import json
import logging
import os
from pathlib import Path

log = logging.getLogger("sheets")

HEADERS = {
    "follower_history": ["date", "handle", "nama", "followers", "delta"],
    "mentions_daily": ["date", "handle", "nama", "mentions", "unique_authors", "mention_views"],
    "members_snapshot": ["date", "rank", "handle", "nama", "tim", "followers", "post_utama",
                         "med_views", "med_likes", "er", "views_per_1k_fol"],
    # Dataset level-tweet (lihat data_rows.HEADER). Di-backfill sekali, lalu cron append tiap hari.
    "Data": ["Handle", "Panggilan", "Tim", "Tanggal (WIB)", "Bulan", "Hari", "Jam", "Kategori", "Grup",
             "Membalas / akun asli", "Like", "Retweet", "Reply", "Quote", "Views", "Bookmark", "Interaksi",
             "Teks", "Link"],
}


def _creds():
    raw = os.environ.get("GOOGLE_SA_JSON", "").strip()
    if not raw:
        return None
    if raw.startswith("{"):
        return json.loads(raw)
    p = Path(raw)
    return json.loads(p.read_text()) if p.exists() else None


class Sheets:
    """Pembungkus tipis gspread. .enabled False kalau kredensial/lib tidak ada."""

    def __init__(self):
        self.enabled = False
        self.sh = None
        sa = _creds()
        sheet_id = os.environ.get("SHEET_ID", "").strip()
        if not sa or not sheet_id:
            log.warning("Google Sheets nonaktif: GOOGLE_SA_JSON / SHEET_ID belum diset.")
            return
        try:
            import gspread
            from google.oauth2.service_account import Credentials
            scopes = ["https://www.googleapis.com/auth/spreadsheets"]
            creds = Credentials.from_service_account_info(sa, scopes=scopes)
            self.sh = gspread.authorize(creds).open_by_key(sheet_id)
            self.enabled = True
            log.info("Google Sheets aktif: %s", self.sh.title)
        except Exception as e:  # lib belum terpasang / kredensial salah / sheet tak dibagikan
            log.warning("Google Sheets gagal diinisialisasi (%s); jalan tanpa Sheets.", e)

    def _ws(self, name):
        import gspread
        try:
            return self.sh.worksheet(name)
        except gspread.WorksheetNotFound:
            ws = self.sh.add_worksheet(title=name, rows=1000, cols=max(4, len(HEADERS.get(name, [])) + 1))
            if name in HEADERS:
                ws.append_row(HEADERS[name])
            return ws

    def append_rows(self, name, rows):
        """Tambahkan baris (list of list) ke worksheet. Aman kalau nonaktif."""
        if not self.enabled or not rows:
            return 0
        try:
            self._ws(name).append_rows(rows, value_input_option="RAW")
            return len(rows)
        except Exception as e:
            log.warning("append_rows %s gagal: %s", name, e)
            return 0

    def replace(self, name, header, rows):
        """Ganti seluruh isi worksheet (untuk snapshot yang ditimpa tiap hari)."""
        if not self.enabled:
            return 0
        try:
            ws = self._ws(name)
            ws.clear()
            ws.update([header] + rows, value_input_option="RAW")
            return len(rows)
        except Exception as e:
            log.warning("replace %s gagal: %s", name, e)
            return 0

    def read(self, name):
        """Semua baris sebagai list of dict (header baris pertama). [] kalau nonaktif/kosong."""
        if not self.enabled:
            return []
        try:
            return self._ws(name).get_all_records()
        except Exception as e:
            log.warning("read %s gagal: %s", name, e)
            return []
