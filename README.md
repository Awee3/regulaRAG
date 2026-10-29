# RegulaRAG Indonesia

Prototipe lokal untuk ingestion terkontrol dan pencarian kutipan UU PDP. Ini belum merupakan sistem RAG lengkap atau nasihat hukum. Corpus saat ini berisi PDF resmi UU PDP dan Putusan MK 151/PUU-XXII/2024; metadata, URL, dan checksum ada di manifest.

## Setup

Gunakan Python 3.11+, lalu jalankan `python -m pip install -e .`. PyMuPDF dipin ke 1.26.5 agar tidak mengambil perubahan major 2.x yang baru dirilis; paket ini berlisensi ganda AGPL-3.0 atau lisensi komersial Artifex, jadi tinjau lisensi sebelum distribusi.

Dokumen awal sudah disimpan di `data/raw/`. Untuk menambahkan dokumen, unduh dari URL resmi di manifest, periksa dokumen dan checksum, lalu isi `sha256` serta ubah `corpus_eligible` ke `true` hanya untuk naskah penuh terverifikasi. Simpan berkas di `data/raw/` sesuai `local_path`. Berita/ringkasan dan kandidat berstatus `unverified` jangan diaktifkan.

Bangun chunk: `python -m ingestion.build_corpus --manifest data/manifest.jsonl`

Cari secara leksikal: `python -m app.search "Pasal 53 ayat (1) huruf b"`

Jalankan model lokal dengan Ollama: `ollama run qwen2.5:1.5b`. [Tag model resmi](https://ollama.com/library/qwen2.5%3A1.5b) sekitar 986 MB dan terdaftar dengan Apache 2.0; model dapat diganti lewat environment variable `OLLAMA_MODEL`.

Jalankan API: `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`; dokumentasi interaktif tersedia di `http://127.0.0.1:8000/docs`. Endpoint: `GET /health`, `GET /documents`, dan `POST /query`. Query dikirim hanya ke Ollama lokal di `127.0.0.1`; log aplikasi tidak menyimpan teks pertanyaan.

Jalankan pemeriksaan lokal: `python -m unittest discover -s tests`

Parser mempertahankan nomor halaman PDF aktual, memisahkan batang tubuh dan penjelasan, serta memakai chunk per halaman untuk putusan agar pasal yang hanya dirujuk tidak salah dilabeli sebagai struktur putusan. API memakai BM25, memanggil Ollama lokal, menolak citation di luar evidence yang diambil, dan mengambil kutipan langsung dari chunk tersimpan. Dense retrieval, hybrid RRF, reranker, UI, OCR, serta benchmark belum tersedia. Sebagian teks PDF dapat memiliki kekeliruan pada text layer; cocokkan kutipan persis dengan PDF resmi sebelum mengandalkannya. Pencarian kosong menghasilkan abstention.

Untuk memahami alur proyek dalam istilah sederhana, mulai dari [docs/architecture.md](docs/architecture.md).

## Batasan sumber

Metadata sumber diverifikasi pada 2026-10-26 dan berkas awal/checksum diperiksa pada 2026-10-29. Lihat [docs/data_sources.md](docs/data_sources.md) dan manifest untuk sumber, jenis dokumen, status, relasi putusan, serta checksum. Perubahan hukum setelah pemeriksaan itu belum tercakup. Corpus tidak lengkap dan bukan penasihat hukum.
