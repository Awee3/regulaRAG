"""Isolated inbox, verification, API publication and recovery checks."""

import hashlib
import tempfile
import time
import unittest
from datetime import date, timedelta
from importlib.util import find_spec
from pathlib import Path
from unittest.mock import patch

import fitz
from fastapi import HTTPException

from app import main, search, vector_index
from app.config import ROOT
from app.corpus import read_manifest, read_registry
from ingestion import build_corpus, build_vector_index
from ingestion.inbox import InboxImporter, ProcessLock, json_lines
from ingestion.official_source import (
    OfficialRedirects,
    SourceError,
    identify,
    pdf_pages,
    validate_url,
    verify,
)

PAGE = "https://peraturan.go.id/id/pp-no-17-tahun-2025"
PDF = "https://peraturan.go.id/files/pp17-2025.pdf"
TITLE = "Tata Kelola Data Pribadi"
HTML = f"""<h1>Peraturan Pemerintah Nomor 17 Tahun 2025 tentang {TITLE}</h1>
<dl><dt>Jenis</dt><dd>Peraturan Pemerintah</dd><dt>Ditetapkan Tanggal</dt><dd>2025-03-27</dd>
<dt>Tanggal Pengundangan</dt><dd>2025-03-28</dd><dt>Status</dt><dd>Berlaku</dd></dl>
<a href='{PDF}'>Unduh</a>""".encode()


def pdf_bytes(*texts):
    with fitz.open() as pdf:
        for text in texts:
            pdf.new_page().insert_text((50, 50), text, fontsize=10)
        return pdf.tobytes()


class InboxTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=ROOT / "data/processed")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.manifest = self.root / "manifest.jsonl"
        self.chunks = self.root / "chunks.jsonl"
        self.old = {"document_id": "OLD", "title": "Corpus sebelumnya", "status": "verified", "corpus_eligible": False}
        self.manifest.write_text(json_lines([self.old]), encoding="utf-8")
        self.chunks.write_bytes(b"")
        self.importer = InboxImporter(self.root, manifest=self.manifest, chunks=self.chunks, settle_seconds=0)
        self.data = pdf_bytes(f"PERATURAN PEMERINTAH REPUBLIK INDONESIA\nNOMOR 17 TAHUN 2025\nTENTANG\n{TITLE.upper()}", "Pasal 1\nData pribadi dilindungi.\nPasal 2\nPeraturan ini mulai berlaku pada tanggal diundangkan.")
        self.digest = hashlib.sha256(self.data).hexdigest()
        self.file = self.importer.inbox / "nama-bebas.pdf"
        self.file.write_bytes(self.data)

    def fetch(self, url):
        if url == PAGE:
            return HTML, PAGE
        if url == PDF:
            return self.data, PDF
        raise SourceError("source_unavailable", "Tidak tersedia")

    def discover(self):
        self.importer.scan()
        self.importer.scan()

    def submit(self):
        with patch.object(main, "IMPORTER", self.importer):
            result = main.set_import_source(self.digest, main.ImportSourceRequest(page_url=PAGE))
        self.assertEqual(result["status"], "queued")

    def test_new_document_through_api_then_query_with_page_citation(self):
        self.discover()
        self.assertEqual(self.importer.jobs()[0]["status"], "needs_source")
        self.submit()
        with patch("ingestion.official_source.fetch", side_effect=self.fetch):
            self.importer.scan()
        job = self.importer.jobs()[0]
        self.assertEqual(job["status"], "ready", job)
        manifest, chunks = self.importer.current()
        docs = read_manifest(manifest)
        new = next(doc for doc in docs if doc["document_id"] == "PP_17_2025")
        self.assertEqual(new["sha256"], self.digest)
        self.assertEqual(new["effective_from"], "2025-03-28")
        self.assertEqual(new["verification_evidence"][0]["url"], PAGE)
        with patch.object(main, "MANIFEST", manifest), patch.object(main, "CHUNKS", chunks), patch.object(main, "generate", return_value={"answer": "Data pribadi dilindungi.", "citation_ids": ["E1"], "abstained": False}):
            result = main.query(main.QueryRequest(question="Apa isi Pasal 1?", document_ids=["PP_17_2025"], top_k=1))
        self.assertEqual(result["citations"][0]["page_start"], 2)
        self.assertEqual(result["citations"][0]["source_url"], PAGE)
        self.assertFalse(result["abstained"])
        (self.importer.inbox / "nama-lain.pdf").write_bytes(self.data)
        self.discover()
        self.assertEqual(len(self.importer.jobs()), 1)
        self.assertEqual(len(self.importer.jobs()[0]["filenames"]), 2)
        self.assertEqual(self.importer.current(), (manifest, chunks))

    def test_verified_law_only_answers_from_its_effective_date(self):
        today = date.today()
        law = {**self.old, "corpus_eligible": True}
        with patch.object(main, "MANIFEST", self.manifest), patch.object(main, "CHUNKS", self.chunks):
            for effective, active in [(today + timedelta(days=1), False), (today, True)]:
                self.manifest.write_text(json_lines([{**law, "effective_from": effective.isoformat()}]), encoding="utf-8")
                record, = main.get_documents()
                self.assertEqual(record["not_yet_effective"], not active)
                with patch.object(main, "search", return_value=[]) as search_request:
                    main.query(main.QueryRequest(question="Apa isi pasal ini?", document_ids=["OLD"]))
                self.assertEqual(search_request.call_args.args[3], {"OLD"} if active else set())

    def test_failed_index_keeps_previous_and_restart_recovers(self):
        self.discover()
        self.submit()
        with patch("ingestion.official_source.fetch", side_effect=self.fetch), patch("ingestion.inbox.build", side_effect=RuntimeError("interrupted")):
            self.importer.scan()
        self.assertEqual(self.importer.jobs()[0]["status"], "failed")
        self.assertEqual(self.importer.current(), (self.manifest, self.chunks))
        self.submit()
        restart = InboxImporter(self.root, manifest=self.manifest, chunks=self.chunks, settle_seconds=0)
        restart.scan()
        with patch("ingestion.official_source.fetch", side_effect=self.fetch):
            restart.scan()
        self.assertEqual(restart.jobs()[0]["status"], "ready")
        self.assertEqual(self.manifest.read_text(encoding="utf-8"), json_lines([self.old]))

    def test_startup_partial_copy_change_and_invalid_file(self):
        self.file.write_bytes(b"%PDF-1.7 incomplete")
        self.discover()
        self.assertEqual(self.importer.jobs()[0]["status"], "unreadable")
        self.file.write_bytes(self.data)
        self.discover()
        self.assertIn("needs_source", {job["status"] for job in self.importer.jobs()})

    def test_unreadable_encrypted_and_scan_do_not_publish(self):
        blank = pdf_bytes("")
        self.file.write_bytes(blank)
        self.discover()
        self.assertEqual(self.importer.jobs()[0]["status"], "needs_ocr")
        self.assertEqual(self.importer.current(), (self.manifest, self.chunks))

    def test_mismatch_and_missing_dates_do_not_publish(self):
        self.discover()
        self.submit()
        with patch("ingestion.official_source.fetch", side_effect=lambda url: (HTML, PAGE) if url == PAGE else (self.data + b"different", PDF)):
            self.importer.scan()
        self.assertEqual(self.importer.jobs()[0]["status"], "mismatch")
        with patch("ingestion.official_source.fetch", side_effect=lambda url: (HTML.replace(b"2025-03-27", b"unknown"), PAGE) if url == PAGE else (self.data, PDF)), self.assertRaisesRegex(SourceError, "Tanggal"):
            verify(self.data, {"page_url": PAGE}, [])

    def test_url_input_is_allowlisted_before_network_and_client_metadata_forbidden(self):
        for url in ("http://peraturan.go.id/a", "https://127.0.0.1/x", "https://peraturan.go.id.evil.test/a", "https://user@peraturan.go.id/a", "https://peraturan.go.id:999/x", "file:///x"):
            with self.assertRaises(ValueError):
                validate_url(url)
        with self.assertRaises(ValueError):
            main.ImportSourceRequest(page_url=PAGE, status="verified")
        self.discover()
        with patch.object(main, "IMPORTER", self.importer), self.assertRaises(HTTPException):
            main.set_import_source("../bad", main.ImportSourceRequest(page_url=PAGE))
        with self.assertRaises(SourceError):
            OfficialRedirects().redirect_request(None, None, 302, "", {}, "https://127.0.0.1/private")

    def test_process_lock_excludes_second_worker_without_dense_dependency(self):
        first = ProcessLock(self.root / "lock")
        try:
            with self.assertRaises(OSError):
                ProcessLock(self.root / "lock")
        finally:
            first.close()

    def test_later_baseline_revocation_is_preserved(self):
        self.discover()
        self.submit()
        with patch("ingestion.official_source.fetch", side_effect=self.fetch):
            self.importer.scan()
        manifest, _ = self.importer.current()
        revoked = {**self.old, "status": "unverified", "corpus_eligible": False}
        self.manifest.write_text(json_lines([revoked]), encoding="utf-8")
        self.assertEqual(read_registry(manifest, self.manifest)[0], revoked)


    def test_primary_title_wins_over_references_and_summary_is_rejected(self):
        full = "SALINAN PUTUSAN NOMOR 135/PUU-XXIII/2025 Undang-Undang Nomor 27 Tahun 2022"
        self.assertEqual(identify(full)[0], "MK_135_PUU_XXIII_2025")
        for prefix in ("IKHTISAR ", "RINGKASAN ", "RANCANGAN "):
            with self.assertRaises(SourceError):
                identify(prefix + full)
        with self.assertRaises(SourceError):
            identify("PERATURAN MENTERI NOMOR 9 TAHUN 2025 tentang pelaksanaan Undang-Undang Nomor 27 Tahun 2022")

    def test_bpk_title_abbreviation_and_supplementary_dates(self):
        bpk_url = "https://peraturan.bpk.go.id/Details/1/pp-17"
        bpk = f"""<table><tr><td>Judul</td><td>Peraturan Pemerintah (PP) Nomor 17 Tahun 2025 tentang {TITLE}</td></tr>
        <tr><td>T.E.U. Badan</td><td>Indonesia</td></tr><tr><td>Status</td><td>Berlaku</td></tr>
        <tr><td>Tanggal Penetapan</td><td>27 Maret 2025</td></tr>
        <tr><td>Tanggal Pengundangan</td><td>28 Maret 2025</td></tr>
        </table><div class="row"><div class="col-lg-3 fw-bold">Tanggal Berlaku</div>
        <div class="col-lg-9"><span>30 Maret 2025</span></div></div>""".encode()
        pdf = pdf_bytes(f"PERATURAN PEMERINTAH NOMOR 17 TAHUN 2025\nTENTANG\n{TITLE.upper()}", "Pasal 1\nData pribadi dilindungi.")

        def fetch(url):
            if url == PDF:
                return pdf, PDF
            return (bpk, bpk_url) if url == bpk_url else self.fetch(url)

        with patch("ingestion.official_source.fetch", side_effect=fetch):
            doc = verify(pdf, {"page_url": PAGE, "metadata_url": bpk_url}, [])
        self.assertEqual(doc["effective_from"], "2025-03-30")
        self.assertNotIn("T.E.U.", doc["title"])

    def test_judgment_summary_with_official_bytes_is_still_rejected(self):
        data = pdf_bytes("IKHTISAR PUTUSAN NOMOR 135/PUU-XXIII/2025", "MENGADILI\nMenolak permohonan seluruhnya.")
        page = b"<h1>Putusan Nomor 135/PUU-XXIII/2025</h1><dl><dt>Status Putusan</dt><dd>Tetap</dd><dt>Tanggal-Bulan-Tahun dibacakan</dt><dd>19-01-2026</dd></dl>"
        with patch("ingestion.official_source.fetch", return_value=(page, PAGE)), self.assertRaisesRegex(SourceError, "ringkasan"):
            verify(data, {"page_url": PAGE, "pdf_url": PDF}, [])

    def test_blank_page_allowed_but_scan_only_is_not(self):
        self.assertEqual(len(pdf_pages(pdf_bytes("Teks naskah resmi yang dapat diekstrak.", ""))), 2)
        with self.assertRaises(SourceError):
            pdf_pages(pdf_bytes(""))

    def test_known_checksum_without_chunks_rebuilds_instead_of_false_ready(self):
        doc = {"document_id": "PP_17_2025", "title": TITLE, "status": "verified", "corpus_eligible": True,
               "sha256": self.digest, "source_kind": "regulation_full_text", "official_source_url": PAGE}
        self.manifest.write_text(json_lines([doc]), encoding="utf-8")
        self.chunks.unlink()
        self.discover()
        self.assertEqual(self.importer.jobs()[0]["status"], "ready")
        _, chunks = self.importer.current()
        self.assertTrue(any(chunk["document_id"] == doc["document_id"] for chunk in read_manifest(chunks)))

    def test_stable_files_are_not_reprocessed_until_source_changes(self):
        self.discover()
        with patch.object(self.importer, "process", wraps=self.importer.process) as process:
            self.importer.scan()
            self.importer.scan()
            process.assert_not_called()
            self.submit()
            with patch("ingestion.official_source.fetch", side_effect=self.fetch):
                self.importer.scan()
            self.assertEqual(process.call_count, 1)

    def test_oversize_is_actionable_and_not_rehashed_each_tick(self):
        with patch("ingestion.inbox.MAX_BYTES", 10):
            self.discover()
            self.assertEqual(self.importer.jobs()[0]["status"], "too_large")
            with patch("ingestion.inbox.hashlib.file_digest") as digest:
                self.importer.scan()
                digest.assert_not_called()

    def test_app_worker_catches_up_and_stops(self):
        self.importer.start()
        try:
            deadline = time.monotonic() + 6
            while not self.importer.jobs() and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertEqual(self.importer.jobs()[0]["status"], "needs_source")
        finally:
            self.importer.stop()
        self.assertIsNone(self.importer.thread)

    @unittest.skipUnless(find_spec("qdrant_client"), "optional dense dependency")
    def test_new_dense_generation_preserves_old_reader_and_matches_new_chunks(self):
        class Encoder:
            def get_sentence_embedding_dimension(self):
                return 2

            def encode(self, texts, **_kwargs):
                return [[1.0, 0.0] for _ in texts]

        old_data = self.data + b"archive"
        old_pdf = self.root / "old.pdf"
        old_pdf.write_bytes(old_data)
        old = {**self.old, "corpus_eligible": True, "local_path": "old.pdf", "sha256": hashlib.sha256(old_data).hexdigest(),
               "source_kind": "regulation_full_text", "official_source_url": PAGE}
        self.manifest.write_text(json_lines([old]), encoding="utf-8")
        build_corpus.build(self.manifest, self.chunks, self.root)
        encoder = Encoder()
        build_vector_index.build(self.chunks, encoder=encoder)
        self.addCleanup(vector_index.close_vector_indexes)
        self.assertTrue(vector_index.dense_index_ready(self.chunks))
        self.discover()
        self.submit()
        with patch("ingestion.official_source.fetch", side_effect=self.fetch), patch.object(search, "create_encoder", return_value=encoder):
            self.importer.scan()
        self.assertEqual(self.importer.jobs()[0]["status"], "ready")
        _, chunks = self.importer.current()
        self.assertTrue(vector_index.dense_index_ready(chunks))
        self.assertTrue(vector_index.dense_index_ready(self.chunks))
        with patch.object(search, "_load_encoder", return_value=encoder):
            hit = search.search("Pasal 1", chunks, document_ids={"PP_17_2025"}, retrieval_mode="dense")[0]
        self.assertEqual(hit["document_id"], "PP_17_2025")
        self.assertEqual(hit["page_start"], 2)


if __name__ == "__main__":
    unittest.main()
