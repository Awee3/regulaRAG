# Scope penerimaan terkini

## Koreksi kualitas 23 November 2026

Suite lokal lulus 53 tes, termasuk regresi untuk ekstraksi Pasal 46, pemilihan ayat pidana pengungkapan, dan pertanyaan akses serta salinan. Ruff dan `pip check` lulus. BM25 tetap menjadi mode default. [Hasil per kasus untuk BM25 dan hybrid](quality_acceptance.md#koreksi-kutipan-dan-seleksi-bukti)

## Migrasi Qdrant Local tahap 0–4 — 18 November 2026

- Titik pemulihan `a8dc293965b09b9ce26fb9ea4f429d027d629ed9` diverifikasi pada `main` lokal dan `refs/heads/main` di origin sebelum branch `codex/migrasi-qdrant` dibuat dari SHA tersebut.
- Ekstraksi ulang dari empat PDF yang lolos pemeriksaan checksum menghasilkan 593 chunk dengan hash yang sama. Builder membuat snapshot Qdrant Local dengan 593 point berdimensi 768. API, UI, CLI dan evaluator memakai jalur dense persisten. BM25 tersedia dengan instalasi dasar.
- Suite awal lulus 43 tes. Suite akhir lulus 49 tes dengan extra dense, termasuk tujuh tes integrasi Qdrant Local pada salinan checkout tanpa corpus lokal. Instalasi dasar di virtualenv terisolasi lulus 42 tes dengan tujuh tes Qdrant dilewati. Ruff, `pip check`, dan `git diff --check` lulus.
- GitHub Actions lulus pada instalasi dasar dan instalasi dengan extra dense. Migrasi masuk ke `main` pada 23 November 2026. [PR migrasi](https://github.com/Awee3/regulaRAG/pull/1) · [Hasil CI](https://github.com/Awee3/regulaRAG/actions/runs/45192284568)
- Kode utama ada di [builder indeks](../ingestion/build_vector_index.py), [penyimpanan snapshot](../app/vector_index.py), [pencarian](../app/search.py), [API](../app/main.py), dan [evaluator retrieval](../evaluation/run_retrieval.py). Alur build, restart, dan pemulihan ada di [README](../README.md#mode-retrieval-opsional).
- Perintah utama yang dijalankan mencakup `ingestion.build_corpus`, `ingestion.build_vector_index`, `app.search --mode dense`, `evaluation.run_retrieval` sebelum dan sesudah, dan `evaluation.run_answers --mode hybrid --limit 10`. Artefak run lokal berada di `data/processed/migrasi-qdrant-20261118-114459/`. [Hasil kualitas migrasi](quality_acceptance.md#migrasi-qdrant-local)
- Snapshot tersedia untuk penggunaan lokal. BM25 adalah mode default. Promosi hybrid, validasi manusia, dan migrasi Qdrant Server tahap 5 masih tertunda.

## Scope model dan riwayat penerimaan

Keputusan pengguna: satu LLM Qwen3 1.7B; menggunakan GPU menurut klarifikasi pengguna, tanpa perbandingan LLM, perbaikan kompatibilitas GPU atau benchmark resource. Pengujian fungsional, akurasi berbasis sumber, citation, abstention dan setup README tetap termasuk.

- Tes parser, citation, pemilihan sumber normatif dan guard abstention dijalankan.
- Output berupa kutipan asli yang dipilih model, bukan ringkasan bebas. Validasi ID dan teks bukan jaminan relevansi kutipan.
- Kasus lama dan pertanyaan tambahan dijalankan pada 1.7B dan ditinjau oleh AI terhadap bukti sumber. Label AI tidak dianggap validasi manusia/ahli hukum. Lihat quality_acceptance.md.
- Instalasi editable sesuai README diuji dalam virtualenv memakai dependency sistem yang sudah terpasang; build dependency diambil melalui pip. Pemulihan checksum, ingestion, tes dan lint juga diuji pada folder source terpisah dengan cache PDF resmi. Instalasi di mesin lain/jaringan lain belum diuji langsung.
- LLM memakai auto/offloading Ollama; CPU tetap alternatif. Penggunaan GPU berasal dari keterangan pengguna, bukan benchmark baru. Tidak ada kewajiban memperbaiki driver atau mengukur resource.

Corpus tidak lengkap. Tanggal verifikasi hukum tetap mengikuti manifest; sesi coding tidak otomatis memperbarui status keberlakuan. Pemeriksaan independen terhadap sumber primer tetap berguna untuk klaim kualitas hukum final, tetapi bukan pekerjaan manual yang ditambahkan untuk menjalankan aplikasi lokal.

Artefak sebelum perubahan: answer_review.md menilai sampel lama 1.7B + hybrid, bukan pipeline terkini. Jawaban lama disimpan untuk error analysis. Rekap AI dan rekap manusia dipisahkan oleh review_status.
