# Retrieval tuning and holdout check

Generated UTC: 2026-11-02T15:53:21.684915+00:00
Questions: 14 dev / 6 holdout | Chunks: 298 | E5: `intfloat/multilingual-e5-base` on CPU | Candidate depth: 20
Corpus SHA-256: `ed48dbb15eaecc2650f0c7cc554e8c194ccc9ff145d3934bd2c93cfd70528af1`
One-time model and passage embedding warmup: 174.68 s (excluded from retrieval ranking metrics)
Config selection uses dev MRR@10, tie-break Recall@5. Selected RRF: k=10, dense weight=2, BM25 weight=1.

Reranker: `Horizon-Labs/multilingual-reranker-small` at revision `d35a2781eeb3de1d971ad328165277bdf5712e35`, ONNX on CPU, max pair length 384. Recall@5 is the fraction of labeled relevant chunks found in the first five results. MRR@10 is the reciprocal rank of the first relevant result (miss=0), averaged across questions.

## Development results

| Mode/config | Recall@5 | MRR@10 |
|---|---:|---:|
| bm25 | 0.429 | 0.400 |
| dense | 0.738 | 0.642 |
| hybrid_baseline (k=60, dense weight=1) | 0.643 | 0.525 |
| hybrid_tuned (dev selected) | 0.738 | 0.616 |
| hybrid_rerank (selected hybrid then reranked) | 0.929 | 0.812 |

## Holdout check (not used to select config)

| Mode/config | Recall@5 | MRR@10 |
|---|---:|---:|
| bm25 | 0.833 | 0.514 |
| dense | 0.833 | 0.861 |
| hybrid_baseline (k=60, dense weight=1) | 1.000 | 0.722 |
| hybrid_tuned | 1.000 | 0.917 |
| hybrid_rerank | 1.000 | 0.667 |

## Mean per-question latency (seconds)

| Split | BM25 | Dense (warm) | RRF fusion | Reranker |
|---|---:|---:|---:|---:|
| dev | 0.056 | 0.112 | 0.000086 | 7.312 |
| holdout | 0.055 | 0.120 | 0.000103 | 6.810 |
Model loading and corpus passage embedding warmup are reported separately; generation latency and peak RAM/VRAM were not measured in this retrieval benchmark.
In this small sample, reranking improved dev MRR@10 (0.812 vs 0.616 for tuned hybrid) but lowered holdout MRR@10 (0.667 vs 0.917) and added about 7 seconds per query on CPU. Keep it optional; hybrid remains the UI default.

## Dev tuning grid (top 10)

| RRF k | Dense weight | Recall@5 | MRR@10 |
|---:|---:|---:|---:|
| 10 | 2 | 0.738 | 0.616 |
| 10 | 1.5 | 0.714 | 0.597 |
| 30 | 2 | 0.643 | 0.547 |
| 30 | 1.5 | 0.643 | 0.546 |
| 60 | 1.5 | 0.643 | 0.546 |
| 60 | 2 | 0.643 | 0.546 |
| 100 | 1.5 | 0.643 | 0.546 |
| 100 | 2 | 0.643 | 0.546 |
| 10 | 1 | 0.643 | 0.540 |
| 30 | 1 | 0.643 | 0.525 |

## Holdout per-question ranks

| ID | Query | BM25 | Dense | Baseline RRF | Tuned RRF | Reranked |
|---|---|---:|---:|---:|---:|---:|
| Q15 | Dapatkah seseorang menuntut ganti rugi atas pelanggaran pemrosesan data tentang dirinya? | 1 | 1 | 1 | 1 | 1 |
| Q16 | Persetujuan siapa yang diperlukan sebelum data pribadi anak diproses? | 4 | 1 | 2 | 1 | 2 |
| Q17 | Jika pemrosesan memakai persetujuan, informasi apa yang wajib diberikan pengendali kepada subjek data? | 3 | 6 | 2 | 2 | 2 |
| Q18 | Apa kewajiban kedua pengendali ketika memindahkan data pribadi di dalam wilayah Indonesia? | 1 | 1 | 1 | 1 | 1 |
| Q19 | Selain pidana pada Pasal 67 atau 68, hukuman tambahan apa yang dapat dijatuhkan? | 3 | 1 | 1 | 1 | 2 |
| Q20 | Apa kewenangan lembaga pelindungan data untuk mengawasi kepatuhan dan menindak pelanggaran? | 6 | 1 | 3 | 1 | 2 |

Dataset labels target the cited chunks, not all potentially relevant text. This is a small exploratory sample; inspect the labels and failure cases before making a general quality claim.
