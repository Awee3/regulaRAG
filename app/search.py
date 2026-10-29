"""Small standard-library lexical baseline; not a semantic retriever."""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

TOKEN = re.compile(r"[\w/.-]+", re.UNICODE)


def search(question: str, chunks_path: Path, top_k: int = 5,
           document_ids: set[str] | None = None) -> list[dict]:
    if not question.strip() or not 1 <= top_k <= 20:
        raise ValueError("Pertanyaan wajib diisi dan top_k harus 1–20.")
    docs = [json.loads(line) for line in chunks_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if document_ids is not None:
        docs = [doc for doc in docs if doc["document_id"] in document_ids]
    query = Counter(TOKEN.findall(question.casefold()))
    if not docs or not query:
        return []
    terms = [Counter(TOKEN.findall(d["text"].casefold())) for d in docs]
    lengths = [sum(words.values()) for words in terms]
    average_length = sum(lengths) / len(lengths) or 1
    document_frequency = {term: sum(term in words for words in terms) for term in query}
    idf = {term: math.log(1 + (len(docs) - frequency + 0.5) / (frequency + 0.5))
           for term, frequency in document_frequency.items()}
    article_match = re.search(r"\bpasal\s+([0-9]+[a-z]?)\b", question, re.IGNORECASE)
    exact_article = f"Pasal {article_match.group(1)}".casefold() if article_match else None
    ranked = []
    for doc, words, length in zip(docs, terms, lengths):
        score = sum(query[term] * idf[term] * (words[term] * 2.5) /
                    (words[term] + 1.5 * (1 - 0.75 + 0.75 * length / average_length))
                    for term in query if words[term])
        if score:
            exact = (doc.get("article") or "").casefold() == exact_article and doc.get("section_type") == "batang_tubuh" if exact_article else False
            ranked.append((exact, score, doc))
    ranked.sort(key=lambda item: (-item[0], -item[1], item[2]["chunk_id"]))
    return [dict(doc, score=score) for _, score, doc in ranked[:top_k]]


if __name__ == "__main__":
    import argparse
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    cli = argparse.ArgumentParser()
    cli.add_argument("question")
    cli.add_argument("--chunks", type=Path, default=Path("data/processed/chunks.jsonl"))
    args = cli.parse_args()
    hits = search(args.question, args.chunks)
    print(json.dumps(hits, ensure_ascii=False, indent=2) if hits else "Tidak ada evidence; abstain.")
