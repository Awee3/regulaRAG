"""Structure-aware extraction for text returned by PDF page extraction."""

from __future__ import annotations

import re

ARTICLE = re.compile(r"(?m)^\s*(?:Pasal\s*([0-9]+[A-Z]?|I|T2|2T)|Pasa7\s*([0-9]+))\s*$", re.IGNORECASE)
BAB = re.compile(r"(?m)^\s*BAB\s+([IVXLCDM]+)\b[^\n]*", re.IGNORECASE)
PARAGRAPH = re.compile(r"(?m)^\s*\(([0-9]+)\)")


def parse_pages(document_id: str, pages: list[str], source_url: str,
                source_kind: str = "regulation_full_text", effective_from: str | None = None,
                status: str = "verified", document_title: str | None = None) -> list[dict]:
    """Keep article chunks separate and retain actual 1-based PDF page spans."""
    if source_kind != "regulation_full_text":
        chunks = []
        for page_number, page in enumerate(pages, start=1):
            if not page.strip():
                continue
            text_upper = page.upper()
            section_type = "duduk_perkara"
            if re.search(r"(?m)^\s*(?:[45]\.\s*)?(?:AMAR PUTUSAN|MENGADILI)\s*:?\s*$", text_upper):
                section_type = "amar_putusan"
            elif "[3." in page or "PERTIMBANGAN HUKUM" in text_upper or "PERTIMBANGAN MAHKAMAH" in text_upper:
                section_type = "pertimbangan_hukum"

            sec_name = ("Amar Putusan" if section_type == "amar_putusan"
                        else ("Pertimbangan Hukum" if section_type == "pertimbangan_hukum"
                              else "Duduk Perkara"))
            heading = f"{sec_name} (Halaman {page_number})"

            chunks.append({
                "document_id": document_id,
                "chunk_id": f"{document_id}:page:{page_number}",
                "page_start": page_number,
                "page_end": page_number,
                "bab": None,
                "article": None,
                "paragraph": None,
                "letter": None,
                "heading": heading,
                "text": page.strip(),
                "source_url": source_url,
                "status": status,
                "effective_from": effective_from,
                "source_kind": source_kind,
                "section_type": section_type,
            })
        return chunks

    chunks: list[dict] = []
    current_bab = None
    section_type = "batang_tubuh"
    current = None

    def flush() -> None:
        if current and current["text"].strip():
            suffix = ":explanation" if current["section_type"] == "penjelasan" else ""
            chunks.append({
                "document_id": document_id,
                "chunk_id": f"{document_id}{suffix}:article:{current['article']}",
                "page_start": current["page_start"],
                "page_end": current["page_end"],
                "bab": current["bab"],
                "article": f"Pasal {current['article']}",
                "paragraph": (f"ayat ({next(iter(numbers))})" if len(numbers := set(PARAGRAPH.findall(current["text"]))) == 1 else None),
                "letter": None,
                "heading": None,
                "text": current["text"].strip(),
                "source_url": source_url,
                "status": status,
                "effective_from": effective_from,
                "source_kind": source_kind,
                "section_type": current["section_type"],
            })

    for page_number, page in enumerate(pages, start=1):
        for line in page.splitlines():
            if line.strip().upper() in {"PENJELASAN", "PENJEI,ASAN"}:
                flush()
                current = None
                current_bab = None
                section_type = "penjelasan"
                continue
            bab = BAB.match(line)
            if bab or re.match(r"^\s*Bagian\s+\w+\s*$", line):
                flush()
                current = None
                if bab:
                    current_bab = bab.group(1).upper()
                continue
            article = ARTICLE.match(line)
            if article:
                flush()
                raw_num = article.group(1) or article.group(2)
                # shortcut: repair visually checked I/1, O/0, 2T/27, Pasa7/Pasal, and T/7 glyphs; add review for other OCR errors.
                number = {"I": "1", "T2": "72", "2T": "27"}.get(raw_num.upper(), raw_num.upper().replace("O", "0").replace("T", "7"))
                heading = f"Pasal {number}" if line.strip() != f"Pasal {number}" else line.strip()
                current = {"article": number, "page_start": page_number,
                           "page_end": page_number, "bab": current_bab,
                           "section_type": section_type, "text": heading}
            elif current:
                current["page_end"] = page_number
                current["text"] += "\n" + line.rstrip()

    flush()
    return chunks


def article_metadata(text: str) -> tuple[str | None, str | None]:
    """Return the first explicit article and paragraph; never infer missing numbers."""
    article = ARTICLE.search(text)
    paragraph = PARAGRAPH.search(text)
    raw_num = (article.group(1) or article.group(2)) if article else None
    num = {"I": "1", "T2": "72", "2T": "27"}.get(raw_num.upper(), raw_num.upper().replace("O", "0").replace("T", "7")) if raw_num else None
    return (num,
            f"ayat ({paragraph.group(1)})" if paragraph else None)
