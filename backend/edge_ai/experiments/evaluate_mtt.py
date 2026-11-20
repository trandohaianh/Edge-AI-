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
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

from edge_ai.config import SEED
from edge_ai.tracking.mtt import MultiTracker
from edge_ai.tracking.pipeline import load_models
from edge_ai.sim.scene import Target, Weather, make_trajectory, rotate_into_view
from edge_ai.sim.sensors import RawProvider, sense_all

from edge_ai.config import CACHE_DIR, MODELS_DIR, RESULTS_DIR  # noqa: F401
OSPA_C, MATCH_M, WARMUP = 100.0, 50.0, 30


def build_targets(spec: list[dict], n: int, rng: np.random.Generator) -> list[Target]:
    out = []
    for i, s in enumerate(spec):
        p, v = make_trajectory(s["kind"], n, rng, s.get("pattern", "approach"), r0=s["r0"])
        tg = Target(kind=s["kind"], pos=p, vel=v, emits_rf=s["kind"] != "bird",
                    patch=s.get("patch", False), tid=i)
        out.append(rotate_into_view(tg, np.deg2rad(s["az"])))
    return out


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
    return {"ospa_m": float(np.mean(o)), "coverage": cover / max(tot, 1),
            "id_switches": switches, "false_tracks_per_frame": fake / max(n - WARMUP, 1),
            "cls_acc": cls_ok / max(cls_n, 1), "bird_operator_frames": bird_ask,
            "lat_mean_ms": float(t.mean()), "lat_p99_ms": float(np.percentile(t, 99)),
            "lat_max_ms": float(t.max()), "spawned": mt.stats["spawned"]}


def _fan(kinds, r0=900.0, spread=50.0, pattern="approach"):
    """Nhiều mục tiêu toả đều trong một góc ``spread`` độ quanh hướng 0."""
    az = np.linspace(-spread / 2, spread / 2, len(kinds)) if len(kinds) > 1 else [0.0]
    return [dict(kind=k, r0=r0 + 60 * i, az=float(a), pattern=pattern)
            for i, (k, a) in enumerate(zip(kinds, az))]


SCENARIOS = [
    ("M1 · 3 drone + 1 chim, báo động giả 1/khung",
     _fan(["multirotor", "fixed_wing", "multirotor", "bird"]), Weather(), 1.0),
    ("M2 · 2 drone bay sát nhau (cách 2°), báo động giả 1/khung",
     [dict(kind="multirotor", r0=900, az=0.0), dict(kind="multirotor", r0=930, az=2.0)],
     Weather(), 1.0),
    ("M3 · bầy 6 drone trong mưa, báo động giả 3/khung",
     _fan(["multirotor"] * 4 + ["fixed_wing"] * 2, spread=70.0), Weather(rain=0.6), 3.0),
    ("M4 · 2 drone + 2 chim, sương mù đêm",
     _fan(["multirotor", "bird", "multirotor", "bird"], r0=700), Weather(fog=0.8, night=True), 1.0),
]
KEYS = ["ospa_m", "coverage", "id_switches", "false_tracks_per_frame", "cls_acc",
        "bird_operator_frames", "lat_mean_ms", "lat_p99_ms", "lat_max_ms"]


def scaling(models, n_frames=120, counts=(1, 3, 6, 10), repeats=3):
    """Thời gian xử lý một khung theo số mục tiêu (báo động giả 1/khung).

    Mỗi mức chạy ``repeats`` lần và lấy TRUNG VỊ của từng thống kê: trên máy
    dùng chung, một lần chạy có thể trùng lúc tiến trình khác chiếm CPU và
    đẩy p99 lên gấp đôi; trung vị của nhiều lần bớt phụ thuộc vào may rủi đó.
    """
    out = []
    keys = ("lat_mean_ms", "lat_p99_ms", "lat_max_ms")
    for c in counts:
        rs = [run(models, _fan(["multirotor"] * c, spread=90.0), Weather(), n_frames,
                  SEED + 900 + c, 1.0) for _ in range(repeats)]
        row = {"targets": c, "repeats": repeats}
        row |= {k: round(float(np.median([r[k] for r in rs])), 3) for k in keys}
        out.append(row)
        print(f"  {c:2d} mục tiêu: trung bình {row['lat_mean_ms']:.2f} ms, "
              f"p99 {row['lat_p99_ms']:.2f} ms, max {row['lat_max_ms']:.2f} ms "
              f"(trung vị {repeats} lần)", flush=True)
    return out


def main(n_runs: int = 5, n_frames: int = 200):
    models = load_models()
    t0 = time.time()
    res = {"scenarios": [], "frames": n_frames, "runs_per_scenario": n_runs,
           "ospa_c_m": OSPA_C, "match_m": MATCH_M, "warmup_frames": WARMUP}
    for si, (name, spec, w, clutter) in enumerate(SCENARIOS):
        runs = [run(models, spec, w, n_frames, SEED + 5000 + 97 * si + i, clutter)
                for i in range(n_runs)]
        s = {"scenario": name, "n_targets": len(spec), "clutter_per_frame": clutter}
        for key in KEYS:
            a = np.asarray([r[key] for r in runs], float)
            s[key] = round(float(a.mean()), 3)
            if key in ("ospa_m", "coverage", "cls_acc"):
                h = 1.96 * a.std(ddof=1) / np.sqrt(len(a)) if len(a) > 1 else 0.0
                s[key + "_ci95"] = [round(float(a.mean() - h), 3), round(float(a.mean() + h), 3)]
        res["scenarios"].append(s)
        print(f"{name:58s} OSPA={s['ospa_m']:6.1f} m  phủ={s['coverage']:.3f}  "
              f"đổiID={s['id_switches']:.1f}  giả={s['false_tracks_per_frame']:.3f}  "
              f"nhận dạng={s['cls_acc']:.3f}  chim hỏi={s['bird_operator_frames']:.1f}",
              flush=True)
    res["scaling"] = scaling(models)
    res["note"] = ("Đo trên CPU x86 (Windows, 2 luồng torch), không phải Jetson. "
                   "Dữ liệu mô phỏng.")
    with open(RESULTS_DIR / "mtt_results.json", "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1, ensure_ascii=False)
    print(f"done {time.time() - t0:.0f}s")
    return res


if __name__ == "__main__":
    main()
