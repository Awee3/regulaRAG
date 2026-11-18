"""Measure one configuration in a fresh process; compare saved reports, not guesses."""
import argparse
import ctypes
import json
import platform
import subprocess
import threading
import time
from ctypes import wintypes
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import urlopen

from app.generation import OLLAMA_MODEL, OLLAMA_NUM_CTX
from app.main import QueryRequest, query
from app.search import EMBEDDING_MODEL


def peak_ram():
    if platform.system() != "Windows":
        return None
    class MemoryCounters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [(name, ctypes.c_size_t) for name in (
            "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
            "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
    counters = MemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(MemoryCounters), wintypes.DWORD]
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    return counters.PeakWorkingSetSize


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("--mode", choices=["bm25", "dense", "hybrid", "hybrid_rerank"], default="bm25")
    cli.add_argument("--output", type=Path, required=True)
    args = cli.parse_args()
    stop = threading.Event()
    vram = []
    def sample():
        while not stop.is_set():
            try:
                result = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"], check=False, capture_output=True, text=True, timeout=3)
                if result.returncode == 0:
                    vram.extend(int(line) for line in result.stdout.splitlines())
            except (OSError, ValueError, subprocess.TimeoutExpired):
                pass
            stop.wait(1)
    monitor = threading.Thread(target=sample, daemon=True)
    monitor.start()
    started = time.perf_counter()
    try:
        result = query(QueryRequest(question="Apa isi Pasal 46 mengenai kegagalan pelindungan data pribadi?", document_ids=["UU_27_2022"], retrieval_mode=args.mode, top_k=1))
    finally:
        stop.set()
        monitor.join(timeout=4)
    with urlopen("http://127.0.0.1:11434/api/version", timeout=5) as response:
        runtime = json.load(response)
    report = {"generated_at_utc": datetime.now(UTC).isoformat(), "platform": platform.platform(),
              "ollama": runtime, "model": OLLAMA_MODEL, "embedding_model": EMBEDDING_MODEL,
              "num_ctx": OLLAMA_NUM_CTX, "retrieval_mode": args.mode,
              "end_to_end_seconds": time.perf_counter()-started,
              "peak_sampled_total_gpu_memory_mib": max(vram) if vram else None,
              "python_peak_ram_bytes": peak_ram(), "ram_note": "Python process peak only, excludes Ollama; GPU sample includes other processes; keep_alive=0 unloads model after query.",
              "result": result}
    metrics = result.get("runtime_metrics") or {}
    duration = metrics.get("eval_duration")
    report["tokens_per_second"] = metrics.get("eval_count", 0)/(duration/1e9) if duration else None
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
