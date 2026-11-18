"""Vòng xử lý đầu-cuối cho một khung, có đo thời gian từng chặng.

Thứ tự đúng như đề bài yêu cầu: nhận tín hiệu → tiền xử lý → suy luận →
hợp nhất → đưa ra toạ độ bám. Toàn bộ ngân sách là 50 ms.

Hai bộ phát hiện nặng (RF và micro-Doppler) KHÔNG chạy mỗi khung. Radar cần
0,35 s chiếu mới có một chữ ký micro-Doppler, nên chạy nó 10 lần/giây là vô
nghĩa về mặt vật lý. Chúng chạy theo chu kỳ riêng, còn mỗi khung 10 Hz chỉ
làm phần nhẹ: liên kết số đo, EKF, hợp nhất. Đây cũng là cách giữ được
ngân sách 50 ms trên chip nhúng.
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import torch

from config import (ALERT_THRESHOLD, CONFIRM_THRESHOLD, FRAME_DT, RADAR_CLASSES,
                    RF_CLASSES)
from ekf import EKF
from fusion import IdentityFuser, track_confidence
from models import MicroDopplerNet, TrajTransformer
from rf_stft import RFNetSTFT
from scene import TARGET_KINDS, Detection, Weather

DATA = Path(__file__).resolve().parent.parent / "data"
torch.set_num_threads(2)

# Ánh xạ lớp của từng bộ phát hiện sang 3 lớp mục tiêu chung.
MD_TO_TARGET = {"multirotor": "multirotor", "fixed_wing": "fixed_wing",
                "bird": "bird", "clutter": None}
HIST, HOR = 20, 10
GAP_MIN = 3        # số khung gián đoạn tối thiểu mới coi là mất dấu
POS_SCALE, VEL_SCALE = 100.0, 30.0
BLACKOUT_STEPS = 90   # số khung tối đa có dự đoán khi mất dấu (9 s)
HIST_KEEP = 256       # số khung lịch sử giữ lại cho mỗi vết bám
TIMING_KEEP = 10_000  # số mẫu thời gian giữ lại cho mỗi chặng
MODEL_FILES = ("rf_model.pt", "md_model.pt", "traj_model.pt")


def load_models(allow_untrained: bool = False, data_dir: Path | None = None):
    """Nạp ba mô hình từ ``data/``.

    Thiếu tệp trọng số thì DỪNG, trừ khi gọi rõ ``allow_untrained=True``.
    Bản cũ lặng lẽ chạy tiếp với trọng số ngẫu nhiên: dashboard vẫn hiện số,
    nhưng mọi nhận dạng là vô nghĩa — với một hệ giám sát đó là kiểu hỏng tệ
    nhất vì không ai biết là nó đang hỏng.

    ``weights_only=True`` để ``torch.load`` không thực thi mã pickle tuỳ ý
    nằm trong tệp .pt (tệp trọng số là dữ liệu, không phải chương trình).
    """
    data_dir = data_dir or DATA
    rf = RFNetSTFT(len(RF_CLASSES))
    md = MicroDopplerNet(len(RADAR_CLASSES))
    tj = TrajTransformer(horizon=HOR)
    missing = []
    for m, f in zip((rf, md, tj), MODEL_FILES):
        p = data_dir / f
        if p.exists():
            m.load_state_dict(torch.load(p, map_location="cpu", weights_only=True))
        else:
            missing.append(f)
        m.eval()
    if missing and not allow_untrained:
        raise FileNotFoundError(
            f"thiếu trọng số {missing} trong {data_dir}; chạy lại các bước huấn "
            "luyện trong README, hoặc gọi load_models(allow_untrained=True) nếu "
            "chỉ cần thử luồng xử lý")
    for m in (rf, md, tj):
        m.trained = not missing
    return rf, md, tj


def warmup(models) -> None:
    """Chạy mỗi mô hình một lần trên đầu vào giả để lần gọi thật đầu tiên
    không phải trả chi phí cấp phát bộ nhớ và chọn kernel."""
    rf, md, tj = models
    with torch.no_grad():
        rf(torch.zeros(1, 2, 2048))
        md(torch.zeros(1, 1, 64, 128))
        tj(torch.zeros(1, HIST, 6))


def md_logp(md: MicroDopplerNet, spec: np.ndarray) -> np.ndarray:
    """Spectrogram -> log xác suất trên 3 lớp mục tiêu chung.

    Lớp 'clutter' của radar không phải một mục tiêu, nên khối lượng xác suất
    của nó được chia đều — tức là 'không có thông tin', chứ không bị ép
    thành một lớp mục tiêu nào.
    """
    with torch.no_grad():
        p = torch.softmax(md(torch.from_numpy(spec[None, None])), 1).numpy()[0]
    out = np.zeros(len(TARGET_KINDS))
    for i, c in enumerate(RADAR_CLASSES):
        t = MD_TO_TARGET[c]
        if t is None:
            out += p[i] / len(TARGET_KINDS)
        else:
            out[TARGET_KINDS.index(t)] += p[i]
    return np.log(np.clip(out, 1e-6, 1.0))


def rf_logp(rf: RFNetSTFT, iq: np.ndarray) -> np.ndarray:
    """I/Q -> log xác suất. RF chỉ nói được 'có link điều khiển hay không'.

    Một link điều khiển loại trừ chim (chim không phát sóng) nhưng không
    phân biệt được đa cánh quạt với cánh bằng, nên bằng chứng được chia đều
    cho hai lớp đó.
    """
    with torch.no_grad():
        p = torch.softmax(rf(torch.from_numpy(iq[None])), 1).numpy()[0]
    drone = float(p[RF_CLASSES.index("drone_ctrl")])
    out = np.array([drone / 2, drone / 2, 1.0 - drone])  # multi, fixed, bird
    return np.log(np.clip(out, 1e-6, 1.0))


@dataclass
class Track:
    tid: int
    ekf: EKF
    fuser: IdentityFuser = field(default_factory=IdentityFuser)
    # (pos, vel) mọi khung — đúng phân bố mà Transformer được huấn luyện
    # (train_traj_ekf.py lấy trạng thái EKF ở MỌI khung). Giới hạn độ dài để
    # vết bám chạy lâu không ăn dần bộ nhớ thiết bị biên.
    hist: deque = field(default_factory=lambda: deque(maxlen=HIST_KEEP))
    last_seen: int = 0
    confidence: float = 0.0
    status: str = "mới"
    operator: str | None = None                   # chuyên viên xác nhận/bỏ qua
    # trạng thái chốt tại thời điểm bắt đầu mất dấu, để ngoại suy
    blackout_from: int | None = None
    blackout_pos: np.ndarray | None = None
    blackout_vel: np.ndarray | None = None
    blackout_pred: np.ndarray | None = None
    blackout_hist: list | None = None              # lịch sử để nối dự đoán tiếp


class Pipeline:
    """Một vết bám cho mỗi mục tiêu (bài toán liên kết đa mục tiêu nằm ngoài
    phạm vi bản này — xem phần hạn chế trong báo cáo)."""

    def __init__(self, models=None):
        self.rf, self.md, self.tj = models or load_models()
        self.tracks: dict[int, Track] = {}
        self.timing: dict[str, deque] = {
            k: deque(maxlen=TIMING_KEEP) for k in
            ["preproc", "rf_net", "md_net", "assoc", "ekf", "fuse", "traj", "total"]}

    # ---------------------------------------------------------------- helpers
    def _t(self, key, t0):
        self.timing[key].append((time.perf_counter() - t0) * 1000.0)

    def ensure_track(self, tid: int, p0: np.ndarray, v0: np.ndarray):
        if tid not in self.tracks:
            self.tracks[tid] = Track(tid, EKF(p0, v0))
        return self.tracks[tid]

    # ------------------------------------------------------------------ frame
    def step(self, tid: int, dets: list[Detection], w: Weather, k: int,
             iq: np.ndarray | None = None, spec: np.ndarray | None = None):
        """Xử lý một khung cho một vết bám. Trả về bản tin trạng thái."""
        t_all = time.perf_counter()
        tr = self.tracks[tid]

        # 1) Tiền xử lý: chuẩn hóa số đo (ở đây là chuyển sang mảng liên tục)
        t0 = time.perf_counter()
        dets = [d for d in dets]
        self._t("preproc", t0)

        # 2) Suy luận nặng, chỉ khi có dữ liệu thô mới
        t0 = time.perf_counter()
        if iq is not None:
            lp = rf_logp(self.rf, iq)
            for d in dets:
                if d.sensor == "rf":
                    d.cls_logp = lp
        self._t("rf_net", t0)

        t0 = time.perf_counter()
        if spec is not None:
            lp = md_logp(self.md, spec)
            for d in dets:
                if d.sensor == "radar":
                    d.cls_logp = lp
        self._t("md_net", t0)

        # 3) Liên kết số đo với vết bám (cổng thống kê nằm trong EKF.update)
        t0 = time.perf_counter()
        order = {"lidar": 0, "radar": 1, "eo": 2, "rf": 3}
        dets = sorted(dets, key=lambda d: order.get(d.sensor, 9))
        self._t("assoc", t0)

        # 4) EKF: dự đoán rồi cập nhật tuần tự theo từng cảm biến
        t0 = time.perf_counter()
        tr.ekf.predict(FRAME_DT)
        used = []
        for d in dets:
            if tr.ekf.update(d.sensor, d.z, d.R):
                used.append(d.sensor)
        self._t("ekf", t0)

        # 5) Hợp nhất nhận dạng
        t0 = time.perf_counter()
        rng_m = float(np.linalg.norm(tr.ekf.pos))
        fused = tr.fuser.update(dets, w, rng_m)
        tr.confidence = track_confidence(fused, tr.ekf.pos_sigma(), len(set(used)))
        self._t("fuse", t0)

        # 6) Dự đoán quỹ đạo khi mất dấu
        #
        # Lịch sử đưa vào Transformer phải là các khung CÓ SỐ ĐO THẬT. Nếu
        # đưa cả những khung mất dấu vào thì đầu vào chính là đường thẳng do
        # EKF tự ngoại suy ra, và Transformer chỉ việc chép lại đường thẳng
        # đó — nó không còn bù được gì nữa.
        t0 = time.perf_counter()
        tr.hist.append((tr.ekf.pos, tr.ekf.vel))
        pred = None
        if used:
            tr.last_seen = k
            tr.blackout_from = None
            tr.blackout_pred = None
            tr.blackout_hist = None
        elif (k - tr.last_seen) >= GAP_MIN and len(tr.hist) > HIST:
            # Chỉ coi là MẤT DẤU khi gián đoạn kéo dài: cảm biến rớt một hai
            # khung là chuyện thường, EKF tự lo được. Gọi Transformer vào lúc
            # đó chỉ thêm sai số.
            if tr.blackout_from is None:       # vừa bắt đầu mất dấu: chốt mốc
                tr.blackout_from = tr.last_seen
                i0 = len(tr.hist) - 1 - (k - tr.last_seen)
                tr.blackout_pos = tr.hist[i0][0]
                tr.blackout_vel = tr.hist[i0][1]
                tr.blackout_hist = list(tr.hist)[max(0, i0 + 1 - HIST):i0 + 1]
                tr.blackout_pred = np.zeros((0, 3))
            d = k - tr.blackout_from - 1       # đã mất dấu bao nhiêu khung
            # Nối dự đoán DẦN DẦN, mỗi lần một đoạn 1 giây, chỉ khi cần tới.
            # Bản cũ tính trọn 9 giây (9 lần gọi Transformer) ngay trong khung
            # đầu tiên mất dấu, tạo một gai thời gian xử lý đúng lúc hệ thống
            # đang khó khăn nhất. Kết quả số học giống hệt (cùng một chuỗi
            # nối), chỉ chia đều chi phí ra theo thời gian.
            need = min(BLACKOUT_STEPS, max(0, d) + HOR)
            while len(tr.blackout_pred) < need:
                tr.blackout_pred, tr.blackout_hist = self._extend(
                    tr.blackout_pred, tr.blackout_hist)
            pred = tr.blackout_pred[:BLACKOUT_STEPS]
            if pred is not None and 0 <= d < len(pred):
                # Dùng dự đoán làm SỐ ĐO GIẢ để kéo vết bám theo đường cong
                # đã học, thay vì để EKF trôi thẳng. Hiệp phương sai nới dần
                # theo thời gian mất dấu: càng lâu càng bớt tin.
                sd = 4.0 + 1.2 * d
                tr.ekf.update("lidar", pred[d], np.eye(3) * sd ** 2, gate=1e9)
            pred = None if pred is None else pred[max(0, d):max(0, d) + HOR]
        self._t("traj", t0)

        if used:
            tr.status = "đang bám"
        elif k - tr.last_seen > 30:
            tr.status = "mất dấu"
        else:
            tr.status = "ngoại suy"

        self._t("total", t_all)
        kind, p = fused.top()
        return {
            "tid": tid, "k": k, "pos": tr.ekf.pos.tolist(),
            "vel": tr.ekf.vel.tolist(), "sigma": tr.ekf.pos_sigma(),
            "sensors": sorted(set(used)), "kind": kind, "kind_p": p,
            "probs": fused.probs().tolist(), "confidence": tr.confidence,
            "conflict": fused.conflict, "status": tr.status,
            "evidence": {k2: round(v, 3) for k2, v in fused.evidence.items()},
            "predicted": None if pred is None else pred.tolist(),
            "alert": tr.confidence >= ALERT_THRESHOLD,
            "needs_operator": (tr.confidence >= CONFIRM_THRESHOLD
                               and kind != "bird" and tr.operator is None),
        }

    def predict_future(self, hist: list) -> np.ndarray:
        """Transformer: HOR (=1 giây) vị trí tương lai tuyệt đối."""
        h = hist[-HIST:]
        p0 = h[-1][0]
        x = np.stack([np.concatenate([(a - p0) / POS_SCALE, b / VEL_SCALE])
                      for a, b in h]).astype(np.float32)
        with torch.no_grad():
            d = self.tj(torch.from_numpy(x[None])).numpy()[0]
        return p0[None] + d * POS_SCALE

    def _extend(self, pred: np.ndarray, hist: list):
        """Nối thêm một đoạn HOR bước vào chuỗi dự đoán."""
        p = self.predict_future(hist)
        v = np.gradient(p, FRAME_DT, axis=0)
        hist = (hist + [(p[i], v[i]) for i in range(len(p))])[-HIST:]
        return np.concatenate([pred, p]), hist

    def rollout(self, hist: list, n_steps: int) -> np.ndarray:
        """Nối nhiều lần dự đoán để phủ quãng mất dấu dài hơn 1 giây.

        Mỗi vòng lấy 1 giây dự đoán, rồi đưa chính đoạn đó trở lại làm lịch
        sử cho vòng sau. Sai số dồn lại nên càng về sau càng kém — báo cáo
        ghi rõ sai số theo từng mốc thời gian mất dấu.
        """
        hist = list(hist)[-HIST:]
        out = np.zeros((0, 3))
        while len(out) < n_steps:
            out, hist = self._extend(out, hist)
        return out[:n_steps]

    # ----------------------------------------------------------------- tổng kết
    def latency_report(self) -> dict:
        out = {}
        for k, v in self.timing.items():
            if not len(v):
                continue
            a = np.asarray(v)
            out[k] = {"mean_ms": round(float(a.mean()), 3),
                      "p95_ms": round(float(np.percentile(a, 95)), 3),
                      "p99_ms": round(float(np.percentile(a, 99)), 3),
                      "max_ms": round(float(a.max()), 3), "n": len(a)}
        return out
