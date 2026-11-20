"""Huấn luyện hai bộ phát hiện sớm: RF (I/Q) và radar (micro-Doppler).

Chạy:  python3 train_detect.py rf     |  python3 train_detect.py md
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

from edge_ai.config import RADAR_CLASSES, RF_CLASSES, SEED
from edge_ai.ml.nets import MicroDopplerNet, RFNet, count_params

from edge_ai.config import CACHE_DIR, MODELS_DIR, RESULTS_DIR  # noqa: F401
for _d in (MODELS_DIR, RESULTS_DIR, CACHE_DIR):
    _d.mkdir(parents=True, exist_ok=True)
torch.set_num_threads(2)


def _loader(X, y, bs, shuffle):
    ds = torch.utils.data.TensorDataset(torch.from_numpy(X), torch.from_numpy(y))
    return torch.utils.data.DataLoader(ds, batch_size=bs, shuffle=shuffle)


def evaluate(model, X, y, bs=128):
    model.eval()
    preds = []
    with torch.no_grad():
        for i in range(0, len(X), bs):
            preds.append(model(torch.from_numpy(X[i:i + bs])).argmax(1).numpy())
    p = np.concatenate(preds)
    return p, (p == y).mean()


def confusion(y, p, n):
    m = np.zeros((n, n), dtype=int)
    for a, b in zip(y, p):
        m[a, b] += 1
    return m


def run(kind: str):
    t0 = time.time()
    if kind == "rf":
        from edge_ai.sim.rf_sim import build_rf_dataset
        classes = RF_CLASSES
        Xtr, ytr = build_rf_dataset(2200, SEED)
        Xva, yva = build_rf_dataset(500, SEED + 1)
        Xte, yte = build_rf_dataset(700, SEED + 2)
        model, bs, epochs, lr = RFNet(len(classes)), 64, 14, 2e-3
    else:
        from edge_ai.sim.radar_sim import build_md_dataset
        classes = RADAR_CLASSES
        Xtr, ytr = build_md_dataset(2200, SEED + 10)
        Xva, yva = build_md_dataset(500, SEED + 11)
        Xte, yte = build_md_dataset(700, SEED + 12)
        model, bs, epochs, lr = MicroDopplerNet(len(classes)), 64, 16, 2e-3

    print(f"[{kind}] train={Xtr.shape} val={Xva.shape} test={Xte.shape} "
          f"params={count_params(model):,} datagen={time.time()-t0:.0f}s", flush=True)

    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(
        opt, max_lr=lr, total_steps=epochs * int(np.ceil(len(ytr) / bs)))
    lossf = nn.CrossEntropyLoss(label_smoothing=0.05)
    tr = _loader(Xtr, ytr, bs, True)

    best, best_state = 0.0, None
    for ep in range(epochs):
        model.train()
        tot = 0.0
        for xb, yb in tr:
            opt.zero_grad()
            loss = lossf(model(xb), yb)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 2.0)
            opt.step()
            sched.step()
            tot += loss.item() * len(yb)
        _, acc = evaluate(model, Xva, yva)
        if acc > best:
            best = acc
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
        print(f"  ep{ep+1:02d} loss={tot/len(ytr):.4f} val_acc={acc:.4f}", flush=True)

    model.load_state_dict(best_state)
    p, acc = evaluate(model, Xte, yte)
    cm = confusion(yte, p, len(classes))
    per = {c: float(cm[i, i] / cm[i].sum()) for i, c in enumerate(classes)}
    print(f"[{kind}] TEST acc={acc:.4f}")
    print("        " + "".join(f"{c[:9]:>11s}" for c in classes))
    for i, c in enumerate(classes):
        print(f"{c[:8]:>8s}" + "".join(f"{v:11d}" for v in cm[i]))

    torch.save(model.state_dict(), MODELS_DIR / f"{kind}_model.pt")
    json.dump({"test_acc": float(acc), "per_class": per,
               "confusion": cm.tolist(), "classes": classes,
               "params": count_params(model), "n_test": int(len(yte))},
              open(RESULTS_DIR / f"{kind}_metrics.json", "w", encoding="utf-8"), indent=1)
    np.savez_compressed(CACHE_DIR / f"{kind}_test.npz", X=Xte[:1500], y=yte[:1500])
    print(f"[{kind}] done in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "rf")
