> **ARSIP — bukan status konfigurasi aktif.** Eksperimen retrieval E5 small pada corpus/konfigurasi saat run. Bukan evaluasi jawaban atau eksekusi GPU sekarang. Scope sekarang: satu LLM 1.7B menggunakan GPU menurut pengguna, tanpa perbandingan LLM atau benchmark resource. Lihat [penerimaan aktif](acceptance.md) dan [hasil kualitas](quality_acceptance.md).

# Retrieval tuning and holdout check

Generated UTC: 2026-11-17T06:02:41.053192+00:00
Questions: 29 dev / 21 holdout | Chunks: 593 | E5: `intfloat/multilingual-e5-small` on CPU | Candidate depth: 20
Corpus SHA-256: `3fc537e5115420366e09c828c57afa6950a67f5bb2f71600e30992d61eef3a8c`
One-time model and passage embedding warmup: 139.23 s (excluded from retrieval ranking metrics)
Config selection uses dev MRR@10, tie-break Recall@5. Selected RRF: k=10, dense weight=1.5, BM25 weight=1.

Reranker: `Horizon-Labs/multilingual-reranker-small` at revision `d35a2781eeb3de1d971ad328165277bdf5712e35`, ONNX on CPU, max pair length 384. Recall@5 is the fraction of labeled relevant chunks found in the first five results. MRR@10 is the reciprocal rank of the first relevant result (miss=0), averaged across questions.

## Development results

| Mode/config | Recall@5 | MRR@10 |
|---|---:|---:|
| bm25 | 0.483 | 0.408 |
| dense | 0.598 | 0.558 |
| hybrid_baseline (k=60, dense weight=1) | 0.483 | 0.473 |
| hybrid_tuned (dev selected) | 0.598 | 0.509 |
| hybrid_rerank (selected hybrid then reranked) | 0.672 | 0.656 |

## Holdout check (not used to select config)

| Mode/config | Recall@5 | MRR@10 |
|---|---:|---:|
| bm25 | 0.717 | 0.560 |
| dense | 0.400 | 0.400 |
| hybrid_baseline (k=60, dense weight=1) | 0.433 | 0.375 |
| hybrid_tuned | 0.400 | 0.327 |
| hybrid_rerank | 0.467 | 0.284 |

## Mean per-question latency (seconds)

| Split | BM25 | Dense (warm) | RRF fusion | Reranker |
|---|---:|---:|---:|---:|
| dev | 0.102 | 0.066 | 0.000114 | 9.695 |
| holdout | 0.097 | 0.063 | 0.000135 | 10.364 |
Model loading and corpus passage embedding warmup are reported separately; generation latency and peak RAM/VRAM were not measured in this retrieval benchmark.
Reranking remains optional. Compare the measured dev and holdout tables before choosing a mode.

## Recall@10

| Split | Mode | Recall@10 |
|---|---|---:|
| dev | bm25 | 0.517 |
| dev | dense | 0.667 |
| dev | hybrid_baseline | 0.701 |
| dev | hybrid_tuned | 0.684 |
| dev | hybrid_rerank | 0.805 |
| holdout | bm25 | 0.800 |
| holdout | dense | 0.400 |
| holdout | hybrid_baseline | 0.783 |
| holdout | hybrid_tuned | 0.600 |
| holdout | hybrid_rerank | 0.533 |

## Dev tuning grid (top 10)

| RRF k | Dense weight | Recall@5 | MRR@10 |
|---:|---:|---:|---:|
| 10 | 1.5 | 0.598 | 0.509 |
| 10 | 2 | 0.632 | 0.505 |
| 30 | 2 | 0.552 | 0.495 |
| 30 | 1.5 | 0.517 | 0.494 |
| 60 | 2 | 0.517 | 0.494 |
| 100 | 2 | 0.517 | 0.494 |
| 60 | 1.5 | 0.483 | 0.493 |
| 100 | 1.5 | 0.483 | 0.493 |
| 10 | 1 | 0.517 | 0.477 |
| 30 | 1 | 0.483 | 0.473 |

## Holdout per-question ranks

| ID | Query | BM25 | Dense | Baseline RRF | Tuned RRF | Reranked |
|---|---|---:|---:|---:|---:|---:|
| Q15 | Dapatkah seseorang menuntut ganti rugi atas pelanggaran pemrosesan data tentang dirinya? | 1 | 1 | 1 | 1 | 1 |
| Q16 | Persetujuan siapa yang diperlukan sebelum data pribadi anak diproses? | 4 | 1 | 1 | 1 | 2 |
| Q17 | Jika pemrosesan memakai persetujuan, informasi apa yang wajib diberikan pengendali kepada subjek data? | 3 | 1 | 2 | 2 | 2 |
| Q18 | Apa kewajiban kedua pengendali ketika memindahkan data pribadi di dalam wilayah Indonesia? | 2 | 1 | 1 | 1 | 2 |
| Q19 | Selain pidana pada Pasal 67 atau 68, hukuman tambahan apa yang dapat dijatuhkan? | 3 | 1 | 2 | 2 | 2 |
| Q20 | Apa kewenangan lembaga pelindungan data untuk mengawasi kepatuhan dan menindak pelanggaran? | 7 | 1 | 2 | 2 | 2 |
| Q36 | Bagaimana Putusan Mahkamah Konstitusi memaknai kata dan pada kriteria penunjukan pejabat pelindungan data pribadi Pasal 53 ayat 1 huruf b? | 1 | miss | 5 | 10 | 6 |
| Q37 | Apa pertimbangan Mahkamah Konstitusi dalam Putusan Nomor 135/PUU-XXIII/2025 terkait uji materi norma larangan dan pidana membocorkan data pribadi? | 2 | miss | 7 | miss | miss |
| Q38 | Bagaimana amar putusan Mahkamah Konstitusi Nomor 135/PUU-XXIII/2025 terhadap permohonan pengujian norma pidana Pasal 65 ayat 2 dan Pasal 67 ayat 2 UU PDP? | 1 | miss | 8 | 10 | miss |
| Q39 | Bagaimana putusan Mahkamah Konstitusi Nomor 133/PUU-XXIV/2026 mengenai pengawasan transfer data pribadi dalam Pasal 62 ayat 2 UU PDP? | 2 | miss | 8 | miss | miss |
| Q40 | Apa amar putusan Mahkamah Konstitusi dalam perkara nomor 133/PUU-XXIV/2026 yang menguji kewajiban negara mengontrol transfer data pribadi? | 1 | miss | 7 | 10 | miss |
| Q41 | Kapan Undang-Undang Nomor 27 Tahun 2022 tentang Pelindungan Data Pribadi mulai berlaku secara hukum? | 3 | miss | 10 | miss | miss |
| Q42 | Apakah Putusan MK Nomor 135/PUU-XXIII/2025 mengubah teks atau status keberlakuan Pasal 65 ayat 2 UU PDP? | miss | miss | miss | miss | miss |
| Q43 | Bagaimana status pemaknaan alternatif penunjukan DPO setelah Putusan Mahkamah Konstitusi Nomor 151/PUU-XXII/2024? | 1 | miss | 7 | 10 | 10 |
| Q44 | Apa saja jenis pidana tambahan yang dapat dijatuhkan kepada pelaku tindak pidana pelindungan data pribadi? | 2 | miss | 7 | miss | 2 |
| Q45 | Berapa rincian besaran tarif denda administratif per klasifikasi industri menurut Peraturan Pemerintah Nomor 33 Tahun 2026? | - | - | - | - | - |
| Q46 | Siapa nama ketua lembaga pengawas pelindungan data pribadi Republik Indonesia yang dilantik pada tahun 2024? | - | - | - | - | - |
| Q47 | Bagaimana mekanisme pelaporan data protection officer kepada European Data Protection Board berdasarkan GDPR? | - | - | - | - | - |
| Q48 | Berapa standar batas toleransi insiden kebocoran data menurut Surat Edaran Otoritas Jasa Keuangan tahun 2025? | - | - | - | - | - |
| Q49 | Apakah Pengadilan Negeri Jakarta Pusat telah memutus perkara ganti rugi kebocoran data konsumen pada tahun 2025? | - | - | - | - | - |
| Q50 | Bagaimana template standar formulir persetujuan pemrosesan data pribadi anak menurut peraturan menteri? | - | - | - | - | - |

Dataset labels target the cited chunks, not all potentially relevant text. This is a small exploratory sample; inspect the labels and failure cases before making a general quality claim.
