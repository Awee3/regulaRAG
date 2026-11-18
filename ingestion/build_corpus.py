"""Build chunks only from manifest entries with a verified local PDF checksum."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .legal_text import parse_pages


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
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != doc["sha256"]:
            raise ValueError(f"Checksum tidak cocok untuk {doc['document_id']}")
        try:
            import fitz
        except ImportError as exc:
            raise RuntimeError("Pasang dependensi proyek: python -m pip install -e .") from exc
        try:
            with fitz.open(path) as pdf:
                if pdf.is_encrypted:
                    raise ValueError("PDF terenkripsi tidak didukung")
                pages = [page.get_text("text") for page in pdf]
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
