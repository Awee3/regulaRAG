"""Conservative verification against public official pages and the complete PDF."""

from __future__ import annotations

import hashlib
import ipaddress
import re
import socket
from datetime import UTC, date, datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

HOSTS = {"peraturan.bpk.go.id", "peraturan.go.id", "www.peraturan.go.id",
         "jdih.setneg.go.id", "jdih.komdigi.go.id", "www.mkri.id", "mkri.id",
         "jdih.mkri.id", "s.mkri.id"}
MAX_BYTES = 64 * 1024 * 1024
MONTHS = ["januari", "februari", "maret", "april", "mei", "juni", "juli", "agustus", "september", "oktober", "november", "desember"]
DATE = r"(?:\d{4}-\d{2}-\d{2}|\d{2}-\d{2}-\d{4}|\d{1,2}\s+(?:" + "|".join(MONTHS) + r")\s+\d{4})"
LAW = re.compile(r"(UNDANG[ -]UNDANG|PERATURAN PEMERINTAH|PERATURAN PRESIDEN)\s+(?:\((?:UU|PP|PERPRES)\)\s+)?(?:REPUBLIK INDONESIA\s+)?(?:NOMOR|NO\.?)\s*(\d+)\s+TAHUN\s+(\d{4})", re.IGNORECASE)
CASE = re.compile(r"(?:PUTUSAN\s+(?:MAHKAMAH KONSTITUSI\s+)?(?:NOMOR\s*)?)(\d+)\s*/\s*(PUU-[IVXLCDM]+)\s*/\s*(\d{4})", re.IGNORECASE)


class SourceError(ValueError):
    def __init__(self, status: str, message: str):
        super().__init__(message)
        self.status = status


def validate_url(url: str, *, resolve: bool = False) -> str:
    parsed = urlsplit(url)
    if (len(url) > 2048 or parsed.scheme != "https" or parsed.hostname not in HOSTS
            or parsed.username or parsed.password or parsed.port not in (None, 443) or parsed.fragment):
        raise SourceError("needs_source", "Gunakan tautan HTTPS halaman/PDF dari portal resmi yang diizinkan, tanpa akun, port khusus atau fragmen.")
    if resolve:
        addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
            raise SourceError("source_unavailable", "Alamat portal resmi tidak menuju jaringan publik.")
    return url


class OfficialRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl, resolve=True)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url: str) -> tuple[bytes, str]:
    validate_url(url, resolve=True)
    try:
        with build_opener(OfficialRedirects()).open(Request(url, headers={"User-Agent": "RegulaRAG-local-source-check/1.0"}), timeout=20) as response:
            final = validate_url(response.url, resolve=True)
            if int(response.headers.get("Content-Length", "0")) > MAX_BYTES:
                raise SourceError("source_unavailable", "Sumber melebihi batas unduhan 64 MB.")
            data = response.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                raise SourceError("source_unavailable", "Sumber melebihi batas unduhan 64 MB.")
            return data, final
    except SourceError:
        raise
    except (OSError, ValueError) as exc:
        raise SourceError("source_unavailable", "Portal tidak dapat diunduh. Periksa tautan resmi lalu kirim ulang untuk mencoba lagi.") from exc


class Page(HTMLParser):
    def __init__(self, data: bytes, url: str):
        super().__init__()
        self.parts, self.links = [], []
        self.hidden = 0
        self.row = None
        self.cell = None
        self.fields = {}
        self.heading = None
        self.headings = []
        self.definition_key = None
        self.definition = None
        self.bpk_layout = urlsplit(url).hostname == "peraturan.bpk.go.id"
        self.div_tags = []
        self.url = url
        self.feed(data.decode("utf-8", errors="replace"))

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "div" and self.bpk_layout:
            classes = (values.get("class") or "").split()
            if "col-lg-3" in classes and "fw-bold" in classes:
                tag = "dt"
            elif "col-lg-9" in classes and self.definition_key:
                tag = "dd"
            self.div_tags.append(tag)
        if tag == "tr":
            self.row = []
        if tag in {"td", "th"} and self.row is not None:
            self.cell = []
        if tag == "h1":
            self.heading = []
        if tag in {"dt", "dd"}:
            self.definition = []
        if tag in {"script", "style"}:
            self.hidden += 1
        link = values.get("href") or (values.get("src") if tag in {"iframe", "embed"} else None)
        if link:
            self.links.append(urljoin(self.url, link))

    def handle_endtag(self, tag):
        if tag == "div" and self.div_tags:
            tag = self.div_tags.pop()
        if tag in {"td", "th"} and self.cell is not None:
            self.row.append(" ".join(self.cell))
            self.cell = None
        if tag == "tr" and self.row is not None:
            if len(self.row) >= 2:
                key = self.row[0].strip().rstrip(":").lower()
                value = " ".join(self.row[1:]).lstrip(": ")
                self.fields.setdefault(key, []).append(value)
            self.row = None
        if tag == "h1" and self.heading is not None:
            self.headings.append(" ".join(self.heading))
            self.heading = None
        if tag == "dt" and self.definition is not None:
            self.definition_key = " ".join(self.definition).strip().rstrip(":").lower()
            self.definition = None
        if tag == "dd" and self.definition is not None:
            if self.definition_key:
                self.fields.setdefault(self.definition_key, []).append(" ".join(self.definition))
            if self.bpk_layout:
                self.definition_key = None
            self.definition = None
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden and data.strip():
            self.parts.append(data.strip())
            if self.cell is not None:
                self.cell.append(data.strip())
            if self.heading is not None:
                self.heading.append(data.strip())
            if self.definition is not None:
                self.definition.append(data.strip())

    @property
    def text(self):
        return " ".join(self.parts)

    @property
    def document_text(self):
        titles = self.fields.get("judul", [])
        if not titles:
            titles = [heading for heading in self.headings if LAW.search(heading) or CASE.search(heading)]
        if len(set(titles)) != 1:
            raise SourceError("needs_metadata", "Halaman belum mempunyai satu judul utama/kolom Judul khusus dokumen. Gunakan halaman detail resmi, bukan hasil pencarian/katalog.")
        title = titles[0]
        return title + " " + " ".join(f"{key} {' '.join(values)}" for key, values in self.fields.items() if key != "judul")


def pdf_pages(data: bytes) -> list[str]:
    import fitz

    try:
        with fitz.open(stream=data, filetype="pdf") as pdf:
            if pdf.is_encrypted:
                raise SourceError("unreadable", "PDF terenkripsi; sediakan salinan resmi tanpa enkripsi.")
            pages = [page.get_text("text") for page in pdf]
            if any(len(text.strip()) < 20 and page.get_images() for text, page in zip(pages, pdf, strict=True)):
                raise SourceError("needs_ocr", "Ada halaman berupa gambar tanpa text layer. Sediakan naskah resmi dengan teks lengkap; OCR otomatis belum tersedia.")
    except SourceError:
        raise
    except (RuntimeError, ValueError) as exc:
        raise SourceError("unreadable", "PDF rusak/belum selesai disalin. Selesaikan penyalinan lalu coba lagi.") from exc
    if not pages or not any(len(page.strip()) >= 20 for page in pages):
        raise SourceError("needs_ocr", "Ada halaman kosong/scan tanpa teks memadai. Sediakan PDF resmi dengan text layer lengkap; OCR otomatis belum tersedia.")
    return pages


def iso_date(value: str) -> str:
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return date.fromisoformat(value).isoformat()
    if re.fullmatch(r"\d{2}-\d{2}-\d{4}", value):
        return datetime.strptime(value, "%d-%m-%Y").date().isoformat()
    day, month, year = value.lower().split()
    return date(int(year), MONTHS.index(month) + 1, int(day)).isoformat()


def labeled_date(text: str, labels: str) -> str | None:
    values = {iso_date(match) for match in re.findall(rf"(?:{labels})\s*:?\s*({DATE})", text, re.IGNORECASE)}
    if len(values) > 1:
        raise SourceError("needs_metadata", "Tanggal pada sumber ambigu. Tambahkan halaman metadata resmi yang khusus untuk dokumen ini.")
    return next(iter(values), None)


def identify(text: str):
    clean = re.sub(r"\s+", " ", text)
    matches = [match for pattern in (LAW, CASE) if (match := pattern.search(clean))]
    match = min(matches, key=lambda value: value.start(), default=None)
    if not match:
        raise SourceError("needs_metadata", "Identitas jenis/nomor/tahun belum terbaca. Tambahkan halaman detail resmi khusus dokumen ini.")
    prefix = clean[:match.start()]
    if re.search(r"\b(?:IKHTISAR|RINGKASAN|ABSTRAK|RANCANGAN|DRAFT)\b", prefix, re.IGNORECASE):
        raise SourceError("unsupported", "Sumber adalah ringkasan/abstrak/rancangan, bukan naskah hukum lengkap.")
    if re.search(r"\b(?:PERATURAN (?:MENTERI|BADAN|DAERAH|KEPALA)|KEPUTUSAN (?:MENTERI|PRESIDEN)|SURAT EDARAN)\b", prefix, re.IGNORECASE):
        raise SourceError("unsupported", "Jenis dokumen utama belum didukung pengenal otomatis (saat ini UU, PP, Perpres, putusan MK); kutipan ke UU tidak menjadikannya UU.")
    if match.re is LAW:
        kind = re.sub(r"[ -]+", " ", match[1].upper())
        prefix, dtype = {"UNDANG UNDANG": ("UU", "undang-undang"), "PERATURAN PEMERINTAH": ("PP", "peraturan_pemerintah"), "PERATURAN PRESIDEN": ("PERPRES", "peraturan_presiden")}[kind]
        return f"{prefix}_{match[2]}_{match[3]}", dtype, match[2], int(match[3]), match
    return f"MK_{match[1]}_{match[2].replace('-', '_')}_{match[3]}", "putusan_mk", f"{match[1]}/{match[2]}", int(match[3]), match


def verify(data: bytes, source: dict, registry: list[dict]) -> dict:
    digest = hashlib.sha256(data).hexdigest()
    pages = pdf_pages(data)
    page_url = source["page_url"]
    page_data, page_url = fetch(page_url)
    if page_data.startswith(b"%PDF"):
        raise SourceError("needs_metadata", "Tautan sumber harus halaman detail resmi. Isi tautan PDF pada kolom PDF dan halaman detail pada kolom sumber.")
    page = Page(page_data, page_url)
    page_text = page.document_text
    evidence = [{"url": page_url, "sha256": hashlib.sha256(page_data).hexdigest()}]
    if source.get("metadata_url"):
        extra_data, extra_url = fetch(source["metadata_url"])
        if extra_data.startswith(b"%PDF"):
            raise SourceError("needs_metadata", "Halaman metadata tambahan harus halaman detail HTML resmi.")
        extra = Page(extra_data, extra_url)
        if identify(extra.document_text)[:4] != identify(page_text)[:4]:
            raise SourceError("mismatch", "Identitas halaman metadata tambahan berbeda.")
        page_text += " " + extra.document_text
        page.links.extend(extra.links)
        evidence.append({"url": extra_url, "sha256": hashlib.sha256(extra_data).hexdigest()})
    identity = identify(page_text)
    if identify(" ".join(pages[:2]))[:4] != identity[:4]:
        raise SourceError("mismatch", "Jenis/nomor/tahun halaman resmi tidak cocok dengan PDF lokal.")
    if re.search(r"\b(?:rancangan|rpp|draft|berita|siaran pers)\b", urlsplit(page_url).path, re.IGNORECASE):
        raise SourceError("unsupported", "Halaman berita/rancangan tidak dapat memverifikasi naskah hukum. Berikan halaman detail peraturan/putusan.")
    candidates = [source["pdf_url"]] if source.get("pdf_url") else [link for link in page.links if re.search(r"\.pdf(?:\?|$)|/unduh/|/download/|/DownloadUjiMateri/", link, re.IGNORECASE)]
    matches = []
    unavailable = False
    for url in list(dict.fromkeys(candidates))[:12]:
        try:
            official, final = fetch(url)
            if official.startswith(b"%PDF") and hashlib.sha256(official).hexdigest() == digest:
                matches.append(final)
        except (SourceError, OSError):
            unavailable = True
    if not matches:
        if not candidates or unavailable:
            raise SourceError("needs_source", "PDF resmi belum dapat dicocokkan. Isi tautan unduhan PDF resmi secara langsung lalu coba lagi.")
        raise SourceError("mismatch", "SHA-256 PDF lokal berbeda dari naskah lengkap resmi. Gunakan file unduhan resmi yang persis sama.")
    doc_id, dtype, number, year, match = identity
    compact_pdf = re.sub(r"\s+", " ", " ".join(pages))
    if re.search(r"\b(?:RANCANGAN|DRAFT)\b", " ".join(pages[:2]), re.IGNORECASE):
        raise SourceError("unsupported", "PDF adalah rancangan; tidak masuk corpus hukum terverifikasi.")
    if dtype == "putusan_mk":
        if not re.search(r"\bMENGADILI\b", compact_pdf, re.IGNORECASE):
            raise SourceError("needs_metadata", "PDF belum terbukti salinan putusan lengkap dengan amar MENGADILI.")
        if not re.search(r"status putusan\s*:?\s*tetap\b", page_text, re.IGNORECASE):
            raise SourceError("needs_metadata", "Status Putusan Tetap belum ditemukan pada halaman resmi; tambahkan halaman metadata resmi.")
        decision = labeled_date(page_text, r"tanggal (?:putusan|dibacakan)|tanggal-bulan-tahun dibacakan|diputus(?:kan)? pada")
        if not decision:
            raise SourceError("needs_metadata", "Tanggal putusan belum tersedia; tambahkan halaman metadata resmi yang mencantumkan tanggal putusan.")
        title = f"Putusan Mahkamah Konstitusi Nomor {number}/{year}"
        adopted = promulgated = effective = None
        legal = "Salinan putusan penuh cocok SHA-256; tanggal putusan dari halaman resmi. Amar harus dibaca pada sumber."
    else:
        # shortcut: supported portals must expose explicit dates/status; other layouts request a supplementary official page.
        if not re.search(r"(?:status(?: peraturan)?\s*:?\s*berlaku)\b", page_text, re.IGNORECASE) or re.search(r"status(?: peraturan)?\s*:?\s*(?:tidak berlaku|dicabut)", page_text, re.IGNORECASE):
            raise SourceError("needs_metadata", "Status Berlaku belum eksplisit pada metadata resmi; tambahkan halaman resmi dengan status peraturan.")
        adopted = labeled_date(page_text, r"tanggal (?:penetapan|ditetapkan)|ditetapkan tanggal")
        promulgated = labeled_date(page_text, r"tanggal (?:pengundangan|diundangkan)|diundangkan tanggal")
        effective = labeled_date(page_text, r"tanggal (?:berlaku|mulai berlaku)|berlaku mulai")
        if effective is None and re.search(r"mulai berlaku pada tanggal diundangkan", compact_pdf, re.IGNORECASE):
            effective = promulgated
        if not adopted or not promulgated or not effective:
            raise SourceError("needs_metadata", "Tanggal penetapan/pengundangan/mulai berlaku belum lengkap. Tambahkan halaman metadata resmi; tanggal tidak ditebak.")
        primary_title = next(iter(page.fields.get("judul", [])), None) or next((heading for heading in page.headings if LAW.search(heading)), "")
        title_match = re.search(r"\btentang\s+(.+)", primary_title, re.IGNORECASE)
        if not title_match:
            raise SourceError("needs_metadata", "Judul lengkap belum terbaca dari metadata resmi.")
        subject = title_match[1].strip()
        normalized_subject = re.sub(r"\W", "", subject).lower()
        if len(subject) < 5 or normalized_subject not in re.sub(r"\W", "", " ".join(pages[:3])).lower():
            raise SourceError("mismatch", "Judul pada halaman resmi belum cocok dengan judul PDF. Gunakan halaman detail khusus dokumen ini.")
        title = f"{match[1].title()} Nomor {number} Tahun {year} tentang {subject}"
        decision = None
        legal = f"Status Berlaku tercantum pada halaman resmi; tanggal mulai berlaku {effective}."
    references = {identify(found.group())[0] for pattern in (LAW, CASE) for found in pattern.finditer(page_text)}
    related = [doc["document_id"] for doc in registry if doc["document_id"] != doc_id and doc["document_id"] in references]
    now = datetime.now(UTC).isoformat()
    return {"document_id": doc_id, "title": title, "document_type": dtype, "number": number, "year": year,
            "issuer": "Mahkamah Konstitusi Republik Indonesia" if dtype == "putusan_mk" else "Pemerintah Republik Indonesia",
            "source_kind": "judgment_full_text" if dtype == "putusan_mk" else "regulation_full_text",
            "official_source_url": page_url, "download_url": matches[0], "adopted_date": adopted,
            "promulgated_date": promulgated, "effective_from": effective, "decision_date": decision,
            "status": "verified", "corpus_eligible": True, "sha256": digest, "verified_at_utc": now,
            "artifact_verified_at_utc": now, "legal_status_note": legal, "related_document_ids": related,
            "verification_evidence": evidence, "notes": "Verifikasi otomatis konservatif; corpus tidak lengkap. Relasi kandidat tercatat dari referensi sumber resmi, bukan penafsiran efek hukum."}
