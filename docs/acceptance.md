# Scope penerimaan terkini

Keputusan pengguna: satu LLM Qwen3 1.7B; menggunakan GPU menurut klarifikasi pengguna, tanpa perbandingan LLM, perbaikan kompatibilitas GPU atau benchmark resource. Pengujian fungsional, akurasi berbasis sumber, citation, abstention dan setup README tetap termasuk.

- Tes parser, citation, pemilihan sumber normatif dan guard abstention dijalankan.
- Output berupa kutipan asli yang dipilih model, bukan ringkasan bebas. Validasi ID dan teks bukan jaminan relevansi kutipan.
- Kasus lama dan pertanyaan tambahan dijalankan pada 1.7B dan ditinjau oleh AI terhadap bukti sumber. Label AI tidak dianggap validasi manusia/ahli hukum. Lihat quality_acceptance.md.
- Instalasi editable sesuai README diuji dalam virtualenv memakai dependency sistem yang sudah terpasang; build dependency diambil melalui pip. Pemulihan checksum, ingestion, tes dan lint juga diuji pada folder source terpisah dengan cache PDF resmi. Instalasi di mesin lain/jaringan lain belum diuji langsung.
- LLM memakai auto/offloading Ollama; CPU tetap alternatif. Penggunaan GPU berasal dari keterangan pengguna, bukan benchmark baru. Tidak ada kewajiban memperbaiki driver atau mengukur resource.

Corpus tidak lengkap. Tanggal verifikasi hukum tetap mengikuti manifest; sesi coding tidak otomatis memperbarui status keberlakuan. Pemeriksaan independen terhadap sumber primer tetap berguna untuk klaim kualitas hukum final, tetapi bukan pekerjaan manual yang ditambahkan untuk menjalankan aplikasi lokal.

Artefak sebelum perubahan: answer_review.md menilai sampel lama 1.7B + hybrid, bukan pipeline terkini. Jawaban lama disimpan untuk error analysis. Rekap AI dan rekap manusia dipisahkan oleh review_status.
