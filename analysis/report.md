# Sanity check & analisis awal — 6 member (Erine, Christy, Freya, Marsha, Fiony, Olla)
_Periode 22 Oct 2025 – 22 Oct 2026 WIB · 3.925 tweet · dibuat 23 Oct 2026 05:24 WIB · tanpa request baru ke X._

Aturan: metrik engagement hanya dari **post utama (Original + Quote)** yang berumur ≥ 7 hari saat diambil. Repost tidak dihitung (metriknya milik tweet asli). Kelompok dengan n < 10 tidak dipakai untuk keputusan.

## Bagian 1 — Sanity check

### 1.1 Kebersihan data
| member | tweet | key≠id | id ganda lintas file | di luar rentang waktu | metrik negatif | kategori tak dikenal | post utama like>views | repost | post utama belum matang (<7 hari) |
|---|---|---|---|---|---|---|---|---|---|
| Christy | 468 | 0 | 0 | 0 | 0 | 0 | 0 | 101 | 3 |
| Fiony | 657 | 0 | 0 | 0 | 0 | 0 | 0 | 79 | 6 |
| Erine | 1.680 | 0 | 0 | 0 | 0 | 0 | 0 | 481 | 10 |
| Olla | 406 | 0 | 0 | 0 | 0 | 0 | 0 | 69 | 4 |
| Freya | 350 | 0 | 0 | 0 | 0 | 0 | 0 | 150 | 2 |
| Marsha | 364 | 0 | 0 | 0 | 0 | 0 | 0 | 99 | 1 |

Repost tetap disimpan untuk analisis perilaku, tapi tidak pernah masuk agregat engagement.

### 1.2 Kelengkapan per minggu
| member | jendela selesai | minggu penuh | median post/minggu | minggu kosong | kosong beruntun terpanjang | minggu sangat rendah |
|---|---|---|---|---|---|---|
| Christy | 53 | 52 | 7,0 | 0 | 0 | 14 Jan 26 |
| Fiony | 53 | 52 | 9,5 | 0 | 0 | – |
| Erine | 53 | 52 | 23,0 | 0 | 0 | – |
| Olla | 53 | 52 | 6,0 | 0 | 0 | 07 Jan 26, 11 Feb 26 |
| Freya | 53 | 52 | 3,0 | 5 | 1 | – |
| Marsha | 53 | 52 | 4,0 | 2 | 1 | – |

Hanya minggu penuh yang dihitung (sampai 21 Oct 2026); minggu parsial terakhir dikeluarkan. Minggu sangat rendah = ≤20% median member itu; bisa nyata (member jarang posting) atau lubang search.

### 1.3 Cakupan search dibanding timeline profil
| member | isi timeline (semua) | timeline mulai | non-repost di periode | ditemukan search | cakupan search % | ditambal dari timeline | repost di timeline | repost di data |
|---|---|---|---|---|---|---|---|---|
| Erine | 1.553 | 16 Dec 2024 | 1.063 | 1.052 | 99,0 | 11 | 487 | 481 |

Hanya 1 dari 6 member punya data timeline untuk dibandingkan; member lain belum terverifikasi cakupannya. Reply ke akun lain jarang muncul di timeline, jadi cakupan reply tidak bisa dicek dengan cara ini.

**Lubang lokal** (hari dengan ≥3 tweet di timeline tapi search menemukan <50%):

| member | tanggal | tweet timeline | ditemukan search |
|---|---|---|---|
| Erine | 10 Apr 2026 | 4 | 1 |
| Erine | 11 Apr 2026 | 3 | 0 |

Tweet non-repost yang terlewat di hari-hari ini sudah ditambal dari timeline, tapi repost dan reply di hari yang sama kemungkinan ikut terlewat.

### 1.4 Kejenuhan metrik menurut umur tweet
Median like/views per kelompok umur saat diambil ÷ median tweet berumur 30–90 hari (1,00 = setara). Sel dengan n < 10 dikosongkan (–).

| member | metrik | <3h | 3–7h | 7–14h | 14–30h | 30–90h | 90–180h | >180h |
|---|---|---|---|---|---|---|---|---|
| Christy | likes | – | – | – | 0,87 | 1,00 | 1,17 | 1,19 |
| Christy | views | – | – | – | 0,90 | 1,00 | 1,28 | 0,88 |
| Christy | n post | 2,00 | 1,00 | 2,00 | 12,00 | 34,00 | 59,00 | 139,00 |
| Fiony | likes | – | – | – | – | 1,00 | 1,63 | 1,20 |
| Fiony | views | – | – | – | – | 1,00 | 1,21 | 0,90 |
| Fiony | n post | 3,00 | 3,00 | 8,00 | 9,00 | 46,00 | 92,00 | 237,00 |
| Erine | likes | – | – | 1,05 | 1,06 | 1,00 | 1,17 | 0,97 |
| Erine | views | – | – | 0,89 | 1,08 | 1,00 | 1,10 | 0,68 |
| Erine | n post | 3,00 | 7,00 | 10,00 | 18,00 | 155,00 | 219,00 | 500,00 |
| Olla | likes | – | – | – | 1,38 | 1,00 | 1,27 | 1,44 |
| Olla | views | – | – | – | 1,01 | 1,00 | 1,19 | 1,37 |
| Olla | n post | 4,00 | 0,00 | 4,00 | 17,00 | 33,00 | 70,00 | 127,00 |
| Freya | likes | – | – | – | – | 1,00 | 1,21 | 1,10 |
| Freya | views | – | – | – | – | 1,00 | 1,47 | 0,86 |
| Freya | n post | 1,00 | 1,00 | 5,00 | 6,00 | 19,00 | 21,00 | 69,00 |
| Marsha | likes | – | – | – | – | 1,00 | 1,69 | 1,35 |
| Marsha | views | – | – | – | – | 1,00 | 1,11 | 0,91 |
| Marsha | n post | 0,00 | 1,00 | 2,00 | 7,00 | 52,00 | 29,00 | 100,00 |

Perbandingan ini antar tweet berbeda, jadi tercampur tren popularitas (mis. tweet >180 hari bisa lebih rendah karena member sedang naik). Uji kejenuhan yang benar: tarik ulang tweet yang sama setelah 7 hari.

### 1.5 Ketergantungan pada tweet viral
| member | post | porsi like tweet #1 % | porsi like top 1% % | rata-rata like | median like | rata-rata/median | trimmed mean 10% |
|---|---|---|---|---|---|---|---|
| Christy | 246 | 1,5 | 2,8 | 7.635 | 6.100 | 1,25 | 6.947 |
| Fiony | 392 | 0,9 | 3,2 | 7.117 | 5.461 | 1,30 | 6.529 |
| Erine | 902 | 0,6 | 4,0 | 5.752 | 4.510 | 1,28 | 4.973 |
| Olla | 251 | 1,5 | 4,2 | 5.971 | 4.491 | 1,33 | 5.327 |
| Freya | 120 | 2,6 | 2,6 | 10.462 | 9.018 | 1,16 | 9.570 |
| Marsha | 190 | 1,5 | 2,9 | 8.814 | 6.673 | 1,32 | 7.994 |

Rata-rata jauh di atas median = satu-dua tweet viral mendongkrak rata-rata; metrik utama memakai median.

### 1.6 Stabilitas dua paruh (batas 19 Apr 2026)
| member | post H1 | post H2 | median like H1 | median like H2 | rasio like H2/H1 | median views H1 | median views H2 | rasio views H2/H1 |
|---|---|---|---|---|---|---|---|---|
| Christy | 134 | 112 | 6.338 | 5.788 | 0,91 | 80.021 | 103.534 | 1,29 |
| Fiony | 227 | 165 | 5.201 | 6.190 | 1,19 | 73.529 | 91.624 | 1,25 |
| Erine | 479 | 423 | 4.294 | 4.762 | 1,11 | 46.348 | 67.585 | 1,46 |
| Olla | 122 | 129 | 4.970 | 4.298 | 0,86 | 62.800 | 51.278 | 0,82 |
| Freya | 65 | 55 | 9.314 | 8.937 | 0,96 | 152.577 | 185.688 | 1,22 |
| Marsha | 91 | 99 | 6.901 | 6.182 | 0,90 | 104.066 | 114.159 | 1,10 |

✅ LULUS (ρ=0.77)

### 1.7 Rasio engagement (deteksi anomali/bot)
| member | like/views % (median per post) | RT/like % (median per post) | bookmark/like % (median per post) | bookmark/like % (total) | reply/like % (median per post) | z like/views | z RT/like | z bookmark/like |
|---|---|---|---|---|---|---|---|---|
| Christy | 7,75 | 7,38 | 1,54 | 3,18 | 4,68 | 0,21 | 0,48 | 1,25 |
| Fiony | 7,34 | 5,79 | 1,04 | 2,65 | 4,96 | -0,21 | -0,87 | -0,40 |
| Erine | 8,96 | 6,33 | 1,20 | 2,80 | 5,80 | 1,47 | -0,41 | 0,11 |
| Olla | 7,82 | 4,90 | 0,88 | 1,86 | 2,38 | 0,29 | -1,64 | -0,94 |
| Freya | 5,56 | 9,18 | 1,57 | 2,62 | 3,62 | -2,06 | 2,01 | 1,33 |
| Marsha | 6,53 | 7,30 | 1,13 | 3,30 | 2,85 | -1,06 | 0,41 | -0,11 |

'median per post' = median dari rasio tiap post; 'total' = jumlah bookmark ÷ jumlah like. Keduanya bisa beda jauh karena post viral punya rasio bookmark lebih tinggi. z dihitung robust (MAD) antar member.

### 1.8 Korelasi antar metrik (Spearman per member, nilai terkecil antar member)
| metrik | likes | retweets | replies | quotes | views | bookmarks |
|---|---|---|---|---|---|---|
| likes | 1,00 | 0,85 | 0,42 | 0,58 | 0,70 | 0,87 |
| retweets | 0,85 | 1,00 | 0,24 | 0,64 | 0,61 | 0,87 |
| replies | 0,42 | 0,24 | 1,00 | 0,49 | 0,31 | 0,28 |
| quotes | 0,58 | 0,64 | 0,49 | 1,00 | 0,61 | 0,65 |
| views | 0,70 | 0,61 | 0,31 | 0,61 | 1,00 | 0,75 |
| bookmarks | 0,87 | 0,87 | 0,28 | 0,65 | 0,75 | 1,00 |

Pasangan yang ρ>0,8 di semua member: likes–retweets (0.85–0.95), likes–bookmarks (0.87–0.96), retweets–bookmarks (0.87–0.96). Pasangan seperti ini jangan dipakai bersamaan sebagai prediktor terpisah; pilih satu atau buat indeks.

### Ringkasan sanity check
| Cek | Hasil |
|---|---|
| Kebersihan data (id, rentang waktu, metrik negatif, kategori) | ✅ LULUS |
| Konsistensi metrik (like tidak melebihi views) | ✅ LULUS |
| Kelengkapan per minggu (tidak ada minggu kosong beruntun ≥3) | ✅ LULUS |
| Cakupan search vs timeline (1/6 member dicek) | ✅ LULUS, 2 hari berlubang |
| Kejenuhan metrik (tweet <7 hari ≥70% dari tweet 30–90 hari) | ⏳ tweet muda < 10 per kelompok |
| Ketergantungan outlier (top 1% tweet < 30% total like) | ✅ LULUS |
| Stabilitas dua paruh (Spearman ≥0,7) | ✅ LULUS (ρ=0.77) |
| Anomali rasio engagement (indikasi bot, |z| ≤ 3) | ✅ LULUS |
| Multikolinearitas (pasangan ρ>0,8 di semua member) | ⚠️ 3 pasangan — pakai satu saja/indeks |

Belum bisa diuji: baseline vs model & uji permutasi (butuh label vote/proxy), CV per tim, audit manual kelengkapan (6 member × 2 minggu), dan kejenuhan dengan tarik ulang.

## Bagian 2 — Analisis awal

### 2.1 Profil member
| member | tim | follower | post utama | reply | thread sendiri | repost | post utama/minggu | % hari aktif | jeda terpanjang (hari) | median like (L50) | persentil-10 like (L10) | median/rata-rata like | median views | median ER % | L10 per 1.000 follower | reply → member aktif % | reply → eks/JKT48V/saudara % | reply → non-roster lain % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Christy | Passion | 871.168 | 249 | 114 | 4 | 101 | 4,8 | 58 | 5,3 | 6.100 | 4.216 | 0,80 | 88.464 | 8,87 | 4,84 | 75 | 19 | 4 |
| Freya | Dream | 830.595 | 122 | 64 | 14 | 150 | 2,3 | 30 | 15,8 | 9.018 | 6.177 | 0,86 | 170.123 | 6,40 | 7,44 | 81 | 14 | 5 |
| Marsha | Dream | 773.209 | 191 | 73 | 1 | 99 | 3,7 | 44 | 13,0 | 6.673 | 3.902 | 0,76 | 107.691 | 7,38 | 5,05 | 78 | 16 | 5 |
| Fiony | Love | 728.705 | 398 | 176 | 4 | 79 | 7,6 | 72 | 6,1 | 5.461 | 3.392 | 0,77 | 82.659 | 8,51 | 4,66 | 82 | 8 | 6 |
| Olla | Dream | 638.816 | 255 | 81 | 1 | 69 | 4,9 | 58 | 10,3 | 4.491 | 2.583 | 0,75 | 54.990 | 8,44 | 4,04 | 91 | 2 | 5 |
| Erine | Passion | 276.906 | 912 | 223 | 64 | 481 | 17,4 | 93 | 3,5 | 4.510 | 3.197 | 0,78 | 56.236 | 10,43 | 11,55 | 88 | 10 | 1 |

- **L50/L10** = median dan persentil-10 like per post utama. Like bersifat anonim dan bisa datang dari non-follower, jadi ini indikator kasar besarnya basis yang rutin bereaksi, bukan hitungan orang.
- **median/rata-rata like** mendekati 1 = engagement merata antar post; kecil = didorong post viral. Selisih kecil antar member (mis. 0,78 vs 0,80) tidak bermakna.
- **Reply → eks/JKT48V/saudara** = balasan ke eks-member, JKT48V, atau grup 48 lain (lihat `related_accounts.csv`). **Non-roster lain** = sisanya (brand/akun lain). Member JKT48 tidak membalas fans, jadi kategori ini bukan interaksi dengan fans.

### 2.2 Efek konten terhadap views (dalam member yang sama)
OLS log1p(views) dengan efek tetap member & bulan; SE cluster per member-minggu; p dikoreksi Holm. n = 2101 post, R² = 0.51. Pembanding: teks, jam 12–18 WIB, hari kerja, Original, teks sedang. Kategori media dengan n < 30 digabung.

| faktor | efek % | CI bawah % | CI atas % | p | p (Holm) |
|---|---|---|---|---|---|
| media_g = photo | 111,1 | 98,3 | 124,7 | 0,000 | 0,000 |
| media_g = video/gif (n kecil) | 113,5 | 65,7 | 175,0 | 0,000 | 0,000 |
| slot = 00–06 | 3,3 | -3,8 | 10,8 | 0,373 | 1,000 |
| slot = 06–12 | -6,4 | -12,1 | -0,4 | 0,036 | 0,217 |
| slot = 18–24 | 4,3 | -0,7 | 9,6 | 0,092 | 0,366 |
| kind = Quote | 14,7 | 3,5 | 27,1 | 0,009 | 0,061 |
| panjang = kosong | 7,4 | -11,9 | 31,1 | 0,480 | 1,000 |
| panjang = panjang | -8,1 | -15,8 | 0,2 | 0,054 | 0,271 |
| panjang = pendek | -7,2 | -11,5 | -2,6 | 0,003 | 0,020 |
| akhir_pekan | -0,1 | -5,6 | 5,6 | 0,958 | 1,000 |

### 2.2 Efek konten terhadap likes (dalam member yang sama)
OLS log1p(likes) dengan efek tetap member & bulan; SE cluster per member-minggu; p dikoreksi Holm. n = 2101 post, R² = 0.64. Pembanding: teks, jam 12–18 WIB, hari kerja, Original, teks sedang. Kategori media dengan n < 30 digabung.

| faktor | efek % | CI bawah % | CI atas % | p | p (Holm) |
|---|---|---|---|---|---|
| media_g = photo | 138,3 | 128,0 | 149,1 | 0,000 | 0,000 |
| media_g = video/gif (n kecil) | 74,2 | 48,2 | 104,8 | 0,000 | 0,000 |
| slot = 00–06 | 4,9 | 0,2 | 9,7 | 0,039 | 0,273 |
| slot = 06–12 | -2,2 | -6,9 | 2,8 | 0,381 | 1,000 |
| slot = 18–24 | 1,2 | -2,0 | 4,5 | 0,482 | 1,000 |
| kind = Quote | -6,9 | -14,1 | 1,0 | 0,085 | 0,508 |
| panjang = kosong | 7,7 | -6,3 | 23,7 | 0,299 | 1,000 |
| panjang = panjang | -4,5 | -10,1 | 1,5 | 0,140 | 0,698 |
| panjang = pendek | -5,5 | -8,5 | -2,5 | 0,000 | 0,004 |
| akhir_pekan | 2,1 | -1,6 | 6,0 | 0,270 | 1,000 |

Jumlah post per kategori: {'media': {'teks': 1571, 'photo': 500, 'video/gif (n kecil)': 30}, 'slot': {'18–24': 889, '12–18': 701, '06–12': 277, '00–06': 234}, 'panjang': {'pendek': 1198, 'sedang': 661, 'panjang': 200, 'kosong': 42}, 'kind': {'Original': 1987, 'Quote': 114}}.

Hanya efek dengan p (Holm) < 0,05 yang layak dianggap sinyal. Semua ini asosiasi terhadap **engagement**, bukan vote: post foto mungkin dibuat saat momen istimewa, jadi foto belum tentu penyebabnya.

**Efek foto per member** (model di atas mengasumsikan efek sama untuk semua member):

| member | n foto | n teks | views foto/teks × | like foto/teks × |
|---|---|---|---|---|
| Christy | 61 | 182 | 1,96 | 2,41 |
| Fiony | 131 | 255 | 2,14 | 2,42 |
| Erine | 131 | 756 | 2,45 | 2,82 |
| Olla | 83 | 165 | 2,22 | 2,39 |
| Freya | 23 | 97 | 1,79 | 2,06 |
| Marsha | 71 | 116 | 1,92 | 2,60 |

### 2.3 Tren bulanan — median views post utama (n post)
| bulan | Christy | Fiony | Erine | Olla | Freya | Marsha |
|---|---|---|---|---|---|---|
| 2025-10 (parsial) | 52.664 (n=5) ⚠ | 62.065 (n=12) | 33.628 (n=25) | 45.601 (n=15) | 195.437 (n=3) ⚠ | 78.568 (n=7) ⚠ |
| 2025-11 | 80.783 (n=17) | 60.893 (n=31) | 36.381 (n=73) | 58.276 (n=18) | 141.268 (n=7) ⚠ | 89.338 (n=10) |
| 2025-12 | 72.573 (n=31) | 58.375 (n=35) | 51.526 (n=68) | 58.683 (n=24) | 156.722 (n=11) | 109.436 (n=26) |
| 2026-01 | 114.842 (n=21) | 75.415 (n=41) | 48.460 (n=82) | 190.898 (n=18) | 422.333 (n=6) ⚠ | 103.590 (n=12) |
| 2026-02 | 82.427 (n=22) | 66.448 (n=49) | 39.236 (n=97) | 58.961 (n=13) | 149.228 (n=9) ⚠ | 121.396 (n=10) |
| 2026-03 | 76.373 (n=25) | 79.684 (n=47) | 51.251 (n=102) | 43.679 (n=21) | 138.508 (n=24) | 126.176 (n=10) |
| 2026-04 | 68.332 (n=20) | 103.908 (n=28) | 44.650 (n=67) | 56.509 (n=21) | 126.826 (n=10) | 96.108 (n=25) |
| 2026-05 | 97.650 (n=12) | 75.786 (n=34) | 55.635 (n=67) | 45.420 (n=21) | 220.828 (n=8) ⚠ | 105.993 (n=13) |
| 2026-06 | 108.166 (n=20) | 116.094 (n=31) | 62.490 (n=83) | 51.280 (n=26) | 256.591 (n=7) ⚠ | 127.304 (n=5) ⚠ |
| 2026-07 | 120.737 (n=29) | 117.930 (n=26) | 94.538 (n=75) | 68.400 (n=25) | 257.328 (n=7) ⚠ | 151.964 (n=13) |
| 2026-08 | 104.596 (n=18) | 76.841 (n=28) | 71.044 (n=80) | 51.750 (n=11) | 191.403 (n=10) | 94.519 (n=32) |
| 2026-09 | 77.788 (n=20) | 88.375 (n=17) | 61.532 (n=65) | 44.432 (n=28) | 143.837 (n=11) | 128.185 (n=21) |
| 2026-10 (parsial) | 88.370 (n=6) ⚠ | 77.556 (n=13) | 62.810 (n=18) | 69.838 (n=10) | 190.970 (n=7) ⚠ | 144.603 (n=6) ⚠ |

⚠ = n < 10. Bulan parsial: bulan pertama dan terakhir periode.

### 2.4 Reply antar member aktif (termasuk nilai seri di batas bawah)
| dari | membalas | jumlah |
|---|---|---|
| Erine | Ribka | 24 |
| Erine | Levi | 17 |
| Erine | Oline | 16 |
| Erine | Delynn | 15 |
| Erine | Nachia | 15 |
| Fiony | Jessi | 14 |
| Olla | Jessi | 13 |
| Erine | Lana | 12 |
| Fiony | Fritzy | 11 |
| Fiony | Nayla | 11 |
| Fiony | Lana | 10 |
| Christy | Kimmy | 9 |
| Marsha | Kathrina | 9 |
| Marsha | Indah | 8 |
| Fiony | Freya | 8 |
| Christy | Kathrina | 8 |

### 2.5 Hashtag yang paling sering dipakai member
| member | hashtag terbanyak |
|---|---|
| Christy | #passionshow (4), #strugglewithg20wingup (3), #guepassion (2), #passionfire (2), #nabungrechehan (2) |
| Fiony | #tgif (42), #andaikubukanidolajkt48 (7), #itadakilovejkt48 (2), #oneloveonespire (2), #risewithspire (2) |
| Erine | #diesvenerine (23), #memory (9), #sahurine (9), #kabarinkalobiru (8), #iftarine (8) |
| Olla | #pestaollangtahun (3), #hollatwentyone (3), #newprofilepic (3), #pokella (2), #dreambakudanjkt48 (2) |
| Freya | #fremakanfre (2), #wongkalahan (1), #lrkoseli (1), #minat (1), #jkt48teamon (1) |
| Marsha | #andaikubukanidolajkt48 (4), #jkt48dream (3), #marsha300flight (2), #gloriousrunway (2), #dreammeledaxxxx (2) |
