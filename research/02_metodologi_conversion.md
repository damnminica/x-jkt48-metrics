# Metodologi analitik: X → Komitmen → Vote (Senbatsu Sousenkyo JKT48)

## 0. Prinsip dan jebakan data

- **Vote = uang** (beli CD/tiket vote). Sebarannya sangat miring: sebagian kecil "whale" bisa menyumbang mayoritas vote. Data X mengukur seberapa *luas* fanbase. Vote mengukur seberapa *dalam* dompetnya. Karena itu conversion selalu dianalisis di skala log.
- **n ≈ 50 di level vote.** Dengan α = 0,05, korelasi baru signifikan kalau |r| ≳ 0,28. Hanya efek besar yang bisa terdeteksi, jadi jumlah fitur harus dibatasi.
- **Bias umur metrik.** Tiap tweet hanya diambil sekali, dan tweet yang masih muda belum jenuh metriknya. Pakai hanya tweet yang umurnya ≥ 7 hari saat diambil. Alternatifnya, koreksi dengan kurva m(a) = m∞·(1 − e^(−a/τ)), τ diestimasi per tipe tweet.
- **Follower hanya snapshot.** Angkanya akumulasi bertahun-tahun dan dipengaruhi umur akun, generasi, bot, dan follower luar negeri. Jangan jadikan penyebut utama. **Mulai sekarang simpan snapshot follower harian.**
- **Views** dipengaruhi algoritma dan baru ada sejak akhir 2022, jadi tidak bisa dibandingkan dengan era sebelumnya.
- **Data hilang ~2%:** cek apakah hilangnya acak. Kalau terpusat di reply atau tweet yang dihapus, kategori itu jadi bias.
- **Leakage:** fitur harus diambil dari jendela *sebelum* label, misalnya 90 hari sebelum pengumuman election. Engagement selama masa election sudah tercampur efek kampanye itu sendiri (kausalitas terbalik).
- **Catat mekanisme vote** (CD, membership, kanal online gratis/berbayar, siapa yang eligible, status trainee). Struktur conversion berubah total kalau kanalnya berubah.

## 1. Definisi conversion rate

Notasi per member i: V = vote, F = follower, ΣW = total views tweet Original, ΣL = total like, C = unit komitmen (tiket exclusive terjual bersih).

**Proxy unique engager.** Tidak ada data siapa yang like, jadi pakai proxy berikut (semuanya dari tweet Original yang sudah jenuh, jendela 90 hari):
- **L50** = median like per tweet ≈ jumlah fans yang like hampir semua post.
- **L10** = persentil ke-10 like = "lantai" fanbase.
- **R50** = median reply.
- **K = L50 / mean(L)** = konsentrasi. K tinggi berarti basisnya loyal. K rendah berarti engagement didorong tweet viral.

| Varian | Rumus | Makna | Kelemahan |
|---|---|---|---|
| CR_F | V/F | vote per follower | follower basi, ada bot, bergantung umur akun |
| CR_W | 1000·V/ΣW | vote per 1.000 views | algoritma, viral bocor ke non-fans, bergantung frekuensi posting |
| CR_L | V/ΣL | vote per like | bergantung jumlah tweet |
| **CR_core** | V/L50 | vote per fan inti aktif | paling dekat dengan unique engager |
| **CR_C** | V/C | vote per unit komitmen | butuh data stok yang lengkap |

**Yang paling bermakna:** CR_core dan CR_C. Vote digerakkan fans inti yang mau mengeluarkan uang, bukan oleh reach.

**Rasio mentah tetap menyesatkan.** Kalau V ∝ E^b dengan b ≠ 1, rasio V/E otomatis menguntungkan akun kecil (b < 1) atau akun besar (b > 1). Ini masalah korelasi rasio palsu (spurious ratio correlation). Definisi utama yang saya sarankan adalah **Conversion Efficiency Index (CEI)** berbasis residual:

```
log V_i = a + b·log E_i + γ'K_i + ε_i      CEI_i = ε̂_i   (exp(ε̂) = "x kali dari yang diharapkan")
```

- E = core engagement (L50).
- K = kontrol struktural: tim/status trainee, generasi, umur akun.
- b sendiri adalah **elastisitas** yang berguna untuk strategi: fan inti naik 10% → vote naik kira-kira b·10%.

**Normalisasi:**
- Pakai log1p untuk semua count.
- Untuk model, pakai z-score global pada nilai log.
- z-score per tim/generasi **hanya untuk laporan** "relatif terhadap rekan". Jangan standarisasi per kelompok sebelum modeling, karena itu menghapus perbedaan nyata antar kelompok. Masukkan kelompok sebagai efek hierarkis.
- Pakai rank/persentil supaya tahan outlier.
- Pakai median per tweet, bukan jumlah, supaya posting yang banyak tidak otomatis dapat nilai tinggi.

## 2. Kerangka funnel

```
V = F · (A/F) · (E/A) · (C/E) · (V/C)
```

Kalau di-log, persamaan ini jadi penjumlahan. Selisih log vote dua member bisa diurai per tahap (waterfall).

- **Reach:** F (residual terhadap umur akun), median views Original (W50), viral rate (% tweet > 3× median views member itu), amplifikasi (RT/views).
- **Engagement:** ER = (L + RT + Rp + Q + BM)/views (pakai median), L50, L10, R50, bookmark rate (niat menyimpan), reply rate, K, konsistensi (CV like mingguan).
- **Perilaku member (hal yang bisa dikendalikan):** frekuensi posting, % hari aktif, jeda terpanjang, komposisi media, % Original vs Repost, rasio reply ke akun lain (fan service), self-thread, kecocokan jam posting dengan jam aktif fans.
- **Komitmen:** θ dari stockcheckerv2 (lihat bagian 3a). Data ekstensi jadwal theater hanya milik pribadi, jadi tidak representatif. Kalau ada data lineup/center/jumlah show per member, tambahkan sebagai ukuran eksposur offline.
- **Vote:** V_prelim, V_final, dan V_late = V_final − V_prelim.

Konversi antar tahap: ER (Reach → Engagement), C/L50 (Engagement → Komitmen), V/C (Komitmen → Vote).

## 3. Masalah label (belum ada data vote)

### a) Proxy sekarang: Commitment Index dari stockcheckerv2

**Data per member i dan sesi s:**
- Q_is = kuota awal, yaitu snapshot pertama saat penjualan dibuka. Pastikan ini dicatat.
- Terjual bersih = Σ stock_decrease − Σ stock_return.
- T_is = waktu sampai sold_out. Kalau tidak habis sampai penutupan, datanya tersensor kanan.

**Jangan pakai waktu sold-out mentah.** Ada dua alasan:
- Kuota dialokasikan manajemen sesuai popularitas (endogen).
- Status habis/tidak habis tersensor.

Gunakan model survival:

```
h_is(t) = h0(t) · exp(θ_i + γ'Z_s + δ·log Q_is)
```

- Z = jenis (MnG/VC/2-shot), slot, hari, harga.
- θ_i (frailty / random effect) = **Commitment Index**.
- Alternatif sederhana: DP_is = terjual dalam 10 menit pertama / Q_is, lalu model campuran (mixed model) pada logit DP.

**Kontaminasi:** bot/scalper (termasuk bot milik sendiri) dan hold yang tidak dibayar (stock_return) mengukur persaingan beli, bukan permintaan organik. Pakai unit bersih, dan uji sensitivitas dengan membuang sesi yang anomali.

**Keuntungan data ini:** ada banyak sesi per member, jadi n efektifnya besar. Ini tempat terbaik untuk mempelajari fitur X:
- Panel member × bulan: fitur X bulan t → θ_i di bulan t+1.
- Validasi temporal: latih di bulan awal, uji di bulan akhir.

### b) Validasi saat hasil keluar

- **Pre-register dulu.** Tulis prediksi dan hipotesis lalu commit ke git (ada timestamp) sebelum hasil keluar. Ini mencegah HARKing (merumuskan hipotesis setelah melihat hasil).
- **Hasil sementara:** hitung Spearman ρ, presisi@16, dan coverage interval 80%. Lalu update posterior dengan V_prelim sebagai label untuk memprediksi hasil akhir.
- **Hasil akhir:** uji tiga hal: (1) apakah θ (uang) memprediksi vote lebih baik daripada metrik X, (2) CR_core vs CEI, (3) analisis residual.

### c) Backtest dengan data election lama

- Member, platform, dan metriknya sudah berbeda (dulu belum ada views). **Jangan pindahkan koefisien per fitur.**
- Data lama hanya untuk **prior struktural**: bentuk distribusi vote (rasio peringkat 1 / 16 / 32, kemiringan Pareto), korelasi rank sementara → akhir, dan porsi vote yang masuk belakangan.
- Kalau follower era itu bisa direkonstruksi (Wayback Machine, wiki), uji CR_F secara kasar saja.
- Election sister group hanya untuk prior bentuk distribusi.

## 4. Model untuk n ≈ 50

**Target:** y = log V (atau log V_late).

**Fitur:** maksimal 6–8 indeks komposit (rata-rata z dalam satu blok, atau PC1 per blok):
- Reach
- Core (L50/L10)
- Kualitas engagement
- Fan service
- Konsistensi
- θ Komitmen
- Kontrol: trainee, umur akun

Tanpa regularisasi, aturan praktisnya hanya n/10–15 ≈ 3–5 parameter efektif. Cek VIF karena fitur-fitur reach biasanya saling berkorelasi tinggi.

**Lapisan model:**
1. **Baseline:** y ~ log F, dan y ~ θ. Model lain harus mengalahkan baseline ini.
2. **Elastic net:** min Σ(y − Xβ)² + λ[(1−α)/2·‖β‖² + α‖β‖₁], dengan nested CV (LOO di luar, K-fold di dalam). Lasso murni tidak stabil kalau fiturnya berkorelasi.
3. **Robust:** Huber atau Student-t, karena ada outlier "oshi whale".
4. **Bayesian hierarkis (PyMC/brms):**
   ```
   y_i ~ Student-t(ν, μ_i, σ);   μ_i = α_g[i] + X_i·β
   α_g ~ N(μ_α, τ);   β ~ N(0, 0.5) atau horseshoe;   g = tim × status/generasi
   ```
   Partial pooling menangani kelompok yang kecil. Hasilnya berupa interval prediktif per member.
5. **Ranking:** Spearman ρ, Kendall τ, presisi@16, NDCG. Dengan Monte Carlo dari posterior: tarik vote untuk semua member, urutkan, lalu hitung P(rank ≤ 16) dan distribusi vote ambang peringkat 16.

**Over/under-performer:**
- CEI_i = y_i − ŷ_i(LOO). Pakai prediksi LOO, jangan in-sample, karena in-sample mengecilkan residual outlier.
- Tandai member kalau y-nya di luar interval prediktif 80%.
- Setelah itu bandingkan profil perilakunya secara deskriptif.

**Pentingnya fitur tanpa overfitting:**
- Permutation importance di fold uji (ΔRMSE, Δρ), dirata-rata dari repeated CV.
- Stability selection: 1.000 bootstrap elastic net. Fitur j dianggap stabil kalau π_j ≥ 0,7 dan tandanya konsisten ≥ 90%.
- Laporkan β terstandarisasi dengan CI bootstrap, bukan p-value tunggal. Pakai koreksi Benjamini-Hochberg kalau banyak hipotesis diuji.

**Evaluasi:**
- LOO-RMSE di skala log. exp(RMSE) = galat multiplikatif.
- ρ, presisi@16, coverage interval.

## 5. Mengukur efek campaign (kausal, bukan sekadar korelasi)

**Masalahnya:**
- Kampanye tidak acak; fanbase biasanya berkampanye justru saat member sedang naik.
- Ada spillover: vote bersifat zero-sum dan fans bisa multi-oshi (melanggar SUTVA).
- Vote hanya punya 2 titik waktu.

**Outcome harian yang bisa dipakai:** L50 harian, ER, sell-through exclusive, follower harian (setelah mulai dicatat), dan volume hashtag/mention (perlu scraper untuk akun fanbase dan hashtag).

**Desain:**
- **Before–after naif:** hanya deskriptif, karena tren dan musiman ikut mengacaukan.
- **ITS (satu member):**
  ```
  Y_t = β0 + β1·t + β2·D_t + β3·(t−T)·D_t + s(hari-minggu) + ε_t
  ```
  ε diperlakukan sebagai AR(1) atau dengan Newey-West. β2 = lonjakan, β3 = perubahan tren.
- **DiD antar member:**
  ```
  Y_it = α_i + λ_t + δ·D_it + ε_it
  ```
  Kontrolnya member se-tim/generasi yang levelnya mirip tapi tidak berkampanye.
  - Event study: Σ_k δ_k·1[t − T_i = k], k = −14..+14, dengan k = −1 sebagai referensi, untuk cek pre-trend.
  - Kalau kampanye mulai di waktu berbeda (staggered), pakai Callaway–Sant'Anna atau Sun–Abraham, bukan TWFE biasa.
- **Synthetic control:** pembanding untuk satu member dibuat dari bobot member lain yang meniru pre-trend-nya.
- **Hasil sementara → akhir:**
  ```
  log V_late,i = a + δ·Kampanye_i + b·log V_prelim,i + γ'X_i + ε
  ```
  Ini sekaligus mengontrol regression to the mean.
- **Placebo:** uji dengan tanggal palsu dan outcome yang semestinya tidak terpengaruh.
- **Paling bersih: eksperimen di level fanbase.**
  - Shortlink/UTM unik per kanal dan per konten.
  - A/B: acak waktu dan variasi pesan.
  - Survei voter anonim (jumlah vote, sumber info). Data yang dikumpulkan seminimal mungkin.
  - Ini menghasilkan conversion mikro yang sungguhan, bukan proxy.
- **Power:** hitung dulu minimum detectable effect dari varians harian baseline 1 tahun sebelum kampanye dimulai.

## 6. Output konkret

1. **Tabel skor member** (refresh mingguan):
   - Reach, Core, ER, Fan service, Konsistensi, θ — masing-masing sebagai persentil global dan z dalam tim.
   - ŷ dengan interval prediktif 80% dan P(top 16).
   - Setelah hasil keluar: CEI dan label over/under-performer.
2. **Dashboard:**
   - Waterfall funnel per member (dekomposisi log).
   - Tren mingguan dengan penanda event/kampanye.
   - Heatmap sell-through per sesi.
   - Scatter log E vs log V dengan garis regresi. Titik di atas garis = conversion tinggi.
3. **Simulator what-if:**
   - (a) Ubah fitur: Δlog V = β·Δx dengan interval. Beri label "asosiasi" kecuali β berasal dari desain kausal.
   - (b) Gap ke senbatsu: dari Monte Carlo, berapa vote tambahan yang dibutuhkan agar P(top 16) ≥ 50% / 80%.
   - (c) Skenario kampanye: terapkan δ hasil DiD.
4. **Laporan pasca-election:** profil faktor yang membuat conversion tinggi vs rendah.

## 7. Data yang perlu mulai dikumpulkan sekarang

- Snapshot follower harian untuk semua member.
- Ambil ulang metrik tweet pada umur tetap (24 jam dan 7 hari) untuk kurva kecepatan.
- Akun fanbase dan hashtag kampanye; sampel reply fans untuk mengetahui geo/bahasa audiens.
- stockcheckerv2: simpan kuota awal, waktu buka penjualan, dan ID sesi.
- Kalender event: ulang tahun, posisi center, MV, jumlah show theater per member.
- Saat election: semua hasil sementara dan akhir per member, plus aturan kanal vote.

**Implementasi:**
- pandas → tabel `member_window`, `session_stock`, `panel_member_day`.
- lifelines (Cox frailty), scikit-learn (ElasticNetCV, permutation_importance), PyMC/bambi (model hierarkis), statsmodels/linearmodels plus csdid/differences (ITS dan DiD).