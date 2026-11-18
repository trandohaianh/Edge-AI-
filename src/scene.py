"""Mô phỏng hiện trường: quỹ đạo mục tiêu 3D và số đo của 4 cảm biến.

Trạm giám sát đặt ở gốc tọa độ. Trục x hướng đông, y hướng bắc, z lên trời.
Mỗi cảm biến có mô hình số đo riêng, đúng với thứ nó thật sự đo được:

* Radar     : cự ly, phương vị, góc tà, vận tốc xuyên tâm  (xa, xuyên sương mù)
* RF        : chỉ phương vị, và chỉ khi mục tiêu có phát sóng điều khiển
* EO/IR     : chỉ phương vị và góc tà (camera không đo được cự ly)
* LiDAR     : tọa độ 3D chính xác nhưng tầm rất ngắn

Chính sự lệch nhau đó là lý do phải hợp nhất: không cảm biến nào một mình
vừa xa, vừa chính xác, vừa bền với thời tiết.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from config import (EO_FOV_DEG, EO_RANGE_CLEAR, FRAME_DT, LIDAR_RANGE,
                    RADAR_RANGE, RF_RANGE)

TARGET_KINDS = ["multirotor", "fixed_wing", "bird"]


@dataclass
class Weather:
    fog: float = 0.0      # 0..1, 1 = sương mù dày / đêm tối mịt
    rain: float = 0.0     # 0..1
    jamming: float = 0.0  # 0..1, nhiễu dải RF
    night: bool = False

    def label(self) -> str:
        parts = []
        if self.night:
            parts.append("đêm")
        if self.fog > 0.3:
            parts.append("sương mù")
        if self.rain > 0.3:
            parts.append("mưa")
        if self.jamming > 0.3:
            parts.append("nhiễu RF")
        return ", ".join(parts) if parts else "trời quang"


@dataclass
class Target:
    kind: str
    pos: np.ndarray                 # [T,3]
    vel: np.ndarray                 # [T,3]
    emits_rf: bool                  # chim không phát sóng
    patch: bool = False             # dán nhãn ngụy trang đánh lừa camera
    tid: int = 0


def _smooth(a: np.ndarray, k: int = 9) -> np.ndarray:
    """Làm trơn quỹ đạo, có đệm biên.

    Phải đệm bằng cách lặp lại giá trị đầu/cuối: nếu dùng thẳng
    ``np.convolve(..., mode="same")`` thì ở hai đầu chuỗi tổng trọng số nhỏ
    hơn 1, tọa độ bị kéo tụt về gốc và vận tốc đầu/cuối vọt lên vô lý.
    """
    ker = np.hanning(k)
    ker /= ker.sum()
    pad = k // 2
    out = np.empty_like(a)
    for i in range(a.shape[1]):
        padded = np.pad(a[:, i], pad, mode="edge")
        out[:, i] = np.convolve(padded, ker, mode="valid")[:len(a)]
    return out


def make_trajectory(kind: str, n: int, rng: np.random.Generator,
                    pattern: str | None = None,
                    r0: float | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Quỹ đạo 3D theo các kiểu bay có thật."""
    if pattern is None:
        pattern = rng.choice(["approach", "orbit", "zigzag", "hover_dash", "pop_up"])
    t = np.arange(n) * FRAME_DT
    if kind == "multirotor":
        speed = rng.uniform(5, 18)
    elif kind == "fixed_wing":
        speed = rng.uniform(20, 38)
    else:
        speed = rng.uniform(4, 14)

    # r0 đặt được từ ngoài để chọn cự ly xuất phát. Phải sinh thẳng ở cự ly
    # mong muốn chứ KHÔNG được co giãn quỹ đạo đã sinh: co giãn toạ độ thì co
    # giãn luôn cả vận tốc, drone 15 m/s hoá ra bay 3 m/s.
    r0 = float(r0) if r0 is not None else rng.uniform(900, 2600)
    th0 = rng.uniform(0, 2 * np.pi)
    z0 = rng.uniform(40, 220)
    p = np.zeros((n, 3))

    # Mọi tốc độ góc đều chia cho cự ly: vận tốc dài = r * dtheta/dt, nên nếu
    # đặt thẳng tốc độ góc thì ở cự ly 2 km mục tiêu sẽ "bay" hàng trăm m/s.
    if pattern == "approach":
        r = r0 - speed * t
        v_lat = speed * rng.uniform(-0.25, 0.25)
        th = th0 + v_lat * t / max(r0, 1.0)
        z = z0 + rng.uniform(-0.6, 0.4) * t
    elif pattern == "orbit":
        r = r0 * 0.6 + rng.uniform(-40, 40) * np.sin(0.1 * t)
        th = th0 + speed / max(r.mean(), 1.0) * t * rng.choice([-1, 1])
        z = z0 + 20 * np.sin(0.15 * t)
    elif pattern == "zigzag":
        r = r0 - speed * 0.75 * t
        period = rng.uniform(6, 14)
        # biên độ ngang chọn sao cho vận tốc ngang <= 0,6 lần tốc độ bay
        amp_m = 0.6 * speed * period / (2 * np.pi)
        th = th0 + (amp_m / max(r0, 1.0)) * np.sin(2 * np.pi * t / period)
        z = z0 + 15 * np.sin(2 * np.pi * t / rng.uniform(8, 20))
    elif pattern == "hover_dash":
        v = np.where((t % 20) < 11, 0.6, 1.0) * speed
        r = r0 - np.cumsum(v) * FRAME_DT
        th = th0 + np.deg2rad(3) * np.sin(0.3 * t)
        z = z0 + 8 * np.sin(0.4 * t)
    else:  # pop_up: bay rất thấp rồi vọt lên
        r = r0 - speed * t
        th = th0 + np.deg2rad(2) * np.sin(0.2 * t)
        z = np.where(t < t[-1] * 0.55, rng.uniform(15, 35),
                     rng.uniform(15, 35) + (t - t[-1] * 0.55) * rng.uniform(4, 9))

    r = np.maximum(r, 60.0)
    p[:, 0] = r * np.cos(th)
    p[:, 1] = r * np.sin(th)
    p[:, 2] = np.clip(z, 8, 600)
    p = p + rng.normal(0, 0.6, p.shape)
    p = _smooth(p)
    v = np.gradient(p, FRAME_DT, axis=0)
    return p, v


def spherical(p: np.ndarray) -> tuple[float, float, float]:
    r = float(np.linalg.norm(p))
    az = float(np.arctan2(p[1], p[0]))
    el = float(np.arcsin(np.clip(p[2] / max(r, 1e-6), -1, 1)))
    return r, az, el


@dataclass
class Detection:
    sensor: str
    z: np.ndarray            # vector số đo
    R: np.ndarray            # hiệp phương sai nhiễu đo
    cls_logp: np.ndarray | None = None   # log xác suất theo TARGET_KINDS
    meta: dict = field(default_factory=dict)


def sense(target: Target, k: int, w: Weather, rng: np.random.Generator,
          md_prob=None, rf_prob=None) -> list[Detection]:
    """Số đo của 4 cảm biến tại khung k. Trả về danh sách (có thể rỗng)."""
    p = target.pos[k]
    v = target.vel[k]
    r, az, el = spherical(p)
    out: list[Detection] = []

    # ---------------------------------------------------------------- RADAR
    # Mưa làm tăng nền nhiễu nhưng không chặn được sóng vi ba.
    p_det = 0.97 * np.exp(-max(0.0, r - 400) / (RADAR_RANGE * 1.4)) * (1 - 0.25 * w.rain)
    if target.kind == "bird":
        p_det *= 0.75                      # RCS chim nhỏ hơn
    if p[2] < 25:
        p_det *= 0.55                      # bay thấp lẫn vào nhiễu địa hình
    if rng.random() < p_det:
        sr = 2.5 + 0.002 * r
        sa = np.deg2rad(0.6) * (1 + 0.5 * w.rain)
        sv = 0.25
        rr = float(np.dot(v, p) / max(r, 1e-6))
        z = np.array([r + rng.normal(0, sr), az + rng.normal(0, sa),
                      el + rng.normal(0, sa * 1.6), rr + rng.normal(0, sv)])
        R = np.diag([sr ** 2, sa ** 2, (sa * 1.6) ** 2, sv ** 2])
        out.append(Detection("radar", z, R, md_prob, {"range": r}))

    # ------------------------------------------------------------------- RF
    # Chỉ bắt được khi mục tiêu có phát sóng điều khiển; chim thì không.
    if target.emits_rf and r < RF_RANGE and rng.random() < 0.93 * (1 - 0.8 * w.jamming):
        sa = np.deg2rad(3.0 + 4.0 * w.jamming)   # AoA từ dàn ăng-ten: thô
        out.append(Detection("rf", np.array([az + rng.normal(0, sa)]),
                             np.array([[sa ** 2]]), rf_prob, {}))

    # ---------------------------------------------------------------- EO/IR
    eo_range = EO_RANGE_CLEAR * (1 - 0.75 * w.fog) * (0.55 if w.night else 1.0)
    in_fov = abs(az) < np.deg2rad(EO_FOV_DEG)
    if in_fov and r < eo_range and rng.random() < 0.9:
        sa = np.deg2rad(0.08) * (1 + 2 * w.fog)
        z = np.array([az + rng.normal(0, sa), el + rng.normal(0, sa)])
        R = np.diag([sa ** 2, sa ** 2])
        # Phân loại ảnh: tốt khi gần và trời quang, kém khi xa hoặc sương mù.
        # Khi kém thì phải tiến về PHÂN BỐ ĐỀU (không biết gì), chứ không được
        # trỏ sang một lớp sai. Bản đầu đặt p_lớp_đúng = q và chia đều phần
        # còn lại, nên khi q < 1/3 thì chính lớp đúng lại thành lớp ít khả
        # năng nhất — camera ở xa hoá ra "chỉ sai một cách tự tin".
        q = float(np.clip(1.0 - r / max(eo_range, 1.0), 0.0, 1.0))
        p_true = 1.0 / 3.0 + q * (2.0 / 3.0) * 0.93
        lp = np.full(3, np.log((1 - p_true) / 2 + 1e-9))
        lp[TARGET_KINDS.index(target.kind)] = np.log(p_true + 1e-9)
        if target.patch:
            # nhãn ngụy trang: camera bị đánh lừa sang lớp khác, rất tự tin
            wrong = (TARGET_KINDS.index(target.kind) + 1) % 3
            lp = np.full(3, np.log(0.04))
            lp[wrong] = np.log(0.92)
        out.append(Detection("eo", z, R, lp, {"patched": target.patch}))

    # ---------------------------------------------------------------- LiDAR
    lidar_range = LIDAR_RANGE * (1 - 0.85 * w.fog)
    if r < lidar_range and rng.random() < 0.85:
        s = 0.25 + 0.002 * r
        z = p + rng.normal(0, s, 3)
        out.append(Detection("lidar", z, np.eye(3) * s ** 2, None,
                             {"n_points": int(max(3, 900 * (1 - r / LIDAR_RANGE)))}))
    return out


def make_scenario(n_frames: int, rng: np.random.Generator, w: Weather,
                  kinds: list[str] | None = None, patch_ids: set[int] | None = None,
                  patterns: list[str] | None = None,
                  r0: float | None = None) -> list[Target]:
    kinds = kinds or [str(rng.choice(TARGET_KINDS))]
    patch_ids = patch_ids or set()
    tg = []
    for i, k in enumerate(kinds):
        pat = patterns[i] if patterns else None
        p, v = make_trajectory(k, n_frames, rng, pat, r0=r0)
        tg.append(Target(kind=k, pos=p, vel=v, emits_rf=(k != "bird"),
                         patch=(i in patch_ids), tid=i))
    return tg
