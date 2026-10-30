"""Worker (Docker di VPS/Railway): tarik 1 tahun tweet member JKT48 satu per satu, lalu kirim Excel gabungan ke Telegram.

Env wajib : TWITTER_AUTH_TOKEN, TWITTER_CT0, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
Env opsi  : TWITTER_PROXY (http://user:pass@host:port atau socks5://...; dicoba otomatis keduanya)
            MEMBERS (handle dipisah koma; default semua di members.csv), MEMBER_LIMIT (mis. 5)
            REQUIRE_PROXY (=1: diam kalau TWITTER_PROXY kosong; dipakai di Railway)
            DATA_DIR (default /data), CUTOFF (YYYY-MM-DD; default 365 hari lalu)
            REQ_PER_WINDOW (default 35 request / 15 menit), RUN_ID (ganti untuk memulai batch baru)

Aman di-restart: progres per minggu per member disimpan di DATA_DIR; batch yang sudah
terkirim tidak dijalankan ulang (worker hanya diam).
"""
import csv
import json
import os
import random
import sys
import time
import traceback
import urllib.request
import uuid
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

from twitter_cli.client import TwitterClient
from twitter_cli.exceptions import NotFoundError, TwitterAPIError

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))
from fetch_v2 import TRANSIENT_WAITS, classify, fetch_member, save_store  # noqa: E402
from export_combined import build_workbook, summary_text  # noqa: E402

DATA = Path(os.environ.get("DATA_DIR", "/data"))
WINDOW_S = 15 * 60
REQ_PER_WINDOW = int(os.environ.get("REQ_PER_WINDOW", "35"))
MAX_429_IN_ROW = 3
WIB = timezone(timedelta(hours=7))


def now_wib():
    return datetime.now(WIB).strftime("%d %b %H:%M")


# ── Telegram (langsung, tidak lewat proxy) ─────────────────────────────
def _tg(method, fields, file_path=None):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    boundary = uuid.uuid4().hex
    body = b""
    for k, v in fields.items():
        body += f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    if file_path:
        body += (f'--{boundary}\r\nContent-Disposition: form-data; name="document"; filename="{file_path.name}"\r\n'
                 "Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n").encode()
        body += file_path.read_bytes() + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/{method}", data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


def notify(text, file_path=None):
    """Kirim ke semua chat; return True kalau minimal satu berhasil."""
    print(text, flush=True)
    delivered = False
    for chat in os.environ["TELEGRAM_CHAT_ID"].split(","):
        try:
            if file_path:
                _tg("sendDocument", {"chat_id": chat.strip(), "caption": text[:1000]}, file_path)
            else:
                _tg("sendMessage", {"chat_id": chat.strip(), "text": text})
            delivered = True
        except Exception as e:  # notifikasi gagal tidak boleh menghentikan penarikan
            print(f"Telegram gagal ke {chat}: {e}", flush=True)
    return delivered


# ── Tempo: maksimal REQ_PER_WINDOW request per 15 menit + jeda acak ───────
class Pacer:
    def __init__(self, limit):
        self.limit, self.stamps, self.count = limit, deque(), 0

    def __call__(self):
        while self.stamps and time.time() - self.stamps[0] > WINDOW_S:
            self.stamps.popleft()
        if len(self.stamps) >= self.limit:
            time.sleep(max(0, WINDOW_S - (time.time() - self.stamps[0])) + random.uniform(5, 30))
            self.stamps.popleft()
        time.sleep(random.uniform(4, 12))
        self.stamps.append(time.time())
        self.count += 1


class Stop(Exception):
    """Tanda bahaya dari X: hentikan semua penarikan."""


class RateLimitGuard:
    def __init__(self):
        self.in_row = 0

    def __call__(self):
        self.in_row += 1
        if self.in_row >= MAX_429_IN_ROW:
            raise Stop(f"{self.in_row}x rate limit berturut-turut walau tempo sudah dijaga")
        notify(f"⏸️ Rate limit ({self.in_row}/{MAX_429_IN_ROW}), istirahat 20 menit. {now_wib()} WIB")
        time.sleep(20 * 60)

    def ok(self):
        self.in_row = 0


# ── Proxy: pilih skema yang jalan ─────────────────────────────────────
def exit_ip(proxy, tries=3):
    from curl_cffi import requests as cr
    for i in range(tries):
        try:
            r = cr.get("https://api.ipify.org?format=json", proxies={"https": proxy, "http": proxy} if proxy else None,
                       timeout=30, impersonate="chrome")
            return r.json()["ip"]
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(10)


def choose_proxy():
    """Return (proxy_url, exit_ip). Cek IP hanya informasi: gagal cek tidak menghentikan worker."""
    raw = os.environ.get("TWITTER_PROXY", "").strip()
    if not raw:
        try:
            return "", exit_ip("")
        except Exception:
            return "", "tidak diketahui"
    rest = raw.split("://", 1)[-1]
    schemes = ["http", "socks5h"]
    if "://" in raw:
        schemes.insert(0, raw.split("://")[0])
    for scheme in dict.fromkeys(schemes):
        candidate = f"{scheme}://{rest}"
        try:
            return candidate, exit_ip(candidate)
        except Exception as e:
            print(f"proxy {scheme} gagal: {type(e).__name__}", flush=True)
    # ipify sendiri bisa yang bermasalah; tetap lewat proxy (tidak pernah langsung) dan biarkan
    # retry error sementara di fetch_v2 yang menangani kalau proxy memang mati
    return (raw if "://" in raw else f"http://{rest}"), "tidak diketahui (cek IP gagal)"


def load_members():
    with open(BASE / "members.csv", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["handle_x"]]
    wanted = [h.strip().lstrip("@").lower() for h in os.environ.get("MEMBERS", "").split(",") if h.strip()]
    if wanted:
        rows = [r for r in rows if r["handle_x"].lower() in wanted]
    limit = int(os.environ.get("MEMBER_LIMIT", "0") or 0)
    return rows[:limit] if limit else rows


REQUIRED_ENV = ["TWITTER_AUTH_TOKEN", "TWITTER_CT0", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]


def send_excel(state, state_path, caption):
    """Kirim Excel yang sudah dibuat; tandai terkirim hanya kalau minimal satu chat menerima."""
    built = Path(state["built"])
    if built.exists() and notify(caption, built):
        state["sent"] = now_wib()
        save_store(state_path, state)
    return bool(state.get("sent"))


def idle(state, state_path, run_id):
    """Tetap hidup (container tidak restart & tidak menarik ulang); kirim ulang Excel yang belum terkirim."""
    if os.environ.get("EXIT_WHEN_DONE"):  # untuk tes lokal
        return
    retries = 0
    while True:
        time.sleep(3600)
        if state.get("built") and not state.get("sent") and retries < 24:
            retries += 1
            send_excel(state, state_path, f"📊 (kirim ulang #{retries}) Excel batch '{run_id}'. {now_wib()} WIB")


def main():
    missing = [k for k in REQUIRED_ENV if not os.environ.get(k)]
    if os.environ.get("REQUIRE_PROXY") and not os.environ.get("TWITTER_PROXY"):
        missing.append("TWITTER_PROXY (REQUIRE_PROXY aktif)")  # jangan pernah jalan dari IP datacenter
    if missing:
        # jangan crash (container akan restart terus); tunggu sampai variabel diisi & restart
        print(f"Env belum lengkap: {', '.join(missing)}. Worker diam, tidak menyentuh X.", flush=True)
        while True:
            time.sleep(3600)
    DATA.mkdir(parents=True, exist_ok=True)
    run_id = os.environ.get("RUN_ID", "default")
    state_path = DATA / f"state_{run_id}.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    if state.get("built") and not state.get("sent"):
        # penarikan sudah selesai tapi kiriman Excel sebelumnya gagal: coba kirim ulang saja, tanpa menyentuh X
        send_excel(state, state_path, f"📊 (kirim ulang) Excel batch '{run_id}'. {now_wib()} WIB")
    if state.get("built"):
        print(f"Batch {run_id} sudah selesai (terkirim: {state.get('sent') or 'belum'}). "
              "Ganti RUN_ID untuk batch baru. Diam.", flush=True)
        return idle(state, state_path, run_id)

    members = load_members()
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    # periode dikunci per batch & langsung disimpan, supaya restart di hari lain tidak menggeser
    # batas jendela mingguan (yang membuat semua minggu ditarik ulang)
    state.setdefault("cutoff", os.environ.get("CUTOFF") or (today - timedelta(days=365)).strftime("%Y-%m-%d"))
    state.setdefault("until", (today + timedelta(days=2)).strftime("%Y-%m-%d"))
    state.setdefault("finished", [])
    state.setdefault("skipped", [])
    save_store(state_path, state)
    day = lambda s: datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    cutoff, until = day(state["cutoff"]), day(state["until"])  # cutoff = tanggal WIB
    fetch_from = cutoff - timedelta(days=1)  # search memakai tanggal UTC; mundur sehari agar 00:00-06:59 WIB ikut
    kept_from = (cutoff - timedelta(hours=7)).isoformat()

    try:
        proxy, ip = choose_proxy()
        if proxy:
            os.environ["TWITTER_PROXY"] = proxy  # dibaca twitter-cli saat membuat sesi
        client = TwitterClient(os.environ["TWITTER_AUTH_TOKEN"], os.environ["TWITTER_CT0"],
                               {"maxRetries": 0, "requestDelay": 0})
        todo = [m for m in members if m["handle_x"] not in state["finished"]]
        notify(f"▶️ Mulai batch '{run_id}': {len(todo)} dari {len(members)} member, periode sejak "
               f"{cutoff:%d %b %Y} WIB. Exit IP: {ip}{' (proxy)' if proxy else ' (langsung)'}. "
               f"Tempo {REQ_PER_WINDOW} req/15 menit. {now_wib()} WIB")

        pacer, guard = Pacer(REQ_PER_WINDOW), RateLimitGuard()

        def pace():
            pacer()
            guard.ok()  # request sebelumnya sukses

        def on_transient(attempt, wait, e):
            notify(f"⚠️ Gangguan jaringan/X (HTTP {e.status_code}: {str(e)[:120]}). Coba lagi {wait // 60} menit "
                   f"({attempt + 1}/{len(TRANSIENT_WAITS)}). {now_wib()} WIB")
            time.sleep(wait)

        for n, m in enumerate(todo, len(members) - len(todo) + 1):
            handle = m["handle_x"]
            t0, c0 = time.time(), pacer.count
            try:
                store = fetch_member(client, handle, fetch_from, until, DATA / f"{handle}_v2.json", pace=pace,
                                     on_rate_limit=guard, on_transient=on_transient,
                                     log=lambda s: print(s, flush=True))
            except NotFoundError as e:  # handle berganti/akun hilang: lewati member ini saja
                state["skipped"].append(handle)
                state["finished"].append(handle)
                save_store(state_path, state)
                notify(f"⏭️ {n}/{len(members)} @{handle} dilewati: {str(e)[:150]}. {now_wib()} WIB")
                continue
            state["finished"].append(handle)
            save_store(state_path, state)
            kept = sum(1 for t in store["tweets"].values() if t["created_at"] >= kept_from)
            notify(f"✅ {n}/{len(members)} {m['panggilan']} (@{handle}): {kept} tweet, "
                   f"{pacer.count - c0} request, {(time.time() - t0) / 60:.0f} menit. {now_wib()} WIB")
            if n < len(members):
                time.sleep(random.uniform(120, 300))  # jeda antar member

        out = DATA / f"JKT48_metrik_X_{run_id}_{datetime.now(WIB):%Y%m%d}.xlsx"
        build_workbook(members, DATA, cutoff.replace(tzinfo=None), out)
        state["built"] = str(out)
        save_store(state_path, state)
        # pratinjau Excel di HP tidak menghitung rumus, jadi ringkasan juga dikirim sebagai teks
        notify(summary_text(members, DATA, cutoff.replace(tzinfo=None)))
        if not send_excel(state, state_path, f"📊 Selesai! {len(members)} member, {pacer.count} request. "
                                             f"Buka di Excel/Google Sheets agar rumus terhitung. {now_wib()} WIB"):
            print("Kirim Excel gagal; dicoba ulang tiap jam.", flush=True)
    except Stop as e:
        notify(f"🛑 Berhenti: {e}. Progres tersimpan; cek akun cadangan di browser sebelum lanjut. {now_wib()} WIB")
    except TwitterAPIError as e:
        kind = classify(e)
        why = {"account": "Kemungkinan cookie kedaluwarsa atau akun cadangan terkunci; cek di browser.",
               "transient": "Gangguan jaringan/proxy/X berlanjut ~1,4 jam walau sudah dicoba ulang.",
               }.get(kind, "Respons X tidak dikenal (mungkin endpoint berubah).")
        notify(f"🛑 Berhenti: X membalas HTTP {e.status_code} ({str(e)[:200]}). {why} Progres tersimpan; "
               f"restart worker untuk melanjutkan. {now_wib()} WIB")
    except Exception as e:
        traceback.print_exc()
        notify(f"🛑 Error tak terduga: {type(e).__name__}: {str(e)[:300]}. Progres tersimpan. {now_wib()} WIB")
    idle(state, state_path, run_id)


if __name__ == "__main__":
    main()
