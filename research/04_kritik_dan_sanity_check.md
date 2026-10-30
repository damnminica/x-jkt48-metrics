# Kritik skeptis: jebakan analisis "conversion rate X → vote" untuk Sousenkyo JKT48

## 0. Tiga masalah inti

1. **Belum ada pembilang, dan penyebutnya tidak terukur langsung.** Rumusnya vote / dukungan di X. Vote belum ada. Siapa yang nge-like tidak tercatat, dan follower cuma satu kali diambil, hari ini. Jadi sekarang kamu punya calon fitur, belum punya conversion rate.
2. **Data ini bukan data kampanye.** Isinya tweet akun member. Tweet akun fanbase, hashtag kampanye, dan thread ajakan vote tidak ada. Model dari data ini paling jauh bisa bilang "member dengan profil X tertentu dapat vote lebih banyak". Data ini tidak bisa bilang "kampanye jenis Y efektif".
3. **Setelah pemilu pun datanya cuma satu potret (cross-section) berisi kira-kira 50 member.** Bisa lebih sedikit kalau hanya peringkat atas yang diumumkan. Itu cukup untuk menguji 1–3 hipotesis yang ditulis sebelum hasil keluar. Itu tidak cukup untuk "menemukan faktor".

## 1. Definisi "conversion rate" sudah bermasalah sejak awal

- **Rasio vote/follower menyesatkan.**
  - Angka follower diambil Okt 2026, bukan saat pemilu. Isinya juga tercampur bot, akun mati, akun alt, dan fans luar negeri.
  - Member dengan follower sedikit akan punya rasio ekstrem.
  - Rasio dari dua angka yang sama-sama berisik bisa berkorelasi palsu dengan apa saja yang berkaitan dengan penyebutnya (spurious ratio, Kronmal 1993).
  - **Mitigasi:**
    - Jangan meregresikan rasio. Pakai model log(vote) ~ log(basis X) + kovariat. Anggap "conversion" sebagai residual atau elastisitas dari model itu.
    - Kalau tetap mau rasio per member, tarik nilainya ke arah rata-rata tim (shrinkage empirical Bayes).
    - Pakai minimal 2–3 definisi penyebut: follower, median like per tweet, median views. Kesimpulan baru bisa dipercaya kalau stabil di semua definisi.
- **Mekanisme vote menentukan segalanya.**
  - Kalau vote gratis (misalnya harian lewat aplikasi), yang diukur adalah luas basis fans. Di sini X cukup relevan.
  - Kalau vote berbayar (CD/single/membership/tiket), yang diukur adalah luas × dalam (uang per fans). Di sini X adalah sinyal lemah.
  - **Mitigasi:** jangan bangun model final sebelum aturan resmi keluar. Siapkan model terpisah untuk tiap kemungkinan mekanisme.
- **Hasil mungkin tersensor.** Kalau hanya peringkat atas yang diumumkan (pola umum 48G), suara member di bawahnya tidak diketahui. Regresi biasa (OLS) hanya pada member yang diumumkan akan bias. **Mitigasi:** pakai model ranking (Spearman, ordinal) atau Tobit.

## 2. Korelasi bukan kausalitas

- **Faktor tersembunyi** yang menaikkan follower/engagement sekaligus vote:
  - posisi senbatsu, center, dan unit;
  - eksposur TV, endorse, dan iklan;
  - generasi, lama di grup, dan umur;
  - tim dan peran di setlist theater;
  - program solo;
  - skandal atau isu lulus.
- **Sebab-akibatnya juga bisa terbalik:** member yang populer diberi posisi, lalu makin populer. Contoh: temuan "member yang sering posting foto dapat vote tinggi" hampir pasti efek popularitas, bukan efek fotonya.
- **Mitigasi:**
  - **Gambar diagram sebab-akibat (DAG) dulu.** Kumpulkan kovariat publik: riwayat senbatsu 12 bulan, generasi, lama di grup, tim, jumlah center. Dengan n=50 hanya 2–3 kovariat yang muat. Pilih berdasarkan teori, jangan dengan stepwise.
  - **Untuk efek konten, bandingkan tweet di dalam member yang sama.** Model per tweet: engagement ~ jenis media + jam + kategori + efek tetap (fixed effect, FE) member + FE minggu. Dengan 60–80 ribu baris, di sinilah data kamu benar-benar kuat. Tapi hasilnya adalah efek ke engagement, bukan ke vote.
  - **Pakai stockcheckerv2 sebagai panel berbayar.** Unitnya member × event penjualan exclusive. Uji apakah perubahan engagement X 2–4 minggu sebelumnya memprediksi kecepatan stok habis (dengan FE member dan FE event). Ini lebih dekat ke pertanyaan "X → uang" dibanding satu potret vote. Tetap tidak kausal murni, karena event besar menggerakkan keduanya sekaligus.
  - **Satu-satunya jalan kausal untuk kampanye adalah eksperimen fanbase sendiri** (lihat §10).

## 3. Engagement gratis vs vote berbayar

- **Like itu gratis, vote berbayar tidak.**
  - Suara per fans biasanya sangat timpang: segelintir whale bisa menyumbang porsi besar suara satu member, dan mereka bisa tidak aktif di X sama sekali.
  - X mengukur luas basis fans, bukan dalamnya dompet.
- **Sumber bias lain:**
  - fans luar negeri ikut menambah like/views tapi mungkin tidak bisa atau tidak ikut vote;
  - fans yang aktifnya di IG, TikTok, IDN Live, atau aplikasi resmi tidak terlihat;
  - bot, alt, dan akun giveaway menggelembungkan engagement tanpa ada uang yang keluar.
- **Mitigasi:**
  - **Pakai proxy "kedalaman" dari stockcheckerv2:** laju stock_decrease pada menit-menit awal, dan waktu sampai sold_out yang dinormalisasi dengan kuota. Ada empat catatan:
    1. Kuota ditentukan manajemen, jadi kuota itu sendiri sudah sinyal popularitas.
    2. Status sold_out berarti permintaan ≥ kuota. Sisa permintaannya tidak terlihat, jadi perlakukan sebagai data tersensor, bukan nilai pasti.
    3. stock_return kebanyakan pembayaran gagal atau kedaluwarsa, bukan hilangnya minat.
    4. Laju pembelian sebagian mencerminkan kapasitas bot, termasuk bot milikmu. Keluarkan transaksimu sendiri dan waspadai bias pada member yang paling diperebutkan bot.
  - **Fans luar negeri tidak bisa dideteksi** karena isi balasan tidak ada. Jangan diklaim. Paling jauh, rasio views/like per member bisa jadi indikator kasar audiens pasif.
  - **Tandai kemungkinan bot:** like/view atau like/RT yang menyimpang lebih dari 3 SD dari pola tim. Jalankan analisis dengan dan tanpa member itu. Jangan dibuang diam-diam.

## 4. Jebakan statistik

- **Sampel kecil.** Dengan n=50, α=0,05, dan power 80%, korelasi terkecil yang bisa terdeteksi andal sekitar |r| 0,39. CI 95% untuk r=0,5 kira-kira [0,26; 0,68]. Faktor dengan efek sedang hampir mustahil terbukti.
- **Multikolinearitas.** Like, RT, views, bookmark, dan follower biasanya berkorelasi ρ>0,85. Koefisien masing-masing jadi tidak bermakna, bahkan tandanya bisa terbalik. Gabungkan jadi satu indeks (PC1 dari log metrik) atau pilih satu saja.
- **Overfitting dan terlalu banyak jalur analisis.** Dua puluh fitur × beberapa definisi hampir pasti menghasilkan p<0,05 palsu.
  - Batasi maksimal sekitar n/15 ≈ 3 prediktor.
  - Pakai LOOCV atau nested CV, plus ridge.
  - Lakukan pre-registrasi: tulis model dan prediksi bertanggal sebelum hasil diumumkan, misalnya lewat commit git.
- **Survivorship.**
  - Member yang lulus atau tidak ikut pemilu hilang dari data.
  - Trainee punya akun lebih muda, jadi follower dan metriknya tidak setara.
  - **Mitigasi:** simpan daftar member per tanggal, analisis hanya kandidat, dan masukkan umur akun sebagai kovariat.
- **Ecological fallacy.** Data agregat per member tidak bisa menjelaskan perilaku fans individual.
- **Kondisi berubah sepanjang tahun:** algoritma X (For You, pembatasan reach), rilis single, konser. **Mitigasi:** pakai FE minggu dan bandingkan antar member di minggu yang sama, bukan level absolutnya.

## 5. Kualitas data dan metrik

- **Bias "metrik saat diambil".**
  - Tweet Okt 2025 sudah jenuh, tweet minggu ini belum.
  - Kalau tiap member diambil di hari berbeda, muncul bias antar member.
  - **Mitigasi:** buang tweet berumur kurang dari 14 hari dari agregat (atau modelkan metrik sebagai fungsi umur), ambil semua member dalam jendela waktu sesingkat mungkin, dan simpan `scraped_at`.
- **Repost wajib dikeluarkan.** Metrik pada repost adalah milik tweet asli orang lain. Quote tetap milik member.
- **Reply ke thread sendiri memecah satu post jadi beberapa baris.** Agregasikan per thread, atau pakai tweet akarnya saja.
- **Views.** Yang dihitung adalah impression: bisa berulang dan termasuk non-follower. Ini berbeda dari jumlah putar video, dan cara hitungnya pernah diubah X. Jangan dicampur dengan video play count. Pakai hanya untuk perbandingan relatif di minggu yang sama.
- **Search X yang tidak lengkap.** Masalahnya bukan angka 2%-nya, tapi apakah hilangnya acak.
  - Yang biasanya hilang: reply, tweet bermedia sensitif, tweet di periode rate-limit, dan tweet yang dihapus.
  - Tweet yang dihapus member sendiri cenderung yang performanya jelek, jadi rata-rata engagement bias ke atas.
- **Follower cuma satu titik waktu.** **Mitigasi:** mulai sekarang ambil snapshot follower mingguan. Sebagian riwayat mungkin bisa direkonstruksi dari Wayback Machine kalau ada.

## 6. Risiko interpretasi untuk kampanye (Goodhart's law)

- **Target merusak ukuran.** Begitu fanbase mengejar like, views, atau trending, engagement naik tanpa vote ikut naik. Data periode kampanye jadi tidak bisa dibandingkan dengan baseline. **Mitigasi:** bekukan baseline (periode sebelum pengumuman Sousenkyo) dan analisis periode kampanye secara terpisah.
- **Bisa berbalik merugikan.** Spam hashtag atau RT massal terkoordinasi bisa memicu deteksi spam X, sehingga reach justru turun.
- **Publikasi bisa berbahaya.**
  - Prediksi yang dipublikasikan bisa memengaruhi hasil (efek bandwagon atau underdog).
  - Label "conversion rendah" untuk member tertentu bisa jadi bahan serangan antar fandom.
  - Bagikan hanya insight agregat soal konten dan timing. Jangan publikasikan peringkat negatif per member.
- **R² tinggi bukan strategi.** R² tinggi pada satu potret hampir pasti didominasi popularitas umum, dan itu sudah diketahui semua orang. Nilai strategisnya ada di residual, padahal residual justru bagian yang paling berisik.

## 7. Etika dan ToS

- **ToS X** melarang scraping tanpa izin tertulis. Risikonya akun di-suspend, ada permintaan takedown, dan ada klausul ganti rugi untuk volume besar.
  - Jaga rate tetap rendah dan pakai data untuk analisis internal.
  - Jangan menyebarkan dataset mentah atau teks penuh. Yang dipublikasikan hanya agregat.
- **Privasi (UU PDP No. 27/2022).**
  - Kolom "akun yang dibalas/direpost" berisi handle fans biasa. Pseudonimisasi dengan hash + salt.
  - Jangan membuat profil fans, dan jangan menggabungkannya dengan data pembelian.
- **Larangan manipulasi:** bot, akun palsu, multi-akun voting, beli suara, jual-beli kode vote (kalau dilarang aturan), atau bot pembeli untuk item pembawa suara.
  - Selain melanggar aturan dan berisiko membuat suara dibatalkan, semua itu juga merusak validitas datamu sendiri.
  - Bot tiket milikmu jangan dipakai untuk item vote, dan transaksinya keluarkan dari analisis stockchecker.
- **Kampanye organik:**
  - ajakan terbuka yang menyasar orang sungguhan;
  - pengukuran pakai instrumen yang disetujui peserta (link pendek, survei sukarela);
  - tidak menekan atau mempermalukan fans secara finansial, karena dorongan "jadi whale" bisa merugikan keuangan fans.

## 8. Apa yang bisa dan tidak bisa disimpulkan

**Bisa sekarang:**
- Gambaran deskriptif: aktivitas, pola posting, sebaran engagement, dan ranking "basis aktif di X" lengkap dengan CI.
- Efek konten dan waktu posting terhadap *engagement*, dibandingkan di dalam member yang sama (dengan FE). Secara statistik ini cukup kuat.
- Uji konvergen X terhadap sinyal berbayar (stockchecker). Ini satu-satunya uji "X ↔ uang" sebelum ada vote.
- Pre-registrasi hipotesis dan model.

**Tidak bisa sekarang:**
- Conversion rate dalam bentuk apa pun.
- Klaim bahwa aktivitas X menyebabkan vote, atau bahwa kampanye jenis tertentu menaikkan vote.
- Prediksi whale atau seberapa dalam dompet fans.
- Kesimpulan tentang perilaku fans individual.

**Bahkan setelah vote ada:**
- Yang didapat hanya asosiasi antar member di satu pemilu.
- "Faktor conversion" statusnya hipotesis untuk pemilu berikutnya, bukan hukum. Daya generalisasinya lemah karena member, format, dan algoritma berubah.

## 9. Sanity check wajib sebelum percaya hasil model

1. **Audit kelengkapan.** Ambil 6 member (2 atas, 2 tengah, 2 bawah) × 2 minggu acak, lalu hitung manual dari timeline. Lulus kalau tweet yang terlewat <5% dan beda tingkat terlewat antar kelompok tidak signifikan (Fisher exact). Cek terpisah per kategori.
2. **Kejenuhan metrik.** Ambil ulang 200 tweet acak (berumur 14, 30, dan 90 hari) setelah 7 hari. Lulus kalau median perubahan like <5% untuk tweet berumur ≥14 hari. Dari situ tetapkan batas umur minimal tweet.
3. **Kebersihan data:**
   - tidak ada repost di agregat engagement;
   - satu thread dihitung satu;
   - tidak ada `tweet_id` ganda;
   - zona waktu WIB konsisten;
   - `scraped_at` tersimpan.
4. **Ketergantungan pada outlier.** Hitung porsi like dari tweet teratas tiap member. Kalau lebih dari 30%, pakai median atau trimmed mean. Laporkan hasil dengan dan tanpa top-1% tweet.
5. **Stabilitas dua paruh.** Hitung Spearman ranking member (median like per tweet) Okt 2025–Apr 2026 vs Apr 2026–Okt 2026. Kalau ρ<0,7, fitur itu terlalu berisik untuk dijadikan prediktor.
6. **Korelasi antar fitur.** Gabungkan fitur dengan |ρ|>0,8, dan buang yang VIF-nya >5.
7. **Baseline dulu.** Hitung ρ(vote, log follower) dan ρ(vote, status senbatsu). Model apa pun harus mengalahkan baseline di LOOCV, misalnya error peringkat rata-rata turun ≥2 posisi. Kalau tidak, model itu tidak berguna.
8. **Uji permutasi.** Acak label vote 1000×, lalu jalankan ulang seluruh pipeline termasuk seleksi fitur. Lulus kalau skor asli di atas persentil ke-95.
9. **Power dan CI.**
   - Laporkan CI bootstrap untuk setiap korelasi.
   - Ingat |r|<0,39 tidak bisa terdeteksi andal pada n=50.
   - Kalau menguji lebih dari 3 faktor, koreksi dengan Holm atau BH.
10. **Validitas konvergen (sebelum vote).** Hitung ρ(engagement X, kecepatan sold-out exclusive per kuota). Kalau ρ<0,3, jangan berharap X bisa memprediksi vote berbayar.
11. **Robustness.**
    - Kesimpulan harus konsisten di minimal 2 definisi penyebut.
    - Cek pengaruh tiap member satu per satu (leave-one-out); tandai yang Cook's D-nya >4/n.
12. **CV per kelompok.** Tahan satu tim atau generasi sebagai data uji. Kalau performa jatuh, model hanya menghafal efek tim.
13. **Anomali bot.** Hitung z-score like/view dan like/RT tiap member terhadap median timnya. Yang >3 ditandai, lalu jalankan analisis dengan dan tanpa member itu.

## 10. Supaya conversion benar-benar bisa diukur

- **Mulai sekarang:**
  - snapshot follower mingguan semua member;
  - metrik tiap tweet diambil pada umur 1, 7, dan 30 hari.
- **Ukur funnel kampanye secara langsung:**
  - link pendek berbeda untuk tiap materi kampanye (klik → halaman vote atau beli);
  - survei sukarela: "berapa vote, dan kenapa".
- **Eksperimen fanbase:** rotasi format konten kampanye secara acak per hari atau slot. Bandingkan jumlah klik, bukan like.
- **Kumpulkan data akun fanbase dan hashtag kampanye** kalau tujuannya menilai efektivitas kampanye, bukan cuma akun member.
- **Kunci pre-registrasi bertanggal** sebelum hasil Sousenkyo diumumkan.