# Penerimaan kualitas jalur 1.7B — 2026-11-17

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
