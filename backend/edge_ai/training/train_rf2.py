"""Huấn luyện bộ phân loại RF phiên bản STFT và so sánh công bằng với bản I/Q thô.

Hai mô hình dùng CHUNG một bộ dữ liệu (cùng hạt giống, cùng mẫu), nên chênh
lệch độ chính xác là của riêng kiến trúc chứ không phải do dữ liệu khác nhau.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

from edge_ai.config import RF_CLASSES, SEED
from edge_ai.ml.nets import count_params
from edge_ai.sim.rf_sim import build_rf_dataset
from edge_ai.ml.rf_stft import RFNetSTFT
from edge_ai.training.train_detect import confusion, evaluate

from edge_ai.config import CACHE_DIR, MODELS_DIR, RESULTS_DIR  # noqa: F401
torch.set_num_threads(2)


def main():
    t0 = time.time()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / "rf_cache.npz"
    if cache.exists():
        d = np.load(cache)
        Xtr, ytr, Xva, yva, Xte, yte = (d[k] for k in
                                        ["Xtr", "ytr", "Xva", "yva", "Xte", "yte"])
    else:
        Xtr, ytr = build_rf_dataset(2200, SEED)
        Xva, yva = build_rf_dataset(500, SEED + 1)
        Xte, yte = build_rf_dataset(700, SEED + 2)
        np.savez(cache, Xtr=Xtr, ytr=ytr, Xva=Xva, yva=yva, Xte=Xte, yte=yte)
    print(f"[rf2] data {Xtr.shape} in {time.time()-t0:.0f}s", flush=True)

    model = RFNetSTFT(len(RF_CLASSES))
    print(f"[rf2] params={count_params(model):,}", flush=True)
    bs, epochs, lr = 64, 14, 2e-3
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(
        opt, max_lr=lr, total_steps=epochs * int(np.ceil(len(ytr) / bs)))
    lossf = nn.CrossEntropyLoss(label_smoothing=0.05)
    ds = torch.utils.data.TensorDataset(torch.from_numpy(Xtr), torch.from_numpy(ytr))
    dl = torch.utils.data.DataLoader(ds, batch_size=bs, shuffle=True)

    best, state = 0.0, None
    for ep in range(epochs):
        model.train()
        tot = 0.0
        for xb, yb in dl:
            opt.zero_grad()
            loss = lossf(model(xb), yb)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 2.0)
            opt.step()
            sched.step()
            tot += loss.item() * len(yb)
        _, acc = evaluate(model, Xva, yva)
        if acc > best:
            best, state = acc, {k: v.clone() for k, v in model.state_dict().items()}
        print(f"  ep{ep+1:02d} loss={tot/len(ytr):.4f} val_acc={acc:.4f}", flush=True)

    model.load_state_dict(state)
    p, acc = evaluate(model, Xte, yte)
    cm = confusion(yte, p, len(RF_CLASSES))
    print(f"[rf2] TEST acc={acc:.4f}")
    print("        " + "".join(f"{c[:9]:>11s}" for c in RF_CLASSES))
    for i, c in enumerate(RF_CLASSES):
        print(f"{c[:8]:>8s}" + "".join(f"{v:11d}" for v in cm[i]))

    # độ chính xác theo SNR: thước đo có ý nghĩa với người làm vô tuyến
    rng = np.random.default_rng(SEED + 99)
    by_snr = {}
    for lo, hi in [(-6, 0), (0, 6), (6, 12), (12, 18), (18, 24)]:
        Xs, ys = build_rf_dataset(120, int(rng.integers(1e6)), snr_range=(lo, hi))
        _, a = evaluate(model, Xs, ys)
        by_snr[f"{lo}..{hi} dB"] = round(float(a), 4)
        print(f"  SNR {lo:3d}..{hi:3d} dB -> acc {a:.4f}", flush=True)

    torch.save(model.state_dict(), MODELS_DIR / "rf_model.pt")
    old = {}
    p_old = RESULTS_DIR / "rf_metrics.json"
    if p_old.exists():
        old = json.load(open(p_old, encoding="utf-8"))
    json.dump({"test_acc": float(acc), "confusion": cm.tolist(),
               "classes": RF_CLASSES, "params": count_params(model),
               "by_snr": by_snr, "arch": "STFT + CNN 2D",
               "ablation_raw_iq_1dcnn_acc": old.get("test_acc"),
               "n_test": int(len(yte))},
              open(RESULTS_DIR / "rf_metrics.json", "w", encoding="utf-8"), indent=1)
    print(f"[rf2] done {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
