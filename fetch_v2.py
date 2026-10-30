"""Tarik 1 tahun tweet 1 akun lewat search per minggu, dengan kategori
Original / Reply / Reply (thread sendiri) / Quote / Repost.

Satu sumber (search) untuk seluruh periode supaya cakupan tiap bulan setara.
Progres disimpan per jendela; jalankan ulang untuk melanjutkan.

Pakai: source ~/.twitter_secrets && <python twitter-cli> fetch_v2.py HANDLE [CUTOFF] [UNTIL]
"""
import json
import os
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from twitter_cli import client as _tc
from twitter_cli.client import TwitterClient, _deep_get, FEATURES
from twitter_cli.exceptions import TwitterAPIError
from twitter_cli.graphql import FALLBACK_QUERY_IDS, _invalidate_query_id, _resolve_query_id

sys.path.insert(0, str(Path(__file__).parent))
from xraw import bottom_cursor, iter_tweet_results, parse_raw_tweet  # noqa: E402

OUT = Path(__file__).parent / "data"
DELAY = 3.0
RATE_WAIT = 15 * 60
WINDOW = timedelta(days=7)
GET_INSTR = lambda d: _deep_get(d, "data", "search_by_raw_query", "search_timeline", "timeline", "instructions")


def default_pace():
    time.sleep(DELAY * random.uniform(0.7, 1.5))


# twitter-cli mengubah semua kegagalan jadi TwitterAPIError: timeout/putus proxy/JSON rusak/'errors' di body 200
# -> status 0, 5xx apa adanya. Hanya masalah akun yang boleh menghentikan penarikan. Frasa dibuat spesifik
# supaya error parsial seperti "Missing TwitterUserNotSuspended" (tweet yang me-quote akun suspend) tidak cocok.
ACCOUNT_HINTS = ("could not authenticate", "your account is suspended", "account is suspended",
                 "temporarily locked", "account is locked", "to protect our users from spam", "unusual activity",
                 "automated behavior")
PARTIAL_ERRORS = {"n": 0}  # jumlah respons 200 yang membawa 'errors' tapi datanya tetap dipakai


def _post_tolerant(client, operation, variables):
    """POST GraphQL yang tetap mengembalikan 'data' walau body juga berisi 'errors' parsial.

    twitter-cli melempar error untuk setiap body ber-'errors', padahal X sering menambahkan error parsial
    (tweet terhapus, akun suspend yang di-quote) di samping data search yang lengkap. Dilempar hanya kalau
    data kosong (status 0) atau rate limit code 88 (dianggap 429).
    """
    qid = _resolve_query_id(operation, prefer_fallback=True, url_fetch_fn=_tc._url_fetch)
    using_fallback = qid == FALLBACK_QUERY_IDS.get(operation)

    def do(q):
        url = f"https://x.com/i/api/graphql/{q}/{operation}"
        headers = client._build_headers(url=url, method="POST")
        try:
            resp = _tc._get_cffi_session().post(url, headers=headers, timeout=30,
                                                json={"variables": variables, "queryId": q, "features": FEATURES})
        except Exception as exc:
            raise TwitterAPIError(0, f"Twitter API network error: {exc}")
        if resp.status_code >= 400:
            raise TwitterAPIError(resp.status_code, f"Twitter API error {resp.status_code}: {resp.text[:500]}")
        try:
            parsed = json.loads(resp.text)
        except (json.JSONDecodeError, ValueError):
            raise TwitterAPIError(0, "Twitter API returned invalid JSON")
        errors = parsed.get("errors") if isinstance(parsed, dict) else None
        if errors:
            code, msg = errors[0].get("code", 0), errors[0].get("message", "Unknown error")
            if code == 88:
                raise TwitterAPIError(429, f"Rate limit exceeded (code 88): {msg}")
            if not (isinstance(parsed, dict) and parsed.get("data")):
                raise TwitterAPIError(0, f"Twitter API returned errors: {msg}")
            PARTIAL_ERRORS["n"] += 1
        return parsed

    try:
        return do(qid)
    except TwitterAPIError as exc:
        if exc.status_code in (404, 422) and using_fallback:
            _invalidate_query_id(operation)
            return do(_resolve_query_id(operation, prefer_fallback=False, url_fetch_fn=_tc._url_fetch))
        raise
TRANSIENT_WAITS = (60, 300, 900, 1800, 1800)  # detik; total ~1,4 jam sebelum menyerah


def classify(e):
    msg = str(e).lower()
    if e.status_code == 429 or "rate limit" in msg:  # termasuk code 88 di body 200 (status 0)
        return "rate"
    if e.status_code in (401, 403) or any(h in msg for h in ACCOUNT_HINTS):
        return "account"
    if e.status_code == 0 or e.status_code >= 500:
        return "transient"
    return "other"


def default_transient(attempt, wait, e):
    print(f"  gangguan sementara ({e}); coba lagi {wait // 60} menit", flush=True)
    time.sleep(wait)


def _call(fn, on_rate_limit, on_transient=default_transient):
    transient = 0
    while True:
        try:
            return fn()
        except TwitterAPIError as e:
            kind = classify(e)
            if kind == "rate":
                on_rate_limit()
                continue
            if kind == "transient" and transient < len(TRANSIENT_WAITS):
                on_transient(transient, TRANSIENT_WAITS[transient], e)
                transient += 1
                continue
            raise


def wait_rate_limit():
    print(f"  rate limit, tunggu {RATE_WAIT // 60} menit...", flush=True)
    time.sleep(RATE_WAIT)


def search_page(client, query, cursor, on_rate_limit=wait_rate_limit, on_transient=default_transient,
                product="Latest"):
    variables = {"count": 40, "rawQuery": query, "querySource": "typed_query", "product": product}
    if cursor:
        variables["cursor"] = cursor
    # SearchTimeline lewat GET kena 404; X memakai POST. Error parsial di body 200 tidak menggagalkan halaman.
    return _call(lambda: _post_tolerant(client, "SearchTimeline", variables), on_rate_limit, on_transient)


def tweet_detail(client, tweet_id, on_rate_limit=wait_rate_limit):
    variables = {"focalTweetId": tweet_id, "referrer": "tweet", "with_rux_injections": False,
                 "includePromotedContent": False, "rankingMode": "Relevance", "withCommunity": True,
                 "withQuickPromoteEligibilityTweetFields": True, "withBirdwatchNotes": True, "withVoice": True}
    return _call(lambda: client._graphql_get("TweetDetail", variables, FEATURES), on_rate_limit)


def load_store(path):
    return json.loads(path.read_text()) if path.exists() else {"tweets": {}, "done": []}


def save_store(path, store):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(store, ensure_ascii=False))
    os.replace(tmp, path)  # atomik: file tidak setengah tertulis saat container mati


def fetch_member(client, handle, cutoff, until, path, pace=default_pace, on_rate_limit=wait_rate_limit, log=print,
                 on_transient=default_transient, keep_prev=False):
    """Tarik semua jendela mingguan yang belum selesai untuk `handle`; return store.

    keep_prev=True: simpan metrik sebelumnya tiap tweet di r["prev"] (views/likes + waktu) → buat Δ vs kemarin.
    """
    store = load_store(path)
    pace()
    store["profile"] = vars(_call(lambda: client.fetch_user(handle), on_rate_limit, on_transient))
    store["fetched_at"] = datetime.now(timezone.utc).isoformat()

    end = until
    while end > cutoff:
        start = max(cutoff, end - WINDOW)
        query = f"from:{handle} since:{start:%Y-%m-%d} until:{end:%Y-%m-%d}"
        if query in store["done"]:
            end = start
            continue
        cursor, pages, added = None, 0, 0
        while True:
            for attempt in range(3):
                pace()
                data = search_page(client, query, cursor, on_rate_limit, on_transient)
                instr = GET_INSTR(data)
                rows = [r for r in (parse_raw_tweet(x, handle) for x in iter_tweet_results(instr)) if r]
                # search kadang mengembalikan halaman pertama kosong padahal ada tweet; coba lagi
                if rows or cursor:
                    break
            fetched_now = datetime.now(timezone.utc).isoformat()
            for r in rows:
                old = store["tweets"].get(r["id"])
                added += old is None
                if keep_prev and old:  # simpan metrik kemarin utk Δ (jaga kalau ter-overwrite 2x semalam)
                    if old.get("fetched_at") == fetched_now:
                        r["prev"] = old.get("prev")
                    else:
                        om = old.get("metrics") or {}
                        r["prev"] = {"views": om.get("views"), "likes": om.get("likes"), "at": old.get("fetched_at")}
                r["fetched_at"] = fetched_now  # umur tweet saat metrik diambil (dipakai analysis.py)
                store["tweets"][r["id"]] = r
            pages += 1
            nxt = bottom_cursor(instr)
            if not rows or not nxt or nxt == cursor:
                break
            cursor = nxt
        store["done"].append(query)
        save_store(path, store)
        log(f"  {handle} {start:%Y-%m-%d}..{end:%Y-%m-%d}: {pages} hal, +{added}, total {len(store['tweets'])}")
        end = start
    return store


def window_query(template, start, end, unit):
    """Tempel batas waktu ke query. unit 'day' = since:/until: (tanggal, terbukti jalan);
    unit 'time' = since_time:/until_time: (detik unix) untuk jendela di bawah 1 hari."""
    if unit == "day":
        return f"{template} since:{start:%Y-%m-%d} until:{end:%Y-%m-%d}"
    return f"{template} since_time:{int(start.timestamp())} until_time:{int(end.timestamp())}"


def load_query_state(path):
    return json.loads(path.read_text()) if path.exists() else {"done": [], "windows": {}}


def fetch_query(client, label, template, parse, start, end, out_dir, window, unit="day", product="Latest",
                pace=default_pace, on_rate_limit=wait_rate_limit, on_transient=default_transient, log=print,
                max_pages=1000, empty_retries=3, split_window=None, split_threshold=None):
    """Tarik semua hasil search `template` per jendela waktu, mundur dari `end` ke `start`.

    Untuk volume besar (mention/hashtag): tweet ditambahkan ke <label>.jsonl (append-only, bisa ada duplikat
    antar jendela; dibuang saat ekspor), progres per jendela di <label>.state.json (ditulis atomik setelah
    jendela selesai). Kalau proses mati di tengah jendela, jendela itu diulang dari awal.

    Pecah otomatis: kalau jendela besar menghasilkan >= split_threshold tweet, jendela itu ditarik ulang dengan
    sub-jendela `split_window` (uji batas: jendela 7 hari berisi ~300 tweet kehilangan 1–3%, jendela 1 hari tidak).
    Return state (berisi statistik per jendela; sub-jendela ditandai "sub": true).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    state_path, rows_path = out_dir / f"{label}.state.json", out_dir / f"{label}.jsonl"
    state = load_query_state(state_path)
    state.update({"label": label, "template": template, "unit": unit, "product": product})

    def run_window(w_start, w_end, sub=False):
        query = window_query(template, w_start, w_end, unit)
        if query in state["done"]:
            return state["windows"][query]["tweets"]
        n = _fetch_window(query, w_start, w_end, sub)
        return n

    def _fetch_window(query, w_start, cur, sub):
        cursor, pages, seen, truncated = None, 0, set(), False
        with open(rows_path, "a", encoding="utf-8") as fh:
            while True:
                for attempt in range(max(1, empty_retries)):
                    pace()
                    data = search_page(client, query, cursor, on_rate_limit, on_transient, product)
                    instr = GET_INSTR(data)
                    rows = [r for r in (parse(x) for x in iter_tweet_results(instr)) if r]
                    # search kadang mengembalikan halaman pertama kosong padahal ada tweet; coba lagi
                    # (untuk hashtag yang jarang dipakai, jendela kosong itu normal -> empty_retries kecil)
                    if rows or cursor:
                        break
                fetched_now = datetime.now(timezone.utc).isoformat()
                for r in rows:
                    if r["id"] in seen:
                        continue
                    seen.add(r["id"])
                    r["fetched_at"] = fetched_now
                    fh.write(json.dumps(r, ensure_ascii=False) + "\n")
                fh.flush()
                pages += 1
                nxt = bottom_cursor(instr)
                if not rows or not nxt or nxt == cursor:
                    break
                if pages >= max_pages:
                    truncated = True  # pengaman; ditandai supaya jendela bisa dipecah lebih kecil
                    break
                cursor = nxt
            os.fsync(fh.fileno())
        state["done"].append(query)
        state["windows"][query] = {"start": w_start.isoformat(), "end": cur.isoformat(), "pages": pages,
                                   "tweets": len(seen), "truncated": truncated, "sub": sub}
        save_store(state_path, state)
        log(f"  {label} {w_start:%Y-%m-%d %H:%M}..{cur:%Y-%m-%d %H:%M}: {pages} hal, {len(seen)} tweet"
            + (" (TERPOTONG)" if truncated else "") + (" [sub]" if sub else ""))
        return len(seen)

    cur = end
    while cur > start:
        w_start = max(start, cur - window)
        n = run_window(w_start, cur)
        if split_window and split_threshold and window > split_window and n >= split_threshold:
            s_cur = cur
            while s_cur > w_start:
                s_start = max(w_start, s_cur - split_window)
                run_window(s_start, s_cur, sub=True)
                s_cur = s_start
        cur = w_start
    return state


def count_unique(path):
    """Jumlah tweet unik di <label>.jsonl (tanpa menahan isinya)."""
    ids = set()
    if path.exists():
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    ids.add(json.loads(line)["id"])
                except (json.JSONDecodeError, KeyError):
                    continue
    return len(ids)


def read_jsonl(path):
    """Baca hasil fetch_query, buang duplikat (versi terbaru per id menang)."""
    out = {}
    if not path.exists():
        return out
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue  # baris terakhir bisa terpotong kalau proses mati saat menulis
            out[r["id"]] = r
    return out


def fill_from_timeline(client, handle, cutoff, until, path, store, timeline):
    """Isi tweet yang terlewat search, dicocokkan dengan hasil timeline profil (fetch_timeline.py)."""
    missing = [t["id"] for t in json.loads(timeline.read_text())["tweets"]
               if not t["isRetweet"] and t["id"] not in store["tweets"]
               and cutoff <= datetime.fromisoformat(t["createdAtISO"]) < until]
    print(f"Isi {len(missing)} tweet timeline yang tidak muncul di search")
    for tid in missing:
        default_pace()
        for x in iter_tweet_results(tweet_detail(client, tid)):
            r = parse_raw_tweet(x, handle)
            if r and r["id"] == tid:
                store["tweets"][tid] = dict(r, source="timeline")
    save_store(path, store)


def main():
    handle = sys.argv[1].lstrip("@")
    day = lambda s: datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    cutoff = day(sys.argv[2] if len(sys.argv) > 2 else "2025-10-22")
    until = day(sys.argv[3]) if len(sys.argv) > 3 else datetime.now(timezone.utc) + timedelta(days=1)
    OUT.mkdir(exist_ok=True)
    path = OUT / f"{handle}_v2.json"

    client = TwitterClient(os.environ["TWITTER_AUTH_TOKEN"], os.environ["TWITTER_CT0"], {"maxRetries": 0})
    store = fetch_member(client, handle, cutoff, until, path)
    timeline = OUT / f"{handle}.json"
    if timeline.exists():
        fill_from_timeline(client, handle, cutoff, until, path, store, timeline)
    print(f"selesai: {path} ({len(store['tweets'])} tweet)")


if __name__ == "__main__":
    main()
