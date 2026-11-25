"""Kiểm thử bám nhiều mục tiêu (mtt.py) và các thành phần nó dựa vào."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]

from edge_ai.experiments import evaluate_mtt as EM  # noqa: E402
from edge_ai.sim.scene import Detection, Weather  # noqa: E402
from edge_ai.sim.sensors import RawProvider, false_alarms, sense_all  # noqa: E402
from edge_ai.tracking import pipeline as PL  # noqa: E402
from edge_ai.tracking.ekf import EKF  # noqa: E402
from edge_ai.tracking.mtt import CHI2_GATE, MultiTracker, _coarse_gate  # noqa: E402
from edge_ai.tracking.pipeline import Track  # noqa: E402


@pytest.fixture(scope="module")
def models():
    return PL.load_models()


def test_jacobian_giai_tich_khop_sai_phan_so():
    rng = np.random.default_rng(0)
    for _ in range(300):
        x = np.concatenate(
            [rng.uniform(-3000, 3000, 2), rng.uniform(5, 600, 1), rng.uniform(-40, 40, 3)]
        )
        for s in ("radar", "eo", "rf", "lidar"):
            np.testing.assert_allclose(EKF.H(s, x), EKF.H_numeric(s, x), rtol=1e-5, atol=1e-7)


def test_loc_tho_khong_bo_cap_nao_qua_cong_chi2():
    """Bộ lọc thô chỉ được bỏ những cặp đằng nào cũng trượt cổng χ²."""
    rng = np.random.default_rng(1)
    w = Weather()
    trs = []
    for i in range(12):
        p = np.array([rng.uniform(-2500, 2500), rng.uniform(-2500, 2500), rng.uniform(30, 300)])
        e = EKF(p, rng.normal(0, 10, 3), p_var=rng.uniform(4, 3000), v_var=rng.uniform(4, 400))
        trs.append(Track(i, e))
    dets = false_alarms(rng, 40, w)
    for t in trs[:6]:  # thêm số đo sát vài vết
        r = float(np.linalg.norm(t.ekf.pos))
        az = float(np.arctan2(t.ekf.pos[1], t.ekf.pos[0]))
        el = float(np.arcsin(t.ekf.pos[2] / r))
        dets.append(
            Detection("radar", np.array([r + 5, az, el, 0.0]), np.diag([9, 1e-4, 2e-4, 0.06]))
        )
        dets.append(Detection("rf", np.array([az + 0.01]), np.array([[0.003]])))
    for sensor in ("radar", "rf"):
        D = [d for d in dets if d.sensor == sensor]
        near = _coarse_gate(sensor, trs, D)
        for i, t in enumerate(trs):
            for j, d in enumerate(D):
                if t.ekf.mahalanobis(sensor, d.z, d.R) < CHI2_GATE[sensor]:
                    assert near[i, j], (sensor, i, j)


def test_batch_cho_cung_ket_qua_nhu_tung_cai(models):
    rf, md, _ = models
    rng = np.random.default_rng(2)
    from edge_ai.sim.sensors import md_spec, rf_iq

    specs = [md_spec(k, 800.0, rng, 0.0) for k in ("multirotor", "bird", "clutter")]
    iqs = [rf_iq(e, rng) for e in (True, False, True)]
    for s, lp in zip(specs, PL.md_logp_batch(md, specs)):
        np.testing.assert_allclose(lp, PL.md_logp(md, s), atol=1e-5)
    for x, lp in zip(iqs, PL.rf_logp_batch(rf, iqs)):
        np.testing.assert_allclose(lp, PL.rf_logp(rf, x), atol=1e-5)


def _run(models, spec, n, seed, clutter=1.0, w=None):
    w = w or Weather()
    rng = np.random.default_rng(seed)
    tgs = EM.build_targets(spec, n, rng)
    prov = RawProvider(tgs, w, rng)
    mt = MultiTracker(models, raw_provider=prov)
    hist = []
    for k in range(n):
        dets = sense_all(tgs, k, w, rng, eo_az=mt.turret.az, clutter_rate=clutter, raw=False)
        hist.append((mt.step(dets, w, k), [t.pos[k] for t in tgs]))
        mt.point_camera(k)
    return mt, hist, prov


def test_bam_dung_so_muc_tieu_trong_bao_dong_gia(models):
    spec = EM.fan_targets(["multirotor", "fixed_wing", "bird"])
    mt, hist, _ = _run(models, spec, 90, seed=11, clutter=2.0)
    for msgs, truth in hist[30:]:
        assert len(msgs) == 3
        for p in truth:
            assert min(np.linalg.norm(np.array(m["pos"]) - p) for m in msgs) < 30.0
    kinds = sorted(m["kind"] for m in hist[-1][0])
    assert kinds == sorted(["multirotor", "fixed_wing", "bird"])
    assert all(not m["needs_operator"] for m in hist[-1][0] if m["kind"] == "bird")


def test_chi_bao_dong_gia_thi_khong_xac_nhan_vet_nao(models):
    w = Weather()
    rng = np.random.default_rng(12)
    mt = MultiTracker(models)
    confirmed = 0
    for k in range(120):
        confirmed += len(mt.step(false_alarms(rng, 3.0, w), w, k))
    assert confirmed == 0
    assert mt.stats["spawned"] > 200 and mt.stats["confirmed"] == 0


def test_hai_drone_sat_nhau_giu_dung_hai_vet_khong_doi_id(models):
    spec = [dict(kind="multirotor", r0=900, az=0.0), dict(kind="multirotor", r0=930, az=2.0)]
    mt, hist, _ = _run(models, spec, 100, seed=13)
    owner = []
    for msgs, truth in hist[30:]:
        assert len(msgs) == 2
        ids = []
        for p in truth:
            d = [np.linalg.norm(np.array(m["pos"]) - p) for m in msgs]
            ids.append(msgs[int(np.argmin(d))]["tid"])
        assert ids[0] != ids[1]
        owner.append(tuple(ids))
    assert len(set(owner)) == 1  # không đổi ID


def test_chi_vet_da_xac_nhan_moi_lay_du_lieu_tho(models):
    """Báo động giả (vết tạm) không được tiêu tốn mạng nặng."""
    spec = EM.fan_targets(["multirotor"])
    mt, hist, prov = _run(models, spec, 60, seed=14, clutter=3.0)
    # 1 mục tiêu: radar mỗi 3 khung, RF mỗi 5 khung, trừ vài khung đầu chưa xác nhận
    assert prov.calls["spec"] <= 60 // 3 + 1
    assert prov.calls["iq"] <= 60 // 5 + 1
    assert prov.calls["spec"] >= 15


def test_ospa():
    X = np.array([[0.0, 0, 0], [100, 0, 0]])
    assert EM.ospa(X, X) == 0.0
    assert EM.ospa(X, X[:1]) == pytest.approx(EM.OSPA_C / 2)
    assert EM.ospa(X, np.zeros((0, 3))) == EM.OSPA_C


def test_du_doan_ekf_theo_lo_trung_tung_cai():
    import copy

    from edge_ai.tracking.ekf import predict_many

    rng = np.random.default_rng(3)
    a = [
        EKF(
            rng.normal(0, 800, 3),
            rng.normal(0, 15, 3),
            sigma_a=rng.uniform(2, 9),
            p_var=rng.uniform(1, 900),
        )
        for _ in range(9)
    ]
    b = copy.deepcopy(a)
    for f in a:
        f.predict(0.1)
    predict_many(b, 0.1)
    for x, y in zip(a, b):
        np.testing.assert_allclose(x.x, y.x, rtol=0, atol=1e-12)
        np.testing.assert_allclose(x.P, y.P, rtol=0, atol=1e-9)


def test_tran_mang_nang_moi_khung_voi_10_muc_tieu(models):
    """10 mục tiêu: mỗi khung không quá trần, nhưng vết nào cũng vẫn được phân loại."""
    from edge_ai.tracking import mtt as MT

    spec = EM.fan_targets(["multirotor"] * 10, spread=90.0)
    rng = np.random.default_rng(15)
    w = Weather()
    tgs = EM.build_targets(spec, 80, rng)
    per_frame = []

    class Counting(RawProvider):
        def __call__(self, d, what):
            per_frame[-1][what] += 1
            return super().__call__(d, what)

    mt = MultiTracker(models, raw_provider=Counting(tgs, w, rng))
    for k in range(80):
        per_frame.append({"spec": 0, "iq": 0})
        mt.step(sense_all(tgs, k, w, rng, eo_az=mt.turret.az, clutter_rate=1.0, raw=False), w, k)
        mt.point_camera(k)
    assert max(f["spec"] for f in per_frame) <= MT.MAX_SPEC_PER_FRAME
    assert max(f["iq"] for f in per_frame) <= MT.MAX_IQ_PER_FRAME
    conf = [t for t in mt.tracks.values() if t.confirmed]
    assert len(conf) == 10
    assert all(t.last_md >= 0 for t in conf)  # vết nào cũng đã được phân loại


def test_bo_bam_tat_dinh_nen_phat_lai_do_duoc_do_tre(models):
    """Phép đo độ trễ bằng phát lại + lấy min (evaluate_mtt.replay_latency) chỉ
    đúng khi mọi lần phát lại làm CÙNG một khối lượng việc."""
    import copy

    rng = np.random.default_rng(16)
    w = Weather()
    tgs = EM.build_targets(EM.fan_targets(["multirotor", "bird"]), 40, rng)
    frames = [sense_all(tgs, k, w, rng, clutter_rate=1.0, raw=False) for k in range(40)]
    outs = []
    for _ in range(2):
        mt = MultiTracker(models)
        outs.append(
            [
                [(m["tid"], m["pos"]) for m in mt.step(copy.deepcopy(d), w, k)]
                for k, d in enumerate(frames)
            ]
        )
    assert outs[0] == outs[1]


def test_vet_non_bi_xoa_nhanh_vet_chin_duoc_cho_lau():
    import edge_ai.tracking.mtt as MT

    tr = Track(1, EKF(np.zeros(3), np.zeros(3)))
    tr.pos_hits = 3
    assert MultiTracker._coast_limit(tr) == MT.YOUNG_COAST
    tr.pos_hits = MT.MATURE_HITS
    assert MultiTracker._coast_limit(tr) == MT.DELETE_AFTER


def test_cuu_vet_gianh_lai_so_do_tu_vet_tam(models):
    """Hồi quy: M1, seed SEED+5003 — vết đã xác nhận trượt cổng 2 khung, vết
    tạm sinh từ chính số đo đó được xác nhận thành bản trùng (2 lần đổi ID)."""
    from edge_ai.config import SEED

    name, spec, w, cl = EM.SCENARIOS[0]
    r = EM.run(models, spec, w, 200, SEED + 5003, cl)
    assert r["id_switches"] == 0
    assert r["false_tracks_per_frame"] == 0.0


# ------------------------------------------------------- cổng χ² của EKF (E2-A)
@pytest.mark.parametrize("d, want", [(1, 15.137), (2, 18.421), (3, 21.108), (4, 23.513)])
def test_cong_ekf_la_phan_vi_chi2_9999_theo_so_chieu(d, want):
    from edge_ai.tracking.ekf import GATE_CONFIDENCE, chi2_gate

    assert GATE_CONFIDENCE == 0.9999
    assert chi2_gate(d) == pytest.approx(want, abs=2e-3)


def test_cong_ekf_dung_nguong_chi2_khong_phai_gate_nhan_len_z():
    """Số đo LiDAR có d² nằm giữa ngưỡng χ²(3) 99,99% (21,11) và ngưỡng cũ
    16·3 = 48 phải bị loại; nới bằng ``gate`` tuyệt đối thì được nhận."""
    from edge_ai.tracking.ekf import chi2_gate

    def make():
        f = EKF(np.array([200.0, 0.0, 50.0]), np.zeros(3), p_var=1.0, v_var=1.0)
        return f

    R = np.eye(3)
    S = make().P[:3, :3] + R  # H = [I 0] cho LiDAR, chưa predict
    d2_target = 30.0  # 21,11 < 30 < 48
    dz = np.array([np.sqrt(d2_target * S[0, 0]), 0.0, 0.0])
    z = make().pos + dz
    f = make()
    assert f.mahalanobis("lidar", z, R) == pytest.approx(d2_target, rel=1e-6)
    assert chi2_gate(3) < d2_target < 16.0 * 3
    assert f.update("lidar", z, R) is False
    assert make().update("lidar", z, R, gate=d2_target + 1.0) is True


def test_so_do_cuu_vet_giu_nguong_tuyet_doi_cu():
    """mtt._rescue đặt meta['gate'] = 4·CHI2_GATE + d: đúng ngưỡng của bản
    trước ((4·c/d + 1)·d), vì giờ ``gate`` là ngưỡng tuyệt đối cho d²."""
    for s, d in (("radar", 4), ("lidar", 3), ("eo", 2), ("rf", 1)):
        old = (4.0 * CHI2_GATE[s] / d + 1.0) * d
        assert 4.0 * CHI2_GATE[s] + d == pytest.approx(old)
