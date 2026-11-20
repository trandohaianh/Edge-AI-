"""Chạy các kịch bản hiện trường và xuất số đo cho báo cáo.

Mỗi kịch bản lặp lại nhiều lần với hạt giống khác nhau rồi lấy trung bình,
kèm khoảng tin cậy, để con số không phụ thuộc vào một lần chạy may mắn.
"""

from __future__ import annotations

import json
import time

import numpy as np

from edge_ai.config import (  # noqa: F401  # noqa: F401
    CACHE_DIR,
    CONFIRM_THRESHOLD,
    FRAME_DT,
    MD_EVERY,
    MODELS_DIR,
    RESULTS_DIR,
    RF_EVERY,
    SEED,
)
from edge_ai.sim.scene import Weather, make_scenario, sense
from edge_ai.sim.sensors import EOTurret, attach_raw, lambda_iq  # noqa: F401  (tương thích)
from edge_ai.tracking.pipeline import Pipeline, load_models


def run_scenario(
    models,
    kind: str,
    w: Weather,
    n_frames: int,
    seed: int,
    patch: bool = False,
    dropout: tuple[int, int] | None = None,
    pattern: str | None = None,
    r0: float | None = None,
):
    rng = np.random.default_rng(seed)
    pipe = Pipeline(models)
    tg = make_scenario(
        n_frames,
        rng,
        w,
        kinds=[kind],
        patch_ids={0} if patch else set(),
        patterns=[pattern] if pattern else None,
        r0=r0,
    )[0]
    tr = pipe.ensure_track(0, tg.pos[0] + rng.normal(0, 25, 3), tg.vel[0] + rng.normal(0, 6, 3))
    # Camera trên bệ quay, được dẫn theo phương vị của vết bám (không phải
    # theo sự thật mô phỏng — hệ thống chỉ biết cái nó bám được).
    turret = EOTurret(float(np.arctan2(tr.ekf.pos[1], tr.ekf.pos[0])))

    errs, confs, kinds_seen, rows = [], [], [], []
    first_confirm = None
    first_correct = None
    pred_err, ekf_err, blind_curve = [], [], []
    operator_asks = 0
    for k in range(n_frames):
        blind = dropout is not None and dropout[0] <= k < dropout[1]
        dets = [] if blind else sense(tg, k, w, rng, eo_az=turret.az)
        attach_raw(dets, tg, k, w, rng)  # I/Q, ảnh phổ khi tới lịch
        msg = pipe.step(0, dets, w, k)
        turret.point(float(np.arctan2(msg["pos"][1], msg["pos"][0])))

        e = float(np.linalg.norm(np.array(msg["pos"]) - tg.pos[k]))
        errs.append(e)
        confs.append(msg["confidence"])
        kinds_seen.append(msg["kind"])
        if first_confirm is None and msg["confidence"] >= CONFIRM_THRESHOLD:
            first_confirm = k * FRAME_DT
        if first_correct is None and msg["kind"] == tg.kind and msg["kind_p"] > 0.6:
            first_correct = k * FRAME_DT
        if blind:
            # So sánh TẠI CHÍNH KHUNG ĐANG MẤT DẤU:
            #  - vết bám có Transformer dẫn (msg["pos"])
            #  - mốc so sánh: ngoại suy vận tốc không đổi từ lúc mất dấu
            tr = pipe.tracks[0]
            if tr.blackout_from is not None and k > tr.blackout_from:
                d = (k - tr.blackout_from) * FRAME_DT
                cv = tr.blackout_pos + tr.blackout_vel * d
                pred_err.append(float(np.linalg.norm(np.array(msg["pos"]) - tg.pos[k])))
                ekf_err.append(float(np.linalg.norm(cv - tg.pos[k])))
                blind_curve.append((round(d, 2), pred_err[-1], ekf_err[-1]))
        if msg["needs_operator"]:
            operator_asks += 1
        rows.append(msg)

    correct = np.mean([k_ == tg.kind for k_ in kinds_seen[len(kinds_seen) // 3 :]])
    return {
        "kind": tg.kind,
        "weather": w.label(),
        "rmse_m": float(np.mean(errs[20:])),
        "rmse_final_m": float(np.mean(errs[-30:])),
        "mean_conf": float(np.mean(confs[len(confs) // 3 :])),
        "cls_acc_after_warmup": float(correct),
        "time_to_confirm_s": first_confirm,
        "time_to_correct_id_s": first_correct,
        "pred_rmse_transformer_m": float(np.mean(pred_err)) if pred_err else None,
        "pred_rmse_const_vel_m": float(np.mean(ekf_err)) if ekf_err else None,
        # Với chim: tỉ lệ khung hệ thống hỏi người trực ca = báo động nhầm.
        "operator_ask_rate": float(operator_asks / n_frames),
        "blind_curve": blind_curve,
        "rows": rows,
        "truth": tg.pos.tolist(),
        "pipeline": pipe,
    }


def summarize(name, runs, keys):
    out = {"scenario": name, "n_runs": len(runs)}
    for k in keys:
        v = [r[k] for r in runs if r.get(k) is not None]
        if not v:
            out[k] = None
            continue
        a = np.asarray(v, dtype=float)
        out[k] = round(float(a.mean()), 3)
        out[k + "_ci95"] = (
            [
                round(float(a.mean() - 1.96 * a.std(ddof=1) / np.sqrt(len(a))), 3),
                round(float(a.mean() + 1.96 * a.std(ddof=1) / np.sqrt(len(a))), 3),
            ]
            if len(a) > 1
            else None
        )
    return out


def main(n_runs: int = 8, n_frames: int = 220):
    models = load_models()
    t0 = time.time()
    KEYS = [
        "rmse_m",
        "rmse_final_m",
        "mean_conf",
        "cls_acc_after_warmup",
        "time_to_confirm_s",
        "time_to_correct_id_s",
        "pred_rmse_transformer_m",
        "pred_rmse_const_vel_m",
        "operator_ask_rate",
    ]
    scen = []
    defs = [
        ("S1 · trời quang, drone đa cánh quạt", dict(kind="multirotor", w=Weather())),
        ("S2 · đêm + sương mù dày", dict(kind="multirotor", w=Weather(fog=0.85, night=True))),
        ("S3 · nhiễu dải RF", dict(kind="multirotor", w=Weather(jamming=0.9))),
        ("S4 · mưa to", dict(kind="fixed_wing", w=Weather(rain=0.8))),
        ("S5 · chim (phải loại, không báo động)", dict(kind="bird", w=Weather())),
        (
            "S6 · dán nhãn ngụy trang đánh lừa camera",
            # r0 = 900 m: mục tiêu phải vào tầm nhận dạng của camera (1,2 km),
            # nếu không kịch bản này chẳng thử được gì về chống đánh lừa camera.
            dict(kind="multirotor", w=Weather(), patch=True, r0=900.0),
        ),
        (
            "S7 · mất dấu 4 giây giữa chừng",
            dict(kind="multirotor", w=Weather(), dropout=(110, 150)),
        ),
    ]
    all_lat = []
    for name, kw in defs:
        runs = [
            run_scenario(models, seed=SEED + 100 * i + len(name), n_frames=n_frames, **kw)
            for i in range(n_runs)
        ]
        all_lat += [r["pipeline"] for r in runs]
        s = summarize(name, runs, KEYS)
        if any(r["blind_curve"] for r in runs):
            agg = {}
            for r in runs:
                for d, a, b in r["blind_curve"]:
                    agg.setdefault(d, ([], []))
                    agg[d][0].append(a)
                    agg[d][1].append(b)
            s["blind_curve"] = [
                {
                    "t_s": d,
                    "transformer_m": round(float(np.mean(v[0])), 2),
                    "const_vel_m": round(float(np.mean(v[1])), 2),
                }
                for d, v in sorted(agg.items())
            ]
        scen.append(s)
        print(
            f"{name:46s} rmse={s['rmse_m']:7.2f}m conf={s['mean_conf']:.3f} "
            f"cls={s['cls_acc_after_warmup']:.3f}",
            flush=True,
        )

    # gộp thời gian xử lý của mọi lần chạy
    # Bỏ 3 khung đầu của mỗi lần chạy: đó là lúc nạp trọng số và cấp phát bộ
    # nhớ lần đầu, không đại diện cho trạng thái chạy ổn định.
    merged = {}
    for p in all_lat:
        for k, v in p.timing.items():
            merged.setdefault(k, []).extend(list(v)[3:])
    lat = {}
    for k, v in merged.items():
        a = np.asarray(v)
        lat[k] = {
            "mean_ms": round(float(a.mean()), 3),
            "p95_ms": round(float(np.percentile(a, 95)), 3),
            "p99_ms": round(float(np.percentile(a, 99)), 3),
            "max_ms": round(float(a.max()), 3),
            "n": int(len(a)),
        }

    res = {
        "scenarios": scen,
        "latency_ms": lat,
        "frames": n_frames,
        "runs_per_scenario": n_runs,
        "note": (
            "Đo trên CPU x86 2 nhân trong container, KHÔNG phải trên "
            "Jetson Orin. Đã bỏ 3 khung khởi động đầu mỗi lần chạy. "
            "Xem phần hạn chế của báo cáo."
        ),
    }
    with open(RESULTS_DIR / "scenario_results.json", "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1, ensure_ascii=False)
    print(json.dumps(lat["total"], indent=1))
    print(f"done {time.time() - t0:.0f}s")
    return res


if __name__ == "__main__":
    main()
