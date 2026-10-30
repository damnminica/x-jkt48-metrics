"""Baca tweet langsung dari respons GraphQL X, termasuk penanda reply/quote/repost
yang dibuang parser twitter-cli."""
import re
from datetime import datetime


def _unwrap(result):
    # tweet dengan batasan visibilitas dibungkus TweetWithVisibilityResults
    if result and result.get("__typename") == "TweetWithVisibilityResults":
        return result.get("tweet") or {}
    return result or {}


def _screen_name(result):
    user = ((result.get("core") or {}).get("user_results") or {}).get("result") or {}
    return (user.get("core") or {}).get("screen_name") or (user.get("legacy") or {}).get("screen_name") or ""


def _text(result):
    note = (((result.get("note_tweet") or {}).get("note_tweet_results") or {}).get("result") or {}).get("text")
    legacy = result.get("legacy") or {}
    text = note or legacy.get("full_text", "")
    if not note:
        # buang "@a @b " otomatis di depan reply (display_text_range)
        rng = legacy.get("display_text_range")
        if rng and rng[0] > 0:
            text = text[rng[0]:]
    return text


def _metrics(result):
    lg = result.get("legacy") or {}
    views = ((result.get("views") or {}).get("count")) or 0
    return {"likes": int(lg.get("favorite_count") or 0), "retweets": int(lg.get("retweet_count") or 0),
            "replies": int(lg.get("reply_count") or 0), "quotes": int(lg.get("quote_count") or 0),
            "views": int(views), "bookmarks": int(lg.get("bookmark_count") or 0)}


def _media(result):
    lg = result.get("legacy") or {}
    return [m.get("type", "") for m in ((lg.get("extended_entities") or {}).get("media") or [])]


def parse_raw_tweet(result, owner):
    """Satu tweet milik `owner` (atau repost oleh owner) -> dict datar dengan kategori."""
    result = _unwrap(result)
    legacy = result.get("legacy") or {}
    if not legacy.get("id_str"):
        return None
    author = _screen_name(result)
    if author.lower() != owner.lower():
        return None  # tweet orang lain yang ikut muncul (mis. tweet induk dalam percakapan)

    rt = _unwrap((legacy.get("retweeted_status_result") or {}).get("result"))
    reply_to = legacy.get("in_reply_to_screen_name") or ""
    if rt:
        kind, src = "Repost", rt
    elif legacy.get("in_reply_to_status_id_str"):
        kind, src = ("Reply (thread sendiri)" if reply_to.lower() == owner.lower() else "Reply"), result
    elif legacy.get("is_quote_status"):
        kind, src = "Quote", result
    else:
        kind, src = "Original", result

    return {
        "id": legacy["id_str"],
        # waktu dari tweet luar = kapan owner memposting/merepost
        "created_at": datetime.strptime(legacy["created_at"], "%a %b %d %H:%M:%S %z %Y").isoformat(),
        "kind": kind,
        "reply_to": reply_to if kind.startswith("Reply") else "",
        "orig_author": _screen_name(rt) if rt else "",
        "orig_id": (rt.get("legacy") or {}).get("id_str", "") if rt else "",
        "text": _text(src),
        "media": _media(src),
        # untuk repost, angka milik tweet asli
        "metrics": _metrics(src),
    }


def _user(result):
    """Info penulis: id, handle, follower, tanggal akun dibuat, centang biru."""
    u = ((result.get("core") or {}).get("user_results") or {}).get("result") or {}
    core, lg = u.get("core") or {}, u.get("legacy") or {}
    created = core.get("created_at") or lg.get("created_at") or ""
    try:
        created = datetime.strptime(created, "%a %b %d %H:%M:%S %z %Y").date().isoformat() if created else ""
    except ValueError:
        created = ""
    return {"id": u.get("rest_id", ""), "handle": core.get("screen_name") or lg.get("screen_name") or "",
            "followers": int(lg.get("followers_count") or 0), "created": created,
            "verified": bool(u.get("is_blue_verified") or lg.get("verified"))}


def parse_raw_any(result, classify_author, hash_id):
    """Tweet dari penulis siapa pun (untuk mode mention/hashtag) -> dict datar.

    classify_author(handle_lower) -> 'member' | 'fanbase' | 'official' | 'lain'.
    Penulis 'lain' (fans individu) disimpan anonim: handle & id diganti hash_id(user_id),
    teks tidak disimpan (hanya hashtag/mention/metrik) demi privasi.
    """
    result = _unwrap(result)
    legacy = result.get("legacy") or {}
    if not legacy.get("id_str"):
        return None
    user = _user(result)
    author_type = classify_author(user["handle"].lower())
    rt = _unwrap((legacy.get("retweeted_status_result") or {}).get("result"))
    reply_to = legacy.get("in_reply_to_screen_name") or ""
    if rt:
        kind, src = "Repost", rt
    elif legacy.get("in_reply_to_status_id_str"):
        kind, src = "Reply", result
    elif legacy.get("is_quote_status"):
        kind, src = "Quote", result
    else:
        kind, src = "Original", result
    ent = (src.get("legacy") or {}).get("entities") or {}
    public = author_type != "lain"
    # teks repost milik penulis tweet asli; simpan hanya kalau penulis asli juga akun publik (member/fanbase/resmi)
    src_public = public if src is result else (public and classify_author(_screen_name(src).lower()) != "lain")
    quoted = _unwrap((result.get("quoted_status_result") or {}).get("result"))

    def keep(handle):
        """Handle akun lain hanya disimpan kalau akun publik; handle fans individu dibuang."""
        handle = (handle or "").lower()
        return handle if handle and classify_author(handle) != "lain" else ""

    return {
        "id": legacy["id_str"],
        "created_at": datetime.strptime(legacy["created_at"], "%a %b %d %H:%M:%S %z %Y").isoformat(),
        "kind": kind,
        "author": user["handle"] if public else "",
        "author_key": user["handle"].lower() if public else hash_id(user["id"]),
        "author_type": author_type,
        "author_followers": user["followers"],
        "author_created": user["created"],
        "author_verified": user["verified"],
        "reply_to": keep(reply_to) if kind == "Reply" else "",
        "quoted_author": keep(_screen_name(quoted)) if quoted else "",
        "mentions": sorted({keep(m.get("screen_name")) for m in ent.get("user_mentions") or []} - {""}),
        "hashtags": sorted({h.get("text", "").lower() for h in ent.get("hashtags") or []} - {""}),
        "lang": legacy.get("lang", ""),
        "text": _text(src) if src_public else "",
        "media": _media(src),
        "metrics": _metrics(src),
    }


def iter_tweet_results(node):
    """Cari semua objek tweet_results.result di respons (entri biasa & modul percakapan)."""
    if isinstance(node, dict):
        tr = node.get("tweet_results")
        if isinstance(tr, dict) and tr.get("result"):
            yield tr["result"]
        for k, v in node.items():
            if k != "tweet_results":
                yield from iter_tweet_results(v)
    elif isinstance(node, list):
        for v in node:
            yield from iter_tweet_results(v)


def bottom_cursor(instructions):
    for ins in instructions or []:
        entries = ins.get("entries") or ([ins["entry"]] if "entry" in ins else [])
        for e in entries:
            if e.get("entryId", "").startswith("cursor-bottom"):
                c = e.get("content") or {}
                return c.get("value") or (c.get("itemContent") or {}).get("value")
    return None


TCO = re.compile(r"\s*https://t\.co/\w+\s*$")
