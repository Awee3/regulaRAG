"""One recoverable, in-app inbox worker; no standalone background service."""

from __future__ import annotations

import atexit
import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path
from uuid import uuid4

from app.config import CONFIG, ROOT
from app.corpus import IMPORTS, active_paths, read_manifest, read_registry
from app.vector_index import DenseSearchUnavailable, index_directory
from ingestion.build_corpus import build
from ingestion.official_source import (
    MAX_BYTES,
    SourceError,
    identify,
    pdf_pages,
    validate_url,
    verify,
)


def atomic_write(path: Path, data: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    with temporary.open("w", encoding="utf-8") as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(path)


def json_lines(records):
    return "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)


class ProcessLock:
    def __init__(self, path: Path):
        self.file = path.open("r+b" if path.exists() else "w+b")
        self.file.seek(0)
        if os.name == "nt":
            import msvcrt
            if path.stat().st_size == 0:
                self.file.write(b"0")
                self.file.flush()
            self.file.seek(0)
            try:
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                self.file.close()
                raise
        else:
            import fcntl
            try:
                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                self.file.close()
                raise

    def close(self):
        self.file.close()


class InboxImporter:
    def __init__(self, root: Path = ROOT, *, manifest: Path | None = None,
                 chunks: Path | None = None, directory: Path | None = None, settle_seconds: float = 3):
        self.root = root.resolve()
        self.inbox = self.root / "data/inbox"
        self.directory = directory or self.root / "data/processed/imports"
        self.manifest = manifest or self.root / CONFIG["storage"]["manifest_path"]
        self.chunks = chunks or self.root / CONFIG["storage"]["chunks_path"]
        self.settle_seconds = settle_seconds
        self.observed = {}
        self.processed = {}
        self.stop_event = threading.Event()
        self.lifecycle_lock = threading.Lock()
        self.thread = None
        self.lock = None
        self.inbox.mkdir(parents=True, exist_ok=True)
        self.directory.mkdir(parents=True, exist_ok=True)

    def current(self):
        return active_paths(self.manifest, self.chunks, self.directory)

    def jobs(self) -> list[dict]:
        result = []
        for path in sorted(self.directory.glob("job-*.json")):
            result.append(json.loads(path.read_text(encoding="utf-8")))
        return result

    def save(self, job: dict, status: str, message: str):
        job.update(status=status, message=message)
        atomic_write(self.directory / f"job-{job['sha256']}.json", json.dumps(job, ensure_ascii=False))

    def submit_source(self, digest: str, source: dict):
        if not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise ValueError("ID impor tidak valid.")
        if not (self.directory / f"job-{digest}.json").is_file():
            raise FileNotFoundError("ID impor tidak ditemukan. Tunggu pemindaian file selesai.")
        source = {key: value.strip() for key, value in source.items() if key in {"page_url", "pdf_url", "metadata_url"} and value and value.strip()}
        if not source.get("page_url"):
            raise ValueError("Tautan halaman resmi wajib diisi.")
        for value in source.values():
            validate_url(value)
        # Requests are separate from jobs so UI/API cannot race the worker's writes.
        atomic_write(self.directory / f"source-{digest}.json", json.dumps({**source, "request_id": uuid4().hex}))

    def start(self):
        with self.lifecycle_lock:
            self.stop_event.clear()
            if self.thread and self.thread.is_alive():
                return
            self.thread = threading.Thread(target=self.run, name="regularag-inbox", daemon=True)
            self.thread.start()

    def stop(self):
        with self.lifecycle_lock:
            self.stop_event.set()
            thread = self.thread
        if thread:
            thread.join(timeout=2)

    def run(self):
        while True:
            with self.lifecycle_lock:
                if self.stop_event.is_set():
                    if self.lock:
                        self.lock.close()
                        self.lock = None
                    self.thread = None
                    return
            if self.lock is None:
                try:
                    self.lock = ProcessLock(self.directory / ".worker.lock")
                except OSError:
                    self.stop_event.wait(2)
                    continue
            try:
                self.scan()
            except (OSError, ValueError, RuntimeError, KeyError, TypeError):
                # A bad job/filesystem must not kill startup catchup for all later files.
                atomic_write(self.directory / "worker-error.txt", "Pemindaian terhenti karena kesalahan penyimpanan. Periksa izin/ruang disk; worker mencoba kembali.")
            self.stop_event.wait(2)

    def scan(self):
        manifest_path, chunks_path = self.current()
        corpus_signature = tuple((str(item), item.stat().st_mtime_ns, item.stat().st_size) if item.exists() else (str(item), None) for item in (manifest_path, chunks_path, self.manifest))
        for path in sorted(self.inbox.iterdir()):
            if path.suffix.lower() != ".pdf" or not path.is_file() or path.is_symlink() or path.resolve().parent != self.inbox.resolve():
                continue
            try:
                before = path.stat()
                signature = (before.st_size, before.st_mtime_ns)
                old, since = self.observed.get(path.name, (None, time.monotonic()))
                if signature != old:
                    self.observed[path.name] = (signature, time.monotonic())
                    continue
                if time.monotonic() - since < self.settle_seconds:
                    continue
                cached = self.processed.get(path.name)
                if cached and cached[0] == signature:
                    request_path = self.directory / f"source-{cached[1]}.json"
                    request_signature = request_path.stat().st_mtime_ns if request_path.exists() else None
                    if cached[2] == request_signature and cached[3] == corpus_signature:
                        continue
                if before.st_size > MAX_BYTES:
                    with path.open("rb") as input_file:
                        digest = hashlib.file_digest(input_file, "sha256").hexdigest()
                    self.save({"sha256": digest, "filenames": [path.name]}, "too_large", "PDF melebihi batas 64 MB. Gunakan naskah resmi yang lebih kecil; jangan memotong isi hukum.")
                    self.processed[path.name] = (signature, digest, None, corpus_signature)
                    continue
                data = path.read_bytes()
                after = path.stat()
                if (after.st_size, after.st_mtime_ns) != signature:
                    continue
                digest = hashlib.sha256(data).hexdigest()
                request_path = self.directory / f"source-{digest}.json"
                processed_request = request_path.stat().st_mtime_ns if request_path.exists() else None
                self.process(path, data)
                self.processed[path.name] = (signature, digest, processed_request, corpus_signature)
            except OSError:
                continue

    def process(self, path: Path, data: bytes):
        digest = hashlib.sha256(data).hexdigest()
        job_path = self.directory / f"job-{digest}.json"
        job = json.loads(job_path.read_text(encoding="utf-8")) if job_path.exists() else {"sha256": digest, "filenames": []}
        renamed = path.name not in job["filenames"]
        if renamed:
            job["filenames"].append(path.name)
        manifest_path, chunks_path = self.current()
        registry = read_registry(manifest_path, self.manifest)
        duplicate = next((doc for doc in registry if doc.get("sha256") == digest and doc.get("status") == "verified" and doc.get("corpus_eligible")), None)
        if duplicate:
            searchable = chunks_path.is_file() and any(chunk.get("document_id") == duplicate["document_id"] and (duplicate.get("source_kind") != "judgment_full_text" or chunk.get("section_type") == "amar_putusan") for chunk in read_manifest(chunks_path))
            if not searchable:
                try:
                    self.save(job, "indexing", "Memulihkan corpus dari byte yang cocok dengan registry terverifikasi…")
                    self.publish(dict(duplicate), data, registry)
                except (OSError, ValueError, RuntimeError, ImportError, KeyError, TypeError) as exc:
                    self.save(job, "failed", f"Corpus dokumen terverifikasi belum dapat dipulihkan ({type(exc).__name__}). Pastikan seluruh PDF aktif tersedia dan dependensi terpasang, lalu kirim sumber untuk mencoba lagi.")
                    return
            job["document_id"] = duplicate["document_id"]
            self.save(job, "ready", "Siap dicari; isi PDF sudah tersedia, termasuk jika nama file berubah.")
            return
        request_path = self.directory / f"source-{digest}.json"
        source = json.loads(request_path.read_text(encoding="utf-8")) if request_path.exists() else None
        retry = bool(source and source.get("request_id") != job.get("request_id"))
        if job.get("status") not in (None, "checking_source", "indexing") and not retry:
            if renamed:
                self.save(job, job["status"], job["message"])
            return
        if source:
            job["request_id"] = source["request_id"]
        try:
            pages = pdf_pages(data)
            if source is None:
                candidate = next((doc for doc in registry if doc.get("sha256") == digest and doc.get("official_source_url")), None)
                if candidate is None:
                    try:
                        candidate_id = identify(" ".join(pages[:2]))[0]
                        candidate = next((doc for doc in registry if doc["document_id"] == candidate_id and doc.get("official_source_url")), None)
                    except SourceError:
                        pass
                if candidate and candidate.get("download_url") != candidate["official_source_url"]:
                    source = {"page_url": candidate["official_source_url"], "pdf_url": candidate.get("download_url")}
                else:
                    self.save(job, "needs_source", "Isi tautan halaman detail resmi untuk memverifikasi PDF ini. Nama file tidak digunakan sebagai bukti.")
                    return
            self.save(job, "checking_source", "Memeriksa sumber resmi dan mencocokkan seluruh byte PDF…")
            document = verify(data, source, registry)
            prior = next((doc for doc in registry if doc["document_id"] == document["document_id"]), None)
            if prior and prior.get("corpus_eligible") and prior.get("sha256") != digest:
                raise SourceError("mismatch", "ID dokumen sudah aktif dengan byte berbeda. Pembaruan versi memerlukan pemeriksaan terpisah agar corpus lama tidak ditimpa.")
            if prior:
                document["related_document_ids"] = sorted(set(document["related_document_ids"] + prior.get("related_document_ids", [])))
            self.save(job, "indexing", "Sumber cocok. Menyiapkan corpus dan indeks baru; corpus sebelumnya tetap melayani pencarian…")
            self.publish(document, data, registry)
            job["document_id"] = document["document_id"]
            self.save(job, "ready", "Siap dicari dengan sumber resmi dan citation halaman PDF.")
        except SourceError as exc:
            self.save(job, exc.status, str(exc))
        except DenseSearchUnavailable as exc:
            self.save(job, "failed", f"Indeks dense belum diterbitkan: {exc} Corpus sebelumnya tetap aktif. Setelah memperbaiki dependensi/cache model, kirim sumber lagi.")
        except (OSError, ValueError, RuntimeError, ImportError, KeyError, TypeError) as exc:
            self.save(job, "failed", f"Impor belum diterbitkan ({type(exc).__name__}). Corpus sebelumnya tetap aktif. Periksa file/dependensi/ruang disk lalu kirim sumber lagi untuk mencoba ulang.")

    def publish(self, document: dict, data: bytes, registry: list[dict]):
        baseline_bytes = self.manifest.read_bytes()
        raw = self.directory / "pdfs" / f"{document['sha256']}.pdf"
        raw.parent.mkdir(exist_ok=True)
        if not raw.exists():
            temporary = raw.with_suffix(".tmp")
            temporary.write_bytes(data)
            temporary.replace(raw)
        document["local_path"] = str(raw.relative_to(self.root))
        records = [doc for doc in registry if doc["document_id"] != document["document_id"]] + [document]
        generation = self.directory / f"generation-{uuid4().hex}"
        generation.mkdir()
        manifest, chunks = generation / "manifest.jsonl", generation / "chunks.jsonl"
        manifest.write_text(json_lines(records), encoding="utf-8")
        (generation / "baseline.jsonl").write_bytes(baseline_bytes)
        if build(manifest, chunks, self.root) == 0:
            raise ValueError("Tidak ada struktur hukum yang berhasil diparse.")
        new_chunks = [chunk for chunk in read_manifest(chunks) if chunk["document_id"] == document["document_id"]]
        if not new_chunks or (document["source_kind"] == "judgment_full_text" and not any(chunk.get("section_type") == "amar_putusan" for chunk in new_chunks)):
            raise SourceError("needs_metadata", "Struktur pasal/amar PDF belum dapat diparse dengan aman. Dokumen tetap di luar pencarian; parser memerlukan pemeriksaan.")
        _, previous_chunks = self.current()
        if (index_directory(previous_chunks) / "active.txt").exists():
            from app.search import create_encoder
            from ingestion.build_vector_index import build as build_vectors
            build_vectors(chunks, chunks.with_name("chunks.jsonl.qdrant"), encoder=create_encoder("cpu"))
        if self.manifest.read_bytes() != baseline_bytes:
            raise RuntimeError("Registry sumber awal berubah selama build; coba ulang impor.")
        atomic_write(self.directory / "active.txt", generation.name + "\n")


IMPORTER = InboxImporter(directory=IMPORTS)
atexit.register(IMPORTER.stop)
