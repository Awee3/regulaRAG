"""Tune weighted RRF on dev questions and check the chosen setting on holdout."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path

from app.reranking import RERANKER_MAX_LENGTH, RERANKER_MODEL, RERANKER_REVISION, rerank
from app.search import DENSE_RRF_WEIGHT, EMBEDDING_MODEL, RRF_K, _rrf, search
from evaluation.metrics import timed_call

ROOT = Path(__file__).resolve().parents[1]
TOP_K = 10
CANDIDATE_K = 20
BASELINE_RRF_K = 60
BASELINE_DENSE_WEIGHT = 1.0
CONFIGS = [(k, weight) for k in (10, 30, 60, 100) for weight in (0.5, 0.75, 1.0, 1.5, 2.0)]


def recall_at_k(relevant: set[str], ranked: list[str], k: int) -> float:
    if not relevant:
        return 0.0
    return len(relevant.intersection(ranked[:k])) / len(relevant)


def reciprocal_rank_at_k(relevant: set[str], ranked: list[str], k: int) -> float:
    if not relevant:
        return 0.0
    return next((1 / rank for rank, chunk_id in enumerate(ranked[:k], 1) if chunk_id in relevant), 0.0)


def _metrics(rows: list[dict], key: str) -> dict:
    answerable = [row for row in rows if row.get("is_answerable", True)]
    if not answerable:
        return {"recall_at_5": 0.0, "mrr_at_10": 0.0}
    return {
        "recall_at_5": statistics.mean(row[key]["recall_at_5"] for row in answerable),
        "mrr_at_10": statistics.mean(row[key]["mrr_at_10"] for row in answerable),
        **({"recall_at_10": statistics.mean(row[key]["recall_at_10"] for row in answerable)} if all("recall_at_10" in row[key] for row in answerable) else {}),
    }


def _mean_latency(rows: list[dict], key: str) -> float:
    return statistics.mean(row["latency_seconds"][key] for row in rows)


def _result(relevant: set[str], ranked: list[str]) -> dict:
    return {
        "ranked_chunk_ids": ranked[:TOP_K],
        "recall_at_5": recall_at_k(relevant, ranked, 5),
        "recall_at_10": recall_at_k(relevant, ranked, 10),
        "mrr_at_10": reciprocal_rank_at_k(relevant, ranked, TOP_K),
        "first_relevant_rank": next((i for i, chunk_id in enumerate(ranked[:TOP_K], 1) if chunk_id in relevant), None),
    }


def _read_dataset(path: Path, chunks_path: Path) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        raise ValueError("Dataset tidak boleh kosong.")
    chunk_ids = {json.loads(line)["chunk_id"] for line in chunks_path.read_text(encoding="utf-8").splitlines() if line.strip()}
    for row in rows:
        if row.get("split") not in {"dev", "holdout"}:
            raise ValueError("Setiap pertanyaan harus memiliki split dev/holdout.")
        is_ans = row.get("is_answerable", True)
        if is_ans and not row.get("relevant_chunk_ids"):
            raise ValueError(f"Pertanyaan answerable {row.get('question_id')} wajib memiliki relevant_chunk_ids.")
        unknown = {cid for cid in row.get("relevant_chunk_ids", []) if cid not in chunk_ids}
        if unknown:
            raise ValueError(f"Label tidak ditemukan di corpus: {sorted(unknown)}")
    if not any(row["split"] == "dev" for row in rows) or not any(row["split"] == "holdout" for row in rows):
        raise ValueError("Dataset perlu memuat dev dan holdout.")
    return rows


def run(dataset_path: Path, chunks_path: Path) -> dict:
    dataset = _read_dataset(dataset_path, chunks_path)
    warmup_started = time.perf_counter()
    search(dataset[0]["question"], chunks_path, top_k=CANDIDATE_K, retrieval_mode="dense")
    dense_warmup_seconds = time.perf_counter() - warmup_started

    prepared = []
    config_scores = {config: [] for config in CONFIGS}
    for sample in dataset:
        print(f"Retrieving {sample['question_id']}", flush=True)
        relevant = set(sample["relevant_chunk_ids"])
        bm25, bm25_seconds = timed_call(
            lambda sample=sample: search(sample["question"], chunks_path, top_k=CANDIDATE_K, retrieval_mode="bm25")
        )
        dense, dense_seconds = timed_call(
            lambda sample=sample: search(sample["question"], chunks_path, top_k=CANDIDATE_K, retrieval_mode="dense")
        )
        bm25_ids = [hit["chunk_id"] for hit in bm25]
        dense_ids = [hit["chunk_id"] for hit in dense]
        hybrid_by_config = {}
        for k, dense_weight in CONFIGS:
            fused = _rrf([dense, bm25], TOP_K, k=k, weights=(dense_weight, 1.0))
            ids = [hit["chunk_id"] for hit in fused]
            key = f"k={k},dense_weight={dense_weight:g}"
            result = _result(relevant, ids)
            hybrid_by_config[key] = result
            if sample["split"] == "dev" and sample.get("is_answerable", True):
                config_scores[(k, dense_weight)].append(result)
        prepared.append({
            "question_id": sample["question_id"], "split": sample["split"],
            "question_type": sample.get("question_type", "lookup"),
            "is_answerable": sample.get("is_answerable", True),
            "question": sample["question"], "relevant_chunk_ids": sample["relevant_chunk_ids"],
            "bm25": _result(relevant, bm25_ids), "dense": _result(relevant, dense_ids),
            "hybrid_by_config": hybrid_by_config,
            "latency_seconds": {"bm25": bm25_seconds, "dense": dense_seconds},
            "_candidate_lists": (dense, bm25),
        })

    tuning = []
    for (k, dense_weight), results in config_scores.items():
        tuning.append({"rrf_k": k, "dense_weight": dense_weight,
                       "recall_at_5": statistics.mean(x["recall_at_5"] for x in results),
                       "mrr_at_10": statistics.mean(x["mrr_at_10"] for x in results)})
    # Choose on dev MRR@10, then Recall@5; ties prefer the current default.
    chosen = max(tuning, key=lambda x: (x["mrr_at_10"], x["recall_at_5"],
                                        x["rrf_k"] == BASELINE_RRF_K and x["dense_weight"] == BASELINE_DENSE_WEIGHT,
                                        -abs(x["rrf_k"] - BASELINE_RRF_K), -abs(x["dense_weight"] - BASELINE_DENSE_WEIGHT)))
    chosen_key = f"k={chosen['rrf_k']},dense_weight={chosen['dense_weight']:g}"
    baseline_key = f"k={BASELINE_RRF_K},dense_weight={BASELINE_DENSE_WEIGHT:g}"
    rerank_started = time.perf_counter()
    first_candidates = prepared[0]["_candidate_lists"]
    first_fused = _rrf(first_candidates, CANDIDATE_K,
                       k=chosen["rrf_k"], weights=(chosen["dense_weight"], 1.0))
    rerank(dataset[0]["question"], first_fused, min(TOP_K, len(first_fused)))
    rerank_warmup_seconds = time.perf_counter() - rerank_started
    for row in prepared:
        print(f"Reranking {row['question_id']}", flush=True)
        row["hybrid_baseline"] = row["hybrid_by_config"][baseline_key]
        row["hybrid_tuned"] = row["hybrid_by_config"][chosen_key]
        del row["hybrid_by_config"]
        dense, bm25 = row.pop("_candidate_lists")
        started = time.perf_counter()
        candidates = _rrf([dense, bm25], CANDIDATE_K,
                          k=chosen["rrf_k"], weights=(chosen["dense_weight"], 1.0))
        row["latency_seconds"]["hybrid_fusion"] = time.perf_counter() - started
        started = time.perf_counter()
        reranked = rerank(row["question"], candidates, min(TOP_K, len(candidates)))
        row["latency_seconds"]["reranker"] = time.perf_counter() - started
        row["hybrid_rerank"] = _result(set(row["relevant_chunk_ids"]), [hit["chunk_id"] for hit in reranked])

    split_summary = {}
    for split in ("dev", "holdout"):
        rows = [row for row in prepared if row["split"] == split]
        split_summary[split] = {key: _metrics(rows, key) for key in ("bm25", "dense", "hybrid_baseline", "hybrid_tuned", "hybrid_rerank")}
        split_summary[split]["mean_latency_seconds"] = {
            key: _mean_latency(rows, key) for key in ("bm25", "dense", "hybrid_fusion", "reranker")
        }

    return {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "dataset": str(dataset_path), "question_count": len(dataset),
        "split_counts": {name: sum(row["split"] == name for row in dataset) for name in ("dev", "holdout")},
        "chunk_count": len({json.loads(line)["chunk_id"] for line in chunks_path.read_text(encoding="utf-8").splitlines() if line.strip()}),
        "chunks_sha256": hashlib.sha256(chunks_path.read_bytes()).hexdigest(),
        "dense_model": EMBEDDING_MODEL, "dense_device": "cpu", "candidate_k": CANDIDATE_K,
        "reranker_model": RERANKER_MODEL, "reranker_revision": RERANKER_REVISION,
        "reranker_onnx_max_length": RERANKER_MAX_LENGTH, "reranker_device": "CPUExecutionProvider",
        "warmup_model_and_passage_embedding_seconds": round(dense_warmup_seconds, 2),
        "reranker_model_and_first_pass_warmup_seconds": round(rerank_warmup_seconds, 2),
        "generation_evaluation": {
            "status": "not_run",
            "reason": "Retrieval benchmark tidak memanggil Ollama; gunakan template evaluasi jawaban manual.",
        },
        "selection_metric": "dev MRR@10, tie-break Recall@5",
        "baseline_config": {"rrf_k": BASELINE_RRF_K, "dense_weight": BASELINE_DENSE_WEIGHT, "bm25_weight": 1.0},
        "current_config": {"rrf_k": RRF_K, "dense_weight": DENSE_RRF_WEIGHT, "bm25_weight": 1.0},
        "selected_config": {"rrf_k": chosen["rrf_k"], "dense_weight": chosen["dense_weight"], "bm25_weight": 1.0},
        "dev_tuning": sorted(tuning, key=lambda x: (-x["mrr_at_10"], -x["recall_at_5"])),
        "summary": split_summary, "questions": prepared,
    }


def markdown(report: dict) -> str:
    selected = report["selected_config"]
    lines = [
        "# Retrieval tuning and holdout check", "",
        f"Generated UTC: {report['generated_at_utc']}",
        f"Questions: {report['split_counts']['dev']} dev / {report['split_counts']['holdout']} holdout | Chunks: {report['chunk_count']} | E5: `{report['dense_model']}` on CPU | Candidate depth: {report['candidate_k']}",
        f"Corpus SHA-256: `{report['chunks_sha256']}`",
        f"One-time model and passage embedding warmup: {report['warmup_model_and_passage_embedding_seconds']} s (excluded from retrieval ranking metrics)",
        f"Config selection uses {report['selection_metric']}. Selected RRF: k={selected['rrf_k']}, dense weight={selected['dense_weight']:g}, BM25 weight=1.",
        "",
        f"Reranker: `{report['reranker_model']}` at revision `{report['reranker_revision']}`, ONNX on CPU, max pair length {report['reranker_onnx_max_length']}. Recall@5 is the fraction of labeled relevant chunks found in the first five results. MRR@10 is the reciprocal rank of the first relevant result (miss=0), averaged across questions.",
        "",
        "## Development results",
        "",
        "| Mode/config | Recall@5 | MRR@10 |",
        "|---|---:|---:|",
    ]
    for key in ("bm25", "dense", "hybrid_baseline"):
        stats = report["summary"]["dev"][key]
        label = "hybrid_baseline (k=60, dense weight=1)" if key == "hybrid_baseline" else key
        lines.append(f"| {label} | {stats['recall_at_5']:.3f} | {stats['mrr_at_10']:.3f} |")
    tuned = report["summary"]["dev"]["hybrid_tuned"]
    lines.append(f"| hybrid_tuned (dev selected) | {tuned['recall_at_5']:.3f} | {tuned['mrr_at_10']:.3f} |")
    reranked_dev = report["summary"]["dev"]["hybrid_rerank"]
    lines.append(f"| hybrid_rerank (selected hybrid then reranked) | {reranked_dev['recall_at_5']:.3f} | {reranked_dev['mrr_at_10']:.3f} |")
    lines.extend(["", "## Holdout check (not used to select config)", "", "| Mode/config | Recall@5 | MRR@10 |", "|---|---:|---:|"])
    for key in ("bm25", "dense", "hybrid_baseline", "hybrid_tuned", "hybrid_rerank"):
        stats = report["summary"]["holdout"][key]
        label = "hybrid_baseline (k=60, dense weight=1)" if key == "hybrid_baseline" else key
        lines.append(f"| {label} | {stats['recall_at_5']:.3f} | {stats['mrr_at_10']:.3f} |")
    lines.extend(["", "## Mean per-question latency (seconds)", "", "| Split | BM25 | Dense (warm) | RRF fusion | Reranker |", "|---|---:|---:|---:|---:|"])
    for split in ("dev", "holdout"):
        latency = report["summary"][split]["mean_latency_seconds"]
        lines.append(f"| {split} | {latency['bm25']:.3f} | {latency['dense']:.3f} | {latency['hybrid_fusion']:.6f} | {latency['reranker']:.3f} |")
    lines.append("Model loading and corpus passage embedding warmup are reported separately; generation latency and peak RAM/VRAM were not measured in this retrieval benchmark.")
    lines.append("Reranking remains optional. Compare the measured dev and holdout tables before choosing a mode.")
    lines.extend(["", "## Recall@10", "", "| Split | Mode | Recall@10 |", "|---|---|---:|"])
    for split in ("dev", "holdout"):
        for mode in ("bm25", "dense", "hybrid_baseline", "hybrid_tuned", "hybrid_rerank"):
            value = report["summary"][split][mode].get("recall_at_10")
            lines.append(f"| {split} | {mode} | {value:.3f} |" if value is not None else f"| {split} | {mode} | not measured |")
    lines.extend(["", "## Dev tuning grid (top 10)", "", "| RRF k | Dense weight | Recall@5 | MRR@10 |", "|---:|---:|---:|---:|"])
    for row in report["dev_tuning"][:10]:
        lines.append(f"| {row['rrf_k']} | {row['dense_weight']:g} | {row['recall_at_5']:.3f} | {row['mrr_at_10']:.3f} |")
    lines.extend(["", "## Holdout per-question ranks", "", "| ID | Query | BM25 | Dense | Baseline RRF | Tuned RRF | Reranked |", "|---|---|---:|---:|---:|---:|---:|"])
    for row in report["questions"]:
        if row["split"] != "holdout":
            continue
        ranks = [(row[key]["first_relevant_rank"] or "miss") if row.get("is_answerable", True) else "-" for key in ("bm25", "dense", "hybrid_baseline", "hybrid_tuned", "hybrid_rerank")]
        lines.append(f"| {row['question_id']} | {row['question']} | " + " | ".join(map(str, ranks)) + " |")
    lines.extend(["", "Dataset labels target the cited chunks, not all potentially relevant text. This is a small exploratory sample; inspect the labels and failure cases before making a general quality claim.", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / "evaluation/dataset/retrieval_sample.jsonl")
    parser.add_argument("--chunks", type=Path, default=ROOT / "data/processed/chunks.jsonl")
    parser.add_argument("--json-out", type=Path, default=ROOT / "evaluation/results/retrieval_tuning_latest.json")
    parser.add_argument("--report-out", type=Path, default=ROOT / "docs/evaluation_report.md")
    args = parser.parse_args()
    report = run(args.dataset, args.chunks)
    report_md = markdown(report)
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.report_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.report_out.write_text(report_md, encoding="utf-8")
    print(report_md)
    print(f"\nJSON detail: {args.json_out}")


if __name__ == "__main__":
    main()
