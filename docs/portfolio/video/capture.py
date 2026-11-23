"""Record the actual Streamlit demo and mark its edit points."""

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from time import monotonic

from playwright.sync_api import sync_playwright

SITE = "http://127.0.0.1:8501"
VIEWPORT = {"width": 432, "height": 450}


@dataclass(frozen=True)
class Shot:
    scene: int
    cue: int
    start: float
    end: float


def record(folder: Path, ffmpeg: str) -> tuple[Path, list[Shot], str]:
    demo_path = Path(__file__).resolve().parent.parent / "demo_run.json"
    demo = json.loads(demo_path.read_text(encoding="utf-8"))["fresh_checks"]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome")
        context = browser.new_context(
            viewport=VIEWPORT, record_video_dir=folder, record_video_size=VIEWPORT
        )
        context.route(
            "**/*",
            lambda route: (
                route.continue_()
                if route.request.url.startswith(f"{SITE}/")
                else route.abort()
            ),
        )
        context.add_init_script("""() => {
            const pointer = document.createElement('div');
            pointer.setAttribute('aria-hidden', 'true');
            pointer.style.cssText = 'position:fixed;z-index:2147483647;width:16px;height:19px;'
                + 'pointer-events:none;background:#ffb400;clip-path:polygon(0 0,100% 69%,48% 69%,31% 100%);display:none';
            document.addEventListener('pointermove', event => {
                if (!pointer.isConnected) document.body.append(pointer);
                pointer.style.display = 'block';
                pointer.style.left = `${event.clientX}px`;
                pointer.style.top = `${event.clientY}px`;
            }, true);
        }""")
        page = context.new_page()
        page.set_content('<body style="background:#ff00ff"></body>')
        page.wait_for_timeout(520)
        page.evaluate("document.body.style.background = '#00ff00'")
        origin = monotonic()
        shots = []

        def shot(scene, cue, action, hold=700):
            start = monotonic() - origin
            action()
            page.wait_for_timeout(hold)
            shots.append(Shot(scene, cue, start, monotonic() - origin))

        def show(locator):
            locator.evaluate(
                "el => el.scrollIntoView({block: 'center', behavior: 'smooth'})"
            )
            page.wait_for_timeout(420)

        try:
            page.wait_for_timeout(420)
            page.goto(SITE, wait_until="domcontentloaded")
            question = page.get_by_role("textbox", name="Pertanyaan")
            question.wait_for(timeout=30_000)
            assert question.input_value() == ""
            dropdown = page.get_by_test_id("stSelectbox").get_by_role("combobox")
            bm25 = page.get_by_role("option", name="BM25 — pencocokan kata", exact=True)
            dense = page.get_by_role(
                "option", name="Dense — kemiripan makna", exact=True
            )
            submit = page.get_by_role("button", name="Cari dan jawab")
            answer = page.get_by_role("heading", name="Jawaban", exact=True)
            filter_box = page.get_by_text("Batasi dokumen (opsional)", exact=True)

            def focus_question():
                show(question)
                question.click()

            def open_menu():
                show(dropdown)
                dropdown.click()
                dense.wait_for()

            def send():
                show(submit)
                submit.click()

            shot(
                0,
                0,
                lambda: page.get_by_role(
                    "heading", name="RegulaRAG Indonesia"
                ).wait_for(),
                850,
            )
            shot(0, 2, focus_question)
            shot(
                1,
                0,
                lambda: question.press_sequentially(
                    demo["retrieval"]["question"], delay=32
                ),
                850,
            )
            shot(1, 1, lambda: show(filter_box))
            shot(2, 0, open_menu, 1000)
            shot(2, 1, bm25.click)
            shot(2, 2, send, 520)

            page.get_by_text("Metode retrieval: bm25", exact=True).wait_for(
                timeout=150_000
            )
            text = page.locator("body").inner_text()
            citation = page.locator("summary").filter(
                has_text=re.compile(r"Pasal 46.*halaman 19")
            )
            if "3 x 24" not in text:
                raise RuntimeError(
                    f"BM25 footage does not support the planned deadline: {text[-1600:]}"
                )
            citation.wait_for(timeout=10_000)
            print(
                "BM25: Article 46, PDF page 19, 3 x 24 in the live answer", flush=True
            )
            shot(3, 0, lambda: show(answer))
            deadline = (
                page.get_by_test_id("stMarkdownContainer")
                .filter(has_text="3 x 24")
                .first
            )
            shot(3, 1, lambda: show(deadline), 850)

            def expand():
                show(citation)
                citation.click()

            source = page.get_by_text("Buka sumber resmi", exact=True)
            shot(3, 2, expand, 850)
            shot(3, 3, lambda: show(source), 850)

            shot(4, 0, open_menu)
            shot(4, 1, dense.click)
            shot(4, 2, send, 520)
            dense_result = page.get_by_text("Metode retrieval: dense", exact=True)
            error = page.get_by_text(
                re.compile(r"[Ii]ndeks.*(tidak|belum|rusak|usang)|[Rr]etrieval.*gagal")
            )
            dense_result.or_(error.first).first.wait_for(timeout=150_000)
            if dense_result.is_visible():
                dense_status = "returned"
                shot(4, 3, lambda: show(dense_result), 850)
            else:
                dense_status = "error"
                print(f"Dense: {error.first.inner_text()}", flush=True)
                shot(4, 3, lambda: show(error.first), 850)
            print(f"Dense: {dense_status}", flush=True)

            def type_flights():
                open_menu()
                bm25.click()
                focus_question()
                question.fill("")
                question.press_sequentially(demo["abstention"]["question"], delay=29)
                send()

            shot(5, 0, type_flights, 480)
            warning = page.get_by_text(
                "Sistem abstain: bukti belum cukup untuk menjawab dengan yakin.",
                exact=True,
            )
            warning.wait_for(timeout=30_000)
            page.get_by_text("Metode retrieval: bm25", exact=True).wait_for()
            no_citations = page.get_by_text(
                "Tidak ada kutipan yang ditemukan dalam dokumen aktif.", exact=True
            )
            no_citations.wait_for()
            shot(5, 1, lambda: show(warning))
            shot(5, 2, lambda: show(no_citations))
            notice = page.get_by_text(
                re.compile(r"^Corpus tidak lengkap dan mungkin belum mencakup")
            )
            shot(5, 3, lambda: show(notice), 1600)
            print("Flight question: BM25 abstention, no citations", flush=True)
            video = page.video.path()
        finally:
            context.close()
            browser.close()
    # The recording clock begins at the first frame, not at page creation.
    marker = subprocess.check_output(
        [
            ffmpeg,
            "-v",
            "error",
            "-i",
            video,
            "-t",
            "4",
            "-an",
            "-vf",
            "fps=25,crop=2:2:0:0,format=rgb24",
            "-f",
            "rawvideo",
            "-",
        ]
    )
    for frame, offset in enumerate(range(0, len(marker), 12)):
        red, green, blue = marker[offset : offset + 3]
        if red < 25 and green > 225 and blue < 25:
            recorded_origin = frame / 25
            break
    else:
        raise RuntimeError("Could not align the browser recording clock")
    return (
        video,
        [
            Shot(s.scene, s.cue, s.start + recorded_origin, s.end + recorded_origin)
            for s in shots
        ],
        dense_status,
    )
