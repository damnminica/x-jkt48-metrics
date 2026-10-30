"""Tarik tweet 1 akun X mundur sampai tanggal cutoff, simpan JSON + CSV.

Fase 1: timeline profil (UserTweets) — X hanya memberi ~800 tweet terakhir.
Fase 2: sisa periode diisi lewat search "from:HANDLE since:.. until:.." per bulan.
Progres disimpan tiap halaman, jadi aman dijalankan ulang kalau terputus.

Pakai: source ~/.twitter_secrets && <python twitter-cli> -I fetch_timeline.py HANDLE [CUTOFF_YYYY-MM-DD] [SEARCH_UNTIL_YYYY-MM-DD]
"""
import csv
import json
import os
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from twitter_cli.client import TwitterClient, _deep_get, FEATURES
from twitter_cli.exceptions import TwitterAPIError
from twitter_cli.parser import parse_timeline_response
from twitter_cli.serialization import tweet_to_dict, tweet_from_dict

OUT = Path(__file__).parent / "data"
DELAY = 3.0          # detik antar halaman (diacak x0.7-1.5)
RATE_WAIT = 15 * 60  # jendela rate limit X
MAX_EMPTY = 2        # halaman kosong berturut-turut = timeline habis


def parse_dt(s):
    return datetime.strptime(s, "%a %b %d %H:%M:%S %z %Y")


class Store:
    def __init__(self, handle):
        self.path = OUT / f"{handle}.json"
        self.tweets, self.profile = {}, None
        if self.path.exists():
            raw = json.loads(self.path.read_text())
            self.profile = raw.get("profile")
            self.tweets = {t["id"]: tweet_from_dict(t) for t in raw["tweets"]}

    def add(self, tweets):
        new = [t for t in tweets if t.id not in self.tweets]
        for t in tweets:  # angka terbaru menimpa yang lama
            self.tweets[t.id] = t
        return len(new)

    def save(self):
        rows = sorted(self.tweets.values(), key=lambda t: parse_dt(t.created_at), reverse=True)
        self.path.write_text(json.dumps({"profile": self.profile, "tweets": [tweet_to_dict(t) for t in rows]},
                                        ensure_ascii=False, indent=1))
        return rows


def call(client, op, variables, get_instr):
    while True:
        try:
            # SearchTimeline lewat GET kena 404 sejak X ganti ke POST
            fetch = client._graphql_post if op == "SearchTimeline" else client._graphql_get
            data = fetch(op, variables, FEATURES)
            tweets, cursor = parse_timeline_response(data, get_instr)
            # mulai halaman 2, search menaruh cursor di TimelineReplaceEntry yang tidak dibaca parser
            for ins in get_instr(data) or []:
                entry = ins.get("entry") or {}
                if ins.get("type") == "TimelineReplaceEntry" and entry.get("entryId", "").startswith("cursor-bottom"):
                    cursor = entry["content"].get("value") or cursor
            return tweets, cursor
        except TwitterAPIError as e:
            if "429" not in str(e):
                raise
            print(f"  rate limit, tunggu {RATE_WAIT // 60} menit...", flush=True)
            time.sleep(RATE_WAIT)


def paginate(client, store, op, base_vars, get_instr, label, stop_before=None):
    cursor, empty, oldest = None, 0, None
    for page in range(1, 400):
        variables = dict(base_vars, **({"cursor": cursor} if cursor else {}))
        tweets, next_cursor = call(client, op, variables, get_instr)
        added = store.add(tweets)
        store.save()
        if tweets:
            oldest = parse_dt(tweets[-1].created_at)
        print(f"  [{label}] hal {page}: +{added}, total {len(store.tweets)}"
              + (f", terlama {oldest:%Y-%m-%d}" if oldest else ""), flush=True)
        empty = empty + 1 if not tweets else 0
        if empty >= MAX_EMPTY or not next_cursor or next_cursor == cursor:
            break
        if stop_before and oldest and oldest < stop_before:
            break
        cursor = next_cursor
        time.sleep(DELAY * random.uniform(0.7, 1.5))
    return oldest


def main():
    handle = sys.argv[1].lstrip("@")
    cutoff = datetime.strptime(sys.argv[2] if len(sys.argv) > 2 else "2025-10-22", "%Y-%m-%d").replace(tzinfo=timezone.utc)
    OUT.mkdir(exist_ok=True)
    client = TwitterClient(os.environ["TWITTER_AUTH_TOKEN"], os.environ["TWITTER_CT0"], {"requestDelay": 0, "maxRetries": 0})
    store = Store(handle)
    resumed = bool(store.tweets)
    store.profile = vars(client.fetch_user(handle))

    print("Fase 1: dilewati (lanjut dari file)" if resumed else "Fase 1: timeline profil")
    resumed or paginate(client, store, "UserTweets",
             {"count": 40, "includePromotedContent": False, "latestControlAvailable": True,
              "requestContext": "launch", "userId": store.profile["id"],
              "withQuickPromoteEligibilityTweetFields": True, "withVoice": True, "withV2Timeline": True},
             lambda d: _deep_get(d, "data", "user", "result", "timeline_v2", "timeline", "instructions"),
             "timeline", stop_before=cutoff)

    # cari batas terlama yang sudah tersambung dari timeline (abaikan tweet pinned yang lebih tua)
    # argumen ke-3 opsional: paksa batas akhir search (YYYY-MM-DD), mis. saat lanjut dari file
    if len(sys.argv) > 3:
        covered = datetime.strptime(sys.argv[3], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        own = sorted((parse_dt(t.created_at) for t in store.tweets.values()), reverse=True)
        covered = own[-2] if len(own) > 1 else datetime.now(timezone.utc)
    print(f"Fase 2: search untuk {cutoff:%Y-%m-%d} .. {covered:%Y-%m-%d}")
    end = covered + timedelta(days=1)
    while end > cutoff:
        start = max(cutoff, end - timedelta(days=30))
        q = f"from:{handle} since:{start:%Y-%m-%d} until:{end:%Y-%m-%d}"
        paginate(client, store, "SearchTimeline",
                 {"count": 40, "rawQuery": q, "querySource": "typed_query", "product": "Latest"},
                 lambda d: _deep_get(d, "data", "search_by_raw_query", "search_timeline", "timeline", "instructions"),
                 q)
        end = start

    rows = store.save()
    with open(OUT / f"{handle}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "created_at", "is_retweet", "likes", "retweets", "replies", "quotes", "views", "bookmarks", "media", "text"])
        for t in rows:
            m = t.metrics
            w.writerow([t.id, parse_dt(t.created_at).isoformat(), t.is_retweet, m.likes, m.retweets, m.replies,
                        m.quotes, m.views, m.bookmarks, ",".join(x.type for x in t.media), t.text.replace("\n", " ")])
    print(f"selesai: {OUT / handle}.csv ({len(rows)} tweet)")


if __name__ == "__main__":
    main()
