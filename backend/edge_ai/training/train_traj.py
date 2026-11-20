"""Huấn luyện Transformer dự đoán quỹ đạo khi mất dấu, và so với EKF.

Bài toán: cho 20 bước quá khứ (2 giây), dự đoán 10 bước tới (1 giây). Khi
mục tiêu bị che khuất hoặc tín hiệu rớt, EKF chỉ còn biết ngoại suy theo mô
hình vận tốc không đổi, nên mục tiêu đang lượn vòng là nó trôi ra ngoài.
Transformer thấy được cả đoạn quá khứ nên nhận ra khuôn lượn và bám theo.

So sánh được thực hiện trên cùng một tập quỹ đạo kiểm thử, cùng một điểm bắt
đầu mất dấu, nên con số chênh lệch là của riêng mô hình.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

from edge_ai.config import FRAME_DT, SEED
from edge_ai.ml.nets import TrajTransformer, count_params
from edge_ai.sim.scene import TARGET_KINDS, make_trajectory

from edge_ai.config import CACHE_DIR, MODELS_DIR, RESULTS_DIR  # noqa: F401
for _d in (MODELS_DIR, RESULTS_DIR, CACHE_DIR):
    _d.mkdir(parents=True, exist_ok=True)
torch.set_num_threads(2)

HIST, HOR = 20, 10
POS_SCALE, VEL_SCALE = 100.0, 30.0    # chuẩn hóa về cỡ đơn vị


def _windows(p: np.ndarray, v: np.ndarray):
    """Cắt cửa sổ (quá khứ, tương lai) từ một quỹ đạo, toạ độ TƯƠNG ĐỐI.

    Dùng toạ độ tương đối so với điểm quan sát cuối: mô hình học hình dạng
    chuyển động, không học vị trí tuyệt đối trong hiện trường. Nhờ vậy nó
    dùng được ở mọi cự ly và hướng.
    """
    X, Y = [], []
    for i in range(HIST, len(p) - HOR):
        p0 = p[i - 1]
        X.append(np.concatenate([(p[i - HIST:i] - p0) / POS_SCALE,
                                 v[i - HIST:i] / VEL_SCALE], axis=1))
        Y.append((p[i:i + HOR] - p0) / POS_SCALE)
    return np.asarray(X, np.float32), np.asarray(Y, np.float32)


def build(n_traj: int, seed: int, noise=(1.0, 12.0)):
    """Sinh dữ liệu huấn luyện VỚI MỨC NHIỄU ĐÚNG NHƯ LÚC CHẠY THẬT.

    Lần đầu mình huấn luyện với nhiễu 1,5 m rồi đem chạy trong hệ thống thật,
    nơi lịch sử đưa vào là ước lượng của EKF sai số 8–12 m ở cự ly 1–2 km.
    Mô hình gần như không hơn được phép ngoại suy vận tốc không đổi: nó chưa
    bao giờ thấy đầu vào nhiễu đến thế. Đây là lỗi lệch giữa lúc huấn luyện
    và lúc phục vụ. Cách sửa là bốc ngẫu nhiên mức nhiễu trong khoảng thật.

    Vận tốc đưa vào cũng được làm trơn đúng như trong hệ thống, vì lấy đạo
    hàm trực tiếp trên chuỗi nhiễu sẽ khuếch đại nhiễu lên rất lớn.
    """
    rng = np.random.default_rng(seed)
    Xs, Ys = [], []
    for _ in range(n_traj):
        kind = str(rng.choice(TARGET_KINDS))
        p, v = make_trajectory(kind, 160, rng)
        sd = rng.uniform(*noise) if isinstance(noise, tuple) else noise
        pn = p + rng.normal(0, sd, p.shape)
        ker = np.ones(5) / 5.0
        ps = np.stack([np.convolve(np.pad(pn[:, i], 2, mode="edge"), ker, "valid")
                       for i in range(3)], 1)
        vn = np.gradient(ps, FRAME_DT, axis=0)
        x, y = _windows(pn, vn)
        Xs.append(x)
        Ys.append(y)
    return np.concatenate(Xs), np.concatenate(Ys)


def ekf_baseline(X: np.ndarray) -> np.ndarray:
    """Ngoại suy vận tốc không đổi — đúng bằng những gì EKF làm khi mất số đo."""
    v_last = X[:, -1, 3:] * VEL_SCALE
    steps = (np.arange(1, HOR + 1) * FRAME_DT)[None, :, None]
    return (v_last[:, None, :] * steps) / POS_SCALE


def main():
    t0 = time.time()
    Xtr, Ytr = build(900, SEED + 20)
    Xva, Yva = build(200, SEED + 21)
    Xte, Yte = build(300, SEED + 22)
    model = TrajTransformer(horizon=HOR)
    print(f"[traj] train={Xtr.shape} params={count_params(model):,}", flush=True)

    opt = torch.optim.AdamW(model.parameters(), lr=3e-3, weight_decay=1e-4)
    bs, epochs = 256, 18
    sched = torch.optim.lr_scheduler.OneCycleLR(
        opt, max_lr=3e-3, total_steps=epochs * int(np.ceil(len(Xtr) / bs)))
    lossf = nn.SmoothL1Loss(beta=0.05)
    ds = torch.utils.data.TensorDataset(torch.from_numpy(Xtr), torch.from_numpy(Ytr))
    dl = torch.utils.data.DataLoader(ds, batch_size=bs, shuffle=True)
    xva, yva = torch.from_numpy(Xva), torch.from_numpy(Yva)

    best, state = 1e9, None
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
            tot += loss.item() * len(xb)
        model.eval()
        with torch.no_grad():
            err = (model(xva) - yva).numpy() * POS_SCALE
        rmse = float(np.sqrt((err ** 2).sum(-1)).mean())
        if rmse < best:
            best, state = rmse, {k: v.clone() for k, v in model.state_dict().items()}
        print(f"  ep{ep+1:02d} loss={tot/len(Xtr):.5f} val_rmse={rmse:.2f} m", flush=True)

    model.load_state_dict(state)
    model.eval()
    with torch.no_grad():
        pred = model(torch.from_numpy(Xte)).numpy()
    base = ekf_baseline(Xte)

    def per_step(a):
        return np.sqrt((((a - Yte) * POS_SCALE) ** 2).sum(-1)).mean(0)

    tr_e, ek_e = per_step(pred), per_step(base)

    # Đánh giá riêng ở từng mức nhiễu lịch sử, để thấy mô hình bền đến đâu
    by_noise = {}
    for sd in (1.5, 5.0, 10.0):
        Xn, Yn = build(80, SEED + 30 + int(sd), noise=sd)
        with torch.no_grad():
            pn_ = model(torch.from_numpy(Xn)).numpy()
        bn = ekf_baseline(Xn)
        e1 = float(np.sqrt((((pn_ - Yn) * POS_SCALE) ** 2).sum(-1)).mean())
        e2 = float(np.sqrt((((bn - Yn) * POS_SCALE) ** 2).sum(-1)).mean())
        by_noise[f"{sd} m"] = {"transformer_m": round(e1, 2),
                               "const_vel_m": round(e2, 2)}
        print(f"  nhiễu lịch sử {sd:4.1f} m -> Transformer {e1:6.2f} m | "
              f"vận tốc không đổi {e2:6.2f} m", flush=True)
    res = {
        "horizon_s": [round((i + 1) * FRAME_DT, 2) for i in range(HOR)],
        "transformer_rmse_m": [round(float(v), 2) for v in tr_e],
        "ekf_const_vel_rmse_m": [round(float(v), 2) for v in ek_e],
        "transformer_mean_m": round(float(tr_e.mean()), 2),
        "ekf_mean_m": round(float(ek_e.mean()), 2),
        "improvement_pct": round(float((1 - tr_e.mean() / ek_e.mean()) * 100), 1),
        "params": count_params(model), "n_test_windows": int(len(Xte)),
        "by_history_noise": by_noise,
        "train_noise_range_m": [1.0, 12.0],
    }
    print(json.dumps(res, indent=1))
    torch.save(model.state_dict(), MODELS_DIR / "traj_model.pt")
    json.dump(res, open(RESULTS_DIR / "traj_metrics.json", "w", encoding="utf-8"), indent=1)
    print(f"[traj] done {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
