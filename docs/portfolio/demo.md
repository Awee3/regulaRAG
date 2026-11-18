# RegulaRAG demo guide: 2–3 minutes

**Audience:** recruiters and AI engineers. **Narration:** English. **Application and source evidence:** Indonesian.  
Supporting materials: [PDF carousel](regularag-linkedin.pdf), [editable PPTX](regularag-linkedin.pptx), [report](report.md), [LinkedIn caption](caption.md), and [demo record](demo_run.json).

The presentation has no recurring footers, page numbers, or display dates. Verification timestamps remain in the source records. English question renderings explain the recorded Indonesian demo; they do not establish that English queries were tested.

## Preparation

1. Follow the [README setup](../../README.md#setup-dari-nol-windows-powershell). Check that Ollama, `qwen3:1.7b-q4_K_M`, and the corpus are available.
2. Start the UI from the repository root. It calls the pipeline directly, so a separate API process is unnecessary:

   ```powershell
   .\.venv\Scripts\python.exe -m streamlit run app/ui.py --server.address 127.0.0.1 --browser.gatherUsageStats false
   ```

3. Open <http://127.0.0.1:8501>. Select BM25 using the interface label **“BM25 — pencocokan kata”**. Leave the document filter, **“Batasi dokumen (opsional)”**, empty. The live application displays corpus information and verification timestamps.
4. Have the official local PDF `D:\regulaRAG\data\raw\UU_27_2022.pdf` ready at PDF page **19** in case the portal fails. Its printed page number also happens to be 19; other PDFs may differ.
5. The recorded configuration used one 1.7B model, a 4096-token context, `num_gpu: null` for Ollama auto/offloading, and four documents containing 593 chunks. GPU use follows the user’s statement. No device, layer, latency, RAM, or VRAM benchmark was performed. The recorded environment used system Python 3.11 with available dependencies; use the README virtualenv for reproduction.

## Script and screen sequence

| Target time | Action | Suggested narration |
|---|---|---|
| 00:00–00:20 | Show the title and corpus information. | “RegulaRAG searches PDP documents locally. Its corpus is limited and has recorded verification metadata. It is a document search aid, not legal advice.” |
| 00:20–01:00 | Enter the first original prompt below. Click **“Cari dan jawab”** (Search and answer). | “The model selects source excerpts. The backend returns their original text and validates citations. This is extractive answering.” |
| 01:00–01:45 | Expand the citation. Click **“Buka sumber resmi”** (Open official source), then inspect PDF page 19. | “The citation identifies the document, article, and page. We still compare the extracted quotation with the visual PDF.” |
| 01:45–02:15 | Submit the flight-schedule prompt. | “The corpus contains no flight schedules. The system abstains and does not invent a citation.” |
| 02:15–02:45 | Show N01 or the final carousel page. | “The system also rejected a question that had supporting evidence. Twelve of thirteen development cases passed AI review. Human validation is not available.” |

These timings structure the narration; they are not measured application performance. Allow for actual response time. Identify saved screenshots as recorded demo evidence when using them as a fallback.

## Scenario 1: successful answer

**English rendering:** How long is the deadline for notifying data subjects after a personal data breach?

Enter the original Indonesian prompt exactly:

> Berapa lama batas waktu untuk memberi tahu subjek data setelah terjadi kebocoran data pribadi?

Recorded result: an answer, `bm25` retrieval, and a citation matching `UU_27_2022:article:46`, PDF page 19. Preserve the exact displayed source text, including extraction defects.

The carousel’s English callout, **“no later than 3 x 24 (three times twenty-four) hours,”** is an unofficial explanatory translation of the excerpt. It is not a verbatim English quotation from an official translation.

![Actual UI answer, original Indonesian evidence](assets/demo-answer.jpg)

## Scenario 2: inspect the citation against the source

1. Expand the citation identifying Law No. 27 of 2022, Article 46, PDF page 19. The live label uses the original Indonesian title.
2. Inspect its recorded `verified` status, effective date, and original quotation.
3. Click **“Buka sumber resmi”** (Open official source). It points to the [BPK detail page](https://peraturan.bpk.go.id/Details/229798/uu-no-27-tahun-2022); it does not automatically open PDF page 19.
4. When the portal is available, follow its official PDF link and navigate to page 19. The manifest’s PDF URL is <https://peraturan.bpk.go.id/Home/Download/224884/UU%20Nomor%2027%20Tahun%202022.pdf>.
5. During the recorded demo, BPK returned **“The service is unavailable.”** Use the checksum-verified local copy and say: “The source portal is unavailable. This is an official local copy with a matching checksum.” Do not claim a fresh download or legal-status verification succeeded.

The local PDF’s SHA-256 is:

```text
ed952dea04b87d14ecf037f9f324a65d50b396ddd34fc28ddf9ff014391971f6
```

![Expanded citation in the actual Indonesian UI](assets/demo-citation.jpg)

![Original official local PDF, page 19](assets/source-pdf-page-19.png)

The visual PDF includes **“menyampaikan”** in paragraph (1), while the extracted text used by the application omits it. This demonstrates that a quotation can match the store and still differ from the rendered document. This inspection is AI review, not human validation. The [portal error screenshot](assets/source-unavailable.jpg) is preserved separately.

The English carousel crops the source screenshots for readability and removes the metadata date row. These full original captures remain available here for inspection.

## Scenario 3: unsupported question

**English rendering:** What are tomorrow’s flights from Jakarta to Tokyo?

Enter the original prompt:

> Apa jadwal penerbangan Jakarta Tokyo besok?

Recorded result: the system reports insufficient corpus evidence and shows no citations. This tests a clearly unrelated topic. It does not demonstrate that every unsupported legal question will be detected.

![Actual abstention in the Indonesian UI](assets/demo-abstention.jpg)

## Closing: a failure that remains visible

**English rendering:** What rights does Article 7 give data subjects?

Original N01 prompt:

> Apa hak subjek data dalam Pasal 7?

The recorded evaluation found a false abstention even though the corpus contains Article 7. See the [item review](../../evaluation/results/quality_final_review.jsonl). N01 was not rerun for the screenshot demo or this translation. Present it as a historical finding. If a future run succeeds, retain the earlier record and report the new result separately.

## Before presenting

- Rehearse the three scenarios using the configuration you will show. Separate new results from archived evidence.
- Check the citation and PDF page. Describe portal availability accurately.
- Verification dates belong to source records; presentation revisions do not update legal verification.
- Keep **“AI review, no human validation yet”** visible on the evaluation page.
- Describe **12/13** as development review after fixes from earlier CPU runs, without implying a new GPU evaluation or general accuracy estimate.
- Keep English translations distinct from original Indonesian prompts, interface output, and legal wording.
- Exclude private questions, tokens, and sensitive data from any new screenshots.
