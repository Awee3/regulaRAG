# Cara kerja RegulaRAG

RegulaRAG mencari bagian dokumen yang relevan, lalu meminta model lokal menyusun ringkasan dari bagian itu. Dua pekerjaan tersebut berbeda:

- **Retrieval** memilih halaman/pasal yang mungkin menjawab pertanyaan. Saat ini memakai BM25, yaitu pencarian kata yang memberi bobot lebih pada istilah yang jarang dan mempertahankan nomor pasal.
- **Generation** merangkum teks yang sudah dipilih. Saat ini diarahkan ke Ollama di komputer yang sama; pertanyaan dan dokumen tidak dikirim ke API LLM cloud.

## Satu pertanyaan, langkah demi langkah

1. `POST /query` memvalidasi pertanyaan dan filter dokumen.
2. `app/search.py` memberi peringkat pada chunk lokal dan mengembalikan evidence teratas.
3. `app/generation.py` mengirim pertanyaan dan evidence itu ke model Ollama lokal. Teks dokumen diperlakukan sebagai data, bukan instruksi.
4. Backend menolak ID citation yang tidak ada dalam evidence teratas. Kutipan dikembalikan dari chunk tersimpan, bukan disalin ulang oleh model.
5. Jika tidak ada evidence, sistem abstain. Jika Ollama belum berjalan, sistem juga tidak mengarang jawaban dan mengembalikan evidence yang ditemukan beserta status `generator_unavailable`.

## Dokumen

`data/manifest.jsonl` adalah daftar dokumen: sumber resmi, status, relasi, tanggal berlaku, lokasi berkas, dan checksum. `ingestion/build_corpus.py` hanya memproses dokumen yang `verified`, `corpus_eligible`, memiliki PDF lokal, dan checksum-nya cocok. PDF diproses halaman demi halaman.

`ingestion/legal_text.py` memecah UU berdasarkan judul Pasal yang dikenali. Batang tubuh dan penjelasan mendapat ID berbeda. Putusan dipotong per halaman karena nomor pasal yang disebut di dalam argumen putusan bukan struktur putusan itu sendiri.

## Batas prototipe saat ini

Corpus memiliki UU PDP dan Putusan MK 151/PUU-XXII/2024. BM25 bekerja; dense retrieval, gabungan dense+BM25 (RRF), reranker, UI, OCR, dan benchmark belum dibuat. Text layer PDF yang diuji menghilangkan beberapa kata, jadi kutipan untuk bunyi persis perlu dicocokkan dengan halaman PDF resmi. Sistem ini alat bantu penelusuran dokumen, bukan penasihat hukum.
