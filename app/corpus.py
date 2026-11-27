"""Resolve one immutable corpus generation for each request."""

import json
import re
from pathlib import Path

from app.config import CONFIG, ROOT

IMPORTS = ROOT / "data/processed/imports"


def paths(manifest: Path, chunks: Path, directory: Path = IMPORTS) -> tuple[Path, Path]:
    # Explicit experimental/test paths never pick up the application's imported corpus.
    if manifest != ROOT / CONFIG["storage"]["manifest_path"] or chunks != ROOT / CONFIG["storage"]["chunks_path"]:
        return manifest, chunks
    return active_paths(manifest, chunks, directory)


def active_paths(manifest: Path, chunks: Path, directory: Path) -> tuple[Path, Path]:
    pointer = directory / "active.txt"
    if not pointer.exists():
        return manifest, chunks
    name = pointer.read_text(encoding="ascii").strip()
    if not re.fullmatch(r"generation-[0-9a-f]{32}", name):
        raise ValueError("Penunjuk corpus impor tidak valid.")
    generation = directory / name
    return generation / "manifest.jsonl", generation / "chunks.jsonl"


def read_manifest(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def read_registry(path: Path, baseline: Path) -> list[dict]:
    records = {doc["document_id"]: doc for doc in read_manifest(path)}
    saved = path.with_name("baseline.jsonl")
    if saved.is_file() and baseline != path:
        previous = {doc["document_id"]: doc for doc in read_manifest(saved)}
        current = {doc["document_id"]: doc for doc in read_manifest(baseline)}
        for doc_id, doc in current.items():
            if previous.get(doc_id) != doc:
                old = records.get(doc_id)
                if old and old.get("sha256") != doc.get("sha256"):
                    doc = {**doc, "corpus_eligible": False, "import_note": "Byte sumber registry berubah; impor ulang PDF resmi agar citation dan registry cocok."}
                records[doc_id] = doc
        for doc_id in previous.keys() - current.keys():
            records.pop(doc_id, None)
    return list(records.values())
