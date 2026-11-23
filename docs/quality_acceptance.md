# Penerimaan kualitas RegulaRAG

## Koreksi kutipan dan seleksi bukti

Pada 23 November 2026, Codex memeriksa gambar halaman 6, 19, dan 30 pada PDF BPK UU 27/2022 yang checksum-nya cocok dengan manifest. Ingestion memulihkan kata **menyampaikan** pada Pasal 46 ayat (1) dan ejaan **mengungkapkan** pada Pasal 67 ayat (2). Setiap koreksi terikat pada SHA-256 berkas, nomor halaman PDF, dan teks di sekelilingnya. PDF sumber serta tanggal verifikasi hukum tetap mengikuti manifest.

Dua kali build menghasilkan 593 chunk dengan SHA-256 `9c8974b005d542ce7ee44b91de6b3d0c1bf04bcd04a2316284b44cf459aeec63` di Windows. Hanya teks dua chunk tersebut yang berubah. ID, halaman, dan URL sama dengan corpus 18 November. Indeks Qdrant dibangun dari hasil yang baru.

Enam pertanyaan dijalankan melalui `POST /query` menggunakan Qwen3 1.7B di masing-masing mode BM25 dan hybrid. Untuk setiap jawaban, ID, dokumen, halaman, URL, dan teks citation cocok dengan chunk yang tersimpan. Teks jawaban juga diperiksa terhadap bukti untuk kasus yang ditanyakan. [Hasil per pertanyaan](../evaluation/results/quality_grounding_recheck.json)

| Kasus | Hasil di kedua mode |
|---|---|
| Q02, tenggat pemberitahuan | Mengutip Pasal 46 di halaman 19. Ayat (1) memuat “wajib menyampaikan pemberitahuan secara tertulis” beserta tenggatnya. |
| Q06 dan N04, pidana pengungkapan | Mengembalikan seluruh ayat (2) Pasal 67 di halaman 30. Pilihan kutipan dibatasi pada ayat yang menyebut perbuatan dan ancaman pidananya bersama-sama. Citation menampilkan chunk pasal untuk melihat konteks. |
| Q08 dan N05, akses dan salinan | Mengutip Pasal 7 di halaman 6 untuk frasa “informasi pribadinya” dan “informasi pribadiku”. |
| N03, jadwal penerbangan | Abstain dengan alasan `no_evidence` dan nol citation. |

Untuk mengulang kasus tersebut setelah membangun corpus dan indeks, jalankan kedua perintah berikut. Ganti `hybrid` dengan `bm25` untuk menguji mode default dan gunakan nama berkas keluaran yang berbeda.

```powershell
.\.venv\Scripts\python.exe -m evaluation.run_answers --mode hybrid --dataset evaluation/dataset/retrieval_sample.jsonl --limit 10 --output data/processed/benchmark-hybrid.jsonl
.\.venv\Scripts\python.exe -m evaluation.run_answers --mode hybrid --dataset evaluation/dataset/quality_smoke.jsonl --limit 5 --output data/processed/probe-hybrid.jsonl
```

Keenam pertanyaan ini merupakan pemeriksaan regresi development dengan review sumber oleh AI. Validasi manusia masih tertunda. Pemeriksaan Q02 mencakup bunyi pemberitahuan pada ayat (1). Pada ayat (2), lapisan teks PDF masih memisahkan penanda huruf a, b, dan c dari butirnya.

## Migrasi Qdrant Local

Pengujian 18 November 2026 memakai corpus identik berisi 593 chunk serta 29 pertanyaan dev dan 21 holdout. Hash SHA-256 corpus, manifest, dan dataset dicatat sebelum dan sesudah di `data/processed/migrasi-qdrant-20261118-114459/`. Corpus dibangun ulang dari empat PDF yang lolos checksum dan menghasilkan SHA-256 `b499f86a469971e8d6839652fa49d9bd6421430d8b86ac2b2f53481228ccc7c5`.

Run memakai Python 3.11.9, Sentence Transformers 5.1.2 dan ONNX Runtime 1.31.1. Jalur baru memakai `qdrant-client==1.17.1`. Revisi E5 base adalah `d128750597153bb5987e10b1c3493a34e5a4502a` dan revisi reranker ONNX adalah `d35a2781eeb3de1d971ad328165277bdf5712e35`. Versi paket lengkap ada di `paket-sebelum.txt` dan `paket-sesudah.txt`.

Semua urutan top 10 identik untuk 50 pertanyaan di lima konfigurasi. Metrik dihitung pada pertanyaan berlabel answerable. Kedalaman kandidat 20 digunakan pada kedua run. Pemilihan pada dev memilih RRF `k=10` dengan bobot dense 2 dan BM25 1 pada kedua run, sama dengan pengaturan aplikasi. RRF tetap dengan `k=60` dan bobot 1 masing-masing juga identik sebelum dan sesudah.

| Mode | Dev Recall@5 / Recall@10 / MRR@10 | Holdout Recall@5 / Recall@10 / MRR@10 |
|---|---:|---:|
| BM25 | 0,5345 / 0,5862 / 0,4383 | 0,6500 / 0,7333 / 0,5151 |
| Dense | 0,6667 / 0,7701 / 0,6007 | 0,4000 / 0,4333 / 0,3574 |
| Hybrid RRF tetap | 0,6552 / 0,7356 / 0,5802 | 0,5000 / 0,7833 / 0,4617 |
| Hybrid RRF terpilih | 0,6667 / 0,7701 / 0,6434 | 0,4333 / 0,4333 / 0,4333 |
| Hybrid + reranker | 0,7414 / 0,8563 / 0,6866 | 0,4667 / 0,5333 / 0,2845 |

Perbandingan per pertanyaan tersimpan di `sebelum.json`, `sesudah.json`, dan `perbandingan.json` dalam direktori run. Hasil mengukur kesetaraan retrieval pada sampel ini. AppTest Streamlit pada mode hybrid menghasilkan cuplikan Pasal 46. ID chunk, dokumen, kutipan, halaman 19 PDF, dan URL dicocokkan dengan corpus.

Smoke hybrid Qwen3 1.7B terdiri dari delapan pertanyaan answerable dan dua di luar corpus. Tujuh pertanyaan mendapat jawaban ekstraktif, dan keenam kasus Q01–Q05 serta Q07 mengutip chunk yang sesuai label benchmark. Q45 dan Q46 abstain tanpa citation. Pemeriksaan otomatis mencocokkan semua citation yang dikembalikan dengan ID, dokumen, kutipan, halaman, dan URL chunk asli. Seluruh 10 kasus selesai tanpa error runtime.

Review Codex (AI) menemukan dua kegagalan kualitas jawaban.

- **Q06** memilih Pasal 68 tentang pemalsuan data ketika pertanyaan meminta sanksi pengungkapan. Bukti yang diberikan ke model mencakup Pasal 67 dan Pasal 65.
- **Q08** abstain pada pertanyaan tentang hak akses dan salinan. Guard topik menolak frasa `informasi pribadinya` bahkan saat Pasal 7 diberikan langsung ke seleksi evidence.

Pemutaran ulang algoritme ranking sebelum migrasi dengan vektor E5 tersimpan menghasilkan urutan 20 kandidat normatif yang sama untuk Q06 dan Q08. Probe aktual `Apa isi Pasal 46?` juga memiliki top 5 dense yang sama sebelum dan sesudah. Keduanya melewatkan chunk Pasal 46 di lima besar. Artefak pemeriksaan tersedia di `jawaban-hybrid.jsonl`, `diagnosis-jawaban.json`, `probe-pasal46-sebelum.json`, dan `smoke-ui.json`. Validasi manusia masih tertunda.

Pada saat migrasi, BM25 dipertahankan sebagai mode default setelah dua kegagalan tersebut. Hasil uji ulang ada pada bagian koreksi di atas.

## Penerimaan kualitas jalur 1.7B — 17 November 2026

## Scope dan status

Scope aktif: satu LLM Qwen3 1.7B Q4_K_M menggunakan GPU menurut klarifikasi pengguna; tanpa perbandingan LLM, perbaikan kompatibilitas GPU atau benchmark resource. Run kualitas yang dilaporkan di bawah dilakukan sebelumnya dengan konfigurasi CPU; nilainya tidak diklaim sebagai evaluasi GPU baru. Implementasi dan penggunaan lokal telah diuji. Kualitas belum dijamin untuk semua pertanyaan; satu probe valid masih abstain.

Perubahan: model memilih ID cuplikan, backend mengembalikan teks sumber asli. Output tidak berupa ringkasan bebas. Citation ditentukan dari cuplikan yang dipilih dan diverifikasi terhadap evidence. Retrieval untuk jawaban menyaring argumen pihak; amar terkait ditambahkan berdasarkan relasi manifest. Kandidat dibatasi ke norma yang sesuai untuk pertanyaan dasar pemrosesan, keamanan, definisi dan transfer luar negeri. Permintaan nama pejabat dan pertanyaan tanpa penanda topik corpus ditolak konservatif.

Parser kini menghentikan chunk saat heading BAB/Bagian berikutnya, sehingga heading transfer luar negeri tidak masuk Pasal 55 tentang transfer domestik. Index perlu dibangun ulang; hasil retrieval lama adalah arsip dan tidak mewakili checksum corpus baru.

## Hasil aktual

Model dijalankan pada sepuluh kasus regresi Q01–Q08/Q45/Q46 dan tiga probe tambahan N01–N03. Kasus yang gagal saat pengembangan diperbaiki dan dijalankan ulang (Q03/Q05/Q07/Q46); hasil dikonsolidasikan tanpa menghapus rekaman run sebelumnya. Ini **validasi development setelah perbaikan**, bukan test set independen atau estimasi akurasi umum. BM25 digunakan; perbandingan dengan review hybrid lama tidak mengisolasi pengaruh satu perubahan.

Review sumber oleh Codex (AI): 12/13 item lolos; satu false abstention. Label tidak diklaim sebagai review manusia/ahli hukum. Semua jawaban yang diterima dalam sampel merupakan cuplikan teks asli; bunyi text layer bisa tetap rusak dibanding tampilan PDF.

| Kasus | Hasil akhir |
|---|---|
| Q01 definisi | Definisi asli tersedia dalam cuplikan Pasal 1; jawaban masih panjang. |
| Q02 pemberitahuan | Mengutip Pasal 46, termasuk tenggat dan ketentuan pemberitahuan. |
| Q03 keamanan | Mengutip Pasal 35, termasuk langkah teknis dan sifat/risiko. |
| Q04 kriteria petugas PDP | Mengutip amar Putusan 151 PDF 159, bukan argumentasi pada halaman 42. |
| Q05 transfer luar negeri | Mengutip Pasal 56, bukan cakupan teritorial Pasal 2 atau transfer domestik Pasal 55. |
| Q06 pidana pengungkapan | Pasal 67 beserta ayat (2) tersedia utuh; model tidak lagi membuat kalimat sanksi 5 tahun untuk pengungkapan. Jawaban memuat ayat lain juga. |
| Q07 dasar pemrosesan | Pasal 20 beserta enam dasar dan syaratnya dikutip utuh. |
| Q08 akses/salinan | Mengutip hak dalam Pasal 7. |
| Q45 PP tanpa naskah aktif | Abstain; tidak menyimpulkan keberadaan peraturan di luar corpus. |
| Q46 nama pejabat | Abstain berdasarkan scope konservatif. |
| N01 hak dalam Pasal 7 | **False abstention**, meskipun sumber tersedia. |
| N02 awal tenggat akses | Mengutip Pasal 32 ayat (2). |
| N03 jadwal penerbangan | Abstain karena di luar topik corpus. |

Tidak ada klaim akurasi 100%. Kutipan autentik belum tentu relevan pada pertanyaan baru. Guard topik dapat menolak pertanyaan yang valid; pipeline belum memahami semua parafrasa atau pertanyaan lintas dokumen. Pengguna perlu membuka citation bila hendak mengandalkan bunyi sumber.

Artefak: `evaluation/results/quality_final_review.jsonl`, `quality_final_summary.json`, run dasar `answers_final.jsonl`, probe `answers_new_final.jsonl`, dan recheck individual. Rekap AI dipisahkan dari validasi manusia.

## Verifikasi teknis dan README

- 43 unit/regression tests lulus; Ruff dan compile check lulus.
- Instalasi editable `pip install -e ".[ui,dev]"` berhasil di virtualenv dengan dependency sistem yang tersedia; build dependency memakai instalasi pip terisolasi. Ini bukan instalasi pada perangkat lain yang benar-benar kosong.
- Folder source terpisah berhasil memeriksa checksum empat PDF, membangun 593 chunk, dan menjalankan tes/lint. Unduhan PDF pada pengujian setup memakai cache resmi yang checksum-nya sesuai, bukan membuktikan semua portal selalu tersedia dari jaringan lain.
- README berisi langkah PowerShell tanpa aktivasi venv, unduhan 1.7B, pemulihan dokumen, ingestion, UI/API dan tes. Backup perubahan workspace utama disimpan di data/processed/sync-backups saat sinkronisasi.

Sumber dan status hukum tetap mengikuti manifest. Review ini tidak memperbarui status hukum secara otomatis. Perbaikan kompatibilitas GPU dan pengukuran resource dikeluarkan sesuai keputusan pengguna; arsip lama dipertahankan sebagai riwayat.

Verifikasi akhir di workspace utama: GET /health melaporkan 1.7B siap dan index siap; POST /query nyata menghasilkan jawaban dengan citation Pasal 46. Halaman awal Streamlit lolos AppTest tanpa exception dan endpoint UI merespons. pip check serta git diff --check juga lulus. Hasil HTTP disimpan di evaluation/results/api_17b_final.json.
