"""Đo các con số quyết định việc có đặt được lên thiết bị biên hay không.

Báo cáo chính chỉ có thời gian xử lý cả khung. Trên Jetson thứ cần biết
thêm là: mỗi mô hình nặng bao nhiêu (tham số, dung lượng tệp), một lần suy
luận mất bao lâu ở batch 1, và khung XẤU NHẤT — khi mạng RF và mạng radar
rơi vào cùng một khung — tốn bao nhiêu so với ngân sách 50 ms.

Chạy trên máy đích (Jetson, Raspberry Pi, x86...) để có số của chính nó:

    cd src && python bench_edge.py            # in ra và ghi data/edge_bench.json
    cd src && python bench_edge.py --threads 4
"""
from __future__ import annotations

import argparse
import json
import platform
import time
from pathlib import Path

import numpy as np
import torch

from config import LATENCY_BUDGET_MS, MD_EVERY, RF_EVERY
from models import count_params
from pipeline import DATA, HIST, MODEL_FILES, Pipeline, load_models, warmup
from mtt import MAX_IQ_PER_FRAME, MAX_SPEC_PER_FRAME
from sensors import md_due, rf_due


def _bench(fn, n: int) -> dict:
    for _ in range(10):
        fn()
    ts = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        ts.append((time.perf_counter() - t0) * 1e3)
    a = np.asarray(ts)
    return {"mean_ms": round(float(a.mean()), 3),
            "p50_ms": round(float(np.percentile(a, 50)), 3),
            "p99_ms": round(float(np.percentile(a, 99)), 3),
            "max_ms": round(float(a.max()), 3), "n": n}


def main(threads: int = 2, n: int = 300, out: Path | None = DATA / "edge_bench.json"):
    torch.set_num_threads(threads)
    models = load_models()
    warmup(models)
    rf, md, tj = models
    iq = torch.randn(1, 2, 2048)
    sp = torch.rand(1, 1, 64, 128)
    x = torch.randn(1, HIST, 6)
    res = {"host": {"machine": platform.machine(), "processor": platform.processor(),
                    "python": platform.python_version(), "torch": torch.__version__,
                    "threads": threads},
           "budget_ms": LATENCY_BUDGET_MS, "models": {}}
    with torch.no_grad():
        for name, m, inp, f in (("rf_stft_cnn", rf, iq, MODEL_FILES[0]),
                                ("micro_doppler_cnn", md, sp, MODEL_FILES[1]),
                                ("traj_transformer", tj, x, MODEL_FILES[2])):
            res["models"][name] = {
                "params": count_params(m),
                "file_kb": round((DATA / f).stat().st_size / 1024, 1),
                "fp32_weights_kb": round(count_params(m) * 4 / 1024, 1),
                "latency": _bench(lambda m=m, inp=inp: m(inp), n)}
        # Khung xấu nhất NẾU hai mạng nặng chạy cùng khung (bản cũ: 6,7% số
        # khung; bản mới: không bao giờ — xem sensors.rf_due).
        res["worst_frame_rf_plus_md"] = _bench(lambda: (rf(iq), md(sp)), n)
        # Khung nặng nhất có thể xảy ra khi bám nhiều mục tiêu: trần của
        # mtt.py là 2 ảnh phổ (một batch) + 1 đoạn I/Q mỗi khung.
        sp2 = torch.rand(MAX_SPEC_PER_FRAME, 1, 64, 128)
        iqn = torch.randn(MAX_IQ_PER_FRAME, 2, 2048)
        res["mtt_capped_frame_nets"] = _bench(lambda: (md(sp2), rf(iqn)), n)
    pipe = Pipeline(models)

    hist = [(np.random.randn(3) * 100, np.random.randn(3)) for _ in range(HIST)]
    res["blackout_full_rollout_9s"] = _bench(lambda: pipe.rollout(hist, 90), max(30, n // 10))
    res["blackout_one_extension_1s"] = _bench(
        lambda: pipe._extend(np.zeros((0, 3)), hist), n)
    res["schedule"] = {"rf_every_frames": RF_EVERY, "md_every_frames": MD_EVERY,
                       "frames_with_both_nets_pct": round(100 * float(np.mean(
                           [rf_due(k) and md_due(k) for k in range(600)])), 1),
                       "rf_runs_per_s": round(sum(rf_due(k) for k in range(600)) / 60, 2)}
    print(json.dumps(res, indent=1, ensure_ascii=False))
    if out is not None:
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(res, fh, indent=1, ensure_ascii=False)
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--no-save", action="store_true")
    a = ap.parse_args()
    main(a.threads, a.n, None if a.no_save else DATA / "edge_bench.json")
