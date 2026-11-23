import io
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from app.generation import (
    OLLAMA_MODEL,
    OLLAMA_NUM_CTX,
    GeneratorUnavailable,
    InvalidModelResponse,
    generate,
)
from app.main import QueryRequest, query
from app.reranking import rerank
from app.search import search
from evaluation.metrics import (
    abstention_metrics,
    answer_correctness_score,
    citation_accuracy,
    groundedness_score,
    timed_call,
)
from evaluation.run_retrieval import _metrics, recall_at_k, reciprocal_rank_at_k
from ingestion.build_corpus import build
from ingestion.legal_text import article_metadata, parse_pages


class LegalTextTests(unittest.TestCase):
    def test_parser_keeps_article_and_actual_page_range(self):
        chunks = parse_pages("UU_27_2022", ["BAB I\nKETENTUAN UMUM\nPasal 1\n(1) bunyi awal", "lanjutan\nPasal 2\nbunyi kedua"], "https://official.test")
        self.assertEqual([(c["article"], c["page_start"], c["page_end"]) for c in chunks], [("Pasal 1", 1, 2), ("Pasal 2", 2, 2)])
        self.assertEqual(chunks[0]["bab"], "I")

    def test_parser_repairs_visually_verified_article_one_glyph(self):
        chunks = parse_pages("UU_27_2022", ["BAB I\nPasal I\nDalam Undang-Undang ini"], "https://official.test")
        self.assertEqual(chunks[0]["article"], "Pasal 1")
        self.assertEqual(chunks[0]["page_start"], 1)
        corrected = parse_pages("UU", ["Pasal 7O\nPasal T2\nPasal 4O\nPasa722\nPasal2T"], "https://official.test")
        self.assertEqual([c["article"] for c in corrected], ["Pasal 70", "Pasal 72", "Pasal 40", "Pasal 22", "Pasal 27"])
        self.assertTrue(corrected[0]["text"].startswith("Pasal 70"))
        self.assertTrue(corrected[3]["text"].startswith("Pasal 22"))
        self.assertTrue(corrected[4]["text"].startswith("Pasal 27"))

    def test_body_and_explanation_get_distinct_chunk_ids(self):
        chunks = parse_pages("UU", ["Pasal 1\nisi", "PENJEI,ASAN\nPasal 1\npenjelasan"], "https://official.test")
        self.assertEqual([c["chunk_id"] for c in chunks], ["UU:article:1", "UU:explanation:article:1"])

    def test_judgment_citations_use_pages_not_referenced_articles(self):
        chunks = parse_pages("MK", ["Putusan menyebut Pasal 53 ayat (1).", "Amar: menolak."], "https://official.test", "judgment_full_text")
        self.assertEqual([c["chunk_id"] for c in chunks], ["MK:page:1", "MK:page:2"])
        self.assertTrue(all(c["article"] is None and c["page_start"] == c["page_end"] for c in chunks))

    def test_metadata_does_not_guess(self):
        self.assertEqual(article_metadata("Pasal 12\n(2) teks"), ("12", "ayat (2)"))
        self.assertEqual(article_metadata("teks saja"), (None, None))


class SearchTests(unittest.TestCase):
    def test_answer_evaluation_metrics(self):
        self.assertEqual(
            citation_accuracy(["c1", "c3"], ["c1", "c2"], {"c1", "c4"}),
            0.5,
        )
        self.assertEqual(groundedness_score([True, True, False]), 2 / 3)
        self.assertEqual(answer_correctness_score([True, False, True]), 2 / 3)
        metrics = abstention_metrics([False, True, True], [False, True, False])
        self.assertAlmostEqual(metrics.accuracy, 2 / 3)
        self.assertAlmostEqual(metrics.precision, 1.0)
        self.assertAlmostEqual(metrics.recall, 0.5)

    def test_answer_evaluation_rejects_mismatched_abstention_labels(self):
        with self.assertRaises(ValueError):
            abstention_metrics([True], [])

    def test_timed_call_returns_result_and_elapsed_seconds(self):
        result, elapsed = timed_call(lambda: "ok")
        self.assertEqual(result, "ok")
        self.assertGreaterEqual(elapsed, 0.0)
    def test_retrieval_metrics_measure_labeled_hits_and_first_relevant_rank(self):
        relevant = {"c2", "c4"}
        ranked = ["c1", "c2", "c3", "c4"]
        self.assertEqual(recall_at_k(relevant, ranked, 3), 0.5)
        self.assertEqual(reciprocal_rank_at_k(relevant, ranked, 10), 0.5)
        self.assertEqual(reciprocal_rank_at_k({"missing"}, ranked, 10), 0.0)
        self.assertEqual(_metrics([{"bm25": {"recall_at_5": 0.5, "mrr_at_10": 0.5}},
                                  {"bm25": {"recall_at_5": 1.0, "mrr_at_10": 1.0}}], "bm25"),
                         {"recall_at_5": 0.75, "mrr_at_10": 0.75})

    def test_unanswerable_metrics_handling(self):
        # Empty relevant set for unanswerable questions should not cause ZeroDivisionError
        self.assertEqual(recall_at_k(set(), ["c1", "c2"], 5), 0.0)
        self.assertEqual(reciprocal_rank_at_k(set(), ["c1", "c2"], 10), 0.0)
        rows = [
            {"is_answerable": True, "bm25": {"recall_at_5": 1.0, "mrr_at_10": 1.0}},
            {"is_answerable": False, "bm25": {"recall_at_5": 0.0, "mrr_at_10": 0.0}},
        ]
        # _metrics filters out is_answerable=False so that unanswerable queries don't skew recall/mrr
        self.assertEqual(_metrics(rows, "bm25"), {"recall_at_5": 1.0, "mrr_at_10": 1.0})

    def test_weighted_rrf_can_favor_dense_ranking(self):
        from app.search import _rrf

        dense = [{"chunk_id": "dense", "text": "semantic"}, {"chunk_id": "lexical", "text": "exact"}]
        lexical = [{"chunk_id": "lexical", "text": "exact"}, {"chunk_id": "dense", "text": "semantic"}]
        equal = _rrf([dense, lexical], 2, k=1, weights=(1.0, 1.0))
        favored = _rrf([dense, lexical], 2, k=1, weights=(2.0, 1.0))
        self.assertEqual(equal[0]["score"], equal[1]["score"])
        self.assertEqual(favored[0]["chunk_id"], "dense")

    def test_reranker_sorts_candidates_by_model_score_and_limits_output(self):
        import numpy as np

        import app.reranking as reranking_module

        class FakeTokenizer:
            def __call__(self, _questions, _passages, **_kwargs):
                return {"input_ids": np.array([[1], [2]], dtype=np.int64)}

        class FakeSession:
            def run(self, _outputs, inputs):
                self.inputs = inputs
                return [np.array([[0.2], [0.9]], dtype=np.float32)]

        session = FakeSession()
        candidates = [{"chunk_id": "first", "text": "passage one"}, {"chunk_id": "second", "text": "passage two"}]
        with patch.object(reranking_module, "_load_runtime", return_value=(FakeTokenizer(), session, {"input_ids"})):
            ranked = rerank("question", candidates, 1)
        self.assertEqual(ranked[0]["chunk_id"], "second")
        self.assertAlmostEqual(ranked[0]["rerank_score"], 0.9)
        self.assertEqual(session.inputs["input_ids"].shape[0], 2)

    def test_api_hybrid_rerank_uses_twenty_candidates_then_limits_sources(self):
        import app.main as main_module

        candidates = [
            {"chunk_id": "UU_27_2022:article:2", "document_id": "UU_27_2022", "text": "candidate"},
            {"chunk_id": "UU_27_2022:article:2", "document_id": "UU_27_2022", "text": "candidate"},
        ]
        with patch.object(main_module, "search", return_value=candidates) as search_mock, \
             patch.object(main_module, "CHUNKS") as chunks, \
             patch.object(main_module, "rerank", return_value=candidates[:1]) as rerank_mock, \
             patch.object(main_module, "generate", return_value={"answer": "jawaban", "citation_ids": ["E1"], "abstained": False}):
            chunks.read_bytes.return_value = b""
            result = query(QueryRequest(question="Apa isi ketentuan?", retrieval_mode="hybrid_rerank", top_k=1))
        self.assertEqual(search_mock.call_args.args[2], 20)
        self.assertEqual(search_mock.call_args.kwargs["retrieval_mode"], "hybrid")
        self.assertEqual(rerank_mock.call_args.args[2], 1)
        self.assertEqual(result["retrieval_mode"], "hybrid_rerank")

    def test_search_returns_exact_evidence_and_validates_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "chunks.jsonl"
            path.write_text(json.dumps({"chunk_id":"UU:article:1","document_id":"UU","text":"Pasal 1 pelindungan data pribadi"}) + "\n", encoding="utf-8")
            self.assertEqual(search("data pribadi", path)[0]["chunk_id"], "UU:article:1")
            path.write_text("\n".join(json.dumps(x) for x in [
                {"chunk_id":"UU:article:2","document_id":"UU","article":"Pasal 2","section_type":"batang_tubuh","text":"Pasal 2 data tentang aturan"},
                {"chunk_id":"MK:page:2","document_id":"MK","article":None,"text":"data Pasal 2 dan aturan"},
            ]), encoding="utf-8")
            self.assertEqual(search("Pasal 2", path)[0]["chunk_id"], "UU:article:2")
            self.assertEqual(search("data pribadi", path, document_ids={"other"}), [])
            with self.assertRaises(ValueError):
                search("  ", path)

    def test_ingestion_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "manifest.jsonl"
            manifest.write_text(json.dumps({"document_id":"bad","status":"verified","corpus_eligible":True,"local_path":"../outside.pdf","sha256":"x"}) + "\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                build(manifest, root / "chunks.jsonl", root)


class GenerationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        chunks = Path(directory.name) / "chunks.jsonl"
        chunks.write_text(json.dumps({"chunk_id": "UU_27_2022:article:2", "document_id": "UU_27_2022", "text": "Pasal 2\\nTeks fixture untuk uji pipeline."}) + "\n", encoding="utf-8")
        patcher = patch("app.main.CHUNKS", chunks)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_generator_accepts_only_retrieved_citations(self):
        answer = json.dumps({"answer":"evidence","citation_ids":["E1"],"abstained":False})
        response = io.BytesIO(json.dumps({"message":{"content":answer}}).encode())
        with patch("app.generation.urlopen", return_value=response) as opener:
            self.assertEqual(generate("apa?", [{"text":"evidence"}])["citation_ids"], ["E1"])
        payload = json.loads(opener.call_args.args[0].data)
        self.assertEqual(payload["model"], OLLAMA_MODEL)
        self.assertEqual(payload["options"]["num_ctx"], OLLAMA_NUM_CTX)

        invalid = json.dumps({"answer":"evidence","citation_ids":["E2"],"abstained":False})
        response = io.BytesIO(json.dumps({"message":{"content":invalid}}).encode())
        with patch("app.generation.urlopen", return_value=response), self.assertRaises(InvalidModelResponse):
            generate("apa?", [{"text":"evidence"}])

    def test_generator_serializes_ollama_requests(self):
        active = 0
        max_active = 0
        guard = threading.Lock()
        answer = json.dumps({"answer":"evidence","citation_ids":["E1"],"abstained":False})

        def fake_urlopen(*_args, **_kwargs):
            nonlocal active, max_active
            with guard:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.02)
            with guard:
                active -= 1
            return io.BytesIO(json.dumps({"message":{"content":answer}}).encode())

        with patch("app.generation.urlopen", side_effect=fake_urlopen):
            threads = [threading.Thread(target=generate, args=("apa?", [{"text":"evidence"}])) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        self.assertEqual(max_active, 1)

    def test_api_abstains_when_filtered_corpus_has_no_evidence(self):
        result = query(QueryRequest(question="Pertanyaan di luar dokumen", document_ids=["PP_33_2026"]))
        self.assertTrue(result["abstained"])
        self.assertEqual(result["reason"], "no_evidence")

    def test_api_rejects_whitespace_question(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as error:
            query(QueryRequest(question="   "))
        self.assertEqual(error.exception.status_code, 422)

    def test_api_returns_retrieved_evidence_when_ollama_is_missing(self):
        with patch("app.main.generate", side_effect=GeneratorUnavailable("offline")):
            result = query(QueryRequest(question="Apa isi Pasal 2?", top_k=1))
        self.assertTrue(result["abstained"])
        self.assertEqual(result["reason"], "generator_unavailable")
        self.assertEqual(len(result["citations"]), 1)

    def test_api_citation_quote_comes_from_retrieved_chunk(self):
        model_result = {"answer":"Ringkasan berbasis sumber.","citation_ids":["E1"],"abstained":False}
        with patch("app.main.generate", return_value=model_result):
            result = query(QueryRequest(question="Apa isi Pasal 2?", top_k=1))
        self.assertFalse(result["abstained"])
        citation = result["citations"][0]
        self.assertEqual(citation["chunk_id"], "UU_27_2022:article:2")
        self.assertTrue(citation["quote"].startswith("Pasal 2"))
        self.assertEqual(citation["document_title"], "Undang-Undang Nomor 27 Tahun 2022 tentang Pelindungan Data Pribadi")


if __name__ == "__main__":
    unittest.main()
