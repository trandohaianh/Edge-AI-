"""Huấn luyện Transformer quỹ đạo TRÊN CHÍNH ĐẦU RA CỦA EKF.

Vì sao phải viết lại bản huấn luyện này:

Bản đầu sinh dữ liệu bằng cách lấy quỹ đạo thật rồi cộng nhiễu Gauss và lấy
đạo hàm số để ra vận tốc. Trên tập đó, Transformer hơn phép ngoại suy vận
tốc không đổi tới 52%. Nhưng đem vào hệ thống thật thì nó KHÔNG hơn.

Lý do: mốc so sánh trong bài kiểm tra kia quá yếu. Nó lấy vận tốc bằng sai
phân của chuỗi vị trí nhiễu, trong khi EKF thật có hẳn số đo vận tốc xuyên
tâm từ radar nên vận tốc của nó tốt hơn nhiều. Nói cách khác, bài kiểm tra
cũ đã tự dựng một đối thủ yếu rồi tuyên bố thắng.

Cách sửa đúng là huấn luyện và đánh giá trên đúng thứ mà mô hình sẽ gặp lúc
chạy: chuỗi trạng thái do EKF thật sinh ra, với mốc so sánh là phép ngoại
suy từ chính vận tốc của EKF đó.
"""

from __future__ import annotations

import json
import time

import numpy as np
import torch
import torch.nn as nn

from edge_ai.config import CACHE_DIR, FRAME_DT, MODELS_DIR, RESULTS_DIR, SEED  # noqa: F401
from edge_ai.io_utils import write_json
from edge_ai.ml.nets import TrajTransformer, count_params
from edge_ai.sim.scene import TARGET_KINDS, Weather, make_scenario, sense
from edge_ai.tracking.ekf import EKF

torch.set_num_threads(2)
HIST, HOR = 20, 10
POS_SCALE, VEL_SCALE = 100.0, 30.0


def roll_track(seed: int, n_frames: int = 190):
    """Chạy trọn vòng cảm biến + EKF, trả về (trạng thái EKF, quỹ đạo thật)."""
    rng = np.random.default_rng(seed)
    w = Weather(
        fog=rng.uniform(0, 0.9),
        rain=rng.uniform(0, 0.8),
        jamming=rng.uniform(0, 0.9),
        night=bool(rng.random() < 0.4),
    )
    kind = str(rng.choice(TARGET_KINDS))
    tg = make_scenario(n_frames, rng, w, kinds=[kind])[0]
    f = EKF(tg.pos[0] + rng.normal(0, 25, 3), tg.vel[0] + rng.normal(0, 6, 3))
    P, V = [], []
    for k in range(n_frames):
        f.predict(FRAME_DT)
        for d in sense(tg, k, w, rng):
            f.update(d.sensor, d.z, d.R)
        P.append(f.pos)
        V.append(f.vel)
    return np.asarray(P), np.asarray(V), tg.pos


def build(n_traj: int, seed: int, warm: int = 40):
    """Cửa sổ (lịch sử EKF -> tương lai THẬT), bỏ đoạn đầu lúc bộ lọc còn bám."""
    Xs, Ys, Bs = [], [], []
    rng = np.random.default_rng(seed)
    for _ in range(n_traj):
        P, V, TRUE = roll_track(int(rng.integers(1e9)))
        for t in range(max(HIST, warm), len(P) - HOR):
            p0 = P[t - 1]
            Xs.append(
                np.concatenate(
                    [(P[t - HIST : t] - p0) / POS_SCALE, V[t - HIST : t] / VEL_SCALE], axis=1
                )
            )
            Ys.append((TRUE[t : t + HOR] - p0) / POS_SCALE)
            # mốc so sánh: ngoại suy bằng chính vận tốc EKF — đối thủ thật sự
            steps = (np.arange(1, HOR + 1) * FRAME_DT)[:, None]
            Bs.append((V[t - 1][None] * steps) / POS_SCALE)
    return (np.asarray(Xs, np.float32), np.asarray(Ys, np.float32), np.asarray(Bs, np.float32))


def rmse(a, b):
    return float(np.sqrt((((a - b) * POS_SCALE) ** 2).sum(-1)).mean())


def per_step(a, b):
    return np.sqrt((((a - b) * POS_SCALE) ** 2).sum(-1)).mean(0)


def main():
    t0 = time.time()
    Xtr, Ytr, _ = build(260, SEED + 40)
    Xva, Yva, Bva = build(60, SEED + 41)
    Xte, Yte, Bte = build(90, SEED + 42)
    print(f"[trajE] train={Xtr.shape} gen={time.time() - t0:.0f}s", flush=True)
    print(
        f"[trajE] mốc so sánh (EKF vận tốc không đổi) trên val: {rmse(Bva, Yva):.2f} m", flush=True
    )

    model = TrajTransformer(horizon=HOR)
    bs, epochs = 256, 16
    opt = torch.optim.AdamW(model.parameters(), lr=3e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(
        opt, max_lr=3e-3, total_steps=epochs * int(np.ceil(len(Xtr) / bs))
    )
    lossf = nn.SmoothL1Loss(beta=0.05)
    dl = torch.utils.data.DataLoader(
        torch.utils.data.TensorDataset(torch.from_numpy(Xtr), torch.from_numpy(Ytr)),
        batch_size=bs,
        shuffle=True,
    )
    xva = torch.from_numpy(Xva)

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
            e = rmse(model(xva).numpy(), Yva)
        if e < best:
            best, state = e, {k: v.clone() for k, v in model.state_dict().items()}
        print(f"  ep{ep + 1:02d} loss={tot / len(Xtr):.5f} val_rmse={e:.2f} m", flush=True)

    model.load_state_dict(state)
    model.eval()
    with torch.no_grad():
        pred = model(torch.from_numpy(Xte)).numpy()
    tr_e, ek_e = per_step(pred, Yte), per_step(Bte, Yte)
    res = {
        "trained_on": "chuỗi trạng thái do EKF thật sinh ra",
        "baseline": "ngoại suy bằng chính vận tốc của EKF (mốc so sánh công bằng)",
        "horizon_s": [round((i + 1) * FRAME_DT, 2) for i in range(HOR)],
        "transformer_rmse_m": [round(float(v), 2) for v in tr_e],
        "ekf_const_vel_rmse_m": [round(float(v), 2) for v in ek_e],
        "transformer_mean_m": round(float(tr_e.mean()), 2),
        "ekf_mean_m": round(float(ek_e.mean()), 2),
        "improvement_pct": round(float((1 - tr_e.mean() / ek_e.mean()) * 100), 1),
        "params": count_params(model),
        "n_test_windows": int(len(Xte)),
    }
    print(json.dumps(res, indent=1, ensure_ascii=False))
    torch.save(model.state_dict(), MODELS_DIR / "traj_model.pt")
    write_json(RESULTS_DIR / "traj_metrics.json", res)
    print(f"[trajE] done {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
