import json
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.search import search
from app.generation import GeneratorUnavailable, InvalidModelResponse, generate
from app.main import QueryRequest, query
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
        corrected = parse_pages("UU", ["Pasal 7O\nPasal T2\nPasal 4O"], "https://official.test")
        self.assertEqual([c["article"] for c in corrected], ["Pasal 70", "Pasal 72", "Pasal 40"])
        self.assertTrue(corrected[0]["text"].startswith("Pasal 70"))

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
    def test_generator_accepts_only_retrieved_citations(self):
        answer = json.dumps({"answer":"Berdasarkan sumber.","citation_ids":["E1"],"abstained":False})
        response = io.BytesIO(json.dumps({"message":{"content":answer}}).encode())
        with patch("app.generation.urlopen", return_value=response):
            self.assertEqual(generate("apa?", [{"text":"evidence"}])["citation_ids"], ["E1"])

        invalid = json.dumps({"answer":"Berdasarkan sumber.","citation_ids":["E2"],"abstained":False})
        response = io.BytesIO(json.dumps({"message":{"content":invalid}}).encode())
        with patch("app.generation.urlopen", return_value=response), self.assertRaises(InvalidModelResponse):
            generate("apa?", [{"text":"evidence"}])

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
