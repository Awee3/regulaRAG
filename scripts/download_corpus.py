"""Restore only eligible manifest artifacts; never change verification status."""
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def run():
    for line in (ROOT / "data/manifest.jsonl").read_text(encoding="utf-8").splitlines():
        doc = json.loads(line)
        if not doc.get("corpus_eligible") or doc.get("status") != "verified":
            continue
        dest = (ROOT / doc["local_path"]).resolve()
        if ROOT / "data/raw" not in dest.parents:
            raise ValueError("Artifact path must stay in data/raw")
        if dest.exists():
            content = dest.read_bytes()
        else:
            with urlopen(doc["download_url"], timeout=90) as response:
                content = response.read()
        if not content.startswith(b"%PDF") or hashlib.sha256(content).hexdigest() != doc["sha256"]:
            raise ValueError(f"Artifact/checksum mismatch: {doc['document_id']}; review official source manually")
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            dest.write_bytes(content)
        print(doc["document_id"], "checksum OK")


if __name__ == "__main__":
    run()
