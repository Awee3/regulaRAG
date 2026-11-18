"""Optional CPU ONNX cross-encoder reranking for hybrid candidates."""

from __future__ import annotations

import threading

from app.config import CONFIG

RERANKER_MODEL = CONFIG["reranker"]["model"]
RERANKER_REVISION = CONFIG["reranker"]["revision"]
RERANKER_MAX_LENGTH = CONFIG["reranker"]["max_length"]
_runtime = None
_runtime_lock = threading.Lock()


class RerankerUnavailable(RuntimeError):
    """Raised when optional ONNX reranker dependencies or weights are unavailable."""


def _load_runtime():
    global _runtime
    if _runtime is None:
        try:
            import onnxruntime
            from huggingface_hub import hf_hub_download
            from transformers import AutoTokenizer
        except ImportError as exc:
            raise RerankerUnavailable('Reranking needs the optional dependencies. Install with: python -m pip install -e ".[rerank]"') from exc
        try:
            model_path = hf_hub_download(
                RERANKER_MODEL, "onnx/model_quantized.onnx", revision=RERANKER_REVISION,
            )
            tokenizer = AutoTokenizer.from_pretrained(RERANKER_MODEL, revision=RERANKER_REVISION)
            session = onnxruntime.InferenceSession(model_path, providers=["CPUExecutionProvider"])
        except Exception as exc:
            raise RerankerUnavailable(
                f"Model reranker {RERANKER_MODEL} tidak dapat dimuat. Periksa koneksi unduhan atau cache lokal."
            ) from exc
        _runtime = tokenizer, session, {item.name for item in session.get_inputs()}
    return _runtime


def rerank(question: str, candidates: list[dict], top_k: int) -> list[dict]:
    if not 1 <= top_k <= min(20, len(candidates)):
        raise ValueError("top_k reranker harus berada dalam rentang 1 sampai jumlah kandidat (maksimum 20).")
    with _runtime_lock:
        tokenizer, session, input_names = _load_runtime()
        encoded = tokenizer(
            [question] * len(candidates), [item["text"] for item in candidates],
            padding=True, truncation=True, max_length=RERANKER_MAX_LENGTH, return_tensors="np",
        )
        inputs = {name: encoded[name] for name in input_names}
        scores = session.run(None, inputs)[0].reshape(-1)
        ranked = sorted(zip(scores, candidates), key=lambda pair: (-float(pair[0]), pair[1]["chunk_id"]))
        return [dict(item, rerank_score=float(score)) for score, item in ranked[:top_k]]


def release_runtime():
    """Release ONNX weights before generation."""
    global _runtime
    with _runtime_lock:
        _runtime = None
