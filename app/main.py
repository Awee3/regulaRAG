"""Local API for document lookup and evidence-grounded answers."""

from __future__ import annotations

import gc
import json
from pathlib import Path
from typing import Literal
from urllib.error import URLError
from urllib.request import urlopen

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.config import CONFIG
from app.evidence import include_holdings, select_evidence
from app.generation import (
    OLLAMA_MODEL,
    OLLAMA_URL,
    GeneratorUnavailable,
    InvalidModelResponse,
    generate,
)
from app.reranking import RerankerUnavailable, release_runtime, rerank
from app.search import DenseSearchUnavailable, release_encoder, search

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / CONFIG["storage"]["manifest_path"]
CHUNKS = ROOT / CONFIG["storage"]["chunks_path"]
DISCLAIMER = "Informasi ini merupakan alat bantu penelusuran dokumen, bukan nasihat hukum."
app = FastAPI(title="RegulaRAG Indonesia", version="0.1.0")


class QueryRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    retrieval_mode: Literal["bm25", "dense", "hybrid", "hybrid_rerank"] = "bm25"
    top_k: int = Field(default=5, ge=1, le=10)
    document_ids: list[str] | None = Field(default=None, max_length=20)


def documents() -> list[dict]:
    return [json.loads(line) for line in MANIFEST.read_text(encoding="utf-8").splitlines() if line.strip()]


@app.get("/health")
def health() -> dict:
    try:
        with urlopen(OLLAMA_URL.rsplit("/", 1)[0] + "/tags", timeout=1) as response:
            installed = {item["name"] for item in json.load(response).get("models", [])}
        model_ready = any(name == OLLAMA_MODEL or name.startswith(OLLAMA_MODEL + "-") for name in installed)
    except (URLError, TimeoutError, OSError, json.JSONDecodeError, KeyError, TypeError):
        model_ready = False
    return {"status": "ok", "index_ready": CHUNKS.is_file() and CHUNKS.stat().st_size > 0,
            "generator": "ollama", "model": OLLAMA_MODEL, "model_ready": model_ready,
            "corpus_verified_at_utc": max((d.get("artifact_verified_at_utc", d.get("verified_at_utc", "")) for d in documents()), default=None)}


@app.get("/documents")
def get_documents() -> list[dict]:
    fields = ("document_id", "title", "document_type", "number", "year", "official_source_url",
              "effective_from", "status", "corpus_eligible", "related_document_ids")
    return [{key: doc.get(key) for key in fields} for doc in documents()]


def citation_records(hits: list[dict], references: list[str] | None = None) -> list[dict]:
    docs = {doc["document_id"]: doc for doc in documents()}
    selected = range(len(hits)) if references is None else (int(ref[1:]) - 1 for ref in references)
    citations = []
    for i in selected:
        hit = hits[i]
        citation = {key: hit.get(key) for key in ("chunk_id", "document_id", "article", "paragraph", "page_start", "page_end", "source_url", "status", "effective_from", "source_kind", "section_type")}
        citation["document_title"] = docs[hit["document_id"]]["title"]
        citation["quote"] = hit["text"]
        citations.append(citation)
    return citations


@app.post("/query")
def query(request: QueryRequest) -> dict:
    if not request.question.strip():
        raise HTTPException(status_code=422, detail="question wajib berisi teks.")
    registry_docs = documents()
    known_ids = {doc["document_id"] for doc in registry_docs}
    active_ids = {doc["document_id"] for doc in registry_docs if doc.get("corpus_eligible") and doc.get("status") == "verified"}
    if request.document_ids and not set(request.document_ids) <= known_ids:
        raise HTTPException(status_code=422, detail="document_ids memuat ID yang tidak terdaftar.")
    try:
        candidate_k = CONFIG["reranker"]["candidate_top_k"]
        mode = "hybrid" if request.retrieval_mode == "hybrid_rerank" else request.retrieval_mode
        hits = search(request.question, CHUNKS, candidate_k,
                      (set(request.document_ids) & active_ids) if request.document_ids else active_ids,
                      retrieval_mode=mode, normative_only=True)
        if request.retrieval_mode == "hybrid_rerank" and hits:
            release_encoder()
            hits = rerank(request.question, hits, min(request.top_k, len(hits)))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail="Index belum dibuat. Jalankan ingestion terlebih dahulu.") from exc
    except DenseSearchUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RerankerUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    registry = {doc["document_id"]: doc for doc in registry_docs}
    if hits and CHUNKS.is_file():
        chunks = [json.loads(line) for line in CHUNKS.read_text(encoding="utf-8").splitlines() if line.strip()]
        hits = include_holdings(hits, registry, chunks, (set(request.document_ids) & active_ids) if request.document_ids else active_ids)
    hits = select_evidence(request.question, hits, request.top_k)
    if not hits:
        return {"answer": "Corpus saat ini tidak menyediakan bukti yang memadai untuk menjawab pertanyaan ini.",
                "abstained": True, "reason": "no_evidence", "retrieval_mode": request.retrieval_mode,
                "citations": [], "disclaimer": DISCLAIMER}
    registry = {doc["document_id"]: doc for doc in documents()}
    for hit in hits:
        doc = registry[hit["document_id"]]
        for key in ("title", "number", "year", "legal_status_note", "related_document_ids", "verified_at_utc", "decision_date"):
            hit[key] = doc.get(key)
    release_encoder()
    release_runtime()
    gc.collect()
    try:
        result = generate(request.question, hits)
    except GeneratorUnavailable as exc:
        return {"answer": None, "abstained": True, "reason": "generator_unavailable", "detail": str(exc),
                "retrieval_mode": request.retrieval_mode, "citations": citation_records(hits), "disclaimer": DISCLAIMER}
    except InvalidModelResponse as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    citations = citation_records(hits, result["citation_ids"])
    abstained = result["abstained"] or not citations
    return {"answer": result["answer"] if not abstained else "Bukti belum cukup untuk menyusun jawaban yang terdukung.",
            "abstained": abstained, "reason": "insufficient_evidence" if abstained else None,
            "retrieval_mode": request.retrieval_mode, "citations": citations, "runtime_metrics": result.get("runtime_metrics"), "disclaimer": DISCLAIMER}
