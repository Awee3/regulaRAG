# RegulaRAG Indonesia

Prototipe lokal untuk ingestion terkontrol dan pencarian kutipan UU PDP serta putusan Mahkamah Konstitusi terkait. Ini merupakan alat bantu penelusuran dokumen berbasis bukti, bukan nasihat hukum. Corpus aktif saat ini berisi 4 dokumen resmi terverifikasi (593 chunk): UU 27/2022 (UU PDP), Putusan MK 151/PUU-XXII/2024, Putusan MK 135/PUU-XXIII/2025, dan Putusan MK 133/PUU-XXIV/2026. Metadata lengkap, tautan resmi, dan checksum SHA-256 tercatat di manifest.

## Setup

Gunakan Python 3.11+, lalu jalankan `python -m pip install -e .`. PyMuPDF dipin ke 1.26.5 agar tidak mengambil perubahan major 2.x yang baru dirilis; paket ini berlisensi ganda AGPL-3.0 atau lisensi komersial Artifex, jadi tinjau lisensi sebelum distribusi.

BM25 berjalan tanpa model tambahan. Untuk dense atau hybrid search, pasang opsi CPU: `python -m pip install -e ".[dense]"`. Model `intfloat/multilingual-e5-base` diunduh saat pertama kali memakai dense/hybrid; mesin perlu akses internet sekali untuk mengambil model. Ganti model melalui `REGULARAG_EMBEDDING_MODEL` (misalnya `intfloat/multilingual-e5-small`).

Dokumen awal sudah disimpan di `data/raw/`. Untuk menambahkan dokumen, unduh dari URL resmi di manifest, periksa dokumen dan checksum, lalu isi `sha256` serta ubah `corpus_eligible` ke `true` hanya untuk naskah penuh terverifikasi. Simpan berkas di `data/raw/` sesuai `local_path`. Berita/ringkasan dan kandidat berstatus `unverified` jangan diaktifkan.

Bangun chunk: `python -m ingestion.build_corpus --manifest data/manifest.jsonl`

Bandingkan pertanyaan yang sama pada ketiga mode dengan menjalankan:

- `python -m app.search "Apa kewajiban saat terjadi kegagalan pelindungan data?" --mode bm25`
- `python -m app.search "Apa kewajiban saat terjadi kegagalan pelindungan data?" --mode dense`
- `python -m app.search "Apa kewajiban saat terjadi kegagalan pelindungan data?" --mode hybrid`

Hybrid mengambil 20 kandidat teratas dari tiap metode (atau semua jika chunk kurang dari 20), lalu menggabungkan peringkat dengan weighted Reciprocal Rank Fusion. Berdasarkan tuning awal dev/holdout, konfigurasi saat ini memakai k=10 dan bobot dense=2, BM25=1; BM25-only tetap tersedia sebagai baseline. Hasilnya masih eksploratif karena dataset kecil. Embedding diproses di CPU; cache vektor berlaku selama proses berjalan.

Gunakan Ollama lokal: `ollama pull qwen3:4b-instruct-2507-q4_K_M`, lalu `ollama run qwen3:4b-instruct-2507-q4_K_M`. Tag utama Qwen3 4B Q4_K_M berukuran sekitar 2.5 GB dan mencantumkan Apache 2.0 di [Ollama Registry](https://ollama.com/library/qwen3%3A4b-instruct-2507-q4_K_M). Untuk uji memori terbatas, gunakan `ollama pull qwen3:1.7b-q4_K_M`. Model dapat diganti lewat `OLLAMA_MODEL`; context default 4096 token dapat diubah lewat `OLLAMA_NUM_CTX`. Ollama mengatur GPU offloading secara otomatis; ketersediaan GPU dan kebutuhan memori aktual belum diuji pada laptop target.

Jalankan API: `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`; dokumentasi interaktif tersedia di `http://127.0.0.1:8000/docs`. Endpoint: `GET /health`, `GET /documents`, dan `POST /query`. Query dikirim hanya ke Ollama lokal di `127.0.0.1`; log aplikasi tidak menyimpan teks pertanyaan.

Jalankan pemeriksaan lokal: `python -m unittest discover -s tests`

Evaluasi 50 pertanyaan (29 development dan 21 holdout, mencakup lookup, numerical, multi-evidence, cross-document, temporal/status, serta unanswerable/out-of-corpus) serta tuning grid RRF dan reranker: `python -m evaluation.run_retrieval`. Hasil metrik dan ranking per pertanyaan ditulis ke `docs/evaluation_report.md` dan `evaluation/results/retrieval_tuning_latest.json`. E5 dan ONNX reranker memakai CPU; jika model sudah ada di cache lokal dan ingin menghindari cek jaringan di PowerShell: `$env:HF_HUB_OFFLINE = "1"; python -m evaluation.run_retrieval`. Konfigurasi default terpusat di `configs/default.yaml` dan variabel lingkungan opsional dapat disalin dari `.env.example`.

Pasang UI dan semua mode retrieval opsional: `python -m pip install -e ".[ui,dense,rerank]"`. Jalankan UI: `python -m streamlit run app/ui.py`. UI memanggil pipeline secara langsung di proses Streamlit, jadi tidak perlu menjalankan Uvicorn terpisah; Ollama tetap harus aktif untuk menyusun jawaban. Untuk penggunaan yang hanya memerlukan BM25, pasang `python -m pip install -e ".[ui]"`.

Parser mempertahankan nomor halaman PDF aktual, memisahkan batang tubuh dan penjelasan, serta memakai chunk per halaman untuk putusan agar pasal yang hanya dirujuk tidak salah dilabeli sebagai struktur putusan. API dan UI mendukung BM25, dense, hybrid RRF, serta hybrid dengan reranker multilingual ONNX pada CPU. Ollama tetap lokal, citation dibatasi ke evidence yang diambil, dan kutipan berasal langsung dari chunk tersimpan. Model reranker diunduh saat pertama kali dipakai; bila belum tersedia, mode tersebut mengembalikan error yang jelas dan mode lain tetap dapat dipakai. OCR belum tersedia. Evaluasi retrieval awal ada di `docs/evaluation_report.md`. Sebagian teks PDF dapat memiliki kekeliruan pada text layer; cocokkan kutipan persis dengan PDF resmi sebelum mengandalkannya. Pencarian kosong menghasilkan abstention.

Untuk memahami alur proyek dalam istilah sederhana, mulai dari [docs/architecture.md](docs/architecture.md).

## Batasan sumber

Metadata UU PDP dicek ulang di BPK pada 2026-11-02; PDF sumber dan checksum diperiksa pada 2026-10-29. Lihat [docs/data_sources.md](docs/data_sources.md) dan manifest untuk sumber, jenis dokumen, status, relasi putusan, serta checksum. Perubahan hukum setelah tanggal verifikasi belum tercakup. Corpus tidak lengkap dan bukan penasihat hukum.
