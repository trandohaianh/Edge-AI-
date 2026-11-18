"""Phần "phần cứng" dùng chung cho đánh giá, thử nghiệm và dashboard.

Trước đây lịch chạy cảm biến và hàm sinh I/Q nằm trong ``evaluate.py``, nên
máy chủ dashboard phải import module đánh giá. Gom về đây để cả ba nơi dùng
đúng một định nghĩa.

Gồm:
* lịch chạy hai bộ phát hiện nặng (``rf_due``, ``md_due``),
* dữ liệu thô gắn vào số đo: đoạn I/Q cho RF, ảnh phổ micro-Doppler cho radar,
* bệ quay camera được radar dẫn hướng (``EOTurret``),
* cảm biến nhiều mục tiêu kèm báo động giả của radar (``sense_all``).
"""
from __future__ import annotations

import numpy as np

from config import (EO_SLEW_DEG_S, FRAME_DT, MD_EVERY, MD_PHASE, RADAR_RANGE,
                    RF_EVERY, RF_PHASE)
from radar_sim import micro_doppler
from rf_sim import make_segment
from scene import Detection, Target, Weather, sense


def md_due(k: int) -> bool:
    return k % MD_EVERY == MD_PHASE


def rf_due(k: int) -> bool:
    """Tới lịch RF; nếu trùng khung với radar thì hoãn sang khung sau."""
    if k % RF_EVERY == RF_PHASE:
        return not md_due(k)
    return (k - 1) % RF_EVERY == RF_PHASE and md_due(k - 1)


def radar_snr(r: float) -> float:
    """SNR của chữ ký micro-Doppler giảm theo cự ly (dB)."""
    return float(np.clip(30 - 20 * np.log10(max(r, 100) / 300), 2, 26))


def rf_iq(emits_rf: bool, rng: np.random.Generator,
          snr: tuple[float, float] = (2, 20)) -> np.ndarray:
    """Một đoạn I/Q [2, N] float32. I và Q lấy từ CÙNG một đoạn tín hiệu."""
    s = make_segment("drone_ctrl" if emits_rf else "noise", rng,
                     snr_db=rng.uniform(*snr))
    return np.stack([s.real, s.imag]).astype(np.float32)


def md_spec(kind: str, r: float, rng: np.random.Generator, rain: float) -> np.ndarray:
    return micro_doppler(kind, rng, snr_db=radar_snr(r), rain=rain)


def lambda_iq(tg: Target, rng: np.random.Generator):
    """Giữ tương thích với mã cũ: trả về [I, Q]."""
    x = rf_iq(tg.emits_rf, rng)
    return [x[0], x[1]]


def _wrap(a: float) -> float:
    return (a + np.pi) % (2 * np.pi) - np.pi


class EOTurret:
    """Bệ quay camera: mỗi khung quay về phía phương vị được giao, có giới hạn
    tốc độ quay. Trạm thật không để camera đứng yên chờ mục tiêu bay vào góc
    nhìn hẹp; radar thấy trước rồi dẫn camera tới."""

    def __init__(self, az: float = 0.0, slew_deg_s: float = EO_SLEW_DEG_S):
        self.az = float(az)
        self.max_step = np.deg2rad(slew_deg_s) * FRAME_DT

    def point(self, target_az: float | None) -> float:
        if target_az is not None:
            d = _wrap(target_az - self.az)
            self.az = _wrap(self.az + float(np.clip(d, -self.max_step, self.max_step)))
        return self.az


def attach_raw(dets: list[Detection], target: Target | None, k: int,
               w: Weather, rng: np.random.Generator) -> None:
    """Gắn dữ liệu thô vào số đo khi tới lịch: I/Q cho RF, ảnh phổ cho radar.

    ``target=None`` là báo động giả: radar thấy "thứ gì đó" mà thực ra là
    nhiễu địa hình, nên ảnh phổ của nó là ảnh phổ clutter.
    """
    for d in dets:
        if d.sensor == "rf" and rf_due(k):
            d.meta["iq"] = rf_iq(target.emits_rf if target else False, rng)
        elif d.sensor == "radar" and md_due(k):
            kind = target.kind if target else "clutter"
            d.meta["spec"] = md_spec(kind, float(d.z[0]), rng, w.rain)


def false_alarms(rng: np.random.Generator, rate: float, w: Weather) -> list[Detection]:
    """Báo động giả của radar: Poisson ``rate`` điểm mỗi khung, rải đều trong
    vùng phủ, vận tốc xuyên tâm nhỏ (cây cối, xe cộ, phản xạ địa hình)."""
    out = []
    for _ in range(rng.poisson(rate)):
        r = rng.uniform(300, RADAR_RANGE)
        az = rng.uniform(-np.pi, np.pi)
        el = rng.uniform(0.0, 0.08)
        sr, sa = 2.5 + 0.002 * r, np.deg2rad(0.6) * (1 + 0.5 * w.rain)
        z = np.array([r, az, el, rng.normal(0, 1.5)])
        R = np.diag([sr ** 2, sa ** 2, (sa * 1.6) ** 2, 0.25 ** 2])
        out.append(Detection("radar", z, R, None, {"truth_id": -1}))
    return out


def sense_all(targets: list[Target], k: int, w: Weather, rng: np.random.Generator,
              eo_az: float | None = None, clutter_rate: float = 0.0,
              raw: bool = True) -> list[Detection]:
    """Số đo của mọi mục tiêu trong một khung, TRỘN LẪN như cảm biến thật trả
    về. ``meta['truth_id']`` chỉ dùng để chấm điểm, bộ bám không được đọc."""
    dets: list[Detection] = []
    for tg in targets:
        ds = sense(tg, k, w, rng, eo_az=eo_az)
        for d in ds:
            d.meta["truth_id"] = tg.tid
        if raw:
            attach_raw(ds, tg, k, w, rng)
        dets += ds
    fa = false_alarms(rng, clutter_rate, w) if clutter_rate > 0 else []
    if raw:
        attach_raw(fa, None, k, w, rng)
    dets += fa
    order = rng.permutation(len(dets))
    return [dets[i] for i in order]


class RawProvider:
    """"Phần cứng" theo yêu cầu: bộ bám chọn số đo nào cần dữ liệu thô
    (ảnh phổ micro-Doppler, đoạn I/Q) rồi mới xin — như radar thật chỉ dừng
    chùm tia lấy chữ ký trên những vết đang bám. Mô phỏng dùng
    ``meta['truth_id']`` để biết số đo đó thật ra của ai (-1: báo động giả)."""

    def __init__(self, targets: list[Target], w: Weather, rng: np.random.Generator):
        self.by_id = {t.tid: t for t in targets}
        self.w, self.rng = w, rng
        self.calls = {"spec": 0, "iq": 0}

    def __call__(self, d: Detection, what: str) -> np.ndarray:
        tg = self.by_id.get(d.meta.get("truth_id", -1))
        self.calls[what] += 1
        if what == "spec":
            return md_spec(tg.kind if tg else "clutter", float(d.z[0]), self.rng, self.w.rain)
        return rf_iq(tg.emits_rf if tg else False, self.rng)

