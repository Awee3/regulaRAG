# RegulaRAG Indonesia LinkedIn video — a walkthrough of the real website

Open on the running RegulaRAG website with the question box empty. Let the viewer watch the question appear character by character, the search menu open, and a result arrive after the submit button is clicked. Use a recording of the actual Streamlit page for the full walkthrough, including the opening and closing shots. The production AI operates the browser and produces the video locally without plugins or manual screen recording.

**Language.** Keep the website exactly as shipped, including its Indonesian labels, questions, and source quotations. Use English for the AI voice-over, captions, translations, and any editorial text. Put translations in the caption area so viewers can still recognize the original control or quotation on the website.

**Deliverables.** Produce `docs/portfolio/video/regularag-linkedin.mp4` for LinkedIn and `docs/portfolio/video/regularag-linkedin.html` with the same MP4 embedded for offline playback. Target about 75 seconds (70–85 seconds), 1080 × 1350, portrait 4:5, 30 fps, H.264 video, and an English AAC voice track. Burn in English captions for muted playback. [Existing video build](video/README.md) · [LinkedIn upload requirements](https://www.linkedin.com/help/linkedin/answer/a7494039)

## What the viewer should be able to do after watching

Type a question in **Pertanyaan**, choose a retrieval method under **Metode pencarian**, submit with **Cari dan jawab**, and find the cited page under **Sumber dan kutipan**. The search menu has these four options in this order. [Streamlit interface](../../app/ui.py) · [Retrieval and model configuration](../../configs/default.yaml)

| Exact menu label | What it does |
|---|---|
| `BM25 — pencocokan kata` | Default. Ranks passages using the words in the question. |
| `Dense — kemiripan makna` | Uses multilingual E5 embeddings and Qdrant Local to retrieve passages by meaning. This is the option to click when the narrator says “E5”. |
| `Hybrid — gabungan keduanya` | Combines the keyword and dense rankings. |
| `Hybrid + reranker CPU (opsional)` | Reranks the combined candidates on the CPU. |

BM25 and E5 change how passages are found. The answer stage uses one local Qwen3 1.7B model through Ollama to select excerpts. Leave **Batasi dokumen (opsional)** empty for the demo.

## Shot list and English voice-over

Use the same browser session throughout. The timings are editing targets. Match the final captions and voice-over to what the captured run actually shows.

| Time | Browser action to record | English narration |
|---|---|---|
| 0–7 s | Show the actual **RegulaRAG Indonesia** page title, corpus notice, extraction warning, and empty form. Move the pointer into **Pertanyaan** and click so the caret is visible. | “This is RegulaRAG. It searches official Indonesian data protection documents on a local computer. Let’s follow one question to its source.” |
| 7–19 s | Type the breach question below into the real text area. Let the viewer see individual characters and the complete question. Briefly show the empty document filter. | “What’s the deadline for notifying someone after a personal data breach? I’ll enter that question and leave the document filter open so we can search the collection.” |
| 19–31 s | Open **Metode pencarian**, hold on the four native options, then click **BM25 — pencocokan kata**. Click **Cari dan jawab**. Show the start of the actual loading state if visible. | “The search menu offers four methods. I’ll start with BM25, which looks for matching words, then submit the question.” |
| 31–48 s | Scroll to **Jawaban**. Show the returned text and **Metode retrieval: bm25**. Under **Sumber dan kutipan**, click the citation expander and pause on its title, PDF page, quotation, and **Buka sumber resmi** link. | “The local Qwen model selected this passage. It gives the deadline as three times twenty-four hours. Opening the citation shows Article forty-six, page nineteen, and a link to the official source.” |
| 48–66 s | Scroll back to the same question. Reopen **Metode pencarian** and visibly select **Dense — kemiripan makna**. Click **Cari dan jawab** again. Show the new response and **Metode retrieval: dense** when returned. | “I’ll keep the question and switch to dense search. This option uses E5 to find passages with similar meaning. Submitting again runs that search. Both methods pass their results to the same answer model.” |
| 66–78 s | Return to the form, select BM25, replace the question with the flight question below, and submit. Hold on the real insufficient-evidence message and the empty citations section. Finish on the app’s own research-use notice. | “What if I ask about flights from Jakarta to Tokyo? The app reports that it has too little evidence and returns no citations. Its collection covers data protection documents.” |

**Inputs to type.** Use these public demo questions with their original spelling. Their English meaning is in the narration. [Recorded demo questions and outcomes](demo_run.json) · [English translations and source notes](demo.md)

- `Berapa lama batas waktu untuk memberi tahu subjek data setelah terjadi kebocoran data pribadi?`
- `Apa jadwal penerbangan Jakarta Tokyo besok?`

The earlier BM25 demo returned Article 46 on PDF page 19 with the text `3 x 24`. Use that narration only when the new recording shows it. Mark the translated legal wording “Unofficial English translation”. The original-source button opens the BPK detail page. If the video follows the link, show where it actually leads. The official PDF includes a verb missing from the archived extraction, so check any quoted wording against the page. [Archived BM25 citation](assets/demo-citation-crop.jpg) · [Official PDF excerpt](assets/source-pdf-article-46.png)

## How to produce the recording

1. **Run the real site.** From the repository root, use the project environment and Ollama with `qwen3:1.7b-q4_K_M`. BM25 needs the built corpus. For the E5 run, use the configured embedding model and a matching Qdrant Local index. Follow the repository setup if either is missing. Use one reader of that index. Reuse the running project UI or start it with the command below, then open `http://127.0.0.1:8501`. [Local setup and index recovery](../../README.md)

   ```powershell
   .\.venv\Scripts\python.exe -m streamlit run app/ui.py --server.address 127.0.0.1 --server.port 8501 --server.headless true --browser.gatherUsageStats false
   ```

2. **Drive and record Chrome with Playwright.** Allow the local Streamlit page and its WebSocket connection during capture. Locate the text area, dropdown, button, and citation by their actual accessible names. Use sequential keystrokes for the questions. Record the native dropdown opening, the selected value changing, both submissions, scrolling, and the expander opening. Keep the browser recording active until the last result is visible, then close the recording context to finalize the clip. If the recorder omits the pointer, composite a small cursor from the actual pointer positions and click times. Preserve the native theme, typography, layout, and notices. [UI source](../../app/ui.py)
3. **Match footage to the answer it belongs to.** Selecting a method edits the form. The previous answer can still be visible until the next submission. For each run, wait for its result-mode line or the app’s actual error. Show a brief portion of any loading wait and trim idle time between the click and its own result. If dense retrieval fails, use the README recovery steps and retry. If it remains unavailable, show the genuine selection and error, adjust the English narration, and report which method completed. Use archived evidence to check the story. Every on-screen interaction and answer must come from the recorded browser session.
4. **Use the existing media pipeline.** Revise the six entries in `narration.py` to match the captured actions. Reuse its local Supertonic 3 voice (`M1`, `lang="en"`) and caption timing. In `build.py`, use the website footage as the picture source in place of the illustrated scenes from `animation.html`. Keep the FFmpeg export, `verify_mp4`, and `make_player` so the offline HTML embeds the checked MP4. Position English captions in a separate band. A gentle crop or zoom can bring a control into view while preserving its proportions. [Narration code](video/narration.py) · [Exporter and offline player](video/build.py)
5. **Check the finished walkthrough.** At a phone viewing width of about 360 pixels, verify that the typing caret, both selected methods, submit button, and expanded citation are legible. Watch once muted to check captions and once with sound to check that each spoken action coincides with its click or result. Check the MP4 audio track and duration, then play the standalone HTML offline. Deliver both files, the rebuild command, and the retrieval modes actually exercised.

## Handoff prompt

> Use this plan to record the real local RegulaRAG Streamlit website. Automate the typing, BM25 submission, citation expansion, and second submission with the same question using Dense/E5. Capture the real responses and the out-of-collection example. Keep the website’s own labels on screen, narrate and caption in English, and deliver the verified LinkedIn MP4 and offline HTML without plugins.
