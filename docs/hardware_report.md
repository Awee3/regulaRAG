> **ARSIP — bukan status konfigurasi aktif.** Pengukuran dan kegagalan runtime historis. Angka dan konfigurasi CPU/4B di bawah dipertahankan sebagai riwayat; bukan konfigurasi aktif atau pekerjaan yang wajib dilanjutkan. Scope sekarang: satu LLM 1.7B menggunakan GPU menurut pengguna, tanpa perbandingan LLM atau benchmark resource. Lihat [penerimaan aktif](acceptance.md) dan [hasil kualitas](quality_acceptance.md).

# Local smoke measurements — 2026-11-17

These are actual single-query CPU measurements, not a controlled performance study. The full retrieval experiment was also active, so CPU contention affects latency. Prompt: Pasal 46, UU PDP only, BM25, top_k=1, context 4096, generation cap 512, keep_alive=0. Ollama 0.40.13. Both returned non-abstained answers with a source citation; human correctness review is pending.

| Model | End-to-end seconds | Load seconds | Generation tokens/sec | Generated tokens | Python peak RAM MiB |
|---|---:|---:|---:|---:|---:|
| Qwen3 4B Q4_K_M | 112.47 | 14.05 | 2.55 | 187 | 50.84 |
| Qwen3 1.7B Q4_K_M | 113.48 | 5.34 | 4.86 | 476 | 50.81 |

The 1.7B sample generated more tokens, so higher token speed did not produce a shorter end-to-end answer here. These Python RAM figures exclude the Ollama model process. Total sampled GPU memory was 623 MiB / 587 MiB and includes unrelated desktop usage; it is **not model VRAM**. Both requests explicitly used num_gpu=0. Model/runtime timings and exact responses are in `evaluation/results/hardware_4b_cpu.json` and `hardware_17b_cpu.json`.

An earlier automatic offload attempt reported 26/37 layers on GPU but did not complete before the old 120s timeout. This does not establish GPU generation compatibility or full GPU operation. Timeout is now configurable (600s). For stable demonstrated behavior use OLLAMA_NUM_GPU=0; GPU default auto still needs a completed isolated test.

Remaining measurement work: isolated repeat trials, total model-process RAM, CPU/GPU comparison, and end-to-end hybrid/reranker generation timings. Do not present these smoke measurements as final hardware acceptance.

## GPU auto failure

A subsequent complete auto attempt returned HTTP 500 in 19.25 seconds. Ollama reported `CUDA error: shared object initialization failed` and runner exit `0xc0000409`. This is a runtime failure, not generation latency; `hardware_4b_auto.json` records `generator_unavailable` and no token speed. The project default now explicitly requests CPU (`generation.num_gpu: 0`). Set this to `null` to retry auto only after addressing runtime compatibility; no driver changes were made.
