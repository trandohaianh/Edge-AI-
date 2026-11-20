"""Sinh chữ ký micro-Doppler cho radar băng X.

Vật lý dùng ở đây là chuẩn sách giáo khoa về micro-Doppler (Chen):

    f_d = 2 * v_r / lambda

Thân mục tiêu cho một vạch Doppler ổn định. Cánh quạt quay cho thêm thành
phần vận tốc hình sin theo thời gian; khi cánh vuông góc tia radar sẽ có
"blade flash" — vạch sáng lặp lại ở tần số

    f_flash = n_blades * f_rot

và trải rộng tới ±2*v_tip/lambda. Chim vỗ cánh ở 2–9 Hz nên chữ ký hình sin
chậm hơn hẳn và không có blade flash. Đây chính là cơ sở để phân biệt drone
với chim, và là thứ mô hình học được.
"""
from __future__ import annotations

import numpy as np

from edge_ai.config import (BIRD, FIXED_WING, MD_SHAPE, MULTIROTOR, RADAR_DWELL,
                    RADAR_LAMBDA, RADAR_NFFT, RADAR_PRF)


def _stft_power(x: np.ndarray) -> np.ndarray:
    """STFT trả về CÔNG SUẤT tuyến tính [freq, time].

    Gộp ô phải làm trên công suất rồi mới đổi sang dB: cộng công suất là
    phép tích phân không kết hợp đúng nghĩa, nhiễu sẽ giảm xuống còn vạch
    tín hiệu thì giữ nguyên. Nếu đổi sang dB trước rồi mới gộp (nhất là gộp
    bằng max) thì nền nhiễu bị kéo lên và lấp mất chữ ký.
    """
    win = np.hanning(RADAR_NFFT).astype(np.float32)
    n_fr = MD_SHAPE[1]
    hop = max(1, (len(x) - RADAR_NFFT) // n_fr)
    frames = []
    for k in range(n_fr):
        i = k * hop
        seg = x[i:i + RADAR_NFFT] * win
        frames.append(np.fft.fftshift(np.abs(np.fft.fft(seg)) ** 2))
    return np.asarray(frames, dtype=np.float32).T  # [RADAR_NFFT, n_fr]


def _pool_freq(P: np.ndarray, n_out=MD_SHAPE[0]) -> np.ndarray:
    """Gộp dải tần theo công suất trung bình (tích phân không kết hợp)."""
    f = P.shape[0]
    assert f % n_out == 0, (f, n_out)
    return P.reshape(n_out, f // n_out, P.shape[1]).mean(axis=1)


def _norm(P: np.ndarray) -> np.ndarray:
    """Công suất -> dB -> thang 0..1 với dải động 40 dB dưới đỉnh."""
    S = 10 * np.log10(P + 1e-12)
    S = S - S.max()
    return (np.clip(S, -40, 0) / 40.0 + 1.0).astype(np.float32)


def micro_doppler(kind: str, rng: np.random.Generator, snr_db: float | None = None,
                  v_radial: float | None = None, rain: float = 0.0) -> np.ndarray:
    """Spectrogram micro-Doppler chuẩn hóa MD_SHAPE = [64,128] của một mục tiêu."""
    if snr_db is None:
        snr_db = rng.uniform(0, 22)
    if v_radial is None:
        v_radial = rng.uniform(-28, 28)

    n = int(RADAR_DWELL * RADAR_PRF)
    t = np.arange(n) / RADAR_PRF
    body_rcs = dict(clutter=1.0, bird=0.4, fixed_wing=0.9, multirotor=0.7)[kind]
    # thân mục tiêu
    phase = 2 * np.pi * (2 * v_radial / RADAR_LAMBDA) * t
    x = body_rcs * np.exp(1j * phase)

    if kind == "multirotor" or kind == "fixed_wing":
        spec = MULTIROTOR if kind == "multirotor" else FIXED_WING
        n_rot = spec["n_rotors"]
        for _ in range(n_rot):
            f_rot = rng.uniform(*spec["f_rot"])
            R = rng.uniform(*spec["radius"])
            v_tip = 2 * np.pi * R * f_rot
            blades = spec["n_blades"]
            for b in range(blades):
                th0 = 2 * np.pi * b / blades + rng.uniform(0, 2 * np.pi)
                # vận tốc chiếu của một điểm trên cánh, lấy trung bình dọc cánh
                for frac in (0.55, 0.8, 1.0):
                    v = v_tip * frac * np.sin(2 * np.pi * f_rot * t + th0)
                    amp = 0.42 * frac ** 2 / n_rot
                    # blade flash: phản xạ mạnh khi cánh vuông góc tia
                    flash = np.abs(np.cos(2 * np.pi * f_rot * t + th0)) ** 8
                    x = x + amp * (0.3 + 0.7 * flash) * np.exp(
                        1j * (phase + 2 * np.pi * (2 * v / RADAR_LAMBDA) * t))
    elif kind == "bird":
        wb = rng.uniform(*BIRD["wingbeat"])
        amp_v = rng.uniform(*BIRD["amp"])
        for h, a in ((1, 1.0), (2, 0.35)):
            v = amp_v * np.sin(2 * np.pi * wb * h * t + rng.uniform(0, 6.28))
            x = x + 0.33 * a * np.exp(1j * (phase + 2 * np.pi * (2 * v / RADAR_LAMBDA) * t))
    elif kind == "clutter":
        # nhiễu địa hình: tán cây đung đưa — Doppler hẹp quanh 0, biến đổi chậm
        x = 0.0 * x
        for _ in range(rng.integers(3, 9)):
            fsw = rng.uniform(0.3, 2.5)
            v = rng.uniform(0.2, 1.6) * np.sin(2 * np.pi * fsw * t + rng.uniform(0, 6.28))
            x = x + rng.uniform(0.3, 1.0) * np.exp(1j * 2 * np.pi * (2 * v / RADAR_LAMBDA) * t)
    else:
        raise ValueError(kind)

    if rain > 0:  # mưa: tán xạ thể tích, Doppler rộng quanh vận tốc rơi
        nr = int(20 * rain)
        for _ in range(nr):
            v = rng.normal(-6.0, 1.5)
            x = x + rain * 0.08 * np.exp(1j * 2 * np.pi * (2 * v / RADAR_LAMBDA) * t
                                         + 1j * rng.uniform(0, 6.28))

    p = np.mean(np.abs(x) ** 2) + 1e-12
    x = x / np.sqrt(p)
    sigma = np.sqrt(10 ** (-snr_db / 10) / 2)
    x = x + (rng.normal(0, sigma, n) + 1j * rng.normal(0, sigma, n))
    return _norm(_pool_freq(_stft_power(x.astype(np.complex64))))


def build_md_dataset(n_per_class: int, seed: int, snr_range=(0, 22), rain_p: float = 0.25):
    from edge_ai.config import RADAR_CLASSES
    rng = np.random.default_rng(seed)
    xs, ys = [], []
    for ci, name in enumerate(RADAR_CLASSES):
        for _ in range(n_per_class):
            rain = rng.uniform(0.2, 1.0) if rng.random() < rain_p else 0.0
            xs.append(micro_doppler(name, rng, snr_db=rng.uniform(*snr_range), rain=rain))
            ys.append(ci)
    X = np.asarray(xs, dtype=np.float32)[:, None]   # [N,1,64,128]
    y = np.asarray(ys, dtype=np.int64)
    idx = rng.permutation(len(y))
    return X[idx], y[idx]
