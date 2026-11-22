"""Đánh giá bám NHIỀU mục tiêu có báo động giả.

Chỉ số (đều là chuẩn trong tài liệu về bám đa mục tiêu):

* **OSPA** (c = 100 m, p = 1): một con số gộp cả sai số vị trí, mục tiêu bị
  sót và vết bám thừa. 0 là hoàn hảo; mỗi mục tiêu sót hay vết thừa bị phạt
  bằng c.
* **Độ phủ**: tỉ lệ (mục tiêu, khung) có một vết bám đã xác nhận nằm trong
  50 m (gán một-một).
* **Đổi ID**: số lần một mục tiêu chuyển sang được bám bởi vết bám khác.
* **Vết giả / khung**: số vết đã xác nhận không ứng với mục tiêu nào.
* **Nhận dạng đúng**: trên các cặp đã gán, nhãn vết bám trùng với loại thật.
* **Hỏi người vì chim**: số khung một con chim bị đưa lên người trực.

Chạy:  python src/evaluate_mtt.py      (ghi data/mtt_results.json)
"""

from __future__ import annotations

import json
import time

import numpy as np
from scipy.optimize import linear_sum_assignment

from edge_ai.config import CACHE_DIR, MODELS_DIR, RESULTS_DIR, SEED  # noqa: F401
from edge_ai.sim.scenarios import build_targets, fan_targets
from edge_ai.sim.scene import Weather
from edge_ai.sim.sensors import RawProvider, sense_all
from edge_ai.tracking.mtt import MultiTracker
from edge_ai.tracking.pipeline import load_models

OSPA_C, MATCH_M, WARMUP = 100.0, 50.0, 30


def ospa(X: np.ndarray, Y: np.ndarray, c: float = OSPA_C) -> float:
    m, n = len(X), len(Y)
    if m == 0 and n == 0:
        return 0.0
    if m == 0 or n == 0:
        return c
    D = np.minimum(np.linalg.norm(X[:, None] - Y[None], axis=2), c)
    r, cc = linear_sum_assignment(D)
    return float((D[r, cc].sum() + c * abs(m - n)) / max(m, n))


def run(models, spec, w: Weather, n: int, seed: int, clutter: float):
    rng = np.random.default_rng(seed)
    tgs = build_targets(spec, n, rng)
    mt = MultiTracker(models, raw_provider=RawProvider(tgs, w, rng))
    o, cover, tot, fake, cls_ok, cls_n, bird_ask = [], 0, 0, 0, 0, 0, 0
    last_tid = {t.tid: None for t in tgs}
    switches = 0
    for k in range(n):
        dets = sense_all(tgs, k, w, rng, eo_az=mt.turret.az, clutter_rate=clutter, raw=False)
        msgs = mt.step(dets, w, k)
        mt.point_camera(k)
        if k < WARMUP:
            continue
        truth = np.array([t.pos[k] for t in tgs])
        est = np.array([m["pos"] for m in msgs]) if msgs else np.zeros((0, 3))
        o.append(ospa(truth, est))
        tot += len(tgs)
        matched = set()
        if len(est):
            D = np.linalg.norm(truth[:, None] - est[None], axis=2)
            r, cc = linear_sum_assignment(D)
            for i, j in zip(r, cc):
                if D[i, j] > MATCH_M:
                    continue
                matched.add(j)
                cover += 1
                tg, m = tgs[i], msgs[j]
                if last_tid[tg.tid] is not None and last_tid[tg.tid] != m["tid"]:
                    switches += 1
                last_tid[tg.tid] = m["tid"]
                if k >= 2 * WARMUP:
                    cls_n += 1
                    cls_ok += m["kind"] == tg.kind
                if tg.kind == "bird" and m["needs_operator"]:
                    bird_ask += 1
        fake += len(msgs) - len(matched)
    t = np.asarray(mt.timing["total"])[3:]
    return {
        "ospa_m": float(np.mean(o)),
        "coverage": cover / max(tot, 1),
        "id_switches": switches,
        "false_tracks_per_frame": fake / max(n - WARMUP, 1),
        "cls_acc": cls_ok / max(cls_n, 1),
        "bird_operator_frames": bird_ask,
        "lat_mean_ms": float(t.mean()),
        "lat_p99_ms": float(np.percentile(t, 99)),
        "lat_max_ms": float(t.max()),
        "spawned": mt.stats["spawned"],
    }


SCENARIOS = [
    (
        "M1 · 3 drone + 1 chim, báo động giả 1/khung",
        fan_targets(["multirotor", "fixed_wing", "multirotor", "bird"]),
        Weather(),
        1.0,
    ),
    (
        "M2 · 2 drone bay sát nhau (cách 2°), báo động giả 1/khung",
        [dict(kind="multirotor", r0=900, az=0.0), dict(kind="multirotor", r0=930, az=2.0)],
        Weather(),
        1.0,
    ),
    (
        "M3 · bầy 6 drone trong mưa, báo động giả 3/khung",
        fan_targets(["multirotor"] * 4 + ["fixed_wing"] * 2, spread=70.0),
        Weather(rain=0.6),
        3.0,
    ),
    (
        "M4 · 2 drone + 2 chim, sương mù đêm",
        fan_targets(["multirotor", "bird", "multirotor", "bird"], r0=700),
        Weather(fog=0.8, night=True),
        1.0,
    ),
]
KEYS = [
    "ospa_m",
    "coverage",
    "id_switches",
    "false_tracks_per_frame",
    "cls_acc",
    "bird_operator_frames",
    "lat_mean_ms",
    "lat_p99_ms",
    "lat_max_ms",
]


class _CachedRaw(RawProvider):
    """Dữ liệu thô sinh MỘT lần rồi dùng lại, để mọi lần phát lại nhận đúng
    cùng ảnh phổ / đoạn I/Q và bộ bám làm đúng cùng một khối lượng việc."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.k = 0
        self.cache: dict = {}

    def __call__(self, d, what):
        key = (self.k, d.meta.get("truth_id", -1), what, float(d.z[0]))
        if key not in self.cache:
            self.cache[key] = super().__call__(d, what)
        return self.cache[key]


def replay_latency(
    models,
    n_targets: int,
    n_frames: int = 120,
    repeats: int = 5,
    clutter: float = 1.0,
    seed: int | None = None,
) -> dict:
    """Thời gian xử lý mỗi khung, đo bằng PHÁT LẠI và lấy MIN theo từng khung.

    Lần chạy đầu ghi lại số đo của từng khung (và sinh dữ liệu thô). Sau đó
    phát lại đúng chuỗi đó qua ``repeats`` bộ bám mới. Bộ bám là tất định nên
    mọi lần phát lại làm cùng một khối lượng việc; chênh lệch thời gian giữa
    các lần CHỈ do tiến trình khác chen vào CPU. Lấy min theo từng khung là
    cách chuẩn để ước lượng chi phí thật (``timeit`` cũng lấy min).

    Trả về cả thống kê của chuỗi min lẫn trung vị p99 của các lần chạy thô,
    để người đọc thấy mức nhiễu của máy đo.
    """
    import copy

    seed = SEED + 900 + n_targets if seed is None else seed
    rng = np.random.default_rng(seed)
    w = Weather()
    tgs = build_targets(fan_targets(["multirotor"] * n_targets, spread=90.0), n_frames, rng)
    raw = _CachedRaw(tgs, w, rng)
    mt = MultiTracker(models, raw_provider=raw)
    frames = []
    for k in range(n_frames):
        dets = sense_all(tgs, k, w, rng, eo_az=mt.turret.az, clutter_rate=clutter, raw=False)
        frames.append(copy.deepcopy(dets))
        raw.k = k
        mt.step(dets, w, k)
        mt.point_camera(k)
    runs = []
    for _ in range(repeats):
        m2 = MultiTracker(models, raw_provider=raw)
        for k, dets in enumerate(frames):
            raw.k = k
            m2.step(copy.deepcopy(dets), w, k)
            m2.point_camera(k)
        runs.append(np.asarray(m2.timing["total"])[3:])
    R = np.stack(runs)
    best = R.min(axis=0)
    return {
        "targets": n_targets,
        "repeats": repeats,
        "min_mean_ms": round(float(best.mean()), 3),
        "min_p99_ms": round(float(np.percentile(best, 99)), 3),
        "min_max_ms": round(float(best.max()), 3),
        "raw_p99_median_ms": round(float(np.median(np.percentile(R, 99, axis=1))), 3),
        "frames_over_budget_min": int((best > 50.0).sum()),
        "frames": int(best.size),
    }


def scaling(models, n_frames=120, counts=(1, 3, 6, 10), repeats=5):
    """Thời gian xử lý một khung theo số mục tiêu (báo động giả 1/khung)."""
    out = []
    for c in counts:
        row = replay_latency(models, c, n_frames, repeats)
        out.append(row)
        print(
            f"  {c:2d} mục tiêu: min-theo-khung TB {row['min_mean_ms']:.2f} ms, "
            f"p99 {row['min_p99_ms']:.2f} ms, max {row['min_max_ms']:.2f} ms | "
            f"p99 thô (trung vị {repeats} lần) {row['raw_p99_median_ms']:.2f} ms",
            flush=True,
        )
    return out


def main(n_runs: int = 5, n_frames: int = 200):
    models = load_models()
    t0 = time.time()
    res = {
        "scenarios": [],
        "frames": n_frames,
        "runs_per_scenario": n_runs,
        "ospa_c_m": OSPA_C,
        "match_m": MATCH_M,
        "warmup_frames": WARMUP,
    }
    for si, (name, spec, w, clutter) in enumerate(SCENARIOS):
        runs = [
            run(models, spec, w, n_frames, SEED + 5000 + 97 * si + i, clutter)
            for i in range(n_runs)
        ]
        s = {"scenario": name, "n_targets": len(spec), "clutter_per_frame": clutter}
        for key in KEYS:
            a = np.asarray([r[key] for r in runs], float)
            s[key] = round(float(a.mean()), 3)
            if key in ("ospa_m", "coverage", "cls_acc"):
                h = 1.96 * a.std(ddof=1) / np.sqrt(len(a)) if len(a) > 1 else 0.0
                s[key + "_ci95"] = [round(float(a.mean() - h), 3), round(float(a.mean() + h), 3)]
        res["scenarios"].append(s)
        print(
            f"{name:58s} OSPA={s['ospa_m']:6.1f} m  phủ={s['coverage']:.3f}  "
            f"đổiID={s['id_switches']:.1f}  giả={s['false_tracks_per_frame']:.3f}  "
            f"nhận dạng={s['cls_acc']:.3f}  chim hỏi={s['bird_operator_frames']:.1f}",
            flush=True,
        )
    res["scaling"] = scaling(models)
    res["note"] = "Đo trên CPU x86 (Windows, 2 luồng torch), không phải Jetson. Dữ liệu mô phỏng."
    with open(RESULTS_DIR / "mtt_results.json", "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1, ensure_ascii=False)
    print(f"done {time.time() - t0:.0f}s")
    return res


if __name__ == "__main__":
    main()
