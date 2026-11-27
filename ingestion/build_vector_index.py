"""Build and publish a persistent Qdrant Local snapshot from verified corpus chunks."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sqlite3
from itertools import islice
from pathlib import Path
from pickle import UnpicklingError
from uuid import uuid4

from app import search
from app.vector_index import (
    CHUNKS,
    COLLECTION,
    EMBEDDING,
    DenseSearchUnavailable,
    active_snapshot,
    check_collection,
    file_sha256,
    identity,
    index_directory,
    local_client,
    lock_store,
    point_id,
    point_payload,
    qdrant_models,
)

BATCH_SIZE = 16


def _chunks(path, digest):
    with path.open("rb") as source:
        for line in source:
            digest.update(line)
            if line.strip():
                yield json.loads(line)


def _validate_points(client, metadata, expected):
    check_collection(client, metadata, len(expected))
    seen = set()
    offset = None
    while True:
        records, offset = client.scroll(COLLECTION, limit=128, offset=offset, with_vectors=False)
        for record in records:
            if record.id not in expected or record.payload != expected[record.id]:
                raise ValueError("ID atau metadata point tidak cocok dengan corpus.")
            seen.add(record.id)
        if offset is None:
            break
    if seen != expected.keys():
        raise ValueError("ID point tidak lengkap.")


def _activate(directory: Path, name: str) -> None:
    temporary = directory / ".active.tmp"
    with temporary.open("w", encoding="ascii") as pointer:
        pointer.write(name + "\n")
        pointer.flush()
        os.fsync(pointer.fileno())
    temporary.replace(directory / "active.txt")


def build(chunks_path: Path, index_path: Path | None = None, *, encoder=None) -> str:
    directory = (index_path or index_directory(chunks_path)).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    models = qdrant_models()
    with lock_store(directory):
        digest = hashlib.sha256()
        expected = {}
        for chunk in _chunks(chunks_path, digest):
            if not all(isinstance(chunk.get(key), str) and chunk[key].strip()
                       for key in ("chunk_id", "document_id", "text")):
                raise ValueError("Setiap chunk wajib memiliki chunk_id, document_id dan text.")
            identifier = point_id(chunk["chunk_id"])
            if identifier in expected:
                raise ValueError(f"chunk_id duplikat: {chunk['chunk_id']}")
            expected[identifier] = point_payload(chunk)
        if not expected:
            raise ValueError("Corpus kosong. Jalankan ingestion.build_corpus terlebih dahulu.")

        metadata = identity(digest.hexdigest())
        try:
            current = active_snapshot(directory)
            with local_client(directory / current) as client:
                _validate_points(client, metadata, expected)
        except (OSError, RuntimeError, ValueError, TypeError, KeyError, sqlite3.Error, UnpicklingError, EOFError):
            # An absent, obsolete or damaged snapshot can be replaced without writing to it.
            current = None
        if current and file_sha256(chunks_path) == metadata["chunks_sha256"]:
            return current

        name = f"snapshot-{uuid4().hex}"
        encoder = encoder or search._load_encoder(device="cpu")
        dimension = encoder.get_sentence_embedding_dimension()
        if not isinstance(dimension, int) or dimension < 1:
            raise ValueError("Dimensi embedding tidak valid.")
        metadata.update(dimension=dimension, point_count=len(expected))
        encoded_digest = hashlib.sha256()
        with local_client(directory / name) as client:
            client.create_collection(
                COLLECTION, vectors_config=models.VectorParams(size=dimension, distance=models.Distance.COSINE),
                metadata=metadata,
            )
            chunks = _chunks(chunks_path, encoded_digest)
            while batch := list(islice(chunks, BATCH_SIZE)):
                vectors = encoder.encode(
                    [EMBEDDING["passage_prefix"] + chunk["text"] for chunk in batch],
                    batch_size=BATCH_SIZE, normalize_embeddings=EMBEDDING["normalize_embeddings"],
                    show_progress_bar=False, device="cpu",
                )
                points = []
                for chunk, values in zip(batch, vectors, strict=True):
                    vector = list(map(float, values))
                    if len(vector) != dimension or not all(map(math.isfinite, vector)) or not any(vector):
                        raise ValueError("Encoder menghasilkan vektor passage yang tidak valid.")
                    points.append(models.PointStruct(
                        id=point_id(chunk["chunk_id"]), vector=vector, payload=point_payload(chunk),
                    ))
                client.upsert(COLLECTION, points=points, wait=True)

        with local_client(directory / name) as client:
            _validate_points(client, metadata, expected)
        if encoded_digest.hexdigest() != metadata["chunks_sha256"] or file_sha256(chunks_path) != metadata["chunks_sha256"]:
            raise ValueError("Corpus berubah selama build. Jalankan ulang build indeks.")
        _activate(directory, name)
        return name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks", type=Path, default=CHUNKS)
    parser.add_argument("--index-dir", type=Path)
    args = parser.parse_args()
    try:
        name = build(args.chunks, args.index_dir)
    except (DenseSearchUnavailable, OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f"Build indeks dense gagal: {exc}\n")
    print(f"Snapshot dense aktif: {name} ({args.index_dir or index_directory(args.chunks)})")


if __name__ == "__main__":
    main()
