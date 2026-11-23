"""Hiệu chỉnh xác suất bằng temperature scaling (Guo và cộng sự, 2017).

Bộ phân loại sau huấn luyện thường "tự tin quá mức" hoặc "rụt rè quá mức":
nó nói 90% thì thực tế chưa chắc đúng 90%. Temperature scaling chia logit
cho MỘT số dương T trước softmax:

    p = softmax(z / T)

* T > 1 làm phân bố mềm đi (bớt tự tin), T < 1 làm nó nhọn hơn.
* Chia cho cùng một số dương không đổi thứ tự các logit, nên argmax — tức
  nhãn dự đoán và độ chính xác — giữ nguyên tuyệt đối. Chỉ độ tin cậy đổi.

T được học bằng cách cực tiểu NLL trên tập KIỂM ĐỊNH (validation) tách riêng,
không bao giờ trên tập test; số đo trước/sau báo cáo trên tập test.

T lưu trong ``data/models/calibration.json`` cạnh các tệp trọng số. Thiếu
tệp (hoặc thiếu khoá của một mô hình) thì T = 1, tức là đúng hành vi cũ.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from scipy.optimize import minimize_scalar

from edge_ai.io_utils import read_json, write_json

CALIBRATION_FILE = "calibration.json"
ECE_BINS = 15
T_MIN, T_MAX = 0.05, 20.0  # khoảng tìm T; ngoài khoảng này gần như chắc chắn là lỗi


def _log_softmax(z: np.ndarray) -> np.ndarray:
    z = z - z.max(axis=1, keepdims=True)
    return z - np.log(np.exp(z).sum(axis=1, keepdims=True))


def softmax_t(logits: np.ndarray, T: float = 1.0) -> np.ndarray:
    return np.exp(_log_softmax(np.asarray(logits, np.float64) / T))


def nll(logits: np.ndarray, y: np.ndarray, T: float = 1.0) -> float:
    """Negative log-likelihood trung bình (nats/mẫu)."""
    lp = _log_softmax(np.asarray(logits, np.float64) / T)
    return float(-lp[np.arange(len(y)), y].mean())


def ece(probs: np.ndarray, y: np.ndarray, n_bins: int = ECE_BINS) -> float:
    """Expected Calibration Error: chia độ tin cậy (xác suất lớn nhất) thành
    ``n_bins`` khoảng đều trên [0, 1]; ECE = Σ (n_b / N)·|acc_b − conf_b|."""
    conf = probs.max(axis=1)
    correct = (probs.argmax(axis=1) == y).astype(float)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    out = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (conf > lo) & (conf <= hi)
        if m.any():
            out += m.mean() * abs(correct[m].mean() - conf[m].mean())
    return float(out)


def fit_temperature(logits: np.ndarray, y: np.ndarray) -> float:
    """T > 0 cực tiểu NLL trên (logits, y) của tập kiểm định.

    Tối ưu theo log T (một chiều, có chặn) nên T luôn dương."""
    logits = np.asarray(logits, np.float64)
    y = np.asarray(y, np.int64)
    res = minimize_scalar(
        lambda lt: nll(logits, y, math.exp(lt)),
        bounds=(math.log(T_MIN), math.log(T_MAX)),
        method="bounded",
        options={"xatol": 1e-5},
    )
    return float(math.exp(res.x))


def report(logits: np.ndarray, y: np.ndarray, T: float) -> dict:
    """Độ chính xác, NLL, ECE trước (T = 1) và sau (T) trên cùng một tập."""
    p0, p1 = softmax_t(logits, 1.0), softmax_t(logits, T)
    return {
        "acc_before": float((p0.argmax(1) == y).mean()),
        "acc_after": float((p1.argmax(1) == y).mean()),
        "nll_before": nll(logits, y, 1.0),
        "nll_after": nll(logits, y, T),
        "ece_before": ece(p0, y),
        "ece_after": ece(p1, y),
    }


def load_temperatures(models_dir: Path) -> dict[str, float]:
    """{"rf": T, "md": T} từ ``calibration.json``; thiếu hoặc hỏng thì {}.

    Giá trị không hợp lệ (không phải số dương hữu hạn) bị bỏ qua — khi đó mô
    hình đó dùng T = 1 như trước khi có hiệu chỉnh."""
    p = Path(models_dir) / CALIBRATION_FILE
    if not p.exists():
        return {}
    try:
        raw = read_json(p)
    except (OSError, ValueError):
        return {}
    out = {}
    for k, v in raw.items() if isinstance(raw, dict) else []:
        T = v.get("T") if isinstance(v, dict) else None
        if isinstance(T, (int, float)) and math.isfinite(T) and T > 0:
            out[k] = float(T)
    return out


def save_temperatures(models_dir: Path, entries: dict[str, dict]) -> None:
    write_json(Path(models_dir) / CALIBRATION_FILE, entries)
