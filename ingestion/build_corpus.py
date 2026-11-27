"""Build chunks only from manifest entries with a verified local PDF checksum."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .legal_text import parse_pages

PDP_PDF_SHA256 = "ed952dea04b87d14ecf037f9f324a65d50b396ddd34fc28ddf9ff014391971f6"
# Transcribed from the visible page images of this exact BPK PDF.
TEXT_LAYER_READINGS = {
    (PDP_PDF_SHA256, 19): (
        ("Pengendali Data Pribadi wajib\npemberitahuan secara tertulis",
         "Pengendali Data Pribadi wajib menyampaikan\npemberitahuan secara tertulis"),
        # The text layer emits the three labels after the Article 48 continuation line.
        (
            ("ayat (1) minimal memuat:\nData Pribadi yang terungkap;\n"
             "kapan dan bagaimana Data Pribadi terungkap; dan\nupaya penanganan dan pemulihan atas"),
            ("ayat (1) minimal memuat:\na. Data Pribadi yang terungkap;\n"
             "b. kapan dan bagaimana Data Pribadi terungkap; dan\nc. upaya penanganan dan pemulihan atas"),
        ),
        ("(2) Pemberitahuan . . .\na.\nb.\nc.\nSK No 155220A",
         "(2) Pemberitahuan . . .\nSK No 155220A"),
    ),
    (PDP_PDF_SHA256, 30): (
        ("mengunglapkan Data Pribadi yang bukan miliknya", "mengungkapkan Data Pribadi yang bukan miliknya"),
    ),
}


def correct_text_layer(text: str, digest: str, page_number: int) -> str:
    for extracted, printed in TEXT_LAYER_READINGS.get((digest, page_number), ()):
        if text.count(extracted) == 1 and printed not in text:
            text = text.replace(extracted, printed)
        elif extracted in text or text.count(printed) != 1:
            raise ValueError(f"Periksa kembali teks PDF pada halaman {page_number} sebelum menerapkan koreksi.")
    return text


def build(manifest_path: Path, output_path: Path, root: Path) -> int:
    manifest = [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    chunks = []
    for doc in manifest:
        if not doc.get("corpus_eligible") or doc.get("status") != "verified":
            continue
        relpath = Path(doc["local_path"])
        path = (root / relpath).resolve()
        if root.resolve() not in path.parents:
            raise ValueError(f"Path di luar workspace data: {relpath}")
        if not path.is_file() or not doc.get("sha256"):
            raise ValueError(f"PDF/checksum belum tersedia untuk {doc['document_id']}")
        pdf_bytes = path.read_bytes()
        digest = hashlib.sha256(pdf_bytes).hexdigest()
        if digest != doc["sha256"]:
            raise ValueError(f"Checksum tidak cocok untuk {doc['document_id']}")
        try:
            import fitz
        except ImportError as exc:
            raise RuntimeError("Pasang dependensi proyek: python -m pip install -e .") from exc
        try:
            with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf:
                if pdf.is_encrypted:
                    raise ValueError("PDF terenkripsi tidak didukung")
                pages = [correct_text_layer(page.get_text("text"), digest, page.number + 1) for page in pdf]
                if not any(page.strip() for page in pages):
                    raise ValueError("PDF kosong/scan tidak memiliki text layer; OCR manual diperlukan")
        except (RuntimeError, ValueError) as exc:
            raise ValueError(f"Ekstraksi {doc['document_id']} gagal: {exc}") from exc
        chunks.extend(parse_pages(
            doc["document_id"], pages, doc["official_source_url"],
            doc.get("source_kind", "unknown"), doc.get("effective_from"), doc.get("status"),
            document_title=doc.get("title"),
        ))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("".join(json.dumps(chunk, ensure_ascii=False) + "\n" for chunk in chunks), encoding="utf-8")
    return len(chunks)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=Path("data/manifest.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/chunks.jsonl"))
    args = parser.parse_args()
    print(f"Dibuat {build(args.manifest, args.output, Path.cwd())} chunk.")
