# Cara kerja RegulaRAG

RegulaRAG mencari bagian dokumen yang relevan, lalu meminta model lokal menyusun ringkasan dari bagian itu. Dua pekerjaan tersebut berbeda:

- **Retrieval** memilih halaman/pasal yang mungkin menjawab pertanyaan. BM25 adalah baseline pencarian kata yang mempertahankan istilah dan nomor pasal. Mode dense opsional memakai multilingual E5 di CPU untuk kemiripan makna. Mode hybrid memakai weighted RRF (konfigurasi eksperimen saat ini: k=10, dense=2, BM25=1), hasil tuning awal dev/holdout yang masih perlu dievaluasi pada sampel lebih besar.
- **Generation** merangkum teks yang sudah dipilih. Saat ini diarahkan ke Ollama di komputer yang sama; pertanyaan dan dokumen tidak dikirim ke API LLM cloud.

## Satu pertanyaan, langkah demi langkah

1. `POST /query` memvalidasi pertanyaan dan filter dokumen.
2. `app/search.py` memberi peringkat pada chunk lokal dalam mode `bm25`, `dense`, atau `hybrid`. E5 bersifat opsional; mode BM25 tidak membutuhkan unduhan model. Dense/hybrid mengunduh model E5 saat pemakaian pertama dan menyimpan embedding chunk di memori proses.
3. `app/generation.py` mengirim pertanyaan dan evidence itu ke model Ollama lokal. Default-nya Qwen3 4B Q4_K_M dengan context 4096 token; `OLLAMA_MODEL` dan `OLLAMA_NUM_CTX` dapat diubah. Sebuah lock membatasi proses generation lokal menjadi satu per worker. Teks dokumen diperlakukan sebagai data, bukan instruksi.
4. Backend menolak ID citation yang tidak ada dalam evidence teratas. Kutipan dikembalikan dari chunk tersimpan, bukan disalin ulang oleh model.
5. Jika tidak ada evidence, sistem abstain. Jika Ollama belum berjalan, sistem juga tidak mengarang jawaban dan mengembalikan evidence yang ditemukan beserta status `generator_unavailable`.

## UI lokal

`app/ui.py` menyediakan antarmuka Streamlit tipis yang memanggil fungsi query yang sama di proses UI. Ini membuat API dan UI tetap memakai retrieval, validasi citation, generation, dan abstention yang satu. Jalankan dengan `python -m streamlit run app/ui.py` setelah memasang opsi `.[ui,dense]`; Uvicorn tidak perlu dijalankan untuk UI.

## Dokumen

`data/manifest.jsonl` adalah daftar dokumen: sumber resmi, status, relasi, tanggal berlaku, lokasi berkas, dan checksum. `ingestion/build_corpus.py` hanya memproses dokumen yang `verified`, `corpus_eligible`, memiliki PDF lokal, dan checksum-nya cocok. PDF diproses halaman demi halaman.

`ingestion/legal_text.py` memecah UU berdasarkan judul Pasal yang dikenali. Batang tubuh dan penjelasan mendapat ID berbeda. Putusan dipotong per halaman karena nomor pasal yang disebut di dalam argumen putusan bukan struktur putusan itu sendiri.

## Batas prototipe saat ini

Corpus memiliki UU PDP dan Putusan MK 151/PUU-XXII/2024. BM25, dense E5 opsional, hybrid RRF, UI lokal, dan benchmark awal 14 pertanyaan dev/6 holdout tersedia; reranker dan OCR belum dibuat. Tuning awal menunjukkan kenaikan MRR pada holdout, tetapi sampel terlalu kecil untuk klaim umum. Text layer PDF yang diuji menghilangkan beberapa kata, jadi kutipan untuk bunyi persis perlu dicocokkan dengan halaman PDF resmi. Sistem ini alat bantu penelusuran dokumen, bukan penasihat hukum. Kompatibilitas Ollama, GPU offloading, dan penggunaan RAM/VRAM pada ASUS TUF Gaming FX505GT belum diukur.
