# x-jkt48-metrics

Penarik data publik X (Twitter) untuk member JKT48: metrik tweet member, mention dari fans, dan hashtag kampanye. Hasilnya berupa Excel, notifikasi Telegram, dan dashboard harian. Dipakai untuk menyusun dataset Senbatsu Sousenkyo (SSK) 2024.

> 📄 Laporan lengkap project (arsitektur, hasil, pelajaran): [`report/laporan_project_x_jkt48.pdf`](report/laporan_project_x_jkt48.pdf) · [versi Markdown](report/laporan_project_x_jkt48.md)

> ⚠️ **Data tidak ada di repo ini.** Data mentah, salt hash, dan file Excel sengaja dikecualikan lewat `.gitignore`, karena data mentah masih menyimpan id tweet asli fans.

---

## Fitur

- **Metrik member** (`worker.py`): semua tweet satu akun member dalam rentang waktu tertentu (default 1 tahun), dipilah menjadi Original / Quote / Reply / Reply (thread sendiri) / Repost, lengkap dengan like, retweet, reply, quote, views, dan bookmark.
- **Job berbasis task** (`job_worker.py`):
  - `member`: tweet member.
  - `mention`: tweet orang lain yang menyebut @member, tanpa reply dan retweet polos.
  - `hashtag`: tweet hashtag kampanye, dibatasi konteks JKT48/member/fanbase.
- **Beberapa akun X sekaligus**: antrean bersama (`taskqueue.py`). Task yang sudah diambil satu akun tidak dikerjakan akun lain.
- **Aman di-restart**: progres disimpan per jendela waktu, jadi worker yang mati melanjutkan dari jendela terakhir.
- **Pengaman**: tempo 35 request/15 menit, istirahat otomatis saat rate limit, percobaan ulang saat jaringan bermasalah, dan wajib lewat proxy.
- **Anonimisasi fans** di semua ekspor: handle dan id tweet di-hash; teks, link, dan follower persis tidak ditulis.
- **Ekspor**: Excel ringkasan (hemat RAM, untuk server) dan Excel dataset lengkap (semua baris, untuk mesin ber-RAM besar).
- **Dashboard harian** (`daily/`): Flask + cron 00:00 WIB + Google Sheets, di-deploy ke Railway.

## Struktur

```text
fetch_v2.py          inti penarik: search X (POST), jendela waktu, pecah jendela adaptif, state atomik
xraw.py              parser tweet mentah + anonimisasi penulis non-publik
worker.py            batch metrik member (members.csv) → Excel → Telegram
build_jobs.py        dataset SSK (xlsx) → jobs/<nama>.json
job_worker.py        worker job multi-akun (antrean bersama / shard)
taskqueue.py         antrean task berbasis file (klaim atomik, detak jantung, ambil alih klaim basi)
stress_test.py       uji batas ukuran jendela search
export_jobs.py       Excel ringkasan job + CSV.gz
export_dataset.py    Excel dataset lengkap (Tweet Member / Mention / Hashtag)
export_combined.py   Excel metrik gabungan semua member
export_excel.py      Excel metrik per member
analysis.py          sanity check + analisis awal → analysis/report.md
fetch_timeline.py    timeline profil (cek silang & tambal tweet yang terlewat search)
members.csv          daftar member + handle X
related_accounts.csv akun eks-member / JKT48V / grup saudara
jobs/ssk2024.json    definisi job SSK 2024 (43 member, 127 task aktif)
daily/               dashboard harian (Railway)
deploy/              unit systemd + skrip setup VPS
research/            riset SSK (01–04)
report/              laporan project (MD + PDF) dan skrip pembuat PDF
tests/               tes offline sistem job (respons X tiruan)
```

## Persiapan

1. **Python 3.12** dan [uv](https://docs.astral.sh/uv/). Dependensi ada di `requirements.txt` (`twitter-cli==0.8.5`, `curl_cffi==0.16.3`, `openpyxl==3.1.5`).
2. **Akun X cadangan.** Jangan pakai akun pribadi. Ambil cookie `auth_token` dan `ct0` dari browser yang login ke akun itu: DevTools → Application → Cookies → `https://x.com`. Cookie ini setara password, jadi simpan di file `.env` (sudah di-`.gitignore`) dengan `chmod 600`.
3. **Proxy residensial** (`http://user:pass@host:port` atau `socks5://…`). Worker menolak berjalan tanpa proxy bila `REQUIRE_PROXY=1`.
4. **Bot Telegram** (token + chat id) untuk notifikasi dan kiriman Excel.

Untuk menjalankan apa pun secara lokal:

```bash
uv run --python 3.12 --with-requirements requirements.txt python <skrip>.py
```

## Konfigurasi

Salin `.env.example` (batch member) atau `.env.job.example` (job), lalu isi.

| Variabel | Dipakai di | Keterangan |
|---|---|---|
| `TWITTER_AUTH_TOKEN`, `TWITTER_CT0` | semua | Cookie akun X cadangan |
| `TWITTER_PROXY` | semua | Proxy residensial; wajib untuk job kecuali `ALLOW_DIRECT=1` |
| `REQUIRE_PROXY` | worker | `1` = diam bila proxy kosong |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | worker, job | Notifikasi + kiriman Excel |
| `DATA_DIR` | semua | Folder data (default `/data`) |
| `RUN_ID` | worker, job | Nama batch; ganti untuk memulai batch baru |
| `REQ_PER_WINDOW` | worker, job | Tempo request per 15 menit (default 35) |
| `MEMBERS`, `MEMBER_LIMIT`, `CUTOFF` | worker | Pilih handle, batasi jumlah member, tanggal awal (default 365 hari lalu) |
| `JOB_FILE`, `MODES`, `TASKS` | job | File job, urutan/filter mode (`member,hashtag,mention`), daftar id task |
| `SHARD` | job | `k/n` untuk pembagian tetap; kosong = antrean bersama |
| `WORKER_ID` | job | Nama worker di antrean (di systemd = nama instance) |
| `HASH_SALT` | job | Salt hash fans (mode antrean: dibuat otomatis di file `.hash_salt`) |
| `QUEUE_POLL_S`, `QUEUE_STALE_S` | job | Jeda cek antrean (300 dtk) dan batas klaim basi (600 dtk) |
| `EXIT_WHEN_DONE` | worker, job | `1` = keluar setelah selesai (tes lokal) |

## Cara pakai

### 1. Metrik member (batch `worker.py`)

Contoh uji lokal 5 member:

```bash
set -a; source .env; set +a
DATA_DIR=./data MEMBER_LIMIT=5 EXIT_WHEN_DONE=1 \
  uv run --python 3.12 --with-requirements requirements.txt python worker.py
```

Data tersimpan sebagai `DATA_DIR/<handle>_v2.json`. Excel gabungan dikirim ke Telegram setelah semua member selesai.

### 2. Job SSK (mention + hashtag + member)

Bangun file job dari dataset SSK:

```bash
uv run --python 3.12 --with openpyxl==3.1.5 \
  python build_jobs.py datasets/ssk2024.xlsx jobs/ssk2024.json
```

Jalankan satu proses `job_worker.py` per akun X, dengan `DATA_DIR` dan `RUN_ID` yang sama, supaya berbagi antrean. Di VPS, tiap akun memakai file `.env.job.<akun>` dan service `jkt48-x-job@<akun>` (lihat bagian Deploy). Data job tersimpan di `DATA_DIR/<RUN_ID>/` (`member/`, `mention/`, `hashtag/`, `queue/`, `exports/`).

Catatan ukuran jendela mention: jendela 3 hari menghemat request untuk member yang sepi, tapi boros 26–40% untuk member yang ramai karena jendela yang meluap ditarik ulang per hari. Untuk member yang ramai, pakai jendela harian (`window_hours: 24`).

### 3. Ekspor

```bash
# Excel ringkasan + CSV.gz (ringan, cocok untuk server)
uv run --python 3.12 --with openpyxl==3.1.5 \
  python export_jobs.py jobs/ssk2024.json DATA_ROOT OUT.xlsx
```

```bash
# Excel dataset lengkap, satu baris per tweet (butuh RAM besar; jalankan di laptop, bukan VPS 1 GB)
uv run --python 3.12 --with openpyxl==3.1.5 \
  python export_dataset.py jobs/ssk2024.json DATA_ROOT OUT.xlsx
```

`DATA_ROOT` adalah folder data job, misalnya `data/ssk2024`. Isinya harus memuat `.hash_salt` supaya id fans di-hash sama dengan ekspor sebelumnya.

### 4. Uji batas jendela

`stress_test.py` membandingkan hasil jendela besar dan kecil untuk task tertentu. Variabel env-nya sama dengan job, ditambah `STRESS_TASKS`, `STRESS_START`, `STRESS_DAYS`, `STRESS_HOURS`, dan `STRESS_BARE`.

### 5. Analisis

```bash
uv run --python 3.12 --with numpy --with pandas --with scipy --with statsmodels \
  python analysis.py analysis data/<handle>_v2.json [file lain …]
```

### 6. Tes offline

Tes ini tanpa request ke X dan tanpa Telegram:

```bash
uv run --python 3.12 --with openpyxl==3.1.5 --with twitter-cli==0.8.5 \
  python tests/test_jobs_offline.py
```

### 7. Laporan PDF

```bash
uv run --python 3.12 --with markdown \
  python report/build_pdf.py report/laporan_project_x_jkt48.md
```

Membutuhkan Google Chrome (dipakai headless untuk mencetak PDF).

## Deploy

### VPS (systemd)

1. Salin folder project ke `~/jkt48-x-metrics` di server Ubuntu, dengan user `ubuntu`. Path ini tertulis di unit systemd.
2. Jalankan `deploy/setup_vps.sh`. Skrip ini membuat `.venv`, memasang dependensi, membuat `.env` dari template, dan memasang unit systemd.
3. Batch member: isi `.env`, lalu `sudo systemctl enable --now jkt48-x-worker`.
4. Job: `cp .env.job.example .env.job.akun1`, isi, `chmod 600`, lalu `sudo systemctl enable --now jkt48-x-job@akun1`. Ulangi untuk akun lain.

Unit memakai prioritas rendah (`Nice=10`, `CPUWeight=20`) dan `MemoryMax`, supaya aman berbagi server.

### Docker / Railway

`Dockerfile` + `run.sh` memilih worker lewat `WORKER=members|jobs|stress`. Belum pernah diuji di Docker. `docker-compose.yml` menyediakan contoh untuk batch member.

### Dashboard harian (`daily/`)

- Deploy ke Railway dengan `RAILWAY_DOCKERFILE_PATH=daily/Dockerfile` dan Volume di `/data`. Env-nya ada di `daily/.env.example`: akun X, proxy, `GOOGLE_SA_JSON`, `SHEET_ID`, `REFRESH_KEY`, `FETCH_ENABLED`.
- Cron 00:00 WIB menyimpan snapshot follower, tweet baru, dan mention harian ke Google Sheets.
- **Jangan deploy saat fetch sedang berjalan**, karena restart membunuh run dan data hari itu tidak lengkap.

## Batasan X

- **Rate limit:** sekitar 50 request per 15 menit per akun. Proxy tidak menambah kuota; untuk mempercepat, tambah akun.
- **Timeline profil** berhenti di sekitar 840 tweet, jadi data utama diambil lewat search berjendela waktu.
- **Search tidak 100% lengkap:** akun protected, tersaring, atau yang sudah dihapus tidak ikut. Dalam uji batas, jendela 1 hari selalu lengkap dan jendela berisi sampai ±180 tweet juga lengkap; jendela berisi 260–300 tweet kehilangan 1–3%.
- **Risiko akun:** pemakaian otomatis tetap berisiko untuk akun yang dipakai. Itu sebabnya selalu pakai akun cadangan dan tempo pelan.

## Privasi dan etika

- Fans individu (di luar daftar member, fanbase, dan official) **tidak diprofilkan**. Di ekspor, handle dan id tweet mereka di-hash; teks, link, dan follower persis tidak ditulis.
- **Data mentah** (`*.jsonl`) masih menyimpan id tweet asli fans, jadi jangan dibagikan. Data mentah, salt, dan ekspor sudah dikecualikan dari git.
- Tweet member ditulis apa adanya. Member JKT48 tidak membalas atau me-quote fans.
- Fandom sensitif terhadap perbandingan member. Sajikan data dengan netral dan jangan publikasikan daftar member "konversi rendah".
# x-jkt48-metrics
