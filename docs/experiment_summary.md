> **ARSIP — bukan status konfigurasi aktif.** Ringkasan eksperimen sebelum revisi pipeline; bukan kriteria penerimaan aktif. Scope sekarang: satu LLM 1.7B menggunakan GPU menurut pengguna, tanpa perbandingan LLM atau benchmark resource. Lihat [penerimaan aktif](acceptance.md) dan [hasil kualitas](quality_acceptance.md).

# Ringkasan eksperimen 2026-11-17

Corpus: 593 chunk, empat PDF resmi, checksum corpus `3fc537e5115420366e09c828c57afa6950a67f5bb2f71600e30992d61eef3a8c`. Dataset: 29 dev / 21 holdout (metrik retrieval mengecualikan pertanyaan unanswerable). Label masih membutuhkan pemeriksaan manusia; dataset kecil dan tidak mewakili seluruh pertanyaan hukum.

| Embedding | Dense holdout Recall@5 | Tuned hybrid Recall@5 | Hybrid rerank Recall@5 | Warmup E5 + passage (s) | Mean warm dense (s) |
|---|---:|---:|---:|---:|---:|
| E5 base | 0.400 | 0.433 | 0.467 | 516.33 | 0.129 |
| E5 small | 0.400 | 0.400 | 0.467 | 139.23 | 0.063 |

BM25 holdout Recall@5=0.717, Recall@10=0.800, MRR@10=0.560. Ini alasan default UI dipilih BM25 pada sampel saat ini; bukan klaim bahwa BM25 selalu terbaik. Pemilihan default berdasarkan holdout ini berarti konfirmasi final perlu test baru. Base/small menghasilkan urutan berbeda; kualitas reranker belum konsisten. Laporan lengkap per pertanyaan: `evaluation_report.md`, `evaluation_small.md` dan JSON di `evaluation/results`.

Latency diukur ketika ada pengujian generation lain pada sebagian waktu run. Angka ini eksploratif; pengukuran performa yang terkontrol perlu proses bergantian dan pengulangan. Jangan mencampur waktu fusion saja dengan total hybrid (dense + lexical + fusion). Peak RAM total Ollama, model loading terpisah dari embedding passage, dan throughput multi-query belum diukur lengkap.

## Error analysis

- BM25 dapat mengambil contoh dalam putusan untuk pertanyaan definisi. Model kecil maupun besar pernah merangkum contoh sebagai definisi. Backend kini membutuhkan frasa definisi eksplisit; bila tidak ada sistem abstain. Ini meningkatkan kehati-hatian tetapi dapat menolak pertanyaan yang sebenarnya answerable dalam corpus.
- Model 1.7B pernah menjawab pertanyaan nama pejabat yang berada di luar corpus. Jangan menganggap fallback setara kualitasnya dengan model utama. Sampel kegagalan disimpan untuk review.
- Corpus memiliki text layer dengan kata hilang. Parser tidak memulihkan kata dengan tebakan. Verifikasi visual PDF masih diperlukan.
- GPU auto gagal inisialisasi CUDA pada runtime ini. CPU berhasil untuk kedua model, tetapi lambat; detail di `hardware_report.md`.
- Pertanyaan multi-dokumen bisa kehilangan konteks karena batas 4096 token. Cuplikan awal ditandai `excerpt_only`; sistem tidak mengklaim melihat teks di luar cuplikan.

## Yang belum boleh diklaim selesai

Correctness, faithfulness dan dukungan citation semantik belum dinilai manusia. Nilainya tetap null di laporan review. Pengukuran resource menyeluruh dan pengujian GPU setelah perbaikan runtime masih terbuka. Prototipe lokal dapat dipakai dengan batasan ini; penerimaan portofolio penuh memerlukan review di `acceptance.md`.
