"""BM25, multilingual E5, and rank fusion for local chunk search."""

from __future__ import annotations

import json
import math
import os
import re
import threading
from collections import Counter
from pathlib import Path

from app.config import CONFIG

TOKEN = re.compile(r"[\w/.-]+", re.UNICODE)
RRF_K = CONFIG["retrieval"]["rrf_k"]
DENSE_RRF_WEIGHT = CONFIG["retrieval"]["dense_rrf_weight"]
EMBEDDING_MODEL = os.getenv("REGULARAG_EMBEDDING_MODEL", CONFIG["embedding"]["model"])
EMBEDDING_REVISION = os.getenv("REGULARAG_EMBEDDING_REVISION", CONFIG["embedding"].get("revisions", {}).get(EMBEDDING_MODEL))
_encoder = None
_embedding_cache: tuple[tuple[str, int, int, str], list[dict], list[list[float]]] | None = None
_dense_lock = threading.Lock()


class DenseSearchUnavailable(RuntimeError):
    """Raised when the optional dense-search dependency is not installed."""


def _load_encoder():
    global _encoder
    if _encoder is None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise DenseSearchUnavailable(
                'Dense search needs the optional dependencies. Install with: python -m pip install -e ".[dense]"'
            ) from exc
        try:
            _encoder = SentenceTransformer(EMBEDDING_MODEL, revision=EMBEDDING_REVISION, device=CONFIG["embedding"]["device"])
        except Exception as exc:
            raise DenseSearchUnavailable(
                f"Model embedding {EMBEDDING_MODEL} tidak dapat dimuat. Periksa koneksi unduhan atau cache model lokal."
            ) from exc
    return _encoder


def _documents(chunks_path: Path) -> list[dict]:
    return [json.loads(line) for line in chunks_path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _normalize_query(question: str) -> str:
    # Expand universal legal acronyms (e.g. DPO <-> PPDP / pejabat/petugas pelindungan data pribadi)
    normalized = re.sub(r"\bdpo\b", "dpo pejabat petugas pelindungan data pribadi ppdp", question, flags=re.IGNORECASE)
    for term, expansion in {"membocorkan": "mengungkapkan", "kebocoran": "kegagalan pelindungan", "dikirim": "transfer", "petugas": "pejabat"}.items():
        normalized = re.sub(rf"\b{term}\b", f"{term} {expansion}", normalized, flags=re.IGNORECASE)
    return normalized


def _bm25(question: str, docs: list[dict], top_k: int) -> list[dict]:
    q_norm = _normalize_query(question)
    query = Counter(TOKEN.findall(q_norm.casefold()))
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

    putusan_match = re.search(r"\b(?:putusan|perkara|nomor|no\.?)\s*(?:mk\s*)?([0-9]{2,3})\b", question, re.IGNORECASE)
    putusan_num = putusan_match.group(1) if putusan_match else None
    is_asking_amar = bool(re.search(r"\b(?:amar|status|membatalkan|mengabulkan|menolak|mengubah|putusan)\b", question, re.IGNORECASE))

    ranked = []
    for doc, words, length in zip(docs, terms, lengths):
        score = sum(query[term] * idf[term] * (words[term] * 2.5) /
                    (words[term] + 1.5 * (1 - 0.75 + 0.75 * length / average_length))
                    for term in query if words[term])
        if score:
            exact = False
            if exact_article and not putusan_num:
                exact = ((doc.get("article") or "").casefold() == exact_article
                         and doc.get("section_type") == "batang_tubuh")
            elif putusan_num and doc.get("document_id", "").startswith("MK_"):
                doc_id = doc.get("document_id", "")
                if putusan_num in doc_id:
                    if is_asking_amar and doc.get("section_type") == "amar_putusan":
                        score *= 2.5
                    elif doc.get("section_type") in ("amar_putusan", "pertimbangan_hukum"):
                        score *= 1.4
            ranked.append((exact, score, doc))
    definition = re.search(r"(?:dimaksud (?:dengan )?|definisi )(.*?)[?.]?$", question, re.IGNORECASE)
    if definition:
        term = definition.group(1).strip().casefold()
        ranked = [(exact or f"{term} adalah" in " ".join(doc["text"].casefold().split()), score, doc) for exact, score, doc in ranked]
    ranked.sort(key=lambda item: (-item[0], -item[1], item[2]["chunk_id"]))
    return [dict(doc, score=score) for _, score, doc in ranked[:top_k]]


def _dense(question: str, chunks_path: Path, docs: list[dict], top_k: int) -> list[dict]:
    global _embedding_cache
    with _dense_lock:
        stat = chunks_path.stat()
        key = (str(chunks_path.resolve()), stat.st_mtime_ns, stat.st_size, EMBEDDING_MODEL)
        if _embedding_cache is None or _embedding_cache[0] != key:
            all_docs = _documents(chunks_path)
            encoder = _load_encoder()
            vectors = encoder.encode([f"passage: {doc['text']}" for doc in all_docs],
                                     normalize_embeddings=True, show_progress_bar=False)
            _embedding_cache = (key, all_docs, [list(map(float, vector)) for vector in vectors])
        encoder = _load_encoder()
        query_vector = list(map(float, encoder.encode([f"query: {_normalize_query(question)}"],
                                                      normalize_embeddings=True, show_progress_bar=False)[0]))
        allowed = {doc["chunk_id"] for doc in docs}
        ranked = [(sum(a * b for a, b in zip(query_vector, vector)), doc)
                  for doc, vector in zip(_embedding_cache[1], _embedding_cache[2])
                  if doc["chunk_id"] in allowed]
        ranked.sort(key=lambda item: (-item[0], item[1]["chunk_id"]))
        return [dict(doc, score=score) for score, doc in ranked[:top_k]]


def _rrf(rankings: list[list[dict]], top_k: int, k: int = RRF_K,
         weights: tuple[float, float] = (DENSE_RRF_WEIGHT, 1.0)) -> list[dict]:
    fused: dict[str, tuple[float, dict]] = {}
    for ranking, weight in zip(rankings, weights):
        for rank, doc in enumerate(ranking, 1):
            chunk_id = doc["chunk_id"]
            score, original = fused.get(chunk_id, (0.0, doc))
            fused[chunk_id] = (score + weight / (k + rank), original)
    ordered = sorted(fused.values(), key=lambda item: (-item[0], item[1]["chunk_id"]))
    return [dict(doc, score=score) for score, doc in ordered[:top_k]]


def search(question: str, chunks_path: Path, top_k: int = 5,
           document_ids: set[str] | None = None, retrieval_mode: str = "bm25",
           normative_only: bool = False) -> list[dict]:
    if not question.strip() or not 1 <= top_k <= 20:
        raise ValueError("Pertanyaan wajib diisi dan top_k harus 1-20.")
    if retrieval_mode not in {"bm25", "dense", "hybrid"}:
        raise ValueError("retrieval_mode harus bm25, dense, atau hybrid.")
    docs = _documents(chunks_path)
    if normative_only:
        docs = [doc for doc in docs if doc.get("source_kind") != "judgment_full_text" or doc.get("section_type") == "amar_putusan"]
    if document_ids is not None:
        docs = [doc for doc in docs if doc["document_id"] in document_ids]
    if retrieval_mode == "bm25":
        return _bm25(question, docs, top_k)
    # Retrieve a shared candidate pool before returning top_k; this leaves BM25's baseline unchanged.
    candidate_k = min(len(docs), max(top_k, CONFIG["retrieval"]["candidate_k"]))
    dense = _dense(question, chunks_path, docs, candidate_k)
    if retrieval_mode == "dense":
        return dense[:top_k]
    lexical = _bm25(question, docs, candidate_k)
    return _rrf([dense, lexical], top_k, weights=(DENSE_RRF_WEIGHT, 1.0))


if __name__ == "__main__":
    import argparse
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    cli = argparse.ArgumentParser()
    cli.add_argument("question")
    cli.add_argument("--chunks", type=Path, default=Path("data/processed/chunks.jsonl"))
    cli.add_argument("--mode", choices=("bm25", "dense", "hybrid"), default="bm25")
    args = cli.parse_args()
    hits = search(args.question, args.chunks, retrieval_mode=args.mode)
    print(json.dumps(hits, ensure_ascii=False, indent=2) if hits else "Tidak ada evidence; abstain.")


def release_encoder():
    """Release model weights while retaining cached passage vectors."""
    global _encoder
    with _dense_lock:
        _encoder = None
