# Sumber data hukum

Metadata hukum diperiksa pada **2026-10-26** terhadap portal primer. PDF UU 27/2022 dan Putusan MK 151/PUU-XXII/2024 kemudian diunduh dari tautan resmi BPK pada **2026-10-29**, dicatat checksum-nya di manifest, dan diaktifkan untuk ingestion. Ini bukan monitor perubahan otomatis; periksa ulang sumber sebelum memakai corpus untuk keputusan hukum. `data/manifest.jsonl` adalah daftar sumber dan statusnya.

## Sumber terverifikasi

| Dokumen | Temuan pada sumber resmi | Corpus default |
|---|---|---|
| UU 27/2022 | [JDIH BPK](https://peraturan.bpk.go.id/Details/229798/uu-no-27-tahun-2022) mencatat ditetapkan dan diundangkan 17 Oktober 2022, berlaku, serta mencatat Putusan MK 151/PUU-XXII/2024 yang memaknai “dan” pada Pasal 53 ayat (1) huruf b sebagai “dan/atau”. Naskah resmi tersedia di [PDF BPK](https://peraturan.bpk.go.id/Home/Download/224884/UU%20Nomor%2027%20Tahun%202022.pdf). | Aktif; PDF resmi lokal dan checksum dicatat. |
| Putusan MK 151/PUU-XXII/2024 | [Salinan putusan resmi di BPK](https://peraturan.bpk.go.id/DownloadUjiMateri/218/putusan_mkri_151_PUU-XXII_2024.pdf); BPK mengaitkan putusan ini dengan Pasal 53 ayat (1) huruf b UU PDP. | Aktif; PDF resmi lokal dan checksum dicatat. |
| Putusan MK 137/PUU-XXIII/2025 | [JDIH Komdigi](https://jdih.komdigi.go.id/judicial/view/48) mencatat putusan tetap, dibacakan 19 Januari 2026, objek Pasal 56 ayat (1)–(4), dan amar menolak permohonan seluruhnya; tautan resmi menuju MK tersedia pada halaman. | Belum: teks putusan belum diunduh dan checksum belum dicatat. |
| Putusan MK 135/PUU-XXIII/2025 | [JDIH Komdigi](https://jdih.komdigi.go.id/judicial/view/49) mencatat putusan tetap, dibacakan 19 Januari 2026, objek Pasal 65 ayat (2) dan Pasal 67 ayat (2), amar menolak seluruhnya, serta menyediakan berkas putusan. | Belum: teks putusan belum diunduh dan checksum belum dicatat. |
| Putusan MK 133/PUU-XXIV/2026 | [MK](https://www.mkri.id/berita/kewajiban-negara-kontrol-transfer-data-pribadi-secara-holistik-25115) dan [JDIH Putusan MK](https://jdih.mkri.id/produk-hukum/putusan?frase=&jenis=PUU&page=22&search=&tahun=) mengonfirmasi tanggal 25 Mei 2026 dan amar menolak seluruhnya; salinan resmi putusan ditemukan di [server MK](https://s.mkri.id/public/content/persidangan/putusan/putusan_mkri_14323_1779697116.pdf). Berita hanya pendukung; corpus diarahkan ke salinan putusan. | Belum: PDF belum disimpan dan checksum belum dicatat. |
| Putusan MK 102/PUU-XXIV/2026 | [Berita MK](https://www.mkri.id/berita/permohonan-uji-uu-pdp-tidak-dapat-diterima-24954) dan [JDIH Putusan MK](https://jdih.mkri.id/produk-hukum/putusan?frase=102%2FPUU-XXIV%2F2026&jenis=PUU&page=1&search=102%2FPUU-XXIV%2F2026&tahun=) mengonfirmasi tanggal 29 April 2026, objek Pasal 20 ayat (2) huruf f, dan amar tidak dapat diterima. Belum menemukan tautan salinan lengkap yang dapat dicatat pada pemeriksaan ini. | Tidak; metadata/berita saja bukan naskah putusan. |
| Putusan MK 153/PUU-XXIV/2026 | [Berita MK](https://www.mkri.id/berita/uji-uu-pdp-menyoal-kekosongan-lembaga-pengawas-independen-tidak-dapat-diterima-25202) dan [JDIH Putusan MK](https://jdih.mkri.id/produk-hukum/putusan?frase=153%2FPUU-XXIV%2F2026&jenis=PUU&page=1&search=153%2FPUU-XXIV%2F2026) mengonfirmasi tanggal 17 Juni 2026, objek Pasal 58 ayat (5) dan Pasal 61, serta amar tidak dapat diterima. Belum menemukan tautan salinan lengkap yang dapat dicatat pada pemeriksaan ini. | Tidak; metadata/berita saja bukan naskah putusan. |

## Belum terverifikasi

- **PP No. 33 Tahun 2026**: penelusuran katalog resmi BPK dan Direktorat Jenderal Peraturan Perundang-undangan tidak menemukan halaman/naskah primer yang mengonfirmasi judul, pengundangan, tanggal mulai berlaku, atau status yang disebut pada catatan kandidat. Tetap `unverified`; tidak ada klaim bahwa PP tersebut ada atau berlaku.
- **PP No. 17 Tahun 2025** tidak dimasukkan sebagai aturan pelaksanaan umum UU PDP. Perlu verifikasi ruang lingkup terpisah sebelum menambahkannya.

Checksum, waktu verifikasi UTC per item, serta catatan status artefak dicatat terpisah dalam manifest. Nilai checksum `null` berarti naskah lokal belum tersedia; metadata terverifikasi tidak menjadikan dokumen tersebut aktif dalam corpus. Berita dan ringkasan tidak boleh diperlakukan sebagai bunyi peraturan atau pengganti putusan lengkap.

Pemeriksaan visual halaman 7 UU menemukan bahwa text layer PDF BPK/JDIH (kedua unduhan memiliki SHA-256 identik) menghilangkan beberapa kata pada hasil ekstraksi meskipun kata terlihat pada halaman. Karena itu, parser menyimpan teks apa adanya dan belum memakai OCR; kutipan yang memerlukan bunyi persis harus dicek pada PDF resmi sampai ada tahap OCR/validasi ekstraksi.
