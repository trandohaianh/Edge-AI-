"""E4-A: p50/p95/p99 thời gian xử lý MỘT khung (PyTorch eager) trên máy đang chạy.

Số THÔ của từng khung (không lấy min qua nhiều lần phát lại như
``evaluate_mtt.replay_latency``), nên gồm cả nhiễu do hệ điều hành chen vào:
đó là con số người trực thật sự gặp. Thời gian sinh dữ liệu mô phỏng không
tính (``MultiTracker.step`` đã trừ ra).

Chạy:  python -m edge_ai.experiments.frame_latency   (trong backend/)
Ghi:   data/results/frame_latency.json
"""

import os
import platform

import numpy as np
import torch

from edge_ai.config import LATENCY_BUDGET_MS, RESULTS_DIR, SEED
from edge_ai.experiments.evaluate import run_scenario
from edge_ai.experiments.evaluate_mtt import SCENARIOS
from edge_ai.io_utils import write_json
from edge_ai.sim.scenarios import build_targets, fan_targets
from edge_ai.sim.scene import Weather
from edge_ai.sim.sensors import RawProvider, sense_all
from edge_ai.tracking.mtt import MultiTracker
from edge_ai.tracking.pipeline import load_models, warmup


def stats(a):
    a = np.asarray(a)
    return {
        "n": int(a.size),
        "p50_ms": round(float(np.percentile(a, 50)), 3),
        "p95_ms": round(float(np.percentile(a, 95)), 3),
        "p99_ms": round(float(np.percentile(a, 99)), 3),
        "max_ms": round(float(a.max()), 3),
        "over_budget": int((a > LATENCY_BUDGET_MS).sum()),
    }


def cpu_model():
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor()


def main(out=RESULTS_DIR / "frame_latency.json"):
    models = load_models()
    warmup(models)
    res = {
        "host": {
            "cpu": cpu_model(),
            "logical_cpus": os.cpu_count(),
            "os": platform.platform(),
            "python": platform.python_version(),
            "numpy": np.__version__,
            "torch": torch.__version__,
            "torch_threads": torch.get_num_threads(),
            "runtime": "PyTorch eager (CPU)",
        },
        "budget_ms": LATENCY_BUDGET_MS,
    }
    # Tên đầy đủ để hạt giống trùng evaluate.main (seed = SEED + 100*i + len(name))
    # 1) Một mục tiêu: 7 kịch bản của evaluate.main, 8 lần x 220 khung
    names = [
        ("S1 · trời quang, drone đa cánh quạt", dict(kind="multirotor", w=Weather())),
        ("S2 · đêm + sương mù dày", dict(kind="multirotor", w=Weather(fog=0.85, night=True))),
        ("S3 · nhiễu dải RF", dict(kind="multirotor", w=Weather(jamming=0.9))),
        ("S4 · mưa to", dict(kind="fixed_wing", w=Weather(rain=0.8))),
        ("S5 · chim (phải loại, không báo động)", dict(kind="bird", w=Weather())),
        (
            "S6 · dán nhãn ngụy trang đánh lừa camera",
            dict(kind="multirotor", w=Weather(), patch=True, r0=900.0),
        ),
        (
            "S7 · mất dấu 4 giây giữa chừng",
            dict(kind="multirotor", w=Weather(), dropout=(110, 150)),
        ),
    ]
    single = []
    for name, kw in names:
        for i in range(8):
            r = run_scenario(models, seed=SEED + 100 * i + len(name), n_frames=220, **kw)
            single += list(r["pipeline"].timing["total"])[3:]
    res["single_target_pipeline"] = stats(single)
    print("single", res["single_target_pipeline"], flush=True)
    # 2) Nhiều mục tiêu: 4 kịch bản của evaluate_mtt.main, 5 lần x 200 khung (thô, không lấy min)
    multi = {}
    for si, (name, spec, w, clutter) in enumerate(SCENARIOS):
        ts = []
        for i in range(5):
            rng = np.random.default_rng(SEED + 5000 + 97 * si + i)
            tgs = build_targets(spec, 200, rng)
            mt = MultiTracker(models, raw_provider=RawProvider(tgs, w, rng))
            for k in range(200):
                dets = sense_all(
                    tgs, k, w, rng, eo_az=mt.turret.az, clutter_rate=clutter, raw=False
                )
                mt.step(dets, w, k)
                mt.point_camera(k)
            ts += list(mt.timing["total"])[3:]
        multi[name] = stats(ts)
        print(name, multi[name], flush=True)
    res["multi_target_mtt"] = multi
    # 3) 10 mục tiêu (trường hợp nặng nhất của scaling), 120 khung x 5 lần, thô
    rows = []
    for rep in range(5):
        rng = np.random.default_rng(SEED + 900 + 10 + rep)
        w = Weather()
        tgs = build_targets(fan_targets(["multirotor"] * 10, spread=90.0), 120, rng)
        mt = MultiTracker(models, raw_provider=RawProvider(tgs, w, rng))
        for k in range(120):
            dets = sense_all(tgs, k, w, rng, eo_az=mt.turret.az, clutter_rate=1.0, raw=False)
            mt.step(dets, w, k)
            mt.point_camera(k)
        rows += list(mt.timing["total"])[3:]
    res["ten_targets_mtt"] = stats(rows)
    print("10 targets", res["ten_targets_mtt"], flush=True)
    write_json(out, res)


if __name__ == "__main__":
    main()
