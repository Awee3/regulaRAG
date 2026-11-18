# Rencana migrasi pencarian dense RegulaRAG ke Qdrant

**Status 18 November 2026.** Dokumen ini adalah instruksi implementasi. Semua kotak masih terbuka. Mulai dari tahap 0 untuk menyimpan kondisi proyek ke remote, lalu kerjakan tahap 1–4 pada branch migrasi. Tahap 5 adalah jalur pertumbuhan ketika beberapa proses perlu mengakses indeks yang sama.

**Keputusan.** Gunakan Qdrant Local persisten melalui `qdrant-client` dan simpan indeks di `data/processed/qdrant/`, yang sudah tercakup dalam aturan Git untuk artefak lokal. Mode ini berjalan di proses Python tanpa layanan Docker. Saat pindah ke server, aplikasi dapat memakai operasi koleksi, penyimpanan vektor, filter, dan pencarian yang sama. Qdrant berlisensi Apache-2.0. [Qdrant](https://github.com/qdrant/qdrant) · [Python client dan mode lokal](https://github.com/qdrant/qdrant-client#local-mode)

**Hasil yang dituju.** Selesai ingestion, E5 menghitung satu embedding per chunk. Setelah aplikasi dimulai ulang, pertanyaan dense pertama cukup menghitung embedding pertanyaan. Qdrant mengembalikan ID kandidat, lalu backend mengambil teks dan halaman sumber dari corpus untuk membentuk citation. BM25 tetap menjadi mode standar. Pekerjaan ini mengikuti scope aktif di [AGENTS.md](../AGENTS.md), termasuk Qwen3 1.7B, jawaban ekstraktif, dan evaluasi kualitas.

## 0. Commit dan push kondisi awal, lalu buat branch migrasi

Jalankan dari root repository sebelum memasang dependensi, merekam baseline, atau mengubah kode. Saat rencana ditulis, branch sumber adalah `main` dengan upstream `origin/main`. Jalankan perintah berurutan dan berhenti jika ada yang gagal.

- [ ] Periksa `git status --short --branch --untracked-files=all`. Pastikan berada di `main`, lalu jalankan blok berikut untuk menyiapkan seluruh perubahan proyek, termasuk berkas baru, penghapusan, dan dokumen rencana ini. Tinjau daftar serta isi yang akan dikirim sesuai aturan repository untuk secret, PDF sumber, model, dan indeks lokal. Hormati `.gitignore` tanpa memakai `git add -f`.

```powershell
git add -A
git diff --cached --name-status
git diff --cached --stat
```

- [ ] Setelah memeriksa staging, commit seluruh perubahan dan push branch sumber. Jika seluruh perubahan sudah di-commit dan working tree bersih, gunakan HEAD yang ada dan langsung jalankan push. Push ini juga mengirim commit lokal sebelumnya yang belum ada di remote.

```powershell
git commit -m "chore: simpan kondisi proyek sebelum migrasi Qdrant"
git push origin main
git rev-parse HEAD
git ls-remote --exit-code origin refs/heads/main
```

- [ ] Cocokkan SHA dari `git rev-parse HEAD` dengan SHA pada baris `refs/heads/main` di remote. Catat SHA tersebut sebagai titik pemulihan. Jika push ditolak atau SHA berbeda, selesaikan penyebabnya dan verifikasi ulang sebelum membuat branch. Hindari force-push pada branch sumber.
- [ ] Buat branch baru dari commit yang sudah terverifikasi. Jika nama berikut sudah dipakai, gunakan nama baru dengan sufiks tanggal atau nomor. Periksa bahwa branch aktif adalah branch migrasi, HEAD sama dengan SHA yang dicatat, dan working tree bersih. Lanjutkan ke tahap 1 di branch ini.

```powershell
git switch -c codex/migrasi-qdrant
git status --short --branch
git rev-parse HEAD
```

## 1. Rekam kondisi awal sebelum mengubah pencarian

- [ ] Periksa `git status --short --branch` dan baca perubahan lokal di berkas yang akan disentuh. Gunakan isi working tree sebagai titik awal. Saat rencana ditulis, corpus lokal berisi 593 chunk dari empat dokumen. Hitung kembali saat eksekusi karena corpus bisa berubah.
- [ ] Telusuri pemanggil `search()` dan `release_encoder()` dari API, UI, CLI, tes, dan evaluator. [app/search.py](../app/search.py) menghitung embedding seluruh corpus pada cache miss dan mengurutkan skor secara eksak. [app/main.py](../app/main.py) membatasi ID dokumen dari manifest dan meminta `normative_only=True`. Evaluator retrieval juga memakai jalur eksplorasi tanpa filter normatif.
- [ ] Dari root repo, siapkan Python 3.11 dan corpus sesuai [README](../README.md). Untuk perbandingan penuh, pasang extra `dense,rerank,dev` dan gunakan revisi model di [konfigurasi](../configs/default.yaml). Jalankan perintah berikut **sebelum mengubah backend**. Gunakan direktori keluaran baru setiap kali mengulang perbandingan.

```powershell
$py = '.\.venv\Scripts\python.exe'
$run = Join-Path 'data/processed' ('migrasi-qdrant-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $run | Out-Null
Get-FileHash data/processed/chunks.jsonl, data/manifest.jsonl, evaluation/dataset/retrieval_sample.jsonl
& $py -m unittest discover -s tests
& $py -m evaluation.run_retrieval --json-out "$run/sebelum.json" --report-out "$run/sebelum.md"
```

Catat hash, ID dan revisi model, versi paket, hasil tes awal, dan lokasi `$run`. Gunakan corpus dan dataset yang sama pada tahap 4. Opsi keluaran eksplisit menjaga laporan eksperimen terdahulu. Jika model atau reranker belum tersedia, catat pemeriksaan yang tertunda dan lanjutkan tes integrasi dengan vektor sintetis.

## 2. Bangun indeks sebagai langkah terpisah dari pembuatan corpus

- [ ] Tambahkan versi `qdrant-client` yang diuji di Python 3.11 ke extra `dense` di [pyproject.toml](../pyproject.toml). Pertahankan instalasi dasar untuk BM25. Muat dependensi Qdrant hanya pada jalur vektor. Pisahkan kode koleksi di satu modul kecil yang dipakai penulis dan pembaca indeks.
- [ ] Tambahkan CLI **baru** `python -m ingestion.build_vector_index`. Jalankan setelah `python -m ingestion.build_corpus` berhasil memeriksa manifest dan checksum PDF. Gunakan lokasi chunks dan direktori indeks dari konfigurasi. Sediakan argumen path untuk fixture dan corpus eksperimen sehingga `--chunks` pada pencarian tetap bermakna.
- [ ] Baca chunk bertahap, tolak ID duplikat, lalu encode dalam batch kecil di CPU menggunakan encoder dan revisi efektif proyek. Pertahankan prefix `passage: `, normalisasi L2, dan cosine similarity. Ambil dimensi dari encoder. Untuk setiap point gunakan UUIDv5 dari namespace tetap dan `chunk_id`. Simpan string `chunk_id` asli, `document_id`, `source_kind`, dan `section_type` sebagai metadata filter. Identitas citation di API tetap string asli.
- [ ] Bangun koleksi baru dari snapshot corpus lengkap. Simpan identitas indeks berupa SHA-256 chunks, model dan revisi efektif, dimensi, pengaturan embedding, versi skema, serta jumlah point. Cocokkan semua ID dengan corpus dan periksa ulang identitas sumber sebelum aktivasi. Aktifkan lewat satu berkas penunjuk yang diganti secara atomik setelah validasi. Build terputus meninggalkan koleksi sebelumnya utuh. Build ulang input identik dapat memakai koleksi tervalidasi, sedangkan build input baru harus menghilangkan chunk yang sudah dicabut.
- [ ] Berikan akses eksklusif ke direktori Qdrant Local. Tutup UI, API, dan pembaca lokal sebelum menjalankan builder. Gunakan satu client per direktori dalam proses aplikasi dan tutup setelah dipakai oleh CLI atau tes. Jika direktori terkunci, tampilkan proses yang perlu ditutup atau petunjuk menggunakan server. [Perilaku penguncian Qdrant Local](https://github.com/qdrant/qdrant-client/blob/master/qdrant_client/local/qdrant_local.py)

## 3. Hubungkan pembacaan indeks ke pipeline jawaban

- [ ] Pertahankan kontrak `search(question, chunks_path, top_k, document_ids, retrieval_mode, normative_only)`. Pada jalur dense, periksa kecocokan indeks dengan corpus dan konfigurasi aktif. Encode `query: ` dengan normalisasi pertanyaan yang sudah ada, cari kandidat, lalu cocokkan ID dengan chunk asli dari snapshot yang sama. Kembalikan struktur hit yang sudah dipakai pemanggil, termasuk skor. Jaga urutan deterministik untuk skor seri.
- [ ] Terapkan filter **sebelum top-k**. Pada jalur jawaban gunakan irisan dokumen pilihan dengan daftar aktif dari manifest saat permintaan diproses. Di fungsi pencarian, `document_ids=None` membuka semua dokumen dalam corpus yang dipilih, sedangkan himpunan kosong memberi nol hasil. Dengan `normative_only=True`, chunk putusan bertipe `judgment_full_text` hanya lolos jika `section_type=amar_putusan`. Uji juga bahwa pencarian eksplorasi tetap bisa mengambil bagian lain.
- [ ] Pertahankan BM25 khusus istilah hukum, penggabungan RRF berbobot, serta reranking terhadap kandidat hybrid. Pakai nilai aktual dari konfigurasi. Pertahankan `include_holdings()`, seleksi evidence, pelepasan encoder sebelum generation, dan validasi citation. Model tetap memilih cuplikan yang dikutip backend. [Aturan evidence](../app/evidence.py) · [Alur API](../app/main.py)
- [ ] Bedakan indeks hilang, kedaluwarsa, atau gagal dibaca dari pencarian sah tanpa hasil. Gunakan `DenseSearchUnavailable` dan respons HTTP 503 yang menyebut langkah pemulihan untuk kegagalan indeks. Nol bukti mengikuti jalur abstention. Tambahkan status kesiapan dense di `GET /health` sambil mempertahankan arti `index_ready` yang sudah digunakan untuk corpus. Pemeriksaan health dan kueri BM25 harus berfungsi tanpa memuat E5.

## 4. Uji, bandingkan, lalu aktifkan

| Pemeriksaan | Bukti kelulusan |
|---|---|
| Persistensi | Tes dengan Qdrant Local sungguhan di direktori sementara dan encoder uji. Tutup client sesudah build, buka kembali, lalu buktikan pencarian hanya meng-encode pertanyaan dan mengembalikan ID yang diharapkan. |
| Rebuild dan pemulihan | Build dua kali memberi ID unik yang sama. Ubah teks, hapus satu chunk, lalu bangun ulang. Chunk yang dihapus hilang. Simulasikan gagal sebelum aktivasi. Pembaca hanya memakai versi lengkap yang cocok dengan corpus. Model atau revisi berbeda terdeteksi walaupun dimensinya sama. |
| Filter dan citation | Pakai fixture dengan kandidat teratas berasal dari dokumen yang dilarang. Dengan top-k satu, kandidat sah tetap ditemukan. Uji pencabutan dokumen di manifest, filter kosong, argumen pihak, amar terkait, dan pertanyaan di luar corpus. Cocokkan ID, dokumen, kutipan, halaman, dan URL dengan chunk asli. |
| Kompatibilitas | Jalankan suite lama dan perbarui fixture yang memalsukan cache dense. Uji instalasi dasar BM25 serta instalasi extra dense. Pastikan CLI, API, UI, evaluator, dan mode hybrid + reranker memakai jalur yang dimaksud. Periksa konfigurasi CI agar tes integrasi Qdrant benar-benar berjalan. |

**Perintah setelah implementasi.** Gunakan kembali `$py` dan `$run` dari tahap 1. Tutup aplikasi yang sedang memegang direktori indeks. Perintah `build_vector_index` di bawah adalah hasil yang harus disediakan tahap 2.

```powershell
& $py -m pip install -e ".[dense,rerank,dev]"
& $py -m ingestion.build_vector_index
& $py -m app.search "Apa isi Pasal 46?" --mode dense
& $py -m unittest discover -s tests
& $py -m ruff check .
& $py -m evaluation.run_retrieval --json-out "$run/sesudah.json" --report-out "$run/sesudah.md"
& $py -m evaluation.run_answers --mode hybrid --limit 10 --output "$run/jawaban-hybrid.jsonl"
```

- [ ] Bandingkan ID per pertanyaan, Recall@5, Recall@10, dan MRR@10 untuk split dev dan holdout. Saat membandingkan hybrid, pastikan nilai `rrf_k`, bobot, dan kedalaman kandidat sama pada kedua run. Evaluator yang ada memilih konfigurasi pada dev. Jika pilihannya berbeda, bandingkan juga dengan konfigurasi tetap. Selidiki perbedaan pada batas top-k, misalnya skor seri atau pembulatan. Tunda aktivasi jika regresi belum dijelaskan atau filter dan citation gagal.
- [ ] Buka hasil smoke jawaban dan periksa isinya. Runner dapat selesai sambil mencatat `runtime_error` atau `generator_unavailable` pada baris hasil. Verifikasi setidaknya satu jawaban ekstraktif dengan citation dan satu abstention sesuai label. Catat penilaian AI dan validasi manusia secara terpisah.
- [ ] Perbarui README dengan urutan instalasi, build, restart, dan pemulihan indeks. Catat hasil aktual dan batas verifikasi di laporan penerimaan aktif. Laporkan berkas yang berubah, perintah yang benar-benar dijalankan, keputusan aktivasi, dan pemeriksaan yang masih tertunda.

**Rollback.** Hentikan proses pembaca. Jika indeks terdahulu masih cocok dengan corpus dan encoder aktif, arahkan penunjuk kepadanya dan uji kueri dense. Jika tidak cocok, jalankan aplikasi dalam mode BM25 dan bangun ulang indeks dari corpus aktif. Pertahankan manifest terbaru agar pencabutan dokumen tetap dihormati. Periksa kembali citation sebelum mengaktifkan dense atau hybrid.

## 5. Pindah ke Qdrant Server ketika akses bersama diperlukan

1. Pilih satu node ketika UI, API, atau ingestion perlu berjalan sebagai proses terpisah yang mengakses koleksi bersamaan. Tambahkan konfigurasi endpoint lokal dan gunakan kembali skema point, filter, serta CLI build yang sudah teruji.
2. Di Windows dengan Docker, pakai volume bernama untuk penyimpanan dan batasi endpoint pengembangan ke localhost. Bangun koleksi server dari corpus terverifikasi menggunakan builder, lalu jalankan pemeriksaan tahap 4 sebelum mengalihkan aplikasi. [Penyimpanan Qdrant di Windows](https://qdrant.tech/documentation/common-errors/)
3. Uji pemulihan snapshot server. Pertimbangkan replikasi jika proyek membutuhkan ketersediaan saat satu node gagal, atau sharding jika data perlu dibagi antarmesin. Pada mode hybrid, BM25 saat ini masih men-tokenisasi seluruh kumpulan kandidat dokumen pada tiap pencarian. Evaluasi biaya jalur itu secara terpisah seiring pertumbuhan corpus. [Snapshot](https://qdrant.tech/documentation/operations/snapshots/) · [Deployment terdistribusi](https://qdrant.tech/documentation/operations/distributed_deployment/)
