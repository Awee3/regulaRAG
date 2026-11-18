# RegulaRAG Indonesia

Aplikasi lokal untuk menelusuri dokumen resmi Pelindungan Data Pribadi Indonesia. LLM proyek hanya **Qwen3 1.7B Q4_K_M** melalui Ollama, dijalankan menggunakan GPU sesuai keterangan pengguna. Jawaban berupa kutipan sumber yang dipilih model dan divalidasi backend, dengan citation, bukan nasihat hukum. Jika bukti tidak cukup sistem abstain.

## Setup dari nol (Windows PowerShell)

Prasyarat: Git, Python 3.11 dan Ollama terpasang. Buka terminal di folder clone repository (folder yang memuat pyproject.toml). Instalasi paket, model dan dokumen memerlukan internet sekali; query selanjutnya memakai runtime lokal.

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[ui,dev]"
ollama --version
ollama pull qwen3:1.7b-q4_K_M
ollama list
.\.venv\Scripts\python.exe -m scripts.download_corpus
.\.venv\Scripts\python.exe -m ingestion.build_corpus
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -m ruff check .
```

Perintah memakai interpreter virtualenv secara langsung sehingga tidak memerlukan perubahan execution policy PowerShell. Jika Ollama belum aktif, jalankan `ollama serve` di terminal tersendiri dan biarkan berjalan. Jika muncul pesan port sudah dipakai, periksa `ollama list` untuk memastikan service aktif.

PDF tidak disertakan Git. Downloader hanya memulihkan dokumen aktif dari URL manifest dan memeriksa checksum SHA-256; tidak otomatis menetapkan keberlakuan hukum. Jika unduhan portal resmi gagal, buka URL download resmi di `data/manifest.jsonl`, simpan ke `local_path`, lalu ulangi downloader untuk memeriksa checksum. Jangan mengganti checksum agar file berbeda diterima; periksa sumber terlebih dahulu. Ingestion menolak checksum berbeda, PDF terenkripsi dan scan tanpa text layer. OCR menyeluruh belum tersedia.

## Menjalankan aplikasi

UI memanggil pipeline langsung; cukup jalankan Ollama dan UI:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app/ui.py --server.address 127.0.0.1 --browser.gatherUsageStats false
```

Buka http://127.0.0.1:8501. Mulai dengan BM25 dan pertanyaan **Apa isi Pasal 46 mengenai kegagalan pelindungan data pribadi?** Untuk menanyakan perubahan suatu pasal, izinkan dokumen UU dan putusan terkait. Membatasi hanya UU dapat menyebabkan abstention bila putusan diperlukan.

API opsional (gunakan satu worker):

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Buka http://127.0.0.1:8000/docs. Endpoint: GET /health, GET /documents, POST /query. Contoh PowerShell:

```powershell
$body = @{question='Apa isi Pasal 46?'; retrieval_mode='bm25'; top_k=5} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/query -ContentType 'application/json' -Body $body
```

Gunakan satu proses aplikasi untuk menghindari duplikasi model. LLM menggunakan pengaturan GPU/offloading otomatis Ollama (`generation.num_gpu: null`). Ini tidak menjamin seluruh layer berada di GPU; embedding dan reranker tetap dapat memakai CPU. Perbaikan kompatibilitas GPU dan benchmark resource tidak termasuk scope. Jika `.env` atau environment masih memuat `OLLAMA_NUM_GPU=0`, hapus override tersebut untuk memakai auto. Untuk jalur CPU alternatif, gunakan nilai `0`. Restart proses setelah mengubah konfigurasi. Jangan menganggap service lama dari folder lain memakai kode terbaru.

## Cara kerja dan batas akurasi

1. Manifest mengizinkan hanya dokumen aktif terverifikasi dan checksum yang cocok.
2. Retrieval memilih kandidat BM25 (default), dense, hybrid RRF atau hybrid + reranker.
3. Jalur jawaban mengecualikan argumen pihak dalam putusan. Untuk pasal dengan relasi uji materi yang dicatat manifest, amar relevan disertakan. Metadata relasi statis, bukan analisis hukum otomatis.
4. Model 1.7B memilih cuplikan asli. JSON schema membatasi teks jawaban ke pilihan kutipan; backend memeriksa kecocokan kutipan dan ID evidence. Angka dan syarat sumber tidak diparafrasakan.
5. Bukti tidak cukup atau output tidak valid menghasilkan abstention/error yang eksplisit. Citation ID valid dan teks asli tetap belum menjamin kutipannya menjawab pertanyaan; lihat hasil uji kualitas terbaru.

Kutipan panjang dibatasi context 4096 token; evidence awal dapat berupa cuplikan bertanda excerpt_only. Model dapat memilih ayat yang kurang relevan, menolak pertanyaan answerable, atau tidak menangkap semua bukti lintas dokumen. Teks hasil ekstraksi PDF dapat kehilangan kata; cocokkan bunyi persis dengan PDF resmi. Putusan yang belum dapat dipisahkan dengan aman tidak dipakai sebagai dasar jawaban default.

## Mode retrieval opsional

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dense,rerank]"
.\.venv\Scripts\python.exe -m app.search "kegagalan pelindungan data" --mode hybrid
```

Embedding E5 dan reranker adalah komponen retrieval, bukan LLM alternatif. Model retrieval diunduh saat pertama dipakai. Empat mode tetap tersedia untuk eksperimen; tidak ada klaim hybrid/reranker selalu lebih baik. Model dilepas sebelum generation. Config di `configs/default.yaml`; `.env` opsional mendukung KEY=value sederhana, menimpa default tetapi tidak environment yang sudah di-set. Pertanyaan hanya dikirim ke Ollama localhost, tidak dicatat lengkap oleh aplikasi.

## Verifikasi kualitas

```powershell
.\.venv\Scripts\python.exe -m evaluation.run_answers --mode bm25 --limit 10 --output evaluation/results/my_answers.jsonl
.\.venv\Scripts\python.exe -m evaluation.review_report evaluation/results/quality_final_review.jsonl --review-status ai_reviewed --output evaluation/results/quality_final_summary.json
```

Runner menyimpan hanya pertanyaan benchmark publik yang sudah tersedia; aplikasi tidak menyimpan pertanyaan penggunaan biasa. Jangan menambahkan pertanyaan sensitif ke benchmark. Laporan review AI dipisahkan dari validasi manusia. Bukti sumber harus diperiksa sebelum membuat label jawaban acuan. Uji kasus kegagalan di `tests/` dan hasil eksperimen di `docs/` membantu memahami batas pipeline.

Evaluasi retrieval historis (bukan evaluasi ulang model LLM): `python -m evaluation.run_retrieval`. Laporan lama menyimpan checksum corpus dan konfigurasi saat run, bukan bukti kualitas jalur jawaban yang berubah setelahnya. Artefak 4B/hardware lama hanya arsip; tidak masuk kriteria penerimaan sekarang.

## Sumber dan lisensi

Corpus awal empat dokumen: UU 27/2022, Putusan MK 151/PUU-XXII/2024, 135/PUU-XXIII/2025 dan 133/PUU-XXIV/2026. Lihat [sumber dan tanggal verifikasi](docs/data_sources.md). Corpus tidak lengkap; perubahan setelah tanggal manifest mungkin belum tercakup. PDF tidak didistribusikan bersama repository.

PyMuPDF menggunakan lisensi AGPL-3.0 atau lisensi komersial Artifex; tinjau kewajiban distribusi sebelum membagikan aplikasi. Lisensi Qwen dan komponen retrieval dicatat di docs/data_sources.md. Pin paket ada di pyproject.toml dan revision embedding/reranker di config. Ini alat bantu penelusuran, bukan penasihat hukum.

Hasil kualitas pipeline terkini: [docs/quality_acceptance.md](docs/quality_acceptance.md). Permintaan nama pejabat dan pertanyaan tanpa penanda topik hukum/PDP ditolak secara konservatif; beberapa pertanyaan valid juga dapat abstain. Pertanyaan baru yang lebih luas perlu evaluasi tambahan.

## Status laporan

[Hasil kualitas aktif](docs/quality_acceptance.md) mencatat validasi development dan false abstention. Angka tersebut berasal dari run sebelumnya; pergantian konfigurasi eksekusi tidak berarti ada evaluasi GPU baru. [Review awal](docs/answer_review.md), laporan retrieval dan hardware adalah arsip; hasil historis tidak diubah menjadi hasil konfigurasi sekarang. Keterangan penggunaan GPU berasal dari klarifikasi pengguna, bukan pengukuran baru pada sesi dokumentasi ini.

## Portfolio and LinkedIn demo

[The English portfolio report](docs/portfolio/report.md) explains the problem, architecture, technical choices, evaluation, fixes, and limitations. The [2–3 minute demo guide](docs/portfolio/demo.md) includes three scenarios with actual screenshots. LinkedIn materials include an [eight-page English PDF carousel](docs/portfolio/regularag-linkedin.pdf), [editable PowerPoint](docs/portfolio/regularag-linkedin.pptx), and [caption](docs/portfolio/caption.md).

AI review is reported separately from human validation, which is not yet available. Original Indonesian screenshots and legal excerpts remain unchanged evidence, with English explanations and clearly labeled translations. The recorded demo does not update development scores or legal verification dates. BPK was unavailable during that demo; source inspection used an official local PDF with a matching checksum. Recurring footers, page numbers, and display dates remain removed from the carousel.
