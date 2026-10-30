"""Sanity check + analisis deskriptif data X member JKT48 (tanpa request baru ke X).

Pakai:
    python analysis.py OUT_DIR FILE_v2.json [FILE_v2.json ...] [--timeline HANDLE=FILE.json] [--cutoff YYYY-MM-DD]

Hanya membaca file <HANDLE>_v2.json hasil fetch_v2.py/worker.py. Menghasilkan OUT_DIR/report.md,
OUT_DIR/member_profile.csv dan OUT_DIR/tweets_clean.csv. Ambang PASS/WARN mengikuti
research/04_kritik_dan_sanity_check.md.
"""
import argparse
import csv
import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats
from statsmodels.stats.multitest import multipletests

BASE = Path(__file__).parent
WIB = timezone(timedelta(hours=7))
METRICS = ["likes", "retweets", "replies", "quotes", "views", "bookmarks"]
KINDS = ["Original", "Quote", "Reply", "Reply (thread sendiri)", "Repost"]
MAIN = ("Original", "Quote")
MIN_AGE_DAYS = 7      # tweet lebih muda dikeluarkan dari agregat engagement
MIN_N = 10            # sel/kelompok dengan n lebih kecil tidak dipakai untuk keputusan
MIN_N_EFFECT = 30     # kategori konten dengan n lebih kecil digabung jadi "lain"
OFFICIAL = {"officialjkt48", "jkt48_pm", "jkt48v_official", "jkt48tour", "_jkt48teamj", "_jkt48teamkiii",
            "_jkt48teamt", "yokosojkt48", "filmjkt48"}
SISTER_RE = re.compile(r"jkt48v|klp48|akb48|bnk48|mnl48|snh48|hkt48|ngt48|stu48|ske48|nmb48|cgm48|qkt48")
HASHTAG_RE = re.compile(r"#(\w+)", re.UNICODE)


# ── Muat data ─────────────────────────────────────────────────────────
def load_members_csv():
    with open(BASE / "members.csv", newline="") as f:
        return {r["handle_x"].lower(): r for r in csv.DictReader(f) if r["handle_x"]}


def load_related():
    path = BASE / "related_accounts.csv"
    if not path.exists():
        return {}
    with open(path, newline="") as f:
        return {r["handle"].lower(): r["kategori"] for r in csv.DictReader(f)}


def target_type(target, roster, related):
    if not target:
        return ""
    if target in roster:
        return "member aktif"
    if target in OFFICIAL:
        return "akun resmi"
    if target in related or SISTER_RE.search(target):
        return "eks-member/JKT48V/grup saudara"
    return "non-roster lain (brand/akun lain)"


def load(files, cutoff_wib):
    roster, related = load_members_csv(), load_related()
    rows, meta = [], {}
    for path in files:
        raw = json.loads(Path(path).read_text())
        handle = raw["profile"]["screen_name"]
        fetched = datetime.fromisoformat(raw["fetched_at"])
        info = roster.get(handle.lower(), {})
        meta[handle] = {"handle": handle, "panggilan": info.get("panggilan", handle), "tim": info.get("tim", "?"),
                        "followers": raw["profile"].get("followers_count", 0), "fetched_at": fetched,
                        "windows_done": raw.get("done", []), "n_raw": len(raw["tweets"]), "file": str(path)}
        for key, t in raw["tweets"].items():
            created = datetime.fromisoformat(t["created_at"])
            wib = created.astimezone(WIB).replace(tzinfo=None)
            if wib < cutoff_wib:
                continue
            target = (t["reply_to"] or t["orig_author"] or "").lower()
            # waktu ambil per tweet kalau tersimpan (fetch_v2 baru); kalau tidak, waktu mulai run terakhir
            t_fetched = datetime.fromisoformat(t["fetched_at"]) if t.get("fetched_at") else fetched
            rows.append({
                "handle": handle, "key": key, "id": t["id"], "created_utc": created, "wib": wib,
                "kind": t["kind"], "target": target, "target_type": target_type(target, roster, related),
                "media": ",".join(t["media"]) if t["media"] else "teks",
                "text": t["text"], "text_len": len(re.sub(r"https://t\.co/\w+", "", t["text"]).strip()),
                "age_days": (t_fetched - created).total_seconds() / 86400, "fetched": t_fetched,
                "source": t.get("source", "search"),
                **{m: t["metrics"][m] for m in METRICS},
            })
    df = pd.DataFrame(rows)
    df["main"] = df["kind"].isin(MAIN)
    df["month"] = df["wib"].dt.strftime("%Y-%m")
    df["hour"] = df["wib"].dt.hour
    df["weekday"] = df["wib"].dt.dayofweek
    df["media1"] = df["media"].str.split(",").str[0].replace({"animated_gif": "gif"})
    df["mature"] = df["age_days"] >= MIN_AGE_DAYS
    df["er"] = np.where(df["views"] > 0, (df["likes"] + df["retweets"] + df["replies"] + df["quotes"]) / df["views"],
                        np.nan)
    return df, meta


# ── Util laporan ──────────────────────────────────────────────────────
def fmt(x, nd=0):
    if isinstance(x, (int, np.integer)):
        return f"{x:,}".replace(",", ".")
    if isinstance(x, (float, np.floating)):
        if np.isnan(x):
            return "–"
        return f"{x:,.{nd}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return str(x)


def table(df, nd=None):
    nd = nd or {}
    cols = list(df.columns)
    out = ["| " + " | ".join(str(c) for c in cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, r in df.iterrows():
        out.append("| " + " | ".join(fmt(r[c], nd.get(c, 0)) for c in cols) + " |")
    return "\n".join(out)


def verdict(ok, warn=False):
    return "✅ LULUS" if ok else ("⚠️ PERHATIAN" if warn else "❌ GAGAL")


# ── Sanity check ──────────────────────────────────────────────────────
def check_hygiene(df, meta, cutoff_wib):
    rows = []
    dup_global = df["id"].duplicated(keep=False)
    for h, g in df.groupby("handle"):
        main = g[g.main]
        rows.append({
            "member": meta[h]["panggilan"], "tweet": len(g),
            "key≠id": int((g["key"] != g["id"]).sum()),
            "id ganda lintas file": int(dup_global[g.index].sum()),
            "di luar rentang waktu": int(((g.wib < cutoff_wib) | (g.created_utc > g.fetched)).sum()),
            "metrik negatif": int((g[METRICS] < 0).any(axis=1).sum()),
            "kategori tak dikenal": int((~g.kind.isin(KINDS)).sum()),
            "post utama like>views": int((main.likes > main.views).sum()),
            "repost": int((g.kind == "Repost").sum()),
            "post utama belum matang (<7 hari)": int((main.main & ~main.mature).sum()),
        })
    t = pd.DataFrame(rows)
    hard = ["key≠id", "id ganda lintas file", "di luar rentang waktu", "metrik negatif", "kategori tak dikenal"]
    return t, bool(t[hard].sum().sum() == 0), bool(t["post utama like>views"].sum() == 0)


def check_windows(df, meta, cutoff_wib):
    """Kelengkapan per minggu penuh (minggu parsial terakhir tidak dihitung)."""
    end = df["wib"].max()
    n_full = int((end - cutoff_wib).days // 7)
    edges = [cutoff_wib + timedelta(days=7 * i) for i in range(n_full + 1)]
    rows = []
    for h, g in df.groupby("handle"):
        own = g[g.kind != "Repost"]
        counts = pd.cut(own["wib"], bins=edges, right=False).value_counts(sort=False).values
        zero_runs, run = [], 0
        for c in counts:
            run = run + 1 if c == 0 else 0
            zero_runs.append(run)
        med = float(np.median(counts)) if len(counts) else 0.0
        low_weeks = [f"{edges[i]:%d %b %y}" for i, c in enumerate(counts) if med >= 5 and c <= max(1, 0.2 * med)]
        rows.append({"member": meta[h]["panggilan"], "jendela selesai": len(meta[h]["windows_done"]),
                     "minggu penuh": len(counts), "median post/minggu": med,
                     "minggu kosong": int((counts == 0).sum()), "kosong beruntun terpanjang": max(zero_runs or [0]),
                     "minggu sangat rendah": ", ".join(low_weeks) or "–"})
    t = pd.DataFrame(rows)
    return t, bool((t["kosong beruntun terpanjang"] < 3).all()), edges[-1]


def check_timeline_coverage(df, meta, timelines):
    """Bandingkan dengan timeline profil (UserTweets): berapa yang ditemukan search, total & per hari."""
    rows, holes = [], []
    for handle, path in timelines.items():
        tl = json.loads(Path(path).read_text())["tweets"]
        g = df[df.handle.str.lower() == handle.lower()]
        start, end = g["wib"].min(), g["wib"].max()
        tl_wib = {t["id"]: datetime.fromisoformat(t["createdAtISO"]).astimezone(WIB).replace(tzinfo=None) for t in tl}
        own = {t["id"] for t in tl if not t["isRetweet"] and start <= tl_wib[t["id"]] <= end}
        rts = {t["id"] for t in tl if t["isRetweet"] and start <= tl_wib[t["id"]] <= end}
        by_search = set(g[g.source == "search"]["id"])
        found = len(own & by_search)
        rows.append({"member": meta.get(handle, {}).get("panggilan", handle),
                     "isi timeline (semua)": len(tl),
                     "timeline mulai": f"{min(tl_wib.values()):%d %b %Y}",
                     "non-repost di periode": len(own), "ditemukan search": found,
                     "cakupan search %": 100 * found / max(1, len(own)),
                     "ditambal dari timeline": int((g.source == "timeline").sum()),
                     "repost di timeline": len(rts),
                     "repost di data": int((g.kind == "Repost").sum())})
        # lubang lokal: hari dengan >=3 tweet timeline tapi cakupan search < 50%
        day = pd.Series({i: tl_wib[i].date() for i in own})
        for d, ids in day.groupby(day).groups.items():
            ids = set(ids)
            if len(ids) >= 3 and len(ids & by_search) / len(ids) < 0.5:
                holes.append({"member": rows[-1]["member"], "tanggal": f"{d:%d %b %Y}", "tweet timeline": len(ids),
                              "ditemukan search": len(ids & by_search)})
    return pd.DataFrame(rows), pd.DataFrame(holes)


def check_age(df, meta):
    """Kejenuhan metrik: median like & views per umur tweet relatif ke tweet berumur 30–90 hari (n>=MIN_N)."""
    bins = [0, 3, 7, 14, 30, 90, 180, 400]
    labels = ["<3h", "3–7h", "7–14h", "14–30h", "30–90h", "90–180h", ">180h"]
    rows, young_vals = [], []
    for h, g in df[df.main].groupby("handle"):
        b = pd.cut(g["age_days"], bins=bins, labels=labels, right=False)
        n = g.groupby(b, observed=False).size()
        for metric in ["likes", "views"]:
            med = g.groupby(b, observed=False)[metric].median()
            ref = med.get("30–90h", np.nan) if n.get("30–90h", 0) >= MIN_N else np.nan
            row = {"member": meta[h]["panggilan"], "metrik": metric}
            for lab in labels:
                row[lab] = med.get(lab, np.nan) / ref if n.get(lab, 0) >= MIN_N else np.nan
            rows.append(row)
            young_vals += [row["<3h"], row["3–7h"]]
        rows.append({"member": meta[h]["panggilan"], "metrik": "n post", **{lab: float(n.get(lab, 0)) for lab in labels}})
    t = pd.DataFrame(rows)
    young = [v for v in young_vals if not np.isnan(v)]
    status = "⏳ tweet muda < 10 per kelompok" if not young else verdict(min(young) >= 0.7, warn=True)
    return t, status


def check_outliers(df, meta):
    rows = []
    for h, g in df[df.main & df.mature].groupby("handle"):
        likes = g["likes"].sort_values(ascending=False)
        n1 = max(1, int(round(len(likes) * 0.01)))
        rows.append({"member": meta[h]["panggilan"], "post": len(g),
                     "porsi like tweet #1 %": 100 * likes.iloc[0] / likes.sum(),
                     "porsi like top 1% %": 100 * likes.iloc[:n1].sum() / likes.sum(),
                     "rata-rata like": likes.mean(), "median like": likes.median(),
                     "rata-rata/median": likes.mean() / likes.median(),
                     "trimmed mean 10%": stats.trim_mean(likes, 0.1)})
    t = pd.DataFrame(rows)
    return t, bool((t["porsi like top 1% %"] < 30).all())


def check_stability(df, meta, cutoff_wib):
    m = df[df.main & df.mature]
    mid = cutoff_wib + (m["wib"].max() - cutoff_wib) / 2
    rows = []
    for h, g in m.groupby("handle"):
        h1, h2 = g[g.wib < mid], g[g.wib >= mid]
        rows.append({"member": meta[h]["panggilan"], "post H1": len(h1), "post H2": len(h2),
                     "median like H1": h1.likes.median(), "median like H2": h2.likes.median(),
                     "rasio like H2/H1": h2.likes.median() / h1.likes.median(),
                     "median views H1": h1.views.median(), "median views H2": h2.views.median(),
                     "rasio views H2/H1": h2.views.median() / h1.views.median()})
    t = pd.DataFrame(rows)
    usable = t[(t["post H1"] >= MIN_N) & (t["post H2"] >= MIN_N)]
    if len(usable) < 5:
        return t, np.nan, mid, f"⏳ butuh ≥5 member dengan ≥{MIN_N} post per paruh (ada {len(usable)})"
    rho = stats.spearmanr(usable["median like H1"], usable["median like H2"]).statistic
    return t, rho, mid, verdict(rho >= 0.7, warn=True) + f" (ρ={rho:.2f})"


def check_ratios(df, meta):
    rows = []
    for h, g in df[df.main & df.mature].groupby("handle"):
        lk = g.likes.replace(0, np.nan)
        rows.append({"member": meta[h]["panggilan"],
                     "like/views % (median per post)": 100 * (g.likes / g.views.replace(0, np.nan)).median(),
                     "RT/like % (median per post)": 100 * (g.retweets / lk).median(),
                     "bookmark/like % (median per post)": 100 * (g.bookmarks / lk).median(),
                     "bookmark/like % (total)": 100 * g.bookmarks.sum() / g.likes.sum(),
                     "reply/like % (median per post)": 100 * (g.replies / lk).median()})
    t = pd.DataFrame(rows)
    zcols = []
    for c in ["like/views % (median per post)", "RT/like % (median per post)", "bookmark/like % (median per post)"]:
        mad = stats.median_abs_deviation(t[c], scale="normal") if len(t) >= 5 else np.nan
        name = "z " + c.split(" %")[0]
        t[name] = (t[c] - t[c].median()) / mad if mad and not np.isnan(mad) and mad > 0 else np.nan
        zcols.append(name)
    if len(t) < 5:
        return t, f"⏳ butuh ≥5 member (ada {len(t)})"
    return t, verdict(bool((t[zcols].abs().fillna(0) <= 3).all().all()), warn=True)


def check_collinearity(df, meta):
    """Spearman antar metrik per member (level post); laporkan nilai terkecil antar member."""
    per = {h: g[METRICS].corr(method="spearman") for h, g in df[df.main & df.mature].groupby("handle")}
    stacked = np.stack([c.values for c in per.values()])
    lo = pd.DataFrame(stacked.min(axis=0), index=METRICS, columns=METRICS)
    hi = pd.DataFrame(stacked.max(axis=0), index=METRICS, columns=METRICS)
    pairs = [(a, b, lo.loc[a, b], hi.loc[a, b]) for i, a in enumerate(METRICS) for b in METRICS[i + 1:]]
    return lo, pairs


# ── Analisis deskriptif ───────────────────────────────────────────────
def member_profile(df, meta):
    rows = []
    for h, g in df.groupby("handle"):
        own = g[g.kind != "Repost"]
        main = g[g.main & g.mature]
        days = (g["wib"].max() - g["wib"].min()).days + 1
        gaps = own["wib"].sort_values().diff().dt.total_seconds().div(86400)
        reply = g[g.kind == "Reply"]
        kc = Counter(g.kind)
        share = (lambda cat: 100 * (reply.target_type == cat).mean() if len(reply) else np.nan)
        rows.append({
            "member": meta[h]["panggilan"], "tim": meta[h]["tim"], "follower": meta[h]["followers"],
            "post utama": int(g.main.sum()), "reply": kc["Reply"], "thread sendiri": kc["Reply (thread sendiri)"],
            "repost": kc["Repost"], "post utama/minggu": 7 * g.main.sum() / days,
            "% hari aktif": 100 * own["wib"].dt.date.nunique() / days, "jeda terpanjang (hari)": gaps.max(),
            "median like (L50)": main.likes.median(), "persentil-10 like (L10)": main.likes.quantile(0.1),
            "median/rata-rata like": main.likes.median() / main.likes.mean(),
            "median views": main.views.median(), "median ER %": 100 * main.er.median(),
            "L10 per 1.000 follower": 1000 * main.likes.quantile(0.1) / max(1, meta[h]["followers"]),
            "reply → member aktif %": share("member aktif"),
            "reply → eks/JKT48V/saudara %": share("eks-member/JKT48V/grup saudara"),
            "reply → non-roster lain %": share("non-roster lain (brand/akun lain)"),
        })
    return pd.DataFrame(rows).sort_values("follower", ascending=False)


def content_effects(df):
    """Efek konten dalam member yang sama: OLS log1p(metrik) ~ fitur + FE member + FE bulan.
    SE cluster per member-minggu; p dikoreksi Holm; kategori kecil digabung."""
    g = df[df.main & df.mature].copy()
    g["slot"] = pd.cut(g["hour"], bins=[0, 6, 12, 18, 24], right=False,
                       labels=["00–06", "06–12", "12–18", "18–24"]).astype(str)
    g["akhir_pekan"] = (g["weekday"] >= 5).astype(int)
    g["panjang"] = pd.cut(g["text_len"], bins=[-1, 0, 40, 120, 10_000],
                          labels=["kosong", "pendek", "sedang", "panjang"]).astype(str)
    small = [m for m, n in g["media1"].value_counts().items() if n < MIN_N_EFFECT and m != "teks"]
    g["media_g"] = g["media1"].where(~g["media1"].isin(small), "video/gif (n kecil)")
    g["cluster"] = pd.factorize(g["handle"] + "_" + g["wib"].dt.strftime("%G-%V"))[0]
    res = {}
    for y in ["views", "likes"]:
        f = (f"np.log1p({y}) ~ C(media_g, Treatment('teks')) + C(slot, Treatment('12–18')) + akhir_pekan"
             " + C(kind, Treatment('Original')) + C(panjang, Treatment('sedang')) + C(handle) + C(month)")
        m = smf.ols(f, data=g).fit(cov_type="cluster", cov_kwds={"groups": g["cluster"]})
        keep = [p for p in m.params.index if not p.startswith(("C(handle)", "C(month)", "Intercept"))]
        ci = m.conf_int().loc[keep]
        out = pd.DataFrame({"efek %": 100 * (np.exp(m.params[keep]) - 1),
                            "CI bawah %": 100 * (np.exp(ci[0]) - 1), "CI atas %": 100 * (np.exp(ci[1]) - 1),
                            "p": m.pvalues[keep], "p (Holm)": multipletests(m.pvalues[keep], method="holm")[1]})
        out.index = [re.sub(r"C\((\w+).*?\)\[T\.(.+)\]", r"\1 = \2", i) for i in out.index]
        res[y] = (out, int(m.nobs), m.rsquared)
    counts = {"media": g["media_g"].value_counts().to_dict(), "slot": g["slot"].value_counts().to_dict(),
              "panjang": g["panjang"].value_counts().to_dict(), "kind": g["kind"].value_counts().to_dict()}
    return res, counts


def photo_effect_by_member(df, meta):
    """Heterogenitas: rasio median views/like foto vs teks per member (model di atas mengasumsikan efek sama)."""
    rows = []
    for h, g in df[df.main & df.mature].groupby("handle"):
        p, t = g[g.media1 == "photo"], g[g.media1 == "teks"]
        rows.append({"member": meta[h]["panggilan"], "n foto": len(p), "n teks": len(t),
                     "views foto/teks ×": p.views.median() / t.views.median() if len(p) >= MIN_N else np.nan,
                     "like foto/teks ×": p.likes.median() / t.likes.median() if len(p) >= MIN_N else np.nan})
    return pd.DataFrame(rows)


def monthly(df, meta, cutoff_wib, end):
    g = df[df.main & df.mature]
    med = g.pivot_table(index="month", columns="handle", values="views", aggfunc="median")
    n = g.pivot_table(index="month", columns="handle", values="views", aggfunc="size")
    out = pd.DataFrame(index=med.index)
    for h in med.columns:
        out[meta[h]["panggilan"]] = [
            "–" if np.isnan(v) else f"{fmt(v)} (n={int(n.loc[mth, h])})" + ("" if n.loc[mth, h] >= MIN_N else " ⚠")
            for mth, v in med[h].items()]
    partial = {cutoff_wib.strftime("%Y-%m"), end.strftime("%Y-%m")}
    out.index = [m + (" (parsial)" if m in partial else "") for m in out.index]
    return out.reset_index().rename(columns={"index": "bulan"})


def interactions(df, top_n=15):
    names = {h: r["panggilan"] for h, r in load_members_csv().items()}
    r = df[(df.kind == "Reply") & (df.target_type == "member aktif")]
    top = r.groupby(["handle", "target"]).size().sort_values(ascending=False)
    if top.empty:
        return pd.DataFrame()
    cut = top.iloc[min(top_n, len(top)) - 1]
    top = top[top >= cut]  # pertahankan nilai seri di batas bawah
    return pd.DataFrame([{"dari": names.get(h.lower(), h), "membalas": names.get(t, "@" + t), "jumlah": int(k)}
                         for (h, t), k in top.items()])


def hashtags(df, meta):
    rows = []
    for h, g in df[df.kind != "Repost"].groupby("handle"):
        c = Counter(tag.lower() for text in g.text for tag in HASHTAG_RE.findall(text))
        rows.append({"member": meta[h]["panggilan"],
                     "hashtag terbanyak": ", ".join(f"#{k} ({v})" for k, v in c.most_common(5)) or "–"})
    return pd.DataFrame(rows)


# ── Laporan ───────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("files", nargs="+")
    ap.add_argument("--timeline", action="append", default=[], help="HANDLE=path timeline json (fetch_timeline.py)")
    ap.add_argument("--cutoff", default="2025-10-22")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    cutoff = datetime.strptime(a.cutoff, "%Y-%m-%d")
    df, meta = load(a.files, cutoff)
    names = ", ".join(meta[h]["panggilan"] for h in meta)
    end = df["wib"].max()

    L = [f"# Sanity check & analisis awal — {len(meta)} member ({names})",
         f"_Periode {cutoff:%d %b %Y} – {end:%d %b %Y} WIB · {len(df):,} tweet · dibuat "
         f"{datetime.now(WIB):%d %b %Y %H:%M} WIB · tanpa request baru ke X._".replace(",", "."), "",
         "Aturan: metrik engagement hanya dari **post utama (Original + Quote)** yang berumur ≥ 7 hari saat diambil. "
         f"Repost tidak dihitung (metriknya milik tweet asli). Kelompok dengan n < {MIN_N} tidak dipakai untuk keputusan.",
         "", "## Bagian 1 — Sanity check", ""]
    summary = []

    t, ok, ok_soft = check_hygiene(df, meta, cutoff)
    summary.append(("Kebersihan data (id, rentang waktu, metrik negatif, kategori)", verdict(ok)))
    summary.append(("Konsistensi metrik (like tidak melebihi views)", verdict(ok_soft, warn=True)))
    L += ["### 1.1 Kebersihan data", table(t), "",
          "Repost tetap disimpan untuk analisis perilaku, tapi tidak pernah masuk agregat engagement.", ""]

    t, ok, last_edge = check_windows(df, meta, cutoff)
    summary.append(("Kelengkapan per minggu (tidak ada minggu kosong beruntun ≥3)", verdict(ok, warn=True)))
    L += ["### 1.2 Kelengkapan per minggu", table(t, {"median post/minggu": 1}), "",
          f"Hanya minggu penuh yang dihitung (sampai {last_edge:%d %b %Y}); minggu parsial terakhir dikeluarkan. "
          "Minggu sangat rendah = ≤20% median member itu; bisa nyata (member jarang posting) atau lubang search.", ""]

    tl = dict(x.split("=", 1) for x in a.timeline)
    checked = [h for h in meta if h.lower() in {k.lower() for k in tl}]
    if tl:
        t, holes = check_timeline_coverage(df, meta, tl)
        ok = bool((t["cakupan search %"] >= 95).all()) and holes.empty
        summary.append((f"Cakupan search vs timeline ({len(checked)}/{len(meta)} member dicek)",
                        verdict(bool((t["cakupan search %"] >= 95).all()), warn=True) +
                        ("" if holes.empty else f", {len(holes)} hari berlubang")))
        L += ["### 1.3 Cakupan search dibanding timeline profil", table(t, {"cakupan search %": 1}), "",
              f"Hanya {len(checked)} dari {len(meta)} member punya data timeline untuk dibandingkan; "
              "member lain belum terverifikasi cakupannya. Reply ke akun lain jarang muncul di timeline, jadi "
              "cakupan reply tidak bisa dicek dengan cara ini.", ""]
        if not holes.empty:
            L += ["**Lubang lokal** (hari dengan ≥3 tweet di timeline tapi search menemukan <50%):", "",
                  table(holes), "",
                  "Tweet non-repost yang terlewat di hari-hari ini sudah ditambal dari timeline, tapi repost dan "
                  "reply di hari yang sama kemungkinan ikut terlewat.", ""]
    else:
        summary.append(("Cakupan search vs timeline", f"⏳ 0/{len(meta)} member dicek"))

    t, status = check_age(df, meta)
    summary.append(("Kejenuhan metrik (tweet <7 hari ≥70% dari tweet 30–90 hari)", status))
    L += ["### 1.4 Kejenuhan metrik menurut umur tweet",
          f"Median like/views per kelompok umur saat diambil ÷ median tweet berumur 30–90 hari (1,00 = setara). "
          f"Sel dengan n < {MIN_N} dikosongkan (–).", "",
          table(t, {c: 2 for c in t.columns if c not in ("member", "metrik")}), "",
          "Perbandingan ini antar tweet berbeda, jadi tercampur tren popularitas (mis. tweet >180 hari bisa lebih "
          "rendah karena member sedang naik). Uji kejenuhan yang benar: tarik ulang tweet yang sama setelah 7 hari.", ""]

    t, ok = check_outliers(df, meta)
    summary.append(("Ketergantungan outlier (top 1% tweet < 30% total like)", verdict(ok, warn=True)))
    L += ["### 1.5 Ketergantungan pada tweet viral",
          table(t, {"porsi like tweet #1 %": 1, "porsi like top 1% %": 1, "rata-rata/median": 2}), "",
          "Rata-rata jauh di atas median = satu-dua tweet viral mendongkrak rata-rata; metrik utama memakai median.", ""]

    t, rho, mid, status = check_stability(df, meta, cutoff)
    summary.append(("Stabilitas dua paruh (Spearman ≥0,7)", status))
    L += [f"### 1.6 Stabilitas dua paruh (batas {mid:%d %b %Y})",
          table(t, {"rasio like H2/H1": 2, "rasio views H2/H1": 2}), "", status, ""]

    t, status = check_ratios(df, meta)
    summary.append(("Anomali rasio engagement (indikasi bot, |z| ≤ 3)", status))
    L += ["### 1.7 Rasio engagement (deteksi anomali/bot)",
          table(t, {c: 2 for c in t.columns if c != "member"}), "",
          "'median per post' = median dari rasio tiap post; 'total' = jumlah bookmark ÷ jumlah like. Keduanya bisa "
          "beda jauh karena post viral punya rasio bookmark lebih tinggi. z dihitung robust (MAD) antar member.", ""]

    lo, pairs = check_collinearity(df, meta)
    high = [(a_, b_, l_, h_) for a_, b_, l_, h_ in pairs if l_ > 0.8]
    summary.append(("Multikolinearitas (pasangan ρ>0,8 di semua member)",
                    f"⚠️ {len(high)} pasangan — pakai satu saja/indeks" if high else "✅ LULUS"))
    L += ["### 1.8 Korelasi antar metrik (Spearman per member, nilai terkecil antar member)",
          table(lo.reset_index().rename(columns={"index": "metrik"}), {c: 2 for c in METRICS}), "",
          "Pasangan yang ρ>0,8 di semua member: " +
          (", ".join(f"{x}–{y} ({l_:.2f}–{h_:.2f})" for x, y, l_, h_ in high) or "tidak ada") +
          ". Pasangan seperti ini jangan dipakai bersamaan sebagai prediktor terpisah; pilih satu atau buat indeks.", ""]

    L += ["### Ringkasan sanity check", table(pd.DataFrame(summary, columns=["Cek", "Hasil"])), "",
          "Belum bisa diuji: baseline vs model & uji permutasi (butuh label vote/proxy), CV per tim, audit manual "
          "kelengkapan (6 member × 2 minggu), dan kejenuhan dengan tarik ulang.", ""]

    prof = member_profile(df, meta)
    prof.to_csv(out / "member_profile.csv", index=False)
    L += ["## Bagian 2 — Analisis awal", "", "### 2.1 Profil member",
          table(prof, {"post utama/minggu": 1, "jeda terpanjang (hari)": 1, "median/rata-rata like": 2,
                       "median ER %": 2, "L10 per 1.000 follower": 2}), "",
          "- **L50/L10** = median dan persentil-10 like per post utama. Like bersifat anonim dan bisa datang dari "
          "non-follower, jadi ini indikator kasar besarnya basis yang rutin bereaksi, bukan hitungan orang.",
          "- **median/rata-rata like** mendekati 1 = engagement merata antar post; kecil = didorong post viral. "
          "Selisih kecil antar member (mis. 0,78 vs 0,80) tidak bermakna.",
          "- **Reply → eks/JKT48V/saudara** = balasan ke eks-member, JKT48V, atau grup 48 lain (lihat "
          "`related_accounts.csv`). **Non-roster lain** = sisanya (brand/akun lain). Member JKT48 tidak membalas fans, jadi kategori ini bukan interaksi dengan fans.", ""]

    res, counts = content_effects(df)
    for y, (t, n, r2) in res.items():
        L += [f"### 2.2 Efek konten terhadap {y} (dalam member yang sama)",
              f"OLS log1p({y}) dengan efek tetap member & bulan; SE cluster per member-minggu; p dikoreksi Holm. "
              f"n = {n} post, R² = {r2:.2f}. Pembanding: teks, jam 12–18 WIB, hari kerja, Original, teks sedang. "
              f"Kategori media dengan n < {MIN_N_EFFECT} digabung.", "",
              table(t.reset_index().rename(columns={"index": "faktor"}),
                    {"efek %": 1, "CI bawah %": 1, "CI atas %": 1, "p": 3, "p (Holm)": 3}), ""]
    L += [f"Jumlah post per kategori: {counts}.", "",
          "Hanya efek dengan p (Holm) < 0,05 yang layak dianggap sinyal. Semua ini asosiasi terhadap **engagement**, "
          "bukan vote: post foto mungkin dibuat saat momen istimewa, jadi foto belum tentu penyebabnya.", "",
          "**Efek foto per member** (model di atas mengasumsikan efek sama untuk semua member):", "",
          table(photo_effect_by_member(df, meta), {"views foto/teks ×": 2, "like foto/teks ×": 2}), ""]

    L += ["### 2.3 Tren bulanan — median views post utama (n post)", table(monthly(df, meta, cutoff, end)), "",
          f"⚠ = n < {MIN_N}. Bulan parsial: bulan pertama dan terakhir periode.", ""]

    it = interactions(df)
    L += ["### 2.4 Reply antar member aktif (termasuk nilai seri di batas bawah)",
          table(it) if len(it) else "Belum ada.", ""]
    L += ["### 2.5 Hashtag yang paling sering dipakai member", table(hashtags(df, meta)), ""]

    df.drop(columns=["text"]).to_csv(out / "tweets_clean.csv", index=False)
    (out / "report.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(f"{c}: {v}" for c, v in summary))
    print(f"laporan: {out / 'report.md'}")


if __name__ == "__main__":
    main()
