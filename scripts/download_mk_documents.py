"""Download candidate Constitutional Court decisions from official portals and verify them."""

import hashlib
import json
import ssl
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data/raw"

DOCUMENTS = [
    {
        "id": "MK_135_PUU_XXIII_2025",
        "url": "https://jdih.komdigi.go.id/judicial/unduh/49",
        "filename": "MK_135_PUU_XXIII_2025.pdf",
    },
    {
        "id": "MK_137_PUU_XXIII_2025",
        "url": "https://jdih.komdigi.go.id/judicial/unduh/48",
        "filename": "MK_137_PUU_XXIII_2025.pdf",
    },
    {
        "id": "MK_133_PUU_XXIV_2026",
        "url": "https://s.mkri.id/public/content/persidangan/putusan/putusan_mkri_14323_1779697116.pdf",
        "filename": "MK_133_PUU_XXIV_2026.pdf",
    },
]

def download_and_verify():
    ctx = ssl.create_default_context()
    # Some gov sites have legacy cert bundles
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    results = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) RegulaRAG-Ingestion/0.1"}

    for doc in DOCUMENTS:
        dest = RAW_DIR / doc["filename"]
        print(f"Downloading {doc['id']} from {doc['url']}...")
        try:
            req = urllib.request.Request(doc["url"], headers=headers)
            with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
                content = resp.read()
                
            if not content.startswith(b"%PDF"):
                print(f"WARNING: {doc['id']} content does not start with %PDF! Length: {len(content)}")
                if len(content) < 2000:
                    print("Sample content:", content[:200])
                results.append({"id": doc["id"], "success": False, "reason": "Not a PDF"})
                continue
                
            dest.write_bytes(content)
            sha256 = hashlib.sha256(content).hexdigest()
            print(f"SUCCESS: {doc['id']} saved to {dest.name} ({len(content)} bytes), SHA-256: {sha256}")
            results.append({
                "id": doc["id"],
                "success": True,
                "url": doc["url"],
                "path": str(dest.relative_to(ROOT)).replace("\\", "/"),
                "sha256": sha256,
                "size": len(content),
            })
        except Exception as e:
            print(f"FAILED: {doc['id']} error: {e}")
            results.append({"id": doc["id"], "success": False, "reason": str(e)})

    print("\nSummary:")
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    download_and_verify()
