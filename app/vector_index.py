"""Identity, storage and exclusive access for local vector snapshots."""

from __future__ import annotations

import atexit
import hashlib
import os
import re
import threading
from contextlib import ExitStack, closing, contextmanager
from pathlib import Path
from uuid import UUID, uuid5

from app.config import CONFIG, ROOT

CHUNKS = ROOT / CONFIG["storage"]["chunks_path"]
EMBEDDING = CONFIG["embedding"]
EMBEDDING_MODEL = os.getenv("REGULARAG_EMBEDDING_MODEL", EMBEDDING["model"])
EMBEDDING_REVISION = os.getenv("REGULARAG_EMBEDDING_REVISION", EMBEDDING["revisions"].get(EMBEDDING_MODEL))
COLLECTION = "chunks"
PAYLOAD_FIELDS = ("chunk_id", "document_id", "source_kind", "section_type")
_POINT_NAMESPACE = UUID("84c3404d-a15f-4121-a8c9-fd36848e196b")
_RECOVERY = "Tutup pembaca indeks, lalu jalankan python -m ingestion.build_vector_index atau gunakan BM25."
_read_lock = threading.Lock()
_readers = {}


class DenseSearchUnavailable(RuntimeError):
    """Dense dependencies, model or matching index are unavailable."""


def index_directory(chunks_path: Path) -> Path:
    if re.fullmatch(r"generation-[0-9a-f]{32}", chunks_path.parent.name):
        return chunks_path.resolve().with_name(f"{chunks_path.name}.qdrant")
    override = os.getenv("REGULARAG_QDRANT_PATH")
    if override:
        return Path(override).resolve()
    if chunks_path.resolve() == CHUNKS.resolve():
        return (ROOT / CONFIG["storage"]["qdrant_path"]).resolve()
    return chunks_path.resolve().with_name(f"{chunks_path.name}.qdrant")


def file_sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def identity(chunks_sha256: str) -> dict:
    if not EMBEDDING_REVISION or not re.fullmatch(r"[0-9a-f]{40}", EMBEDDING_REVISION):
        raise DenseSearchUnavailable("Tetapkan REGULARAG_EMBEDDING_REVISION ke SHA commit model embedding (40 digit heksadesimal).")
    return {
        "schema": 1,
        "chunks_sha256": chunks_sha256,
        "model": EMBEDDING_MODEL,
        "revision": EMBEDDING_REVISION,
        "query_prefix": EMBEDDING["query_prefix"],
        "passage_prefix": EMBEDDING["passage_prefix"],
        "normalize_embeddings": EMBEDDING["normalize_embeddings"],
        "distance": "Cosine",
    }


def point_id(chunk_id: str) -> str:
    return str(uuid5(_POINT_NAMESPACE, chunk_id))


def point_payload(chunk: dict) -> dict:
    return {key: chunk.get(key) for key in PAYLOAD_FIELDS}


def qdrant_models():
    try:
        from qdrant_client import models
    except ImportError as exc:
        raise DenseSearchUnavailable('Pasang dependensi dense dengan python -m pip install -e ".[dense]".') from exc
    return models


@contextmanager
def lock_store(directory: Path):
    qdrant_models()
    from portalocker import Lock, exceptions

    lock = Lock(directory / ".store.lock", timeout=0, fail_when_locked=True)
    try:
        lock.acquire()
    except exceptions.LockException as exc:
        raise DenseSearchUnavailable(
            "Direktori Qdrant Local sedang digunakan. Tutup UI, API, evaluator atau builder yang memegang "
            "direktori indeks. Gunakan Qdrant Server jika perlu akses dari beberapa proses."
        ) from exc
    try:
        yield
    finally:
        lock.release()


def local_client(directory: Path):
    from qdrant_client import QdrantClient

    # All access to a reader client is serialized, including SQLite reads across API threads.
    return closing(QdrantClient(path=str(directory), force_disable_check_same_thread=True))


def active_snapshot(directory: Path) -> str:
    name = (directory / "active.txt").read_text(encoding="ascii").strip()
    if not re.fullmatch(r"snapshot-[0-9a-f]{32}", name):
        raise ValueError("Penunjuk snapshot tidak valid.")
    if not (directory / name / "meta.json").is_file():
        raise ValueError("Snapshot aktif tidak tersedia.")
    return name


def check_collection(client, expected: dict, point_count: int | None = None) -> int:
    models = qdrant_models()
    info = client.get_collection(COLLECTION)
    metadata = info.config.metadata or {}
    vectors = info.config.params.vectors
    if any(metadata.get(key) != value for key, value in expected.items()):
        raise DenseSearchUnavailable(f"Indeks dense tidak cocok dengan corpus atau konfigurasi embedding. {_RECOVERY}")
    if (not isinstance(vectors, models.VectorParams) or vectors.distance != models.Distance.COSINE
            or vectors.size != metadata.get("dimension") or info.points_count != metadata.get("point_count")
            or (point_count is not None and info.points_count != point_count) or not info.points_count):
        raise ValueError("Dimensi atau jumlah point tidak cocok dengan metadata indeks.")
    return vectors.size


@contextmanager
def read_index(chunks_path: Path, digest: str, point_count: int | None = None):
    directory = index_directory(chunks_path)
    with _read_lock:
        try:
            expected = identity(digest)
            if directory not in _readers:
                if not (directory / "active.txt").is_file():
                    raise FileNotFoundError
                with ExitStack() as stack:
                    stack.enter_context(lock_store(directory))
                    name = active_snapshot(directory)
                    client = stack.enter_context(local_client(directory / name))
                    dimension = check_collection(client, expected, point_count)
                    _readers[directory] = (client, stack.pop_all())
            else:
                client, _ = _readers[directory]
                dimension = check_collection(client, expected, point_count)
            yield client, dimension
        except DenseSearchUnavailable:
            raise
        except FileNotFoundError as exc:
            raise DenseSearchUnavailable(f"Indeks dense belum tersedia. {_RECOVERY}") from exc
        except Exception as exc:
            raise DenseSearchUnavailable(f"Indeks dense gagal dibaca. {_RECOVERY}") from exc


@atexit.register
def close_vector_indexes() -> None:
    with _read_lock:
        while _readers:
            _, (_, stack) = _readers.popitem()
            stack.close()


def dense_index_ready(chunks_path: Path) -> bool:
    try:
        with read_index(chunks_path, file_sha256(chunks_path)):
            return True
    except (OSError, DenseSearchUnavailable):
        return False
