# Video LinkedIn RegulaRAG Indonesia

- [MP4 untuk LinkedIn](regularag-linkedin.mp4)
- [Pemutar HTML luring](regularag-linkedin.html)

Buka `regularag-linkedin.html` dari File Explorer di Chrome dan tekan tombol putar pada video. MP4 lengkap tertanam di dalam berkas, sehingga pemutaran tetap berfungsi setelah HTML disalin sendiri ke folder lain. Pemutar bawaan browser dapat digunakan tanpa internet atau JavaScript.

## Reproduksi

Gunakan Python 3.11, Google Chrome, serta `ffmpeg` dengan libass dan `ffprobe` pada `PATH`. Build juga mendeteksi FFmpeg Windows yang diekstrak ke `.venv/ffmpeg/<nama-build>/bin` di folder video. [Unduhan FFmpeg](https://ffmpeg.org/download.html)

Jalankan setup sekali dari folder ini.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install ffmpeg
```

Siapkan corpus, indeks Qdrant Local, dan Ollama sesuai README proyek. Jalankan Streamlit di `http://127.0.0.1:8501`, lalu jalankan satu perintah ini dari folder video. [Penyiapan RegulaRAG](../../../README.md#menjalankan-aplikasi)

```powershell
.\.venv\Scripts\python.exe .\build.py
```

Build merekam satu sesi Chrome dengan jawaban yang benar-benar dikembalikan Streamlit. Narasi bahasa Inggris memakai suara pria M4 dari Supertonic 3. Build pertama mengunduh bobot ke `.venv/supertonic-3`. Waktu takarir mengikuti klip suara, dan HTML memuat MP4 hasil ekspor. [Suara Supertonic](https://github.com/supertone-oss-archive/supertonic-py/blob/main/docs/voices.md) · [Lisensi model](https://huggingface.co/Supertone/supertonic-3/blob/main/LICENSE)

## Pemeriksaan pemutaran

- Rekaman langsung menunjukkan BM25, pengiriman ulang pertanyaan dengan Dense/E5, dan abstention BM25 untuk pertanyaan penerbangan. Kedua pencarian PDP menampilkan Pasal 46, halaman 19 PDF. Rekaman BM25 memperlihatkan batas 3 × 24 jam dan tombol sumber resmi.
- Pada simulasi lebar 360 piksel, menu pencarian, tindakan pengetikan, hasil, kutipan yang dibuka, dan takarir Inggris diperiksa dari frame MP4 akhir. Transkripsi lokal mengenali “Article 46”, “page 19”, dan “three times 24 hours”.
- MP4 berdurasi 71,73 detik pada 1080 × 1350 dan 30 fps, dengan H.264 dan AAC bahasa Inggris. Selisih durasi audio dan gambar sekitar 26 ms. Loudness terukur −16,2 LUFS dengan true peak −1,4 dBTP. FFmpeg mendekode seluruh MP4 tanpa galat.
- HTML memuat MP4 yang cocok byte per byte dengan berkas siap unggah. Pemutaran dan dekode audio diuji di Chrome dengan jaringan dan JavaScript dimatikan.
