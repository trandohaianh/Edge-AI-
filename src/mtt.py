"""Bám NHIỀU mục tiêu: liên kết số đo, sinh – xác nhận – xoá vết bám.

``Pipeline`` (pipeline.py) chỉ biết một mục tiêu đã có sẵn vết bám, và coi
mọi số đo trong khung là của mục tiêu đó. Ngoài thực địa thì khác: radar trả
về một danh sách điểm TRỘN LẪN của nhiều drone, chim và cả báo động giả, và
không ai cho biết điểm nào của ai. Module này giải đúng bài toán đó:

1. **Suy luận theo batch, chia lượt.** Chỉ vết bám ĐÃ XÁC NHẬN mới được
   lấy chữ ký micro-Doppler / đoạn I/Q, và mỗi vết có pha riêng
   (``(k + tid) % chu kỳ``) nên mỗi khung chỉ khoảng N/3 vết chạy mạng radar
   và N/5 vết chạy mạng RF, gộp thành một batch mỗi loại. Bản đầu cho cả N
   vết chạy cùng một khung và tạo đuôi thời gian xử lý hơn 150 ms với 6 mục
   tiêu.
2. **Liên kết toàn cục (GNN).** Với từng loại cảm biến, dựng ma trận khoảng
   cách Mahalanobis giữa vết bám (đã dự đoán) và số đo, cắt bằng cổng χ² mức
   99,9% theo đúng số chiều của số đo, rồi gán một-một bằng thuật toán
   Hungarian. Gán toàn cục tránh được lỗi "vết bám tham lam" giành số đo của
   vết bám bên cạnh khi hai mục tiêu bay gần nhau.
3. **Quản lý vết bám M-of-N.** Số đo radar/LiDAR không gán được cho ai sinh
   ra vết bám *tạm*. Vết tạm có số đo VỊ TRÍ (radar/LiDAR) ở ít nhất 3 trong
   5 khung gần nhất thì được *xác nhận*; không thì bị xoá. Báo động giả rải
   ngẫu nhiên nên gần như không bao giờ qua được luật này. Vết đã xác nhận bị
   xoá khi quá lâu không có số đo vị trí hoặc khi trùng với một vết khác.

   Chỉ đếm số đo VỊ TRÍ là bài học từ bản đầu: RF và camera chỉ đo GÓC, nên
   một vết rác nằm cùng hướng với drone thật (cách vài trăm mét theo cự ly)
   vẫn nhận được số đo góc của drone đó mỗi khung và sống mãi. Số đo góc
   cũng chỉ được gán cho vết đã xác nhận.
4. **Dẫn camera lần lượt.** Camera chỉ có một và chỉ nhìn 60°, nên nó được
   quay lần lượt tới từng vết bám chưa phải chim, mỗi vết 1 giây.

Sau khi đã gán, mỗi vết bám đi qua đúng ``Pipeline.advance`` (EKF, hợp nhất
nhận dạng, dự đoán khi mất dấu) như bản một mục tiêu.
"""
from __future__ import annotations

import time
from collections import deque

import numpy as np
from scipy.optimize import linear_sum_assignment

from config import FRAME_DT, MD_EVERY, RF_EVERY
from ekf import EKF
from pipeline import Pipeline, Track
from scene import Detection, Weather
from sensors import EOTurret

# Cổng χ² mức 99,9% theo số chiều của số đo.
CHI2_GATE = {"radar": 18.47, "lidar": 16.27, "eo": 13.82, "rf": 10.83}
SENSOR_ORDER = ("lidar", "radar", "eo", "rf")
POS_SENSORS = ("lidar", "radar")       # chỉ các cảm biến cho đủ toạ độ 3D mới sinh được vết
CONFIRM_M, CONFIRM_N = 3, 5            # xác nhận: 3 trong 5 khung gần nhất có số đo
TENTATIVE_MAX_AGE = 6                  # vết tạm quá 6 khung chưa xác nhận thì xoá
DELETE_AFTER = 40                      # vết đã xác nhận: mất dấu 4 s thì xoá
DELETE_SIGMA = 250.0                   # hoặc độ bất định vị trí quá 250 m
MERGE_DIST = 12.0                      # hai vết cách nhau < 12 m liên tục: trùng
MERGE_FRAMES = 5
SPAWN_SEP = 40.0                       # trong cùng khung, số đo mới cách vết vừa sinh < 40 m thì bỏ
CAMERA_DWELL = 10                      # khung camera dừng ở mỗi vết bám
_BIG = 1e9


def radar_to_state(z: np.ndarray, R: np.ndarray) -> tuple[np.ndarray, np.ndarray, float, float]:
    """Số đo radar (r, az, el, ṙ) -> vị trí, vận tốc ban đầu và phương sai."""
    r, az, el, rr = (float(v) for v in z)
    u = np.array([np.cos(el) * np.cos(az), np.cos(el) * np.sin(az), np.sin(el)])
    p = r * u
    v = rr * u                      # chỉ biết thành phần xuyên tâm
    sa = float(np.sqrt(R[1, 1]))
    p_var = float(R[0, 0] + (r * sa * 1.6) ** 2)
    return p, v, max(p_var, 25.0), 20.0 ** 2


def _det_xyz_sigma(d: Detection) -> tuple[np.ndarray, float]:
    if d.sensor == "lidar":
        return np.asarray(d.z, float), float(np.sqrt(d.R[0, 0]))
    p, _, p_var, _ = radar_to_state(d.z, d.R)
    return p, float(np.sqrt(p_var))


def _coarse_gate(sensor: str, trs: list[Track], D: list[Detection]) -> np.ndarray:
    """Lọc thô, vector hoá: loại các cặp vết–số đo xa nhau rõ ràng trước khi
    tính Mahalanobis. Ngưỡng 5σ + 30 m (σ lấy theo vết dọc trace(P), luôn ≥
    trục lớn nhất của elip sai số) rộng hơn cổng χ² 99,9% (~4,3σ), nên nó
    chỉ bỏ những cặp đằng nào cũng trượt cổng."""
    tp = np.array([t.ekf.x[:3] for t in trs])
    ts = np.array([np.sqrt(np.trace(t.ekf.P[:3, :3])) for t in trs])
    if sensor in POS_SENSORS:
        xs = [_det_xyz_sigma(d) for d in D]
        dp = np.array([x[0] for x in xs])
        ds = np.array([x[1] for x in xs])
        dist = np.linalg.norm(tp[:, None] - dp[None], axis=2)
        return dist < 5.0 * np.sqrt(ts[:, None] ** 2 + ds[None] ** 2) + 30.0
    taz = np.arctan2(tp[:, 1], tp[:, 0])
    rr = np.maximum(np.linalg.norm(tp, axis=1), 1.0)
    daz = np.array([float(d.z[0]) for d in D])
    dsa = np.array([float(np.sqrt(d.R[0, 0])) for d in D])
    diff = np.abs((taz[:, None] - daz[None] + np.pi) % (2 * np.pi) - np.pi)
    return diff < 5.0 * np.sqrt((ts / rr)[:, None] ** 2 + dsa[None] ** 2) + 0.02


class MultiTracker:
    def __init__(self, models=None, pipe: Pipeline | None = None, raw_provider=None):
        self.pipe = pipe or Pipeline(models)
        self.raw = raw_provider         # (det, "spec"|"iq") -> dữ liệu thô
        self.tracks: dict[int, Track] = {}
        self.next_id = 1
        self.turret = EOTurret(0.0)
        self._cam_tid: int | None = None
        self._cam_since = 0
        self._close: dict[tuple[int, int], int] = {}
        self.timing = {k: deque(maxlen=10_000) for k in ("assoc", "manage", "total")}
        self.stats = {"spawned": 0, "confirmed": 0, "deleted": 0, "merged": 0}

    # ------------------------------------------------------------ vết bám
    def _spawn(self, d: Detection, k: int) -> Track:
        if d.sensor == "radar":
            p, v, p_var, v_var = radar_to_state(d.z, d.R)
        else:                                            # lidar
            p, v, p_var, v_var = np.asarray(d.z, float), np.zeros(3), float(d.R[0, 0]) + 4.0, 20.0 ** 2
        tr = Track(self.next_id, EKF(p, v, p_var=p_var, v_var=v_var))
        tr.born = tr.last_seen = tr.pos_seen = k
        tr.confirmed = False
        self.tracks[tr.tid] = tr
        self.next_id += 1
        self.stats["spawned"] += 1
        return tr

    def _delete(self, tid: int, why: str = "deleted"):
        self.tracks.pop(tid, None)
        self.stats[why] += 1
        if self._cam_tid == tid:
            self._cam_tid = None

    # --------------------------------------------------------------- liên kết
    def associate(self, dets: list[Detection]) -> tuple[dict[int, list], list[Detection]]:
        """Gán số đo cho vết bám (GNN theo từng loại cảm biến).

        Trả về (tid -> danh sách số đo, các số đo vị trí không gán được)."""
        assigned: dict[int, list] = {tid: [] for tid in self.tracks}
        free: list[Detection] = []
        for sensor in SENSOR_ORDER:
            D = [d for d in dets if d.sensor == sensor]
            if not D:
                continue
            trs = [t for t in self.tracks.values()
                   if sensor in POS_SENSORS or t.confirmed]
            if not trs:
                if sensor in POS_SENSORS:
                    free += D
                continue
            C = np.full((len(trs), len(D)), _BIG)
            gate = CHI2_GATE[sensor]
            near = _coarse_gate(sensor, trs, D)
            for i, tr in enumerate(trs):
                js = np.flatnonzero(near[i])
                if not len(js):
                    continue
                terms = tr.ekf.gate_terms(sensor)
                for j in js:
                    d = D[j]
                    d2 = EKF.mahalanobis_from(sensor, terms, d.z, d.R)
                    if d2 < gate:
                        # Vết đã xác nhận được ưu tiên hơn vết tạm khi tranh
                        # cùng một số đo.
                        C[i, j] = d2 + (0.0 if tr.confirmed else 2.0)
            rows, cols = linear_sum_assignment(C)
            used = set()
            for i, j in zip(rows, cols):
                if C[i, j] < _BIG:
                    assigned[trs[i].tid].append(D[j])
                    used.add(j)
            if sensor in POS_SENSORS:
                free += [d for j, d in enumerate(D) if j not in used]
        return assigned, free

    # ------------------------------------------------------------------ khung
    def step(self, dets: list[Detection], w: Weather, k: int) -> list[dict]:
        """Xử lý một khung. Trả về bản tin của các vết bám ĐÃ XÁC NHẬN."""
        t_all = time.perf_counter()
        for tr in self.tracks.values():
            tr.ekf.predict(FRAME_DT)

        t0 = time.perf_counter()
        assigned, free = self.associate(dets)
        free = self._rescue(assigned, free)
        self.timing["assoc"].append((time.perf_counter() - t0) * 1e3)
        t_raw = time.perf_counter()
        self._request_raw(assigned, k)
        # Thời gian "phần cứng" sinh dữ liệu thô (ở đây là mô phỏng, ~20 ms
        # một ảnh phổ) không thuộc vòng xử lý của thiết bị biên: trừ ra.
        t_all += time.perf_counter() - t_raw
        self.pipe.run_nets([d for ds in assigned.values() for d in ds])

        msgs = {}
        for tid, ds in assigned.items():
            tr = self.tracks[tid]
            ds = sorted(ds, key=lambda d: SENSOR_ORDER.index(d.sensor))
            m = self.pipe.advance(tr, ds, w, k, predict=False)
            pos_hit = any(s in POS_SENSORS for s in m["sensors"])
            tr.hits.append(1 if pos_hit else 0)
            if pos_hit:
                tr.pos_seen = k
            m["confirmed"] = tr.confirmed
            m["operator"] = tr.operator
            m["needs_operator"] = m["needs_operator"] and tr.confirmed
            msgs[tid] = m

        t0 = time.perf_counter()
        self._manage(k, msgs)
        # sinh vết mới từ số đo vị trí còn thừa (LiDAR trước, chính xác hơn)
        born: list[np.ndarray] = []
        for d in sorted(free, key=lambda d: POS_SENSORS.index(d.sensor)):
            p = radar_to_state(d.z, d.R)[0] if d.sensor == "radar" else np.asarray(d.z)
            if any(np.linalg.norm(p - b) < SPAWN_SEP for b in born):
                continue
            tr = self._spawn(d, k)
            tr.hits.append(1)
            born.append(p)
        self.timing["manage"].append((time.perf_counter() - t0) * 1e3)
        self.timing["total"].append((time.perf_counter() - t_all) * 1e3)
        return [msgs[t] for t in sorted(msgs) if t in self.tracks and self.tracks[t].confirmed]

    def _rescue(self, assigned: dict, free: list) -> list:
        """Cứu vết trước khi sinh vết mới.

        Mục tiêu đổi hướng gấp có thể làm số đo radar trượt cổng χ² 99,9%
        của chính vết bám đang theo nó (nhất là thành phần vận tốc xuyên tâm,
        đo rất chính xác). Nếu cứ thế sinh vết mới thì một mục tiêu có hai vết:
        vết mới bám tiếp, vết cũ trôi theo dự đoán và thành vết giả. Ở đây số
        đo vị trí chưa ai nhận được thử lại với cổng nới rộng 4 lần, chỉ với
        các vết ĐÃ XÁC NHẬN mà khung này chưa có số đo vị trí nào."""
        hungry = [self.tracks[t] for t, ds in assigned.items()
                  if self.tracks[t].confirmed and not any(d.sensor in POS_SENSORS for d in ds)]
        if not hungry or not free:
            return free
        C = np.full((len(hungry), len(free)), _BIG)
        for i, tr in enumerate(hungry):
            for j, d in enumerate(free):
                d2 = tr.ekf.mahalanobis(d.sensor, d.z, d.R)
                if d2 < 4.0 * CHI2_GATE[d.sensor]:
                    C[i, j] = d2
        rows, cols = linear_sum_assignment(C)
        taken = set()
        for i, j in zip(rows, cols):
            if C[i, j] < _BIG:
                d = free[j]
                assigned[hungry[i].tid].insert(0, d)
                d.meta["rescued"] = True
                d.meta["gate"] = 4.0 * CHI2_GATE[d.sensor] / len(d.z) + 1.0
                taken.add(j)
        return [d for j, d in enumerate(free) if j not in taken]

    def _request_raw(self, assigned: dict, k: int) -> None:
        """Xin dữ liệu thô cho các vết đã xác nhận tới lượt (xem docstring)."""
        if self.raw is None:
            return
        for tid, ds in assigned.items():
            if not self.tracks[tid].confirmed:
                continue
            for d in ds:
                if d.sensor == "radar" and (k + tid) % MD_EVERY == 0 and "spec" not in d.meta:
                    d.meta["spec"] = self.raw(d, "spec")
                elif d.sensor == "rf" and (k + tid) % RF_EVERY == 0 and "iq" not in d.meta:
                    d.meta["iq"] = self.raw(d, "iq")

    def _manage(self, k: int, msgs: dict):
        for tid in list(self.tracks):
            tr = self.tracks[tid]
            age = k - tr.born
            if not tr.confirmed:
                if sum(list(tr.hits)[-CONFIRM_N:]) >= CONFIRM_M:
                    tr.confirmed = True
                    self.stats["confirmed"] += 1
                    msgs[tid]["confirmed"] = True
                elif age >= TENTATIVE_MAX_AGE:
                    self._delete(tid)
            elif k - tr.pos_seen > DELETE_AFTER or tr.ekf.pos_sigma() > DELETE_SIGMA:
                self._delete(tid)
        # Hai vết bám đã xác nhận nằm sát nhau nhiều khung liền là một mục
        # tiêu bị bám hai lần: giữ vết già hơn.
        conf = [t for t in self.tracks.values() if t.confirmed]
        seen = set()
        for i, a in enumerate(conf):
            for b in conf[i + 1:]:
                key = (min(a.tid, b.tid), max(a.tid, b.tid))
                if np.linalg.norm(a.ekf.pos - b.ekf.pos) < MERGE_DIST:
                    seen.add(key)
                    self._close[key] = self._close.get(key, 0) + 1
                    if self._close[key] >= MERGE_FRAMES:
                        young = a if a.born > b.born else b
                        if young.tid in self.tracks:
                            self._delete(young.tid, "merged")
        self._close = {kk: v for kk, v in self._close.items() if kk in seen}

    # ---------------------------------------------------------------- camera
    def point_camera(self, k: int) -> float:
        """Quay camera lần lượt qua các vết bám đã xác nhận mà chưa bị coi là
        chim, mỗi vết ``CAMERA_DWELL`` khung. Gọi sau ``step``."""
        cand = sorted(t.tid for t in self.tracks.values()
                      if t.confirmed and t.fuser.state.top()[0] != "bird")
        if not cand:
            cand = sorted(t.tid for t in self.tracks.values() if t.confirmed)
        if cand:
            if self._cam_tid not in cand or k - self._cam_since >= CAMERA_DWELL:
                nxt = [t for t in cand if self._cam_tid is None or t > self._cam_tid]
                self._cam_tid = (nxt or cand)[0]
                self._cam_since = k
            p = self.tracks[self._cam_tid].ekf.pos
            self.turret.point(float(np.arctan2(p[1], p[0])))
        return self.turret.az

    def act(self, tid: int, action: str) -> bool:
        tr = self.tracks.get(tid)
        if tr is None or not tr.confirmed or tr.operator is not None:
            return False
        tr.operator = action
        return True
