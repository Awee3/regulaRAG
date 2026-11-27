"""Small local Streamlit interface for the RegulaRAG query pipeline."""

from __future__ import annotations

import streamlit as st
from fastapi import HTTPException

from app.main import (
    DISCLAIMER,
    IMPORTER,
    ImportSourceRequest,
    QueryRequest,
    documents,
    get_imports,
    query,
    set_import_source,
)

st.set_page_config(page_title="RegulaRAG Indonesia", page_icon="📚", layout="wide")
st.title("RegulaRAG Indonesia")
st.caption("Pencarian dokumen Pelindungan Data Pribadi berbasis sumber lokal.")
IMPORTER.start()


@st.fragment(run_every="3s")
def inbox_panel():
    with st.expander("Impor PDF dari folder data/inbox", expanded=True):
        st.caption("Salin PDF resmi yang dapat dicari ke data/inbox. Pemindaian berjalan selama UI/API terbuka dan dilanjutkan pada peluncuran berikutnya. Hanya tautan sumber resmi yang diunduh; file lokal tidak diunggah.")
        jobs = get_imports()
        ready = tuple((job["sha256"], job.get("document_id")) for job in jobs if job["status"] == "ready")
        previous = st.session_state.get("inbox_ready")
        st.session_state["inbox_ready"] = ready
        if previous is not None and previous != ready:
            st.rerun()
        if not jobs:
            st.info("Menunggu PDF selesai disalin ke data/inbox…")
        for job in jobs:
            st.write(" · ".join(job["filenames"]))
            st.caption(f"{job['status']}: {job['message']}")
            if job["status"] not in {"ready", "checking_source", "indexing"}:
                with st.form(f"source-{job['sha256']}"):
                    page_url = st.text_input("Halaman detail resmi", key=f"page-{job['sha256']}")
                    pdf_url = st.text_input("Tautan PDF resmi langsung (opsional)", key=f"pdf-{job['sha256']}")
                    metadata_url = st.text_input("Halaman metadata resmi tambahan (opsional)", key=f"meta-{job['sha256']}")
                    if st.form_submit_button("Periksa sumber / coba lagi"):
                        try:
                            set_import_source(job["sha256"], ImportSourceRequest(page_url=page_url, pdf_url=pdf_url or None, metadata_url=metadata_url or None))
                            st.success("Sumber masuk antrean pemeriksaan.")
                        except (HTTPException, ValueError) as exc:
                            st.error(getattr(exc, "detail", str(exc)))
        if st.button("Perbarui daftar dokumen"):
            st.rerun()


inbox_panel()

all_documents = documents()
for doc in all_documents:
    if doc["not_yet_effective"]:
        st.caption(f"{doc['title']} belum berlaku. Mulai berlaku pada {doc['effective_from']}.")
eligible_documents = [doc for doc in all_documents if doc.get("corpus_eligible")]
verified_at = max((doc.get("artifact_verified_at_utc") or doc.get("verified_at_utc") or "" for doc in all_documents), default="")
st.info(f"Corpus berisi {len(eligible_documents)} dokumen aktif. Verifikasi corpus terakhir tercatat: {verified_at or 'tidak tersedia'}.")
st.warning("Teks hasil ekstraksi PDF dapat kehilangan atau mengubah kata. Buka PDF resmi untuk memeriksa bunyi kutipan sebelum mengandalkannya.")

with st.form("query"):
    question = st.text_area("Pertanyaan", placeholder="Contoh: Apa yang harus dilakukan setelah terjadi kegagalan pelindungan data?", max_chars=2000)
    retrieval_mode = st.selectbox(
        "Metode pencarian", ["bm25", "dense", "hybrid", "hybrid_rerank"], index=0,
        format_func={"bm25": "BM25 — pencocokan kata", "dense": "Dense — kemiripan makna", "hybrid": "Hybrid — gabungan keduanya", "hybrid_rerank": "Hybrid + reranker CPU (opsional)"}.get,
    )
    selected_ids = st.multiselect(
        "Batasi dokumen (opsional)", [doc["document_id"] for doc in eligible_documents],
        format_func={doc["document_id"]: doc["title"] for doc in eligible_documents}.get,
    )
    submitted = st.form_submit_button("Cari dan jawab", type="primary")

if submitted:
    st.session_state.pop("result", None)
    if len(question.strip()) < 3:
        st.error("Masukkan pertanyaan minimal 3 karakter.")
    else:
        try:
            with st.spinner("Mencari bukti dan menyusun jawaban dari model lokal…"):
                st.session_state["result"] = query(QueryRequest(
                    question=question, retrieval_mode=retrieval_mode,
                    document_ids=selected_ids or None,
                ))
        except HTTPException as exc:
            st.error(exc.detail)

result = st.session_state.get("result")
if result:
    st.subheader("Jawaban")
    st.caption("Model memilih kutipan asli; periksa apakah sumber menjawab pertanyaan Anda.")
    if result["abstained"]:
        st.warning("Sistem abstain: bukti belum cukup untuk menjawab dengan yakin.")
    else:
        st.success("Jawaban berbasis bukti yang ditemukan.")
    if result.get("answer"):
        st.write(result["answer"])
    if result.get("detail"):
        st.caption(result["detail"])
    st.caption(f"Metode retrieval: {result['retrieval_mode']}")

    st.subheader("Sumber dan kutipan")
    if not result["citations"]:
        st.info("Tidak ada kutipan yang ditemukan dalam dokumen aktif.")
    for citation in result["citations"]:
        location = " · ".join(value for value in (citation.get("article"), citation.get("paragraph")) if value)
        pages = citation.get("page_start")
        if pages is not None:
            pages = f"halaman {pages}" if pages == citation.get("page_end") else f"halaman {pages}–{citation.get('page_end')}"
        title = citation["document_title"]
        if location:
            title += f" · {location}"
        if pages:
            title += f" · {pages}"
        with st.expander(title):
            st.caption(f"Status: {citation.get('status') or 'tidak tercatat'} · Berlaku sejak: {citation.get('effective_from') or 'tidak tercatat'}")
            if citation.get("source_url"):
                st.link_button("Buka sumber resmi", citation["source_url"])
            st.text(citation["quote"])

    st.caption(result.get("disclaimer", DISCLAIMER))

st.divider()
st.caption("Corpus tidak lengkap dan mungkin belum mencakup perubahan terbaru. Hasil ini adalah alat bantu penelusuran dokumen, bukan nasihat hukum.")
