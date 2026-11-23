"""Học nhiệt độ T cho hai bộ phân loại (RF, micro-Doppler) và đo ECE trước/sau.

Dữ liệu là dữ liệu MÔ PHỎNG, sinh lại đúng như lúc huấn luyện
(training/train_detect.py, train_rf2.py), cùng hạt giống:

* tập kiểm định (học T):  RF ``SEED + 1``, micro-Doppler ``SEED + 11``, 500 mẫu/lớp
* tập test (báo cáo số):   RF ``SEED + 2``, micro-Doppler ``SEED + 12``, 700 mẫu/lớp

Tập test không bao giờ dùng để học T. Lưu ý: tập kiểm định cũng là tập đã
dùng để chọn epoch tốt nhất khi huấn luyện — đó là cách làm chuẩn của
temperature scaling (Guo và cộng sự, 2017), không đụng vào tập test.

Chạy:  python -m edge_ai.experiments.calibrate
Ghi:   data/models/calibration.json  (T, dùng lúc suy luận)
       data/results/calibration.json (số đo trước/sau)
"""

from __future__ import annotations

import time

import numpy as np
import torch

from edge_ai.config import MODELS_DIR, RESULTS_DIR, SEED
from edge_ai.io_utils import utf8_stdio, write_json
from edge_ai.ml.calibration import ECE_BINS, fit_temperature, report, save_temperatures
from edge_ai.tracking.pipeline import load_models

torch.set_num_threads(2)

VAL_N, TEST_N = 500, 700  # mẫu mỗi lớp, như lúc huấn luyện


def logits_of(model, X: np.ndarray, bs: int = 128) -> np.ndarray:
    model.eval()
    out = []
    with torch.no_grad():
        for i in range(0, len(X), bs):
            out.append(model(torch.from_numpy(X[i : i + bs])).numpy())
    return np.concatenate(out).astype(np.float64)


def calibrate_one(name: str, model, build, val_seed: int, test_seed: int) -> dict:
    Xva, yva = build(VAL_N, val_seed)
    Xte, yte = build(TEST_N, test_seed)
    T = fit_temperature(logits_of(model, Xva), yva)
    r = report(logits_of(model, Xte), yte, T)
    r.update(T=T, n_val=int(len(yva)), n_test=int(len(yte)))
    print(
        f"[{name}] T={T:.4f}  ECE {r['ece_before']:.4f} -> {r['ece_after']:.4f}  "
        f"NLL {r['nll_before']:.4f} -> {r['nll_after']:.4f}  "
        f"acc {r['acc_before']:.4f} -> {r['acc_after']:.4f}",
        flush=True,
    )
    return r


def main() -> dict:
    from edge_ai.sim.radar_sim import build_md_dataset
    from edge_ai.sim.rf_sim import build_rf_dataset

    utf8_stdio()
    t0 = time.time()
    rf, md, _ = load_models()
    res = {
        "rf": calibrate_one("rf", rf, build_rf_dataset, SEED + 1, SEED + 2),
        "md": calibrate_one("md", md, build_md_dataset, SEED + 11, SEED + 12),
    }
    save_temperatures(
        MODELS_DIR,
        {k: {"T": round(v["T"], 6), "fit_on": f"val n={v['n_val']}"} for k, v in res.items()},
    )
    res["ece_bins"] = ECE_BINS
    res["note"] = (
        "Dữ liệu MÔ PHỎNG (sim/rf_sim.py, sim/radar_sim.py), không phải dữ liệu "
        "thật. T học trên tập kiểm định, số đo trên tập test tách riêng."
    )
    write_json(RESULTS_DIR / "calibration.json", res)
    print(f"done {time.time() - t0:.0f}s")
    return res


if __name__ == "__main__":
    main()
