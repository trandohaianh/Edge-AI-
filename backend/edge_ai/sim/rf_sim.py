"""Sinh tín hiệu I/Q băng gốc cho 4 lớp: nhiễu nền, WiFi, Bluetooth, link điều khiển drone.

Mục tiêu không phải là mô phỏng chuẩn giao thức, mà là tái tạo đúng những
dấu hiệu mà một bộ phân loại RF thật sự dựa vào:

* bề rộng phổ chiếm dụng,
* dạng nhảy tần theo thời gian (hop rate, dwell),
* chu kỳ bật/tắt của burst,
* đường bao biên độ và hệ số đỉnh (PAPR).

Drone điều khiển (OcuSync/Lightbridge và các họ tương tự) nhảy tần nhanh
trên băng rộng với burst đều đặn; WiFi là burst OFDM rộng, thưa và dài hơn;
Bluetooth nhảy tần hẹp 1 MHz. Những khác biệt này là có thật và đủ để
phân loại, nên bộ phân loại học được thứ nó cũng sẽ học trên dữ liệu thật.
"""
from __future__ import annotations

import numpy as np

from edge_ai.config import RF_FS, RF_SEG, RF_CLASSES


def _awgn(rng: np.random.Generator, n: int, sigma: float) -> np.ndarray:
    return (rng.normal(0, sigma, n) + 1j * rng.normal(0, sigma, n)).astype(np.complex64)


def _tone_chain(rng, n, fs, hops, dwell_samp, bw, start=0):
    """Chuỗi sóng mang nhảy tần: mỗi dwell một tần số, pha liên tục."""
    x = np.zeros(n, dtype=np.complex64)
    t = np.arange(n) / fs
    i = start
    while i < n:
        j = min(n, i + dwell_samp)
        f = rng.choice(hops)
        # băng thông trong mỗi dwell: điều chế số -> coi như nhiễu băng hẹp quanh f
        seg = j - i
        sym_rate = max(1.0, bw / 2)
        n_sym = max(1, int(seg / fs * sym_rate))
        sym = rng.choice([1 + 1j, 1 - 1j, -1 + 1j, -1 - 1j], n_sym) / np.sqrt(2)
        base = np.repeat(sym, int(np.ceil(seg / n_sym)))[:seg]
        x[i:j] = (base * np.exp(2j * np.pi * f * t[i:j])).astype(np.complex64)
        i = j
    return x


def _burst_mask(rng, n, on_ms, off_ms, fs, guarantee=True):
    """Mặt nạ bật/tắt với sườn lên xuống mềm.

    ``guarantee=True`` buộc có ít nhất một đoạn phát nằm trong cửa sổ quan
    sát. Đây không phải mẹo làm đẹp số liệu mà là mô hình đúng của máy thu
    quét thật: nó bắt theo NGƯỠNG NĂNG LƯỢNG rồi mới cắt cửa sổ quanh burst
    để phân loại. Nếu cắt cửa sổ 1 ms một cách mù quáng thì phần lớn cửa sổ
    của tín hiệu nhảy tần sẽ rỗng, và nhãn "có drone" gán cho một cửa sổ
    toàn nhiễu là nhãn sai, không mô hình nào học được.
    """
    m = np.zeros(n, dtype=np.float32)
    i = int(rng.uniform(0, 0.2 * n)) if guarantee else int(rng.uniform(0, off_ms) * 1e-3 * fs)
    first = True
    while i < n:
        on = int(max(1, rng.normal(on_ms, on_ms * 0.15)) * 1e-3 * fs)
        if first and guarantee:
            on = max(on, int(0.25 * n))
        j = min(n, i + on)
        m[i:j] = 1.0
        first = False
        i = j + int(max(1, rng.normal(off_ms, off_ms * 0.25)) * 1e-3 * fs)
    k = max(3, int(2e-6 * fs))
    ker = np.hanning(k)
    ker /= ker.sum()
    return np.convolve(m, ker, mode="same").astype(np.float32)


def _multipath(rng, x, fs):
    """Vài tia phản xạ ngắn — địa hình thực địa luôn có."""
    n_tap = rng.integers(1, 4)
    y = x.copy()
    for _ in range(n_tap):
        d = max(1, int(rng.uniform(0.1e-6, 2.0e-6) * fs))
        a = rng.uniform(0.1, 0.45) * np.exp(2j * np.pi * rng.random())
        if d < len(x):
            y[d:] += (a * x[:-d]).astype(np.complex64)
    return y


def make_segment(label: str, rng: np.random.Generator, snr_db: float | None = None,
                 n: int = RF_SEG, fs: float = RF_FS) -> np.ndarray:
    """Một đoạn I/Q của một lớp, đã chuẩn hóa công suất."""
    if snr_db is None:
        snr_db = rng.uniform(-6, 24)

    if label == "noise":
        x = _awgn(rng, n, 1.0)
        return (x / (np.std(x) + 1e-9)).astype(np.complex64)

    if label == "wifi":
        # OFDM 20 MHz vượt quá băng quan sát -> trong cửa sổ của ta là băng rộng,
        # burst dài 0,3–1,5 ms, khoảng lặng dài hơn.
        # 52 sóng mang con cách đều quanh MỘT tần số trung tâm: phổ là một
        # khối liên tục, chiếm trọn băng, và giữ nguyên tần số suốt burst.
        fc = rng.uniform(-0.12, 0.12) * fs
        bw = rng.uniform(0.55, 0.85) * fs
        n_car = 52
        f = fc + np.linspace(-bw / 2, bw / 2, n_car)
        t = np.arange(n) / fs
        ph = rng.uniform(0, 2 * np.pi, n_car)
        x = np.zeros(n, dtype=np.complex64)
        for fi, pi_ in zip(f, ph):
            x += np.exp(2j * np.pi * fi * t + 1j * pi_).astype(np.complex64)
        # OFDM đổi ký hiệu mỗi ~4 us -> pha nhảy theo khối
        sym = int(4e-6 * fs)
        for i0 in range(0, n, sym):
            x[i0:i0 + sym] *= np.exp(1j * rng.uniform(0, 2 * np.pi))
        x *= _burst_mask(rng, n, rng.uniform(0.4, 1.2), rng.uniform(0.6, 3.0), fs)

    elif label == "bluetooth":
        # 1 MHz/kênh, nhảy 1600 hop/s -> dwell 625 us, băng hẹp
        # Khe 625 us, kênh rộng 1 MHz: trong cửa sổ 1,024 ms chỉ thấy 1–2 hop,
        # và mỗi hop rất hẹp so với băng quan sát.
        hops = rng.uniform(-0.45, 0.45, 40) * fs
        x = _tone_chain(rng, n, fs, hops, int(625e-6 * fs), bw=0.8e6)
        x *= _burst_mask(rng, n, 0.625, rng.uniform(0.2, 0.8), fs)

    elif label == "drone_ctrl":
        # Link điều khiển: nhảy tần nhanh (dwell 0,1–0,6 ms), burst đều đặn
        # theo chu kỳ khung 2–10 ms, băng mỗi hop rộng hơn Bluetooth.
        # Nhảy tần nhanh: dwell 0,08–0,35 ms -> 3–12 hop trong một cửa sổ,
        # mỗi hop rộng vài MHz. Chính mật độ nhảy này phân biệt với Bluetooth.
        hops = rng.uniform(-0.45, 0.45, rng.integers(8, 32)) * fs
        dwell = int(rng.uniform(0.08, 0.35) * 1e-3 * fs)
        x = _tone_chain(rng, n, fs, hops, dwell, bw=rng.uniform(1.5e6, 6e6))
        x *= _burst_mask(rng, n, rng.uniform(0.6, 1.1), rng.uniform(0.15, 0.6), fs)

    else:
        raise ValueError(label)

    x = _multipath(rng, x, fs)
    x *= np.exp(2j * np.pi * rng.uniform(-2000, 2000) * np.arange(n) / fs)  # lệch tần
    p = np.mean(np.abs(x) ** 2) + 1e-12
    x = x / np.sqrt(p)
    sigma = np.sqrt(10 ** (-snr_db / 10) / 2)
    x = x + _awgn(rng, n, sigma)
    return (x / (np.std(x) + 1e-9)).astype(np.complex64)


def build_rf_dataset(n_per_class: int, seed: int, snr_range=(-6, 24)):
    """Trả về (X[N,2,RF_SEG] float32, y[N] int64)."""
    rng = np.random.default_rng(seed)
    xs, ys = [], []
    for ci, name in enumerate(RF_CLASSES):
        for _ in range(n_per_class):
            snr = rng.uniform(*snr_range)
            s = make_segment(name, rng, snr_db=snr)
            xs.append(np.stack([s.real, s.imag]))
            ys.append(ci)
    X = np.asarray(xs, dtype=np.float32)
    y = np.asarray(ys, dtype=np.int64)
    idx = rng.permutation(len(y))
    return X[idx], y[idx]
