import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.evidence import select_evidence
from app.generation import InvalidModelResponse, generate
from ingestion import build_corpus
from ingestion.legal_text import parse_pages

PAGE_19_LAYER = (
    "Pasal 46\n(1) Dalam hal terjadi kegagalan Pelindungan Data Pribadi,\n"
    "Pengendali Data Pribadi wajib\npemberitahuan secara tertulis paling lambat 3 x 24\n"
    "(tiga kali dua puluh empat) jam kepada:\na. Subjek Data Pribadi; dan\nb. lembaga.\n"
    "(2) Pemberitahuan tertulis sebagaimana dimaksud pada\nayat (1) minimal memuat:\n"
    "Data Pribadi yang terungkap;\nkapan dan bagaimana Data Pribadi terungkap; dan\n"
    "upaya penanganan dan pemulihan atas\nterungkapnya Data Pribadi oleh Pengendali Data\nPribadi.\n"
    "Pasal 48\n(2) Pemberitahuan . . .\na.\nb.\nc.\nSK No 155220A"
)
PRINTED_46_2_LIST = (
    "a. Data Pribadi yang terungkap;\n"
    "b. kapan dan bagaimana Data Pribadi terungkap; dan\n"
    "c. upaya penanganan dan pemulihan atas\nterungkapnya Data Pribadi oleh Pengendali Data\nPribadi."
)


class RegressionTests(unittest.TestCase):
    def test_article_46_reading_is_scoped_to_the_verified_pdf_and_page(self):
        digest = "ed952dea04b87d14ecf037f9f324a65d50b396ddd34fc28ddf9ff014391971f6"
        result = build_corpus.correct_text_layer(PAGE_19_LAYER, digest, 19)
        self.assertIn("wajib menyampaikan\npemberitahuan secara tertulis", result)
        self.assertIn("a. Subjek Data Pribadi; dan\nb. lembaga.", result)
        self.assertIn("ayat (1) minimal memuat:\n" + PRINTED_46_2_LIST, result)
        self.assertTrue(result.endswith("(2) Pemberitahuan . . .\nSK No 155220A"))
        self.assertEqual(build_corpus.correct_text_layer(result, digest, 19), result)
        self.assertEqual(build_corpus.correct_text_layer(PAGE_19_LAYER, "different-pdf", 19), PAGE_19_LAYER)
        self.assertEqual(build_corpus.correct_text_layer(PAGE_19_LAYER, digest, 18), PAGE_19_LAYER)
        with self.assertRaises(ValueError):
            build_corpus.correct_text_layer(PAGE_19_LAYER + "\n" + PAGE_19_LAYER, digest, 19)

    def test_article_46_rejects_unrecognized_label_layout(self):
        for changed in (PAGE_19_LAYER.replace("\nb.\nc.\n", "\nb.\nb.\nc.\n"),
                        PAGE_19_LAYER.replace("kapan dan bagaimana", "bagaimana")):
            with self.subTest(layer=changed), self.assertRaises(ValueError):
                build_corpus.correct_text_layer(changed, build_corpus.PDP_PDF_SHA256, 19)

    def test_ingestion_puts_the_checked_reading_in_the_citable_chunk(self):
        import pymupdf

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with pymupdf.open() as pdf:
                page = pdf.new_page()
                body, footer = PAGE_19_LAYER.split("\na.\nb.\nc.\n")
                page.insert_text((60, 40), body, fontsize=10, lineheight=1.5)
                first_item_y = 40 + 15 * body.splitlines().index("Data Pribadi yang terungkap;")
                page.insert_text((45, first_item_y), "a.\nb.\nc.", fontsize=10, lineheight=1.5)
                page.insert_text((40, 420), footer, fontsize=10)
                self.assertEqual(page.get_text("text").strip(), PAGE_19_LAYER)
                pdf.save(root / "fixture.pdf")
            digest = hashlib.sha256((root / "fixture.pdf").read_bytes()).hexdigest()
            doc = {"document_id": "fixture", "sha256": digest, "local_path": "fixture.pdf", "status": "verified",
                   "corpus_eligible": True, "official_source_url": "https://official.test", "source_kind": "regulation_full_text"}
            manifest, output = root / "manifest.jsonl", root / "chunks.jsonl"
            manifest.write_text(json.dumps(doc), encoding="utf-8")
            readings = build_corpus.TEXT_LAYER_READINGS[build_corpus.PDP_PDF_SHA256, 19]
            with patch.dict(build_corpus.TEXT_LAYER_READINGS, {(digest, 1): readings}):
                self.assertEqual(build_corpus.build(manifest, output, root), 2)
            chunk, following = map(json.loads, output.read_bytes().splitlines())
            self.assertEqual((chunk["chunk_id"], chunk["page_start"], chunk["page_end"]), ("fixture:article:46", 1, 1))
            self.assertIn("wajib menyampaikan\npemberitahuan secara tertulis", chunk["text"])
            self.assertIn(PRINTED_46_2_LIST, chunk["text"])
            self.assertEqual(following["text"], "Pasal 48\n(2) Pemberitahuan . . .\nSK No 155220A")

    def test_disclosure_penalty_offers_only_the_matching_source_paragraph(self):
        question = "Berapa lama ancaman penjara untuk pengungkapan data pribadi milik orang lain?"
        paragraph = ("(2) Setiap Orang yang dengan sengaja dan melawan hukum\n"
                     "mengungkapkan Data Pribadi yang bukan miliknya\n"
                     "sebagaimana dimaksud dalam Pasal 65 ayat (2) dipidana\n"
                     "dengan pidana penjara paling lama 4 (empat) tahun\n"
                     "dan/atau pidana denda paling banyak\nRp4.000.000.000,00 (empat miliar rupiah).")
        layer = paragraph.replace("mengungkapkan", "mengunglapkan")
        self.assertEqual(build_corpus.correct_text_layer(layer, build_corpus.PDP_PDF_SHA256, 30), paragraph)
        hits = [
            {"text": "Orang yang memalsukan Data Pribadi dipidana dengan pidana penjara enam tahun."},
            {"text": "Dilarang mengungkapkan Data Pribadi yang bukan miliknya."},
            {"text": "Pasal 67\n(1) Mengumpulkan Data Pribadi dipidana lima tahun.\n" + paragraph
                     + "\n(3) Menggunakan Data Pribadi dipidana lima tahun."},
        ]
        self.assertEqual(select_evidence(question, hits, limit=1), hits[2:])
        self.assertEqual(select_evidence(question, hits[:2]), [])
        self.assertEqual(select_evidence("Apa perbedaan pidana pemalsuan dan pengungkapan data?", hits), hits)
        with patch("app.generation.urlopen") as model:
            self.assertTrue(generate(question, hits[:2])["abstained"])
            model.assert_not_called()
        raw = {"message": {"content": json.dumps({"answer": "S1", "citation_ids": ["E3"], "abstained": False})}}
        with patch("app.generation.urlopen", return_value=io.BytesIO(json.dumps(raw).encode())) as model:
            result = generate(question, hits)
        options = json.loads(json.loads(model.call_args.args[0].data)["messages"][1]["content"])["quote_options"]
        self.assertEqual([option["text"] for option in options], [paragraph])
        self.assertEqual((result["answer"], result["citation_ids"]), (paragraph, ["E3"]))

    def test_access_to_personal_information_accepts_possessives(self):
        hits = [{"text": "Subjek Data Pribadi berhak mendapatkan akses dan memperoleh salinan Data Pribadi."}]
        for noun in ("informasi pribadinya", "informasi pribadiku", "informasi pribadimu"):
            with self.subTest(noun=noun):
                self.assertEqual(select_evidence(f"Bagaimana memperoleh salinan {noun}?", hits), hits)
        self.assertEqual(select_evidence("Bagaimana memperoleh salinan tiket penerbangannya?", hits), [])
        self.assertEqual(select_evidence("Bisakah aku melihat dan mendapat salinan informasi pribadiku?",
                                         [{"text": "Pengendali memberikan akses kepada Subjek Data Pribadi."}]), [])

    def test_explanation_does_not_leak_into_last_article(self):
        chunks = parse_pages("UU", ["Pasal 76\nBerlaku.\nPENJEI,ASAN\nUMUM\nPengantar\nPasal 1\nPenjelasan"], "https://official.test")
        self.assertEqual(chunks[0]["text"], "Pasal 76\nBerlaku.")
        self.assertEqual(chunks[1]["section_type"], "penjelasan")

    def test_multiple_paragraphs_have_no_single_paragraph_label(self):
        chunk = parse_pages("UU", ["Pasal 1\n(1) pertama\n(2) kedua"], "https://official.test")[0]
        self.assertIsNone(chunk["paragraph"])

    def test_judgment_quote_is_original_text(self):
        chunk = parse_pages("MK", ["MENGADILI\nMenolak permohonan"], "https://official.test", "judgment_full_text")[0]
        self.assertEqual(chunk["text"], "MENGADILI\nMenolak permohonan")
        self.assertEqual(chunk["section_type"], "amar_putusan")

    def test_generator_bounds_large_first_chunk_without_changing_source(self):
        response = io.BytesIO(json.dumps({"message": {"content": json.dumps({"answer":"x", "citation_ids":["E1"], "abstained":False})}}).encode())
        source = "a" * 20000
        with patch("app.generation.urlopen", return_value=response) as call:
            generate("apa?", [{"text":source}])
        payload = json.loads(call.call_args.args[0].data)
        evidence = json.loads(payload["messages"][1]["content"])["quote_options"][0]
        self.assertTrue(source.startswith(evidence["text"]))
        self.assertLess(len(evidence["text"]), 3000)

    def test_generator_rejects_reference_to_omitted_evidence(self):
        response = io.BytesIO(json.dumps({"message": {"content": json.dumps({"answer":"x", "citation_ids":["E2"], "abstained":False})}}).encode())
        with patch("app.generation.urlopen", return_value=response), self.assertRaises(InvalidModelResponse):
            generate("apa?", [{"text":"short"}, {"text":"x"*20000}])

    def test_query_never_searches_revoked_manifest_documents(self):
        from app import main
        with patch.object(main, "documents", return_value=[{"document_id":"revoked", "status":"unverified", "corpus_eligible":False}]), \
                patch.object(main, "CHUNKS") as chunks, patch.object(main, "search", return_value=[]) as search:
            chunks.read_bytes.return_value = b""
            result = main.query(main.QueryRequest(question="apa?"))
        self.assertTrue(result["abstained"])
        self.assertEqual(search.call_args.args[3], set())


    def test_unreviewed_answers_do_not_get_correctness_scores(self):
        from evaluation.review_report import summarize
        result = summarize([{"is_answerable":False, "result":{"abstained":True}, "review_status":"pending_human_review"}])
        self.assertIsNone(result["answer_correctness"])
        self.assertEqual(result["pending"], 1)

    def test_definition_requires_explicit_definition_in_evidence(self):
        with patch("app.generation.urlopen") as call:
            result = generate("Apa yang dimaksud dengan Data Pribadi?", [{"text":"Contoh data pribadi berupa data paspor."}])
        self.assertTrue(result["abstained"])
        call.assert_not_called()

    def test_missing_numbered_regulation_abstains(self):
        with patch("app.generation.urlopen") as call:
            result = generate("Apa isi PP Nomor 33 Tahun 2026?", [{"text":"Data pribadi", "title":"Undang-Undang Nomor 27 Tahun 2022", "number":"27", "year":2022}])
        self.assertTrue(result["abstained"])
        call.assert_not_called()

    def test_ai_review_is_separate_from_human_review(self):
        from evaluation.review_report import summarize
        rows = [{"is_answerable": True, "result": {"abstained": False},
                 "review_status": "ai_reviewed", "answer_correct": False,
                 "claim_support": [False], "citation_supported": [False]}]
        self.assertIsNone(summarize(rows)["answer_correctness"])
        ai = summarize(rows, "ai_reviewed")
        self.assertEqual(ai["reviewer_kind"], "ai")
        self.assertEqual(ai["answer_correctness"], 0.0)

    def test_invented_penalty_is_rejected_even_with_valid_citation(self):
        raw = {"message": {"content": json.dumps({"answer":"Pidana 5 tahun", "citation_ids":["E1"], "abstained":False})}}
        with patch("app.generation.urlopen", return_value=io.BytesIO(json.dumps(raw).encode())):
            result = generate("Apa pidananya?", [{"text":"Pidana 4 tahun"}])
        self.assertTrue(result["abstained"])

    def test_exact_source_excerpt_is_accepted(self):
        raw = {"message": {"content": json.dumps({"answer":"(2) pidana empat tahun", "citation_ids":["E1"], "abstained":False})}}
        with patch("app.generation.urlopen", return_value=io.BytesIO(json.dumps(raw).encode())):
            result = generate("Apa pidananya?", [{"text":"Pasal 67\n(1) lain\n(2) pidana empat tahun"}])
        self.assertFalse(result["abstained"])

    def test_party_arguments_are_excluded(self):
        from app.evidence import select_evidence
        self.assertEqual(select_evidence("Apa amar?", [{"source_kind":"judgment_full_text", "section_type":"duduk_perkara", "text":"Pemohon meminta"}]), [])

    def test_related_holding_is_required_and_respects_filters(self):
        from app.evidence import include_holdings
        hit = {"document_id":"UU", "chunk_id":"a", "article":"Pasal 53"}
        docs = {"UU":{"legal_status_note":"Putusan terkait Pasal 53 ayat (1)", "related_document_ids":["MK"]}}
        holding = {"document_id":"MK", "chunk_id":"b", "section_type":"amar_putusan"}
        self.assertEqual(include_holdings([hit], docs, [holding], {"UU"}), [])
        self.assertEqual(include_holdings([hit], docs, [holding], {"UU","MK"})[0], holding)

    def test_unrelated_lower_ranked_article_does_not_inject_holding(self):
        from app.evidence import include_holdings
        hits = [{"document_id":"UU","chunk_id":"a","article":"Pasal 46"}, {"document_id":"UU","chunk_id":"b","article":"Pasal 53"}]
        docs = {"UU":{"legal_status_note":"Pasal 53", "related_document_ids":["MK"]}}
        self.assertEqual(include_holdings(hits, docs, [], {"UU"}), hits)

    def test_next_section_heading_does_not_enter_previous_article(self):
        chunks = parse_pages("UU", ["Pasal 55\nTransfer domestik.\nBagian Kedua\nTransfer ke Luar Wilayah\nPasal 56\nTransfer internasional."], "https://official.test")
        self.assertNotIn("Luar", chunks[0]["text"])
        self.assertIn("internasional", chunks[1]["text"])

    def test_personnel_questions_abstain_without_inventing_a_role(self):
        from app.evidence import select_evidence
        self.assertEqual(select_evidence("Siapa nama ketua lembaga?", [{"text":"Ketua Mahkamah"}]), [])

    def test_legal_basis_does_not_use_transition_period(self):
        from app.evidence import select_evidence
        hits = [{"text":"Menyesuaikan pemrosesan dua tahun"}, {"text":"Wajib memiliki dasar pemrosesan Data Pribadi"}]
        self.assertEqual(select_evidence("Apa dasar sebelum memproses data?", hits), hits[1:])

    def test_cross_border_question_does_not_use_territorial_scope(self):
        from app.evidence import select_evidence
        hits = [{"text":"Berlaku di luar wilayah Indonesia"}, {"text":"Transfer dalam wilayah Indonesia"}, {"text":"Transfer kepada Prosesor di luar wilayah Indonesia"}]
        self.assertEqual(select_evidence("Kapan data boleh dikirim ke luar Indonesia?", hits), hits[2:])

    def test_unrelated_question_cannot_receive_a_legal_quote(self):
        from app.evidence import select_evidence
        self.assertEqual(select_evidence("Apa jadwal penerbangan besok?", [{"text":"Undang-undang berlaku tanggal ..."}]), [])

    def test_security_question_preserves_technical_measures(self):
        from app.evidence import select_evidence
        hits = [{"text":"Wajib menjaga kerahasiaan data"}, {"text":"Menentukan langkah teknis dan tingkat keamanan data"}]
        self.assertEqual(select_evidence("Apa kewajiban keamanan data?", hits), hits[1:])
