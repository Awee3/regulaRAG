"""Capture real local answers for subsequent human review; no automatic truth labels."""
import argparse
import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path

from fastapi import HTTPException

from app.generation import OLLAMA_MODEL, OLLAMA_NUM_CTX
from app.main import CHUNKS, QueryRequest, query


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="bm25", choices=["bm25", "dense", "hybrid", "hybrid_rerank"])
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--output", type=Path, default=Path("evaluation/results/answers.jsonl"))
    parser.add_argument("--dataset", type=Path, default=Path("evaluation/dataset/retrieval_sample.jsonl"))
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")
    dataset = [json.loads(s) for s in args.dataset.read_text(encoding="utf-8").splitlines() if s.strip()]
    # Include out-of-corpus questions in every smoke review.
    negative = [s for s in dataset if not s["is_answerable"]][:min(2, args.limit)]
    selected = [s for s in dataset if s["is_answerable"]][:args.limit-len(negative)] + negative
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as output:
        for sample in selected:
            started = time.perf_counter()
            try:
                result = query(QueryRequest(question=sample["question"], retrieval_mode=args.mode))
            except HTTPException as exc:
                result = {"answer": None, "abstained": True, "reason": "runtime_error", "http_status": exc.status_code, "detail": exc.detail}
            row = dict(sample, result=result, latency_seconds=time.perf_counter()-started,
                       model=OLLAMA_MODEL, num_ctx=OLLAMA_NUM_CTX,
                       corpus_sha256=hashlib.sha256(CHUNKS.read_bytes()).hexdigest(),
                       generated_at_utc=datetime.now(UTC).isoformat(),
                       answer_correct=None, claim_support=None, citation_supported=None,
                       review_status="pending_human_review")
            output.write(json.dumps(row, ensure_ascii=False)+"\n")
            output.flush()
            print(sample["question_id"], result.get("reason"), flush=True)


if __name__ == "__main__":
    main()
