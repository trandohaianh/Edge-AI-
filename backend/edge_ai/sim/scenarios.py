"""Dựng kịch bản nhiều mục tiêu từ một mô tả ngắn.

Dùng chung cho đánh giá (experiments/evaluate_mtt.py) và dashboard
(api/server.py). Đặt ở ``sim/`` để máy chủ không phải import mã đánh giá.
"""

from __future__ import annotations

import numpy as np

from edge_ai.sim.scene import Target, make_trajectory, rotate_into_view


def build_targets(spec: list[dict], n: int, rng: np.random.Generator) -> list[Target]:
    out = []
    for i, s in enumerate(spec):
        p, v = make_trajectory(s["kind"], n, rng, s.get("pattern", "approach"), r0=s["r0"])
        tg = Target(
            kind=s["kind"],
            pos=p,
            vel=v,
            emits_rf=s["kind"] != "bird",
            patch=s.get("patch", False),
            tid=i,
        )
        out.append(rotate_into_view(tg, np.deg2rad(s["az"])))
    return out


def fan_targets(kinds, r0=900.0, spread=50.0, pattern="approach"):
    """Nhiều mục tiêu toả đều trong một góc ``spread`` độ quanh hướng 0."""
    az = np.linspace(-spread / 2, spread / 2, len(kinds)) if len(kinds) > 1 else [0.0]
    return [
        dict(kind=k, r0=r0 + 60 * i, az=float(a), pattern=pattern)
        for i, (k, a) in enumerate(zip(kinds, az))
    ]
