"""Summarize captured answers without treating unreviewed output as ground truth."""
import argparse
import json
from pathlib import Path

from evaluation.metrics import (
    abstention_metrics,
    answer_correctness_score,
    groundedness_score,
)


def summarize(rows, review_status="reviewed"):
    if review_status not in {"reviewed", "ai_reviewed"}:
        raise ValueError("Unsupported review status")
    valid = [r for r in rows if r["result"].get("reason") not in {"runtime_error", "generator_unavailable"}]
    reviewed = [r for r in valid if r.get("review_status") == review_status]
    for row in reviewed:
        if type(row.get("answer_correct")) is not bool or any(not isinstance(row.get(key), list) or any(type(v) is not bool for v in row[key]) for key in ("claim_support", "citation_supported")):
            raise ValueError("Reviewed rows require boolean correctness and boolean lists for claims/citations")
    abstention = abstention_metrics([not r["is_answerable"] for r in valid], [r["result"]["abstained"] for r in valid]) if valid else None
    return {"review_status":review_status, "reviewer_kind":"ai" if review_status == "ai_reviewed" else "human", "count":len(rows), "runtime_failures":len(rows)-len(valid), "reviewed":len(reviewed), "pending":len(valid)-len(reviewed),
            "abstention":vars(abstention) if abstention else None,
            "answer_correctness":answer_correctness_score([r["answer_correct"] for r in reviewed]) if reviewed else None,
            "groundedness":groundedness_score([v for r in reviewed for v in r["claim_support"]]) if any(r["claim_support"] for r in reviewed) else None,
            ("ai_citation_support" if review_status == "ai_reviewed" else "manual_citation_support"):groundedness_score([v for r in reviewed for v in r["citation_supported"]]) if any(r["citation_supported"] for r in reviewed) else None}


def main():
    cli=argparse.ArgumentParser()
    cli.add_argument("input", type=Path)
    cli.add_argument("--output", type=Path, default=Path("evaluation/results/answer_review_summary.json"))
    cli.add_argument("--review-status", choices=["reviewed", "ai_reviewed"], default="reviewed")
    args=cli.parse_args()
    rows=[json.loads(s) for s in args.input.read_text(encoding="utf-8").splitlines() if s.strip()]
    report=summarize(rows, args.review_status)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))


if __name__ == "__main__":
    main()
