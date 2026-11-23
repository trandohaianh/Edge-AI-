"""Hợp nhất 4 luồng cảm biến thành một kết luận kèm bằng chứng.

Hai việc tách bạch:

1. Hợp nhất VỊ TRÍ: do EKF làm (ekf.py), mỗi cảm biến cập nhật theo mô hình
   đo của nó.
2. Hợp nhất NHẬN DẠNG: cộng log tỉ lệ khả năng (log-odds) của từng cảm biến,
   mỗi cảm biến có một TRỌNG SỐ TIN CẬY thay đổi theo điều kiện hiện trường.

Trọng số tin cậy là chỗ quan trọng nhất. Camera trong sương mù hay bị dán
nhãn ngụy trang vẫn trả lời rất tự tin — nhưng tự tin sai. Nếu cộng đều mọi
cảm biến thì một camera bị đánh lừa đủ sức lật kết luận. Vì vậy trọng số của
EO bị hạ khi tầm nhìn kém, và bị hạ tiếp khi nó mâu thuẫn với radar + RF,
là hai cảm biến mà thủ đoạn dán nhãn không chạm tới được.

Hệ thống chỉ dừng ở mức đưa ra kết luận kèm điểm tin cậy và bằng chứng cho
người trực ca quyết định. Không có bất kỳ cơ chế tự động hành động nào.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from edge_ai.sim.scene import TARGET_KINDS, Weather


def _clip(v: float, lo: float, hi: float) -> float:
    """Kẹp một SỐ VÔ HƯỚNG: nhanh hơn np.clip hàng chục lần khi gọi trên số
    lẻ, mà hàm này được gọi cho mọi vết bám ở mọi khung."""
    return lo if v < lo else hi if v > hi else float(v)


SENSORS = ["radar", "rf", "eo", "lidar"]


def reliability(sensor: str, w: Weather, rng_m: float | None = None) -> float:
    """Độ tin cậy 0..1 của một cảm biến trong điều kiện hiện tại."""
    if sensor == "radar":
        return _clip(0.9 - 0.15 * w.rain, 0.2, 1.0)
    if sensor == "rf":
        return _clip(0.85 - 0.7 * w.jamming, 0.05, 1.0)
    if sensor == "eo":
        base = 0.9 * (1 - 0.8 * w.fog) * (0.6 if w.night else 1.0)
        if rng_m is not None:
            base *= _clip(1.2 - rng_m / 1500.0, 0.1, 1.0)
        return _clip(base, 0.03, 1.0)
    if sensor == "lidar":
        return _clip(0.95 * (1 - 0.9 * w.fog), 0.02, 1.0)
    return 0.5


PER_SENSOR_CAP = 4.0  # nats: trần bằng chứng một cảm biến được phép dồn
CONFLICT_MARGIN = 0.5  # nats: radar+RF phải chê lớp của camera ít nhất chừng này
DECEPTION_LEVEL = 0.5  # mức mâu thuẫn từ đó coi là nghi bị đánh lừa


@dataclass
class FusedState:
    logp: np.ndarray = field(default_factory=lambda: np.zeros(len(TARGET_KINDS)))
    by_sensor: dict = field(default_factory=dict)  # bằng chứng dồn theo cảm biến
    evidence: dict = field(default_factory=dict)  # sensor -> đóng góp (0..1)
    seen: dict = field(default_factory=dict)  # sensor -> số khung có số đo
    conflict: float = 0.0
    n_evidence: int = 0  # số khung đã có bằng chứng nhận dạng

    def probs(self) -> np.ndarray:
        z = self.logp - self.logp.max()
        p = np.exp(z)
        return p / p.sum()

    def top(self) -> tuple[str, float]:
        p = self.probs()
        i = int(p.argmax())
        return TARGET_KINDS[i], float(p[i])


class IdentityFuser:
    """Cộng dồn bằng chứng nhận dạng theo thời gian, có quên dần."""

    def __init__(self, decay: float = 0.985, max_abs: float = 9.0):
        self.state = FusedState()
        self.decay = decay
        self.max_abs = max_abs

    def update(self, dets, w: Weather, rng_m: float | None):
        s = self.state
        contrib = {}
        for d in dets:
            s.seen[d.sensor] = s.seen.get(d.sensor, 0) + 1
            if d.cls_logp is None:
                continue
            rel = reliability(d.sensor, w, rng_m if d.sensor == "eo" else None)
            lp = np.asarray(d.cls_logp, dtype=float)
            if not np.all(np.isfinite(lp)):
                # NaN/Inf cộng vào by_sensor thì kẹp (np.clip) cũng không xoá
                # được: nhận dạng thành NaN mãi. Pipeline đã lọc và đếm trước
                # (``Pipeline.dropped``); đây là chốt chặn cuối.
                continue
            # Trừ GIÁ TRỊ TRUNG BÌNH chứ không trừ giá trị lớn nhất.
            # Trừ max thì lớp tốt nhất luôn được cộng 0 còn các lớp khác bị
            # trừ đi — tức là cảm biến chỉ biết dìm lớp khác xuống, và hạ
            # trọng số nó cũng chỉ làm việc dìm chậm lại chứ không đảo được.
            # Trừ trung bình cho ra bằng chứng tổng bằng 0: cộng cho lớp mình
            # tin, trừ các lớp còn lại, nên nhân với độ tin cậy mới có nghĩa.
            contrib[d.sensor] = rel * (lp - lp.mean())

        # Phát hiện mâu thuẫn: EO chỉ một đằng, radar+RF chỉ một nẻo.
        #
        # Ba trường hợp, không phải hai. Bản cũ so argmax của radar+RF với
        # argmax của camera; nhưng RF chỉ nói "drone" chứ không phân biệt đa
        # cánh quạt với cánh bằng, nên khi chỉ có RF, hai lớp đó HOÀ nhau và
        # argmax luôn chọn lớp đứng đầu ("đa cánh quạt"). Kết quả: mỗi lần
        # camera nói đúng "cánh bằng" lại bị tính là mâu thuẫn và bị hạ quyền.
        # Giờ chỉ gọi là mâu thuẫn khi bằng chứng vật lý thật sự CHÊ lớp mà
        # camera chọn; vật lý không phân biệt được thì không kết luận gì.
        phys = [c for k, c in contrib.items() if k in ("radar", "rf")]
        if phys and "eo" in contrib:
            ph = sum(phys)
            b = int(np.argmax(contrib["eo"]))
            gap = float(ph.max() - ph[b])
            second = float(np.sort(ph)[-2])
            if gap > CONFLICT_MARGIN:
                s.conflict = min(1.0, s.conflict + 0.12)
                contrib["eo"] = contrib["eo"] * 0.25  # hạ quyền camera khi nghi bị lừa
            elif gap < 1e-9 and ph.max() - second > CONFLICT_MARGIN:
                s.conflict = max(0.0, s.conflict - 0.05)

        # Dồn bằng chứng THEO TỪNG CẢM BIẾN, mỗi cảm biến một trần riêng.
        #
        # Camera nhìn cùng một nhãn ngụy trang 10 khung liền thì đó vẫn chỉ là
        # một bằng chứng, không phải mười bằng chứng độc lập. Nếu cộng dồn tự
        # do, cảm biến nào lấy mẫu dày nhất sẽ thắng bất kể đúng sai — và
        # camera chạy 10 Hz lấy mẫu dày hơn radar (0,35 s một chữ ký) gấp mấy
        # lần. Đặt trần cho mỗi cảm biến buộc kết luận phải có nhiều loại cảm
        # biến cùng đồng ý.
        #
        # Trần của cảm biến đang mâu thuẫn bị siết lại theo mức mâu thuẫn:
        # càng lệch lâu với radar và RF thì tiếng nói của nó càng nhỏ.
        if contrib:
            s.n_evidence += 1
        for k in set(list(s.by_sensor) + list(contrib)):
            cap = PER_SENSOR_CAP
            if k == "eo":
                cap *= 1.0 - 0.9 * s.conflict
            if k in contrib:
                acc = s.by_sensor.get(k, np.zeros(len(TARGET_KINDS))) + contrib[k]
                s.evidence[k] = s.evidence.get(k, 0.0) * 0.9 + float(np.abs(contrib[k]).sum()) * 0.1
            else:
                acc = s.by_sensor.get(k, np.zeros(len(TARGET_KINDS))) * self.decay
            s.by_sensor[k] = np.clip(acc, -cap, cap)
        total = np.zeros(len(TARGET_KINDS))
        for v in s.by_sensor.values():
            total = total + v
        s.logp = np.clip(total, -self.max_abs, self.max_abs)
        return s


def track_confidence(fused: FusedState, pos_sigma: float, n_sensor: int) -> float:
    """Điểm tin cậy của vết bám.

    Gồm bốn phần: độ chắc của nhận dạng, độ chính xác vị trí, số LOẠI cảm
    biến đã góp bằng chứng nhận dạng, và độ chín — tức là đã quan sát đủ lâu
    hay chưa.

    Phần độ chín là thứ phải thêm vào sau khi đo lại: bản đầu không có nó nên
    hệ thống đạt mức "đủ tin để báo người" ngay ở khung đầu tiên, chỉ nhờ sai
    số vị trí ban đầu còn nhỏ. Một hệ cảnh báo sớm mà tự tin sau 0,1 giây thì
    điểm tin cậy đó không có nghĩa gì. Giờ muốn vượt ngưỡng phải có ít nhất
    hai loại cảm biến đồng ý và quan sát được khoảng hai giây.
    """
    _, p = fused.top()
    geo = _clip(1.0 - pos_sigma / 120.0, 0.0, 1.0)
    n_cls = len([k for k, v in fused.by_sensor.items() if float(np.abs(v).sum()) > 0.3])
    div = _clip(n_cls / 2.0, 0.0, 1.0)
    # Độ chín là một HỆ SỐ NHÂN, không phải một số hạng cộng thêm. Cộng thêm
    # thì ba thành phần kia vẫn đủ sức đẩy điểm qua ngưỡng ngay khung đầu —
    # trong đó "độ chính xác vị trí" ở khung đầu thực chất chỉ là hiệp phương
    # sai khởi tạo mình tự đặt ra, chưa phải bằng chứng gì cả. Nhân vào thì
    # hệ thống buộc phải quan sát khoảng 1,5 giây mới dám tự tin.
    gate = _clip(fused.n_evidence / 15.0, 0.12, 1.0)
    c = (0.45 * p + 0.25 * geo + 0.30 * div) * gate
    return _clip(c * (1 - 0.35 * fused.conflict), 0.0, 1.0)
