"""BM25, multilingual E5, and rank fusion for local chunk search."""

from __future__ import annotations

import hashlib
import json
import math
import re
import threading
from collections import Counter
from pathlib import Path

from app.config import CONFIG
from app.vector_index import (
    CHUNKS,
    COLLECTION,
    EMBEDDING,
    EMBEDDING_MODEL,
    EMBEDDING_REVISION,
    DenseSearchUnavailable,
    point_id,
    qdrant_models,
    read_index,
)

TOKEN = re.compile(r"[\w/.-]+", re.UNICODE)
RETRIEVAL = CONFIG["retrieval"]
RRF_K = RETRIEVAL["rrf_k"]
DENSE_RRF_WEIGHT = RETRIEVAL["dense_rrf_weight"]
BM25_RRF_WEIGHT = RETRIEVAL["bm25_rrf_weight"]
_encoder = None
_dense_lock = threading.Lock()


def _load_encoder(device: str = CONFIG["embedding"]["device"]):
    global _encoder
    if _encoder is None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise DenseSearchUnavailable(
                'Dense search needs the optional dependencies. Install with: python -m pip install -e ".[dense]"'
            ) from exc
        try:
            _encoder = SentenceTransformer(EMBEDDING_MODEL, revision=EMBEDDING_REVISION, device=device)
        except Exception as exc:
            raise DenseSearchUnavailable(
                f"Model embedding {EMBEDDING_MODEL} tidak dapat dimuat. Periksa koneksi unduhan atau cache model lokal."
            ) from exc
    return _encoder


def chunks_from_bytes(corpus: bytes) -> list[dict]:
    return [json.loads(line) for line in corpus.splitlines() if line.strip()]


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


def _dense(question: str, chunks_path: Path, digest: str, docs: list[dict], top_k: int,
           document_ids: set[str] | None, normative_only: bool) -> list[dict]:
    if not docs:
        return []
    by_id = {doc["chunk_id"]: doc for doc in docs}
    with _dense_lock, read_index(chunks_path, digest) as (client, dimension):
        models = qdrant_models()
        filters = {}
        if document_ids is not None:
            filters["must"] = [models.FieldCondition(
                key="document_id", match=models.MatchAny(any=sorted(document_ids)),
            )]
        if normative_only:
            filters["must_not"] = [models.Filter(
                must=[models.FieldCondition(key="source_kind", match=models.MatchValue(value="judgment_full_text"))],
                must_not=[models.FieldCondition(key="section_type", match=models.MatchValue(value="amar_putusan"))],
            )]
        query_filter = models.Filter(**filters) if filters else None
        encoder = _load_encoder()
        vector = list(map(float, encoder.encode(
            [EMBEDDING["query_prefix"] + _normalize_query(question)],
            normalize_embeddings=EMBEDDING["normalize_embeddings"], show_progress_bar=False,
        )[0]))
        if len(vector) != dimension or not all(map(math.isfinite, vector)) or not any(vector):
            raise DenseSearchUnavailable("Vektor query tidak cocok dengan indeks. Bangun ulang dengan python -m ingestion.build_vector_index.")

        query_options = {"query": vector, "query_filter": query_filter, "with_payload": ["chunk_id"]}
        limit = min(top_k + 1, len(docs))
        points = client.query_points(COLLECTION, limit=limit, **query_options).points
        # Qdrant may truncate a tie before the corpus ID tie-break can be applied.
        if top_k < len(points) < len(docs) and points[-1].score == points[-2].score:
            limit = len(docs)
            points = client.query_points(COLLECTION, limit=limit, **query_options).points
        if len(points) != limit:
            raise ValueError("Jumlah kandidat Qdrant tidak cocok dengan filter corpus.")
        ranked = []
        for point in points:
            chunk_id = point.payload["chunk_id"]
            if point.id != point_id(chunk_id):
                raise ValueError("Identitas point tidak cocok dengan chunk.")
            ranked.append(dict(by_id[chunk_id], score=point.score))
        return sorted(ranked, key=lambda hit: (-hit["score"], hit["chunk_id"]))[:top_k]


def _rrf(rankings: list[list[dict]], top_k: int, k: int = RRF_K,
         weights: tuple[float, float] = (DENSE_RRF_WEIGHT, BM25_RRF_WEIGHT)) -> list[dict]:
    fused: dict[str, tuple[float, dict]] = {}
    for ranking, weight in zip(rankings, weights):
        for rank, doc in enumerate(ranking, 1):
            chunk_id = doc["chunk_id"]
            score, original = fused.get(chunk_id, (0.0, doc))
            fused[chunk_id] = (score + weight / (k + rank), original)
    ordered = sorted(fused.values(), key=lambda item: (-item[0], item[1]["chunk_id"]))
    return [dict(doc, score=score) for score, doc in ordered[:top_k]]


def search(question: str, chunks_path: Path, top_k: int = RETRIEVAL["default_top_k"],
           document_ids: set[str] | None = None, retrieval_mode: str = "bm25",
           normative_only: bool = False, *, corpus_bytes: bytes | None = None) -> list[dict]:
    if not question.strip() or not 1 <= top_k <= 20:
        raise ValueError("Pertanyaan wajib diisi dan top_k harus 1-20.")
    if retrieval_mode not in {"bm25", "dense", "hybrid"}:
        raise ValueError("retrieval_mode harus bm25, dense, atau hybrid.")
    corpus = chunks_path.read_bytes() if corpus_bytes is None else corpus_bytes
    docs = chunks_from_bytes(corpus)
    if normative_only:
        docs = [doc for doc in docs if doc.get("source_kind") != "judgment_full_text" or doc.get("section_type") == "amar_putusan"]
    if document_ids is not None:
        docs = [doc for doc in docs if doc["document_id"] in document_ids]
    if retrieval_mode == "bm25":
        return _bm25(question, docs, top_k)
    digest = hashlib.sha256(corpus).hexdigest()
    if retrieval_mode == "dense":
        return _dense(question, chunks_path, digest, docs, top_k, document_ids, normative_only)
    pool_k = max(top_k, RETRIEVAL["candidate_k"])
    dense_k = min(pool_k, max(top_k, RETRIEVAL["dense_top_k"]))
    bm25_k = min(pool_k, max(top_k, RETRIEVAL["bm25_top_k"]))
    dense = _dense(question, chunks_path, digest, docs, dense_k, document_ids, normative_only)
    lexical = _bm25(question, docs, bm25_k)
    return _rrf([dense, lexical], top_k)


if __name__ == "__main__":
    import argparse
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    cli = argparse.ArgumentParser()
    cli.add_argument("question")
    cli.add_argument("--chunks", type=Path, default=CHUNKS)
    cli.add_argument("--mode", choices=("bm25", "dense", "hybrid"), default="bm25")
    args = cli.parse_args()
    try:
        hits = search(args.question, args.chunks, retrieval_mode=args.mode)
    except DenseSearchUnavailable as exc:
        cli.exit(1, f"{exc}\n")
    print(json.dumps(hits, ensure_ascii=False, indent=2) if hits else "Tidak ada evidence; abstain.")


def release_encoder():
    """Release encoder weights while retaining the persisted vector index."""
    global _encoder
    with _dense_lock:
        _encoder = None
