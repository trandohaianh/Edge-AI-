"""Temperature scaling (ml/calibration.py) và cách pipeline dùng T."""

from __future__ import annotations

import json

import numpy as np
import pytest
import torch

from edge_ai.ml import calibration as CAL
from edge_ai.tracking import pipeline as PL


def _overconfident(n: int, seed: int):
    """Logit của một bộ phân loại 'tự tin quá mức': logit đúng được nhân lên
    nhiều lần, nên xác suất lớn nhất cao hơn hẳn tỉ lệ đúng thật."""
    rng = np.random.default_rng(seed)
    k = 4
    y = rng.integers(0, k, n)
    z = rng.normal(0, 1, (n, k))
    z[np.arange(n), y] += 1.2  # tín hiệu vừa phải: đúng khoảng 70%
    return z * 4.0, y  # ×4: quá tự tin


def test_hoc_T_duong_va_giam_ece_tren_tap_kiem():
    zv, yv = _overconfident(3000, 0)  # tập kiểm định: học T
    zt, yt = _overconfident(3000, 1)  # tập test: chỉ đo
    T = CAL.fit_temperature(zv, yv)
    assert T > 0
    assert T > 1.5  # mô hình quá tự tin thì T phải > 1 (làm mềm)
    r = CAL.report(zt, yt, T)
    assert r["ece_after"] <= r["ece_before"]
    assert r["nll_after"] <= r["nll_before"]
    assert r["acc_after"] == r["acc_before"]


def test_T_khong_doi_thu_hang():
    zt, _ = _overconfident(500, 2)
    for T in (0.3, 1.0, 2.7, 15.0):
        np.testing.assert_array_equal(CAL.softmax_t(zt, T).argmax(1), zt.argmax(1))


def test_mo_hinh_da_hieu_chinh_thi_T_gan_1():
    """Sinh nhãn đúng theo softmax(z): mô hình đã hiệu chỉnh sẵn, T ≈ 1."""
    rng = np.random.default_rng(3)
    z = rng.normal(0, 2, (20000, 4))
    p = CAL.softmax_t(z)
    y = np.array([rng.choice(4, p=row) for row in p])
    assert abs(CAL.fit_temperature(z, y) - 1.0) < 0.08


def test_ece_bang_0_khi_tin_cay_dung_bang_ti_le_dung():
    probs = np.tile([0.75, 0.25], (400, 1))
    y = np.array([0] * 300 + [1] * 100)  # đúng 75%, tin cậy 0.75
    assert CAL.ece(probs, y) == pytest.approx(0.0, abs=1e-12)


def test_thieu_hoac_hong_calibration_json_thi_T_bang_1(tmp_path):
    assert CAL.load_temperatures(tmp_path) == {}
    (tmp_path / CAL.CALIBRATION_FILE).write_text("{hỏng", encoding="utf-8")
    assert CAL.load_temperatures(tmp_path) == {}
    (tmp_path / CAL.CALIBRATION_FILE).write_text(
        json.dumps({"rf": {"T": -2}, "md": {"T": "x"}, "tj": {"T": 1.5}}), encoding="utf-8"
    )
    assert CAL.load_temperatures(tmp_path) == {"tj": 1.5}
    rf, md, _ = PL.load_models(allow_untrained=True, data_dir=tmp_path)
    assert rf.temperature == 1.0 and md.temperature == 1.0


def test_pipeline_ap_T_vao_logit(tmp_path):
    CAL.save_temperatures(tmp_path, {"rf": {"T": 2.0}, "md": {"T": 0.5}})
    rf, md, _ = PL.load_models(allow_untrained=True, data_dir=tmp_path)
    assert rf.temperature == 2.0 and md.temperature == 0.5
    torch.manual_seed(0)
    spec = np.random.default_rng(0).normal(0, 1, (64, 128)).astype(np.float32)
    with torch.no_grad():
        logits = md(torch.from_numpy(spec[None, None]))
    want = PL._md_map(torch.softmax(logits / 0.5, 1).numpy()[0])
    np.testing.assert_allclose(PL.md_logp(md, spec), want, atol=1e-6)


def test_T_da_luu_cho_mo_hinh_that_hop_le():
    """calibration.json đi kèm trọng số đã commit: T dương, hữu hạn."""
    temps = CAL.load_temperatures(PL.MODELS_DIR)
    assert set(temps) == {"rf", "md"}
    assert all(0 < t < 20 for t in temps.values())


def test_so_do_da_ghi_ece_sau_khong_te_hon_va_do_chinh_xac_khong_doi():
    """data/results/calibration.json (experiments/calibrate.py, tập test mô phỏng)."""
    from edge_ai.config import RESULTS_DIR
    from edge_ai.io_utils import read_json

    res = read_json(RESULTS_DIR / "calibration.json")
    for k in ("rf", "md"):
        r = res[k]
        assert r["T"] > 0
        assert r["ece_after"] <= r["ece_before"]
        assert r["acc_after"] == r["acc_before"]
        assert r["T"] == pytest.approx(CAL.load_temperatures(PL.MODELS_DIR)[k], rel=1e-4)
