"""Select normative evidence without treating party arguments as court holdings."""
import re
from datetime import date


def select_evidence(question, hits, limit=5):
    if not re.search(r"\b(?:data|pribadi|pdp|pasal|ayat|uu|undang|putusan|mk|amar|pengendali|prosesor|persetujuan|pemrosesan|dpo|ppdp|pelindungan|perlindungan|subjek|transfer|pidana|denda|kebocoran)\b", question, re.IGNORECASE):
        return []
    if re.search(r"\b(?:siapa|sebutkan)\s+(?:nama|ketua|pejabat)\b", question, re.IGNORECASE):
        return []
    selected = []
    for hit in hits:
        kind = hit.get("source_kind")
        if kind == "judgment_full_text" and hit.get("section_type") != "amar_putusan":
            continue
        if hit.get("effective_from") and hit["effective_from"] > date.today().isoformat():
            continue
        selected.append(hit)
    # Definitions need the explicit defining sentence, not incidental mentions.
    match = re.search(r"(?:dimaksud (?:dengan )?|definisi )(.*?)[?.]?$", question, re.IGNORECASE)
    if match:
        term = match.group(1).strip().casefold()
        selected = [hit for hit in selected if f"{term} adalah" in " ".join(hit["text"].casefold().split())]
    if re.search(r"\bdasar\b", question, re.IGNORECASE) and re.search(r"\b(?:memproses|pemrosesan)\b", question, re.IGNORECASE):
        selected = [hit for hit in selected if "dasar pemrosesan" in " ".join(hit["text"].casefold().split())]
    if re.search(r"\b(?:luar|internasional)\b", question, re.IGNORECASE) and re.search(r"\b(?:transfer|dikirim|memindahkan|pengiriman)\b", question, re.IGNORECASE):
        selected = [hit for hit in selected if "transfer" in hit["text"].casefold() and re.search(r"(?:ke|di) luar wilayah", " ".join(hit["text"].casefold().split()))]
    if re.search(r"\bkeamanan\b", question, re.IGNORECASE):
        selected = [hit for hit in selected if "keamanan" in hit["text"].casefold() and "langkah" in hit["text"].casefold()]
    return selected[:limit]


def include_holdings(hits, registry, chunks, allowed_ids):
    related = set()
    for hit in hits[:1]:
        doc = registry[hit["document_id"]]
        reviewed_articles = re.findall(r"Pasal\s+\d+", doc.get("legal_status_note") or "")
        if hit.get("article") in reviewed_articles:
            related.update(doc.get("related_document_ids", []))
    holdings = [c for c in chunks if c["document_id"] in related & allowed_ids and c.get("section_type") == "amar_putusan"]
    if related and not holdings:
        return []
    ids = {c["chunk_id"] for c in holdings}
    return holdings + [hit for hit in hits if hit["chunk_id"] not in ids]
