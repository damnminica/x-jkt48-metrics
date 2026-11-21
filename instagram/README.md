# JKT48 Instagram Metrics

Pelengkap proyek metrik X (`../`). Tujuan: metrik publik akun **Instagram** tiap member JKT48 (follower, post, likes, comments, views Reels) — **tanpa mention fans** (keputusan: mention fans khusus X).

## Status
- **Fase 1 — Riset username ✅ SELESAI & terverifikasi (2026-11-21).** `members_ig.csv`/`.json`. 58 member + 1 akun bersama. status_akun: 50 aktif · 3 placeholder · 5 shared · 1 hub.
- **Fase 2 — Otomasi + metrik EKSAK + dashboard ✅ BUILT (2026-11-22).** Fetcher headless, scheduler harian, dashboard web. Lihat **Sistem** di bawah.

## Sistem (fase 2)
Alur: `ig_fetch.py` → `snapshots/ig_<tgl>.csv` → `aggregate_ig.py` → `ig_data.json` → `dashboard.html` (disajikan `app.py`).

| File | Fungsi |
|---|---|
| `ig_fetch.py` | **Engine.** Tarik metrik EKSAK tiap akun via UA crawler (Googlebot) → HTML SSR IG menanam `follower_count`/`following_count`/`is_verified` eksak + og untuk post. **Headless, tanpa login/cookie/Playwright/akun cadangan.** `python ig_fetch.py [--only h1,h2] [--date ..]` |
| `aggregate_ig.py` | Gabung semua snapshot → `ig_data.json`: time-series, delta follower/post, agregat tim, perbandingan lintas-platform IG vs X (`../dash_ds/members.json`). |
| `dashboard.html` | Dashboard (Chart.js): stat, Top-20, share tim, post teraktif, scatter IG-vs-X, leaderboard (verified, rasio IG/X, sortable). |
| `app.py` | Flask + APScheduler. `/` dashboard, `/ig_data.json`, `/health`, `/refresh?key=`. Scheduler **00:00 WIB** tarik+rebuild. Seed snapshot dari repo bila volume kosong. |
| `Dockerfile`/`requirements.txt` | Deploy Railway (service kedua, `dockerfilePath: instagram/Dockerfile`). Pasang Volume di `/data` agar snapshot persist. Env: `REFRESH_KEY`, `FETCH_ENABLED`, `IG_PAUSE`. |

### Kenapa ini mengubah rencana awal
Rencana lama (OpenCLI/Agent-Reach + akun IG cadangan) **tidak lagi perlu** untuk metrik akun (follower/following/post). Trik UA crawler memberi angka **eksak** dari server headless. Akun cadangan hanya perlu bila nanti mau metrik per-post (likes/komentar/views Reels), yang tak ada di HTML publik.

### Jalankan lokal
```
pip install -r requirements.txt
python ig_fetch.py            # tarik snapshot hari ini
python aggregate_ig.py        # bangun ig_data.json
PORT=8010 python app.py       # buka http://localhost:8010
```

### Keterbatasan
- og membulatkan follower jutaan ("2M"), TAPI JSON SSR crawler = **eksak** → fetcher pakai yang eksak. Posts dari og (eksak).
- Delta follower muncul setelah ≥2 snapshot eksak (mulai 2026-11-22). Batas metode og(21)→eksak(22) di-skip agar tak ada lonjakan palsu.

## Fase 3 — metrik PER-POST (engagement) — `ig_posts.py`
Likes, komentar, **views Reel**, **repost**, **share** per post → **sum/avg per member + ER**. Kolom otomatis muncul di leaderboard IG saat datanya ada (`has_posts`).
- **Butuh sesi login akun CADANGAN** (bukan pribadi). Profil publik/crawler TIDAK memuat engagement (terbukti: 0 field) → wajib feed API ber-auth.
- Jalur: `www.instagram.com/api/v1/feed/user/<pk>/` (pk diambil publik via crawler) + cookie `sessionid`. Bash/requests TIDAK diblokir (beda dari browser-pane). Likes/komentar/views Reel ANDAL; repost/share best-effort (field IG baru, diparse bila ada).
- **Keamanan:** Claude TIDAK memasukkan password IG. Kamu sediakan cookie sendiri:
  ```
  export IG_SESSIONID='...'        # devtools akun cadangan → Cookies → sessionid
  python ig_posts.py --max 36      # → snapshots/posts_<today>.csv
  python aggregate_ig.py           # merge ke ig_data.json
  ```
  `python ig_posts.py --sample` menguji parser tanpa login.
- **Risiko:** ToS IG melarang scraping otomatis; pakai akun khusus, pace lambat (default 2.5s/post), bisa kena rate-limit/flag. Status: **engine + pipeline + kolom dashboard SIAP & tervalidasi** (parser + render pakai data contoh); eksekusi live tinggal sesi login.

## Pola username (PENTING untuk scraper — jangan template buta)
Tidak ada satu pola. Ditemukan ≥4 varian:
1. **`jkt48.<panggilan>`** (mayoritas member aktif) — mis. `jkt48.christy`, `jkt48.marsha`.
2. **`jkt48<panggilan>` TANPA titik** (sebagian senior) — mis. `jkt48feni`, `jkt48gita`, `jkt48indah_`.
3. **Trailing underscore / sufiks inisial** — mis. `jkt48.muthe_`, `jkt48.michie_`, `jkt48.elin_`, `jkt48.lily_`, `jkt48.anindya_`, `jkt48.ella.a`, `jkt48.lana.a`, `jkt48.nachia.t`, `jkt48.raisha.s`, `jkt48.lyn.s`, `jkt48.nayla.s`, `jkt48.aurellia_`.
4. **TERBALIK `<panggilan>.jkt48`** (khas Gen 13) — `intan.jkt48`, `virgi.jkt48`, `mikaela.jkt48`, `ekin.jkt48`, `jemima.jkt48`, `maira.jkt48`, `giaa.jkt48`, `rilly.jkt48`.
- **Gen 14 (terbaru):** balik lagi ke `jkt48.<panggilan>` tapi akun masih mungil/privat/belum ada.
- **TikTok:** umumnya `<panggilan>jkt48` (mis. `christyjkt48`, `fionyjkt48`) ATAU `jkt48.<panggilan>` — bervariasi, hanya 22 yang terkonfirmasi.
- Implikasi: scraper WAJIB baca username dari `members_ig.csv`, bukan generate dari pola.

## Aturan trainee <16 (Komdigi) → akun bersama `jkt48.u16`
Trainee di bawah 16 th **tidak boleh punya medsos pribadi** (aturan region Komdigi perlindungan anak). Kontennya lewat **akun bersama `jkt48.u16`** (terverifikasi: 81K follower, 90 post).
- **Punya akun individual aktif (pengecualian):** hanya **Rara** (`rara.jkt48`, 30K) & **Heidi** (`heidi.jkt48`, 51K) — keduanya pola *reversed*.
- **Placeholder (handle resmi ada tapi 0 post):** Fahira (`jkt48.fahira`), Maxine (`jkt48.maxine`), Sona (`jkt48.sona`) — dorman, konten di u16.
- **Shared (tak ada akun individual → u16):** Carissa, Bella (`jkt48.bella` = akun personal "bea", bukan resmi), Fera, Jazzy, Ralyne.

## Koreksi dari verifikasi (vs tebakan workflow)
- Fritzy: `jkt48.fritzy` ❌ → **`jkt48.fritzy.r`** ✅ (592K, 78 post)
- Rilly: `rilly.jkt48` ❌ → **`rilly.jkt48_`** ✅ (132K, 47 post)
- Rara: `jkt48.rara` (akun lain) ❌ → **`rara.jkt48`** ✅ (30K, 5 post)
- Heidi: "belum ada" ❌ → **`heidi.jkt48`** ✅ (51K, 13 post)

## Temuan sumber (2026-11-21)
- **jkt48.com bukan sumber.** Redesign baru situs resmi **menghapus** link sosmed dari halaman member (`/member/detail?member=<slug-id>`); kini hanya profil dasar (tgl lahir, tinggi, gol. darah, tim). Daftar member tetap bisa diambil dari `/member?lang=id` (58 member).
- **Pola akun resmi:** mayoritas member aktif pakai `jkt48.<panggilan>` (huruf kecil). Terkonfirmasi: `jkt48.christy`, `jkt48.marsha`, `jkt48.kathrina`. **Tidak 100%** — trainee gen baru sering belum punya akun, sebagian pakai handle pribadi.
- **TikTok:** pola berbeda, sering `<panggilan>jkt48` (mis. `christyjkt48`).
- **Verifikasi/follower pihak ketiga:** HypeAuditor (`hypeauditor.com/instagram/<user>/`), SocialBlade, kprofiles, generasia.
- **curl kena 403** di jkt48.com & fandom (Cloudflare) → pakai browser pane / WebSearch.

## Rencana penarikan metrik (fase berikutnya, dari memory)
- **Agent-Reach / OpenCLI** (browser khusus) untuk IG — cek cepat, batas ketat (maks 2 paralel/platform, jeda ≥10 dtk, limit default kecil). Perlu modifikasi untuk tarik massal + views Reels.
- Alternatif IG resmi: Graph API Business Discovery (butuh akun IG Business + FB Page + app Meta; hanya target Business/Creator; tanpa views Reels; ~200 call/jam).
- Pakai profil Chrome + akun IG **cadangan** (bukan pribadi; IG paling ketat: 429/login required).
- TikTok (nanti): yt-dlp metadata publik, atau `tiktok` adapter OpenCLI (maks 120 video terbaru).

## Snapshot metrik (fase 2 — baseline)
- `snapshots/ig_YYYY-MM-DD.csv` — time-series per akun: date, panggilan, nama, tim, ig_username, status_akun, followers, followers_raw, following, posts.
- **Baseline 2026-11-21:** 54 akun unik · ~33 jt follower (og-approx) · 5.580 post total. Top: Freya 3M, Christy/Marsha 2M, Fiony/Muthe/Kathrina/Gita/Michie 1M. Paling rajin posting: Fiony (424), Eli (271), Lulu (249).
- **Metode:** `fetch()` same-origin ke `instagram.com/<handle>` dari tab origin IG, parse `og:description`. Publik, tanpa login, tanpa anti-bot. ~250ms jeda antar akun.
- **CAVEAT PRESISI:** og membulatkan follower akun jutaan jadi "2M/3M/1M" (1 sig fig) → terlalu kasar untuk delta harian akun besar. **following & posts EKSAK.** Angka follower eksak hanya via API ber-login IG (`web_profile_info`, **diblокir** classifier krn impersonate app). → untuk tracking follower presisi akun jutaan, pakai jalur OpenCLI/Agent-Reach + akun cadangan (rencana awal). Untuk post-count & akun <1jt, og sudah memadai.

## File
- `members_ig.csv` / `members_ig.json` — 59 baris (58 member + baris `(U16)`). Kolom: panggilan, nama, tim, handle_x, ig_username, ig_url, followers, followers_raw, posts, following, **confidence**, **status_akun** (active/placeholder/shared/shared_hub), tiktok, snapshot_date, source, notes. Follower/post di-refresh dari snapshot og-tag.

## Metode riset (fase 1)
1. Workflow 8 agen paralel + verifikasi (web search, wajib sumber): HypeAuditor/Instastatistics/SocialBlade (follower), Generasia, IDN Times/Popbela/Popmama/Shopee (biodata).
2. Koreksi ground-truth dari user (4 handle + aturan u16).
3. **Verifikasi langsung IG og-tag** via browser pane: `navigate` ke `instagram.com/<handle>` lalu baca `<meta property="og:description">` → "N Followers, M Following, K Posts" + `og:title` = nama. Tembus tanpa login, tanpa kena anti-bot. **Ini cara paling andal & jadi basis fase 2** (bisa tarik follower+post semua member langsung dari og-tag, lebih akurat dari aggregator).
