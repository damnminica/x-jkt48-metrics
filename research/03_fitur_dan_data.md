# Rancangan fitur: dari data X dan stok tiket ke prediksi conversion rate vote

## 0. Lima aturan yang dipakai di semua fitur

1. **Repost tidak dihitung sebagai engagement.** Di `data/CErine_JKT48.csv`, baris dengan `is_retweet=True` membawa metrik tweet aslinya (contohnya tweet resmi JKT48 dengan 161 ribu views). Metrik engagement dihitung dari set **E = Original + Quote**. Reply dianalisis terpisah. Repost hanya dipakai untuk fitur perilaku.
2. **Umur tweet memengaruhi metrik.** Metrik diambil satu kali, jadi tweet yang umurnya di bawah 7 hari belum matang. Tweet itu dibuang dari fitur engagement.
3. **Follower hanya diketahui hari ini.** Kalau engagement lama dibagi follower sekarang, member yang sedang naik daun akan terlihat jelek. Karena itu penyebut per tweet sebaiknya **views**, bukan follower.
4. **Normalisasi per bulan dan per event.** Kalau ada pengumuman grup, semua member ikut naik. Pakai skor-z atau persentil antar-member di bulan yang sama.
5. **Jumlah sampel cuma sekitar 50 member.** Satu model maksimal berisi 4–5 fitur. Ujinya pakai Spearman, partial correlation, dan leave-one-out CV. Hipotesis ditulis lebih dulu, sebelum hasil pemilu keluar, supaya tidak terjadi p-hacking.

### Definisi target
- `CR_follower = votes / follower` di awal masa voting
- `CR_core = votes / ukuran basis inti`, misalnya median like atau jumlah unique replier
- **Over-conversion** = residual ε dari `log(votes) = α + β·log(ukuran) + ε`. Nilai ε ini yang dijelaskan oleh "faktor-faktor". Ukuran = besar basis fans, ε = seberapa efektif basis itu diubah jadi vote.
- Semua fitur dibekukan pada tanggal cutoff, yaitu saat pemilu diumumkan, supaya tidak bocor ke target. Aktivitas selama masa kampanye dijadikan kelompok fitur tersendiri.

---

## A. Fitur dari data X yang sudah ada
Jendela default: 90 hari dan 365 hari. Semua dihitung per member.

**A1. Ukuran**
- `log_fol`: log follower saat ini
- `med_likes_90`, `med_views_90`: median like dan views di set E
- `floor_likes_90`: persentil ke-10 like. Ini "penonton minimal" yang selalu muncul di setiap post, jadi jadi proxy fans inti.
- `p90_likes`: ekor atas, mengukur potensi viral
- `reach_ratio = med_views / follower`: seberapa jauh tweet menjangkau orang di luar follower

**A2. Intensitas** (dihitung per tweet, lalu diambil median)
- `like_rate = likes/views`
- `bm_rate = bookmarks/views` dan `bm_per_like = bookmarks/likes`. Bookmark adalah sinyal niat untuk menyimpan, lebih "berkomitmen" daripada sekadar like.
- `reply_per_like = replies/likes`: kedalaman percakapan
- `quote_rate = quotes/views` dan `rt_rate = retweets/views`: amplifikasi, proxy fanbase yang terorganisir
- `cv_likes`: koefisien variasi like. Nilai rendah berarti basisnya stabil.
- `top5_share`: porsi total like yang datang dari 5 tweet teratas, yaitu ketergantungan pada tweet viral

**A3. Aktivitas member**
- Post per minggu dihitung per kategori
- `active_day_ratio`, streak hari aktif terpanjang, jeda terpanjang, simpangan baku jarak antar-post (keteraturan)
- Porsi reply ke fans, ke member, dan ke akun resmi. Butuh daftar handle member dan akun resmi untuk klasifikasi.
- `fan_reply_per_week`: intensitas fan service
- Porsi reply ke thread sendiri dan porsi repost, dirinci menurut asalnya (repost dari akun resmi, member lain, atau fans)
- `account_age`, `tweets_total`

**A4. Konten**
- Porsi foto, video, gif, dan teks, plus *lift* tiap jenis media terhadap median member itu sendiri (efek dalam satu member)
- Distribusi jam posting dalam WIB, misalnya porsi post jam 19–24 dan post setelah show
- Panjang teks, jumlah emoji, jumlah hashtag, bahasa (ID/EN/JP)
- Porsi post yang menyebut kata kunci "monetisasi": theater, show, VC, video call, 2shot, MnG, meet, makasih udah dateng

**A5. Momentum**
- Skor-z bulanan `log(med_like_rate)` dan `log(med_views)` relatif ke semua member di bulan yang sama
- `slope_12m`: kemiringan regresi skor-z selama 12 bulan
- `accel_3m`: rata-rata skor-z 3 bulan terakhir dikurangi rata-rata 9 bulan sebelumnya
- `rank_delta`: perubahan peringkat median like antara Okt 2025 dan Sep 2026

**A6. Jaringan antar-member**
- Bangun graf berarah antar-member dengan bobot dari reply, quote, dan repost
- Fitur: `in_strength` (seberapa sering member lain berinteraksi dengannya), `out_strength`, PageRank, betweenness, clustering
- `top_partner_share`: porsi interaksi dengan satu member tertentu, misalnya pasangan "ship"

**A7. Event**
- `rh_uplift`: median like_rate di jendela ±3 hari sekitar Request Hour 13 Jun 2026 dibagi baseline 28 hari sebelumnya. Kalau Request Hour memakai voting fans, hasil peringkatnya adalah label proxy terbaik yang sudah ada.
- `bday_uplift`: dihitung dengan cara yang sama di sekitar ulang tahun. Butuh kolom `tgl_lahir` di `members.csv`.
- `bday_hashtag_authors`: jumlah unique author pada hashtag ulang tahun. Data ini bisa ditarik mundur lewat search. Gunanya mengukur kemampuan fanbase memobilisasi orang, semacam gladi kampanye.
- `official_mentions`: frekuensi member disebut atau difoto oleh akun resmi JKT48, sebagai proxy dorongan manajemen. Cukup menarik 1 akun tambahan.

---

## B. Fitur dari stockcheckerv2
Notasi: event e, member m, sesi s, `q(t)` = `available_quota`.

**Cara menurunkan dari change log:**
1. **`Q0(m,s)`** adalah `available_quota` pertama sebelum atau tepat saat penjualan dibuka. Kalau monitor baru jalan setelah buka, pakai q maksimum yang teramati dan beri flag `q0_reliable=0`.
2. **`T_open(e)`** diambil dari jadwal resmi. Kalau tidak ada, pakai `stock_decrease` pertama di event itu.
3. **Bedakan `stock_return` dari tambahan kuota oleh admin.** Return biasanya delta kecil (1–2) dan menumpuk di sekitar batas waktu pembayaran. Tambahan admin biasanya delta besar.
4. Hitung `G = Σ|stock_decrease|` (beli kotor), `R = Σ stock_return`, `A = Σ tambahan admin`, dan `N = Q0 + A − q_final` (terjual bersih). Cek konsistensinya: N harus kira-kira sama dengan G − R.
5. **`TTS(m,s) = t(sold_out pertama) − T_open`**. Sesi yang tidak pernah sold out diperlakukan sebagai data tersensor. Resolusi TTS sama dengan interval polling, jadi member yang habis dalam satu kali polling dianggap seri.

**Fitur per member per event.** Semuanya dinormalisasi jadi persentil di dalam event, lalu dirata-rata antar-event.
- `tts_last`: waktu sampai **sesi terakhir** habis. Ini yang paling informatif karena mengukur seberapa dalam permintaannya.
- `tts_first`, `tts_median`
- `soldout_share`: jumlah sesi yang habis dibagi jumlah sesi
- `sell_through_5m = (Q0 − q(T_open+5m)) / Q0`: bisa dibandingkan walaupun TTS tersensor
- `peak_rate`: tiket per menit tertinggi
- `return_rate = R/G`. Angka ini sendiri ambigu: bisa karena gagal bayar, *hold* bot, atau calo.
- `reabsorb_time`: median waktu dari `stock_return` sampai kuota kembali ke 0. Kalau cepat, ada permintaan berlebih yang antre. Kalau lambat atau tidak terserap, permintaannya memang lemah.
- `unabsorbed_returns`: tiket kembalian yang tidak terjual lagi
- `q0_share = Q0_m / ΣQ0_event`: perkiraan permintaan versi manajemen, yang tahu riwayat penjualan
- `admin_add_flag`: manajemen menambah kuota, artinya permintaan melebihi ekspektasi mereka
- `demand_ratio_proxy` (heuristik): `N/Q0` kalau tidak sold out, dan `1 + log10(3600/TTS_detik)` kalau sold out
- Pisahkan per produk (MnG, VC, 2-shot) karena harga dan jangkauannya berbeda. VC daring juga bisa dijangkau fans dari luar kota atau luar negeri.
- `trend_demand`: kemiringan persentil antar-event

**Peringatan:**
- Untuk member teratas, kecepatan sold out banyak didorong bot dan calo. Keluarkan transaksi milik sendiri dari data.
- Ada efek plafon: semua member top habis di polling pertama. Karena itu `tts_last`, `soldout_share`, dan `reabsorb_time` lebih berguna daripada `tts_first`.

---

## C. Data yang harus mulai dikumpulkan sekarang
Biaya X di bawah adalah perkiraan rate limit GraphQL per akun: Search sekitar 50/15 menit, UserByScreenName sekitar 95/15 menit, TweetDetail sekitar 150/15 menit. Angka ini bisa berubah.

| # | Item dan isinya | Frekuensi | Request kira-kira | Risiko akun |
|---|---|---|---|---|
| 1 | **Profil member**: follower, following, statuses, `listed_count` (proxy fans serius), media_count, perubahan bio | Harian, jam tetap. Mingguan bisa melewatkan lonjakan event, padahal biayanya sama kecil. | 50/hari | Rendah |
| 2 | **Metrik tweet pada umur tetap**: tarik ulang tweet terbaru tiap member sehingga dapat metrik di umur sekitar 1 hari dan 7 hari | Harian | 50–100/hari (UserTweets atau search 1–2 page) | Rendah–sedang |
| 3 | **Sampel balasan fans**: 3–5 tweet E per member per minggu (acak + teratas). Simpan ID author yang di-hash, waktu, dan bahasa saja, tanpa teks. | Mingguan | ~1.000/minggu (TweetDetail + pagination) | Sedang |
| 4 | **Hashtag kampanye dan ulang tahun**: daftar per member dikurasi manual, lalu tambah otomatis dari tweet fanbase. Rekam jumlah tweet, unique author, author baru, dan waktu puncak. | Harian, lebih rapat saat event | 100–300/hari | Sedang (Search paling ketat; pakai pacing seperti `worker.py`) |
| 5 | **Akun fanbase per member** (1–5 per member, 100–250 akun): follower, frekuensi post, adanya open donasi atau project, engagement | Profil harian, timeline harian 1 page | 200–500/hari | Sedang. Kurasi manual adalah pekerjaan terbesarnya. |
| 6 | **Snapshot tiket exclusive** (stockcheckerv2): simpan snapshot mentah lengkap, bukan cuma diff, plus Q0, harga, jenis, sesi, event_id, interval polling, dan status HTTP | 1–2 detik dari T−5 menit sampai T+30 menit, lalu 1 menit sampai tutup. Di luar penjualan cukup 15–60 menit, karena listing kosong. | Ke API JKT48, bukan ke X | Sedang. Login JKT48 hanya boleh satu sesi, jadi **jangan pakai akun WAR untuk monitor**. Polling cepat bisa memicu Managed Challenge. Kalau endpoint stok bisa dibuka tanpa login, lebih aman. |
| 7 | **SHOWROOM / IDN Live**: frekuensi dan durasi live, penonton rata-rata dan puncak, follower room, ranking gift atau poin bila terlihat. Gift adalah uang sungguhan, jadi paling dekat dengan vote. | `onlives` tiap 1–2 menit, profil room harian | ~1.000–1.500/hari ke SHOWROOM, tidak ke X | Rendah kalau endpoint publik. Verifikasi endpoint dulu. IDN kemungkinan perlu login, jadi risikonya lebih tinggi. |
| 8 | **Jadwal theater dan lineup per member**: jumlah show per bulan, show spesial atau ulang tahun, posisi unit. Kalau ekstensi jadwal bisa melihatnya, tambahkan rasio peminat per show. | Harian | 1–5/hari | Rendah |
| 9 | Opsional: follower akun resmi JKT48 di X, TikTok, YouTube, Instagram, dan Google Trends per nama | Harian atau mingguan | Kecil | Instagram tinggi, sisanya rendah |
| 10 | **Begitu pemilu diumumkan**: mekanisme dan harga vote, hasil sementara (sokuhou), progres donasi fanbase, hashtag kampanye | Harian | Kecil | Rendah |

Data balasan fans (#3) cukup disimpan dalam bentuk agregat. Tidak perlu membangun profil fans per individu.

---

## D. Prioritas: 10 fitur paling prediktif
Kerangka uji yang sama untuk semua fitur:
- **Label sementara (bisa dipakai sekarang):** indeks permintaan exclusive dari B, dan hasil Request Hour kalau berbasis voting fans.
- **Label akhir:** log(votes) dan peringkatnya.
- **Uji per fitur:**
  - Spearman dengan CI bootstrap
  - Partial correlation dengan mengontrol `log_fol`, atau korelasi terhadap residual ε
  - ΔR² leave-one-out dibanding baseline `log(votes) ~ log_fol`
  - Uji permutasi
- **Model akhir:** ridge dengan maksimal 5 fitur.

| # | Fitur | Hipotesis | Cara uji khusus |
|---|---|---|---|
| 1 | **Indeks permintaan exclusive** (persentil `tts_last` + `soldout_share`, dirata-rata per event) | Dompet yang sama dengan pembeli vote. Kemungkinan prediktor terkuat. | Spearman dengan votes. Cek apakah tetap signifikan setelah mengontrol follower. |
| 2 | **`q0_share`** | Manajemen mengalokasikan kuota berdasarkan riwayat penjualan yang tidak kita lihat. | Lihat apakah menambah daya prediksi di atas #1. Kalau tidak, cukup pakai salah satu. |
| 3 | **`reabsorb_time` dan `admin_add_flag`** | Memecah plafon di member top: memperlihatkan permintaan berlebih di atas kuota. | Uji hanya pada member yang `soldout_share=1`: apakah fitur ini memisahkan peringkat vote mereka? |
| 4 | **`floor_likes_90`** | Vote adalah hitungan absolut dari fans inti. Follower tercampur akun pasif, bot, dan fans kasual luar negeri. | Bandingkan R² LOO `~log(floor_likes)` dengan `~log_fol`. Kalau lebih tinggi, jadikan penyebut CR. |
| 5 | **`bm_rate` / `bm_per_like`** | Bookmark adalah komitmen, jadi lebih dekat ke perilaku "membayar". | Korelasi dengan residual ε. |
| 6 | **Unique replier dan porsi repeat replier** (data baru #3) | Mengukur langsung jumlah fans inti dan loyalitasnya. | Mulai sampling sekarang. Uji dulu terhadap #1 sebelum pemilu. |
| 7 | **`accel_3m`** (momentum) | Member yang sedang naik membuat fans lebih termotivasi dan memicu efek ikut-ikutan. | Partial correlation. Saat pemilu, cek juga terhadap perubahan dari sokuhou ke hasil akhir. |
| 8 | **Indeks mobilisasi fanbase** (`bday_hashtag_authors`, `quote_rate`, `rt_rate`) | Fanbase yang terorganisir mampu menggalang dana dan vote kolektif. | Bisa diuji sekarang dari hashtag ulang tahun yang ditarik mundur. Terhadap ε, interpretasinya: mobilisasi mendongkrak konversi. |
| 9 | **`fan_reply_per_week`** | Fan service membangun timbal balik dan loyalitas, sehingga konversi naik. | Uji terhadap ε. Ada risiko kausalitas terbalik (member membalas karena fansnya aktif), jadi lihat urutan waktunya. |
| 10 | **Engagement SHOWROOM** (gift/poin, penonton puncak) | Dukungan berbayar yang rutin, perilakunya paling mirip membeli vote. | Data baru #7. Uji terhadap #1 dalam 2–3 bulan. |

Cadangan: `in_strength` jaringan (visibilitas lintas fandom), `rh_uplift`, `listed_count/follower`, dan porsi reply berbahasa Indonesia (fans domestik mungkin lebih mudah membeli vote).

### Untuk strategi kampanye
Pisahkan dua jenis faktor:
- **Yang bisa diubah fanbase:** #8, timing posting (dari A4 dengan efek dalam satu member), dan mengubah liker jadi voter (#4 ke votes).
- **Yang struktural atau dari sisi member dan manajemen:** #1–3, #9, `official_mentions`.

Hasil n=50 bersifat korelasional. Dorongan manajemen kemungkinan memengaruhi engagement X dan jumlah vote sekaligus, jadi jangan dibaca sebagai hubungan sebab-akibat.

**File yang relevan:**
- `/Users/yohanesaditri/Claude/x-jkt48-metrics/data/CErine_JKT48.csv` (contoh repost yang membawa metrik tweet aslinya)
- `/Users/yohanesaditri/Claude/x-jkt48-metrics/members.csv` (perlu ditambah kolom `tgl_lahir` dan daftar akun fanbase)
- `/Users/yohanesaditri/Claude/x-jkt48-metrics/fetch_v2.py` dan `/Users/yohanesaditri/Claude/x-jkt48-metrics/worker.py` (pacing yang bisa dipakai ulang untuk C1–C5)