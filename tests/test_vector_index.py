"""Exercise persistent Qdrant Local without downloading models."""

import io
import json
import os
import tempfile
import unittest
from importlib.util import find_spec
from pathlib import Path
from unittest.mock import patch

from app import main, search, vector_index
from ingestion import build_vector_index


class FakeEncoder:
    def __init__(self):
        self.calls = []

    def get_sentence_embedding_dimension(self):
        return 2

    def encode(self, texts, **kwargs):
        self.calls.append((texts, kwargs))
        scores = {"UU": [0.8, 0.6], "amar": [0.6, 0.8]}
        return [scores.get(next((key for key in scores if key in text), ""), [1.0, 0.0])
                if text.startswith("passage: ") else [1.0, 0.0] for text in texts]


@unittest.skipUnless(find_spec("qdrant_client"), "install the dense extra to test persistent Qdrant Local")
class VectorIndexTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.chunks_path = Path(temporary.name) / "chunks.jsonl"
        self.manifest_path = Path(temporary.name) / "manifest.jsonl"
        self.enterContext(patch.dict(os.environ))
        os.environ.pop("REGULARAG_QDRANT_PATH", None)
        self.directory = vector_index.index_directory(self.chunks_path)
        self.addCleanup(vector_index.close_vector_indexes)
        self.encoder = FakeEncoder()
        self.loader = self.enterContext(patch.object(search, "_load_encoder", return_value=self.encoder))
        self.law = self.chunk(
            "law", "UU", "UU Pasal 53\nData pribadi dan tugas petugas.", article="Pasal 53",
            source_kind="regulation", section_type="batang_tubuh", page_start=19, page_end=20,
        )
        self.argument = self.chunk(
            "argument", "MK", "Pemohon berargumen tentang data pribadi.",
            source_kind="judgment_full_text", section_type="duduk_perkara",
        )
        self.holding = self.chunk(
            "holding", "MK", "amar: Menyatakan syarat secara alternatif.",
            source_kind="judgment_full_text", section_type="amar_putusan", page_start=45, page_end=45,
        )
        self.other = self.chunk("other", "OTHER", "Pertanyaan umum tentang data.")
        self.write_chunks(self.law, self.argument, self.holding, self.other)

    @staticmethod
    def chunk(chunk_id, document_id, text, **metadata):
        return {"chunk_id": chunk_id, "document_id": document_id, "text": text,
                "source_url": f"https://official.example/{document_id}", **metadata}

    def write_chunks(self, *docs):
        self.chunks_path.write_text("\n".join(map(json.dumps, docs)), encoding="utf-8")

    def manifest(self, *, court_active=True):
        law = {"document_id": "UU", "title": "Undang-Undang fixture", "status": "verified",
               "corpus_eligible": True, "legal_status_note": "Pasal 53", "related_document_ids": ["MK"]}
        court = {"document_id": "MK", "title": "Putusan fixture", "status": "verified",
                 "corpus_eligible": court_active}
        unrelated = {"document_id": "OTHER", "title": "Dokumen dicabut", "status": "unverified",
                     "corpus_eligible": False}
        self.manifest_path.write_text("\n".join(map(json.dumps, (law, court, unrelated))), encoding="utf-8")

    def dense(self, *, top_k=1, document_ids=None, normative_only=False):
        return search.search("Pasal 53 tentang DPO", self.chunks_path, top_k=top_k,
                             document_ids=document_ids, retrieval_mode="dense", normative_only=normative_only)

    def points(self, snapshot):
        with vector_index.local_client(self.directory / snapshot) as client:
            records, offset = client.scroll(vector_index.COLLECTION, limit=10)
        self.assertIsNone(offset)
        return {record.payload["chunk_id"]: record.id for record in records}

    def test_reopen_encodes_only_query_and_filters_before_top_k(self):
        build_vector_index.build(self.chunks_path)
        self.assertEqual(len(self.encoder.calls), 1)
        texts, settings = self.encoder.calls[0]
        self.assertTrue(all(text.startswith("passage: ") for text in texts))
        self.assertTrue(settings["normalize_embeddings"])
        self.assertEqual(settings["device"], "cpu")
        self.encoder.calls.clear()
        self.loader.reset_mock()

        self.assertTrue(vector_index.dense_index_ready(self.chunks_path))
        self.loader.assert_not_called()
        self.assertEqual(self.dense()[0]["chunk_id"], "argument")
        self.assertEqual(self.dense(document_ids={"UU", "MK"}, normative_only=True)[0]["chunk_id"], "law")
        self.assertEqual(self.dense(document_ids={"MK"}, normative_only=True)[0]["chunk_id"], "holding")
        self.assertEqual(self.dense(document_ids={"MK"})[0]["chunk_id"], "argument")
        self.assertEqual(self.dense(document_ids=set()), [])
        self.assertEqual([len(texts) for texts, _ in self.encoder.calls], [1, 1, 1, 1])
        self.assertTrue(self.encoder.calls[0][0][0].startswith("query: Pasal 53 tentang dpo pejabat"))
        self.assertAlmostEqual(self.dense(document_ids={"UU"})[0]["score"], 0.8, places=6)
        with self.assertRaisesRegex(vector_index.DenseSearchUnavailable, "Tutup UI"):
            build_vector_index.build(self.chunks_path)

    def test_build_is_idempotent_and_interrupted_rebuild_keeps_old_snapshot(self):
        original = self.chunks_path.read_bytes()
        first = build_vector_index.build(self.chunks_path)
        stable_ids = self.points(first)
        self.assertEqual(len(set(stable_ids.values())), 4)
        self.encoder.calls.clear()
        self.assertEqual(build_vector_index.build(self.chunks_path), first)
        self.assertEqual(self.encoder.calls, [])

        revised_law = dict(self.law, text="UU Pasal 53\nNaskah yang diperbarui.")
        self.write_chunks(revised_law, self.holding, self.other)
        revised = self.chunks_path.read_bytes()
        with patch.object(build_vector_index, "_activate", side_effect=OSError("interrupted")), self.assertRaises(OSError):
            build_vector_index.build(self.chunks_path)
        self.assertEqual(vector_index.active_snapshot(self.directory), first)
        with self.assertRaisesRegex(vector_index.DenseSearchUnavailable, "tidak cocok"):
            self.dense()

        self.chunks_path.write_bytes(original)
        self.assertEqual(self.dense()[0]["chunk_id"], "argument")
        vector_index.close_vector_indexes()
        self.chunks_path.write_bytes(revised)
        second = build_vector_index.build(self.chunks_path)
        self.assertNotEqual(second, first)
        self.assertEqual(self.points(second), {key: stable_ids[key] for key in ("law", "holding", "other")})
        self.assertEqual(self.dense(document_ids={"UU"})[0]["text"], revised_law["text"])
        for key, value in (("EMBEDDING_MODEL", "another/e5"), ("EMBEDDING_REVISION", "b" * 40)):
            with self.subTest(key=key), patch.object(vector_index, key, value), \
                    self.assertRaisesRegex(vector_index.DenseSearchUnavailable, "tidak cocok"):
                self.dense()

    def test_duplicate_ids_never_publish(self):
        self.write_chunks(self.law, self.law)
        with self.assertRaisesRegex(ValueError, "duplikat"):
            build_vector_index.build(self.chunks_path)
        self.assertFalse((self.directory / "active.txt").exists())
        self.loader.assert_not_called()

    def test_corpus_change_during_build_does_not_publish(self):
        encode = self.encoder.encode

        def change_corpus(texts, **kwargs):
            self.write_chunks(self.other)
            return encode(texts, **kwargs)

        with patch.object(self.encoder, "encode", side_effect=change_corpus), \
                self.assertRaisesRegex(ValueError, "Corpus berubah"):
            build_vector_index.build(self.chunks_path)
        self.assertFalse((self.directory / "active.txt").exists())

    def test_hybrid_keeps_lexical_and_dense_candidates(self):
        lexical = self.chunk("exact", "UU", "Kewajiban pengendali data. UU")
        semantic = self.chunk("semantic", "UU", "Makna tanggung jawab entitas.")
        self.write_chunks(lexical, semantic)
        build_vector_index.build(self.chunks_path)
        modes = {}
        for mode in ("bm25", "dense", "hybrid"):
            modes[mode] = search.search("kewajiban data", self.chunks_path, retrieval_mode=mode)
        self.assertEqual(modes["bm25"][0]["chunk_id"], "exact")
        self.assertEqual(modes["dense"][0]["chunk_id"], "semantic")
        self.assertEqual({hit["chunk_id"] for hit in modes["hybrid"]}, {"exact", "semantic"})

    def test_http_health_distinguishes_unavailable_index_from_no_evidence(self):
        from fastapi.testclient import TestClient

        self.manifest()
        with patch.object(main, "CHUNKS", self.chunks_path), patch.object(main, "MANIFEST", self.manifest_path), \
                patch.object(main, "urlopen", side_effect=OSError), TestClient(main.app) as client:
            health = client.get("/health").json()
            self.assertTrue(health["index_ready"])
            self.assertFalse(health["dense_index_ready"])
            payload = {"question": "Apa isi Pasal 53?", "retrieval_mode": "dense"}
            response = client.post("/query", json=payload)
            self.assertEqual(response.status_code, 503)
            self.assertIn("ingestion.build_vector_index", response.json()["detail"])
            self.directory.mkdir()
            (self.directory / "active.txt").write_text("../rusak", encoding="ascii")
            self.assertFalse(client.get("/health").json()["dense_index_ready"])
            corrupt = client.post("/query", json=payload)
            self.assertEqual(corrupt.status_code, 503)
            self.assertIn("gagal dibaca", corrupt.json()["detail"])
            response = client.post("/query", json=dict(payload, document_ids=[]))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["reason"], "no_evidence")
            self.loader.assert_not_called()

    def test_http_reranking_related_holding_citation_and_live_revocation(self):
        from fastapi.testclient import TestClient

        build_vector_index.build(self.chunks_path)
        self.manifest()
        selected = {"answer": "S1", "citation_ids": ["E1"], "abstained": False}
        ollama = json.dumps({"message": {"content": json.dumps(selected)}}).encode()
        original = self.chunks_path.read_bytes()

        def rerank_while_corpus_changes(_, hits, k):
            self.write_chunks(self.law, self.other)
            return hits[:k]

        with patch.object(main, "CHUNKS", self.chunks_path), patch.object(main, "MANIFEST", self.manifest_path), \
                patch("app.generation.urlopen", return_value=io.BytesIO(ollama)) as model, \
                patch.object(main, "rerank", side_effect=rerank_while_corpus_changes) as rerank, \
                TestClient(main.app) as client:
            payload = {"question": "Apa isi Pasal 53 tentang data pribadi?", "retrieval_mode": "hybrid_rerank", "top_k": 1}
            response = client.post("/query", json=payload)
            self.assertEqual(response.status_code, 200)
            result = response.json()
            self.assertFalse(result["abstained"])
            self.assertEqual(result["answer"], self.holding["text"])
            citation, = result["citations"]
            for key in ("chunk_id", "document_id", "page_start", "page_end", "source_url"):
                self.assertEqual(citation[key], self.holding[key])
            self.assertEqual(citation["quote"], self.holding["text"])
            self.assertEqual(citation["document_title"], "Putusan fixture")
            self.assertEqual({item["chunk_id"] for item in rerank.call_args.args[1]}, {"law", "holding"})

            model.reset_mock()
            rerank.side_effect = lambda _, hits, k: hits[:k]
            self.chunks_path.write_bytes(original)
            self.manifest(court_active=False)
            for question in (payload["question"], "Siapa nama ketua lembaga PDP?"):
                response = client.post("/query", json=dict(payload, question=question))
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.json()["abstained"])
                self.assertEqual(response.json()["citations"], [])
            self.assertEqual([item["chunk_id"] for item in rerank.call_args.args[1]], ["law"])
            model.assert_not_called()
