"""So sánh công bằng: CNN 1D trên I/Q thô vs STFT + CNN 2D, CÙNG một bộ dữ liệu."""

import numpy as np
import torch
import torch.nn as nn

from edge_ai.config import CACHE_DIR, MODELS_DIR, RESULTS_DIR, RF_CLASSES  # noqa: F401
from edge_ai.io_utils import read_json, write_json
from edge_ai.ml.nets import RFNet, count_params
from edge_ai.training.train_detect import confusion, evaluate

torch.set_num_threads(2)
d = np.load(CACHE_DIR / "rf_cache.npz")
Xtr, ytr, Xva, yva, Xte, yte = (d[k] for k in ["Xtr", "ytr", "Xva", "yva", "Xte", "yte"])
m = RFNet(len(RF_CLASSES))
bs, ep_n, lr = 64, 14, 2e-3
opt = torch.optim.AdamW(m.parameters(), lr=lr, weight_decay=1e-4)
sch = torch.optim.lr_scheduler.OneCycleLR(
    opt, max_lr=lr, total_steps=ep_n * int(np.ceil(len(ytr) / bs))
)
lf = nn.CrossEntropyLoss(label_smoothing=0.05)
dl = torch.utils.data.DataLoader(
    torch.utils.data.TensorDataset(torch.from_numpy(Xtr), torch.from_numpy(ytr)),
    batch_size=bs,
    shuffle=True,
)
best, st = 0.0, None
for ep in range(ep_n):
    m.train()
    for xb, yb in dl:
        opt.zero_grad()
        l = lf(m(xb), yb)
        l.backward()
        nn.utils.clip_grad_norm_(m.parameters(), 2.0)
        opt.step()
        sch.step()
    _, a = evaluate(m, Xva, yva)
    if a > best:
        best, st = a, {k: v.clone() for k, v in m.state_dict().items()}
    print(f"  ep{ep + 1:02d} val={a:.4f}", flush=True)
m.load_state_dict(st)
p, acc = evaluate(m, Xte, yte)
print(f"[ablation raw I/Q 1D-CNN] TEST acc={acc:.4f} params={count_params(m)}")
print(confusion(yte, p, 4))
mt = read_json(RESULTS_DIR / "rf_metrics.json")
mt["ablation_raw_iq_1dcnn_acc"] = float(acc)
mt["ablation_note"] = "Cùng bộ dữ liệu, cùng số epoch, cùng số tham số (62k)."
write_json(RESULTS_DIR / "rf_metrics.json", mt)
