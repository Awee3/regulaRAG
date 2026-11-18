> **ARSIP — bukan status konfigurasi aktif.** Review AI awal terhadap 1.7B + hybrid sebelum revisi pipeline. Bukan hasil pipeline aktif. Scope sekarang: satu LLM 1.7B menggunakan GPU menurut pengguna, tanpa perbandingan LLM atau benchmark resource. Lihat [penerimaan aktif](acceptance.md) dan [hasil kualitas](quality_acceptance.md).

# Review berbasis sumber oleh AI — 2026-11-17

Reviewer: Codex (AI). Review dilakukan langsung terhadap jawaban tersimpan dan dokumen primer lokal, bukan mengambil label yang dibuat model generator sebagai kebenaran. Ini tetap review AI, bukan persetujuan manusia atau ahli hukum. Hasil hanya sinyal evaluasi awal sesuai batas LLM-as-judge pada AGENTS.md.

## Cakupan dan metode

Sepuluh sampel pada `evaluation/results/answers.jsonl`: Q01–Q08, Q45 dan Q46. Seluruh sampel memakai `qwen3:1.7b-q4_K_M`, hybrid retrieval. Tidak ada generation ulang, tuning, atau perubahan jawaban asli pada sesi review. Hasil tidak mewakili model utama 4B, mode BM25 default, atau seluruh benchmark 50 pertanyaan.

PDF sumber tidak tersedia di worktree baru; salinan resmi di repository asal D:/regulaRAG/data/raw dibaca tanpa diubah. Ketiga checksum cocok dengan manifest worktree. Teks halaman relevan diperiksa; halaman kunci UU 2/19/24/30, Putusan 151 halaman 42/159, dan Putusan 135 halaman 1 juga dirender dan dilihat. Halaman pendukung lain diperiksa melalui text layer. Artefak kerja berada di data/processed/review (diabaikan Git).

BPK tidak berhasil diakses ulang (timeout/tipe konten tidak didukung). Karena itu review isi memakai PDF lokal yang cocok checksum, tanpa memperbarui tanggal/status verifikasi hukum manifest. [Halaman resmi Komdigi perkara 135](https://jdih.komdigi.go.id/judicial/view/49) berhasil diperiksa dan mengidentifikasi Masduki sebagai Pemohon I. Sumber UU: [BPK](https://peraturan.bpk.go.id/Details/229798/uu-no-27-tahun-2022); putusan 151: [PDF resmi di BPK](https://peraturan.bpk.go.id/DownloadUjiMateri/218/putusan_mkri_151_PUU-XXII_2024.pdf).

Rubrik ketat: jawaban lolos jika menjawab pertanyaan dengan klaim didukung, tidak menghilangkan syarat penting, dan memakai otoritas yang tepat. Jawaban parsial mendapat label boolean false dengan alasan yang membedakannya dari jawaban sepenuhnya salah. Citation dinilai mendukung klaim yang diatribusikan, bukan hanya cocok dokumen/pasal. Claim support menilai klaim yang tertulis; ketidaklengkapan dapat menurunkan correctness tanpa membuat semua klaim salah. Tidak ada citation atau klaim pada abstention, sehingga tidak diberi skor citation 100% secara otomatis.

## Hasil per item

| ID | Putusan review | Bukti dan alasan |
|---|---|---|
| Q01 | Lolos | Definisi cocok dengan Pasal 1 angka 1, PDF UU halaman 2. |
| Q02 | Lolos | Bentuk tertulis, batas 3 x 24 jam, dan penerima didukung Pasal 46 ayat (1), PDF 19. |
| Q03 | Terlalu luas | Kewajiban penilaian dampak berkaitan pemrosesan berisiko tinggi; jawaban menghilangkan kondisi. Bagian teknis/perekaman didukung. Citation: putusan 151 PDF 65. |
| Q04 | Parsial; otoritas tidak tepat | Arah kesimpulan selaras amar tetapi penjelasan bercampur pembacaan kumulatif lama. Halaman 42 memuat argumentasi, bukan amar. Amar pada PDF 159 menetapkan pemaknaan dan/atau dan seharusnya menjadi evidence utama. |
| Q05 | Salah pasal | Pasal 2 adalah cakupan penerapan; Pasal 55 transfer domestik. Syarat transfer luar negeri ada pada Pasal 56, PDF 24. Citation yang dipakai tidak mendukung izin/kondisi transfer yang disimpulkan. |
| Q06 | Salah ayat dan angka | Untuk pengungkapan sebagaimana Pasal 65 ayat (2), Pasal 67 ayat (2), PDF 30 menyebut maksimum 4 tahun dan/atau Rp4 miliar; jawaban memakai 5 tahun/Rp5 miliar dari ayat lain. |
| Q07 | Parsial/tidak lengkap | Lima dasar yang disebut didukung, tetapi dasar kepentingan umum/pelayanan publik/kewenangan tidak disebut dan syarat penting disederhanakan. Bandingkan Pasal 20, PDF 10–11; citation putusan 135 PDF 125. |
| Q08 | Lolos | Pasal 7, Penjelasan Pasal 7, dan Pasal 32 ayat (2) mendukung hak, biaya dan batas waktu. PDF 6/39/14. |
| Q45 | Abstention tepat | Dokumen yang ditanya tidak tersedia sebagai corpus aktif. Ini tidak menyimpulkan peraturan tersebut ada atau tidak ada di dunia nyata. |
| Q46 | Gagal abstain | PDF putusan 135 halaman 1 menyebut dosen/Pemohon I, bukan bukti jabatan ketua lembaga atau pelantikan 2024. Model mengubah peran seseorang berdasarkan nama di sumber. |

## Rekap

Pemeriksaan integritas terpisah: seluruh 12 citation cocok persis dengan ekstraksi ulang parser dari PDF sumber dan rentang halamannya cocok (12/12). Hasil ada di `evaluation/results/ai_review_citation_integrity.json`. Ini menjelaskan mengapa kutipan yang autentik tetap dapat dipakai untuk kesimpulan yang salah.

- 4/10 lolos penuh (40%); 6/10 parsial atau gagal menurut rubrik di atas.
- Dukungan klaim: 18/26 = 69,23%, berdasarkan segmentasi klaim tersimpan; sensitif terhadap cara membagi klaim.
- Dukungan citation: 6/12 = 50%, penilaian semantik AI, bukan validitas ID.
- Abstention: accuracy 90%, precision 100%, recall 50%. Hanya dua pertanyaan unanswerable; satu dijawab tanpa bukti yang mendukung. Accuracy tinggi bukan bukti aman karena kebanyakan item answerable.

Label per item, klaim yang dinilai, halaman, checksum sumber dan alasan ada di `evaluation/results/answers_ai_review.jsonl`. `review_status=ai_reviewed`; label human pada jawaban asli tetap tidak diisi. Rekap: `evaluation/results/ai_review_summary.json`.

Reproduksi rekap:

```powershell
python -m evaluation.review_report evaluation/results/answers_ai_review.jsonl --review-status ai_reviewed --output evaluation/results/ai_review_summary.json
```

## Implikasi

Sampel fallback ini belum memenuhi kualitas jawaban yang diharapkan. Prioritas perbaikan berikutnya: evidence per ayat untuk angka pidana, membedakan argumentasi pihak dari amar, mempertahankan syarat/pengecualian, dan menolak inferensi jabatan dari nama orang. Review tidak mengubah pipeline atau memperbaiki jawaban untuk menyembunyikan kegagalan. Jangan menggunakan skor ini sebagai klaim kualitas hukum final; penilaian independen manusia tetap berguna untuk penerimaan portofolio.

Kompatibilitas GPU dikeluarkan dari cakupan atas permintaan pengguna. Konfigurasi CPU tetap berlaku; tidak ada pemeriksaan atau perubahan driver/GPU pada sesi ini.
