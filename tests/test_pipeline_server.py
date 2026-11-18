"""Kiểm thử cho các lỗi tìm ra trong đợt rà soát 11/2026.

Mỗi bài nhắm đúng một lỗi đã sửa: nạp trọng số thiếu/độc hại, gai thời gian
khi mất dấu, bộ nhớ tăng mãi, I/Q ghép từ hai đoạn khác nhau, nhật ký chỉ
nằm trong RAM, API nhận đầu vào tuỳ ý, và đọc JSON sai bảng mã trên Windows.

Chạy:  python -m pytest tests/ -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest
import torch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pipeline as PL                                 # noqa: E402
from scene import Weather, make_scenario, rotate_into_view, sense  # noqa: E402


@pytest.fixture(scope="module")
def models():
    return PL.load_models()


# ------------------------------------------------------------ nạp mô hình
def test_thieu_trong_so_thi_dung_lai_chu_khong_chay_ngau_nhien(tmp_path):
    """Bản cũ thiếu tệp .pt vẫn chạy tiếp với trọng số ngẫu nhiên, im lặng."""
    with pytest.raises(FileNotFoundError):
        PL.load_models(data_dir=tmp_path)
    rf, md, tj = PL.load_models(allow_untrained=True, data_dir=tmp_path)
    assert rf.trained is False and md.trained is False and tj.trained is False


class _Evil:
    def __reduce__(self):
        return (Path.write_text, (_Evil.target, "pwned"))


def test_tep_trong_so_khong_duoc_chay_ma_pickle(tmp_path):
    """torch.load phải dùng weights_only=True: tệp .pt là dữ liệu, không phải mã."""
    _Evil.target = tmp_path / "side_effect.txt"
    for f in PL.MODEL_FILES:
        torch.save({"x": _Evil()}, tmp_path / f)
    with pytest.raises(Exception):
        PL.load_models(data_dir=tmp_path)
    assert not _Evil.target.exists()


def test_trong_so_that_nap_duoc(models):
    assert all(m.trained for m in models)


# ---------------------------------------------------------- mất dấu / bộ nhớ
def _blind_run(models, n=150, drop=(80, 125), seed=3):
    rng = np.random.default_rng(seed)
    w = Weather()
    tg = make_scenario(n, rng, w, kinds=["multirotor"], patterns=["approach"], r0=900)[0]
    pipe = PL.Pipeline(models)
    tr = pipe.ensure_track(0, tg.pos[0], tg.vel[0])
    calls = []
    orig = pipe.predict_future

    def counted(h):
        calls.append(len(calls))
        return orig(h)

    pipe.predict_future = counted
    expected, calls_at_start = None, None
    for k in range(n):
        blind = drop[0] <= k < drop[1]
        before = len(calls)
        pipe.step(0, [] if blind else sense(tg, k, w, rng), w, k)
        if blind and expected is None and tr.blackout_from is not None:
            calls_at_start = len(calls) - before
            pipe.predict_future = orig
            expected = pipe.rollout(_hist_at(tr, k), PL.BLACKOUT_STEPS)
            pipe.predict_future = counted
        if k == drop[1] - 1:
            got = tr.blackout_pred.copy()
    return expected, got, calls_at_start, pipe, tr


def _hist_at(tr, k):
    i0 = len(tr.hist) - 1 - (k - tr.last_seen)
    return list(tr.hist)[:i0 + 1]


def test_du_doan_mat_dau_noi_dan_cho_ket_qua_giong_het(models):
    """Nối dự đoán dần từng giây phải ra đúng chuỗi như tính trọn 9 giây một lần,
    nhưng khung đầu tiên mất dấu chỉ được gọi Transformer tối đa 2 lần (bản cũ: 9)."""
    expected, got, calls_at_start, _, _ = _blind_run(models)
    assert calls_at_start is not None and calls_at_start <= 2
    assert len(got) >= 40
    np.testing.assert_allclose(got, expected[:len(got)], rtol=0, atol=1e-9)


def test_lich_su_va_so_do_thoi_gian_co_gioi_han(models):
    """Vết bám chạy lâu không được ăn dần bộ nhớ thiết bị biên."""
    rng = np.random.default_rng(4)
    w = Weather()
    n = PL.HIST_KEEP + 120
    tg = make_scenario(n, rng, w, kinds=["fixed_wing"], patterns=["orbit"])[0]
    pipe = PL.Pipeline(models)
    tr = pipe.ensure_track(0, tg.pos[0], tg.vel[0])
    for k in range(n):
        pipe.step(0, sense(tg, k, w, rng), w, k)
    assert len(tr.hist) == PL.HIST_KEEP
    assert all(v.maxlen == PL.TIMING_KEEP for v in pipe.timing.values())


# --------------------------------------------------------------- cảnh dựng
def test_xoay_vao_tam_camera_giu_nguyen_toc_do():
    rng = np.random.default_rng(5)
    tg = make_scenario(120, rng, Weather(), kinds=["multirotor"], patterns=["approach"])[0]
    sp0 = np.linalg.norm(tg.vel, axis=1).copy()
    r0 = np.linalg.norm(tg.pos[:, :2], axis=1).copy()
    rotate_into_view(tg, np.deg2rad(10))
    assert abs(np.arctan2(tg.pos[0, 1], tg.pos[0, 0]) - np.deg2rad(10)) < 1e-9
    np.testing.assert_allclose(np.linalg.norm(tg.vel, axis=1), sp0, atol=1e-9)
    np.testing.assert_allclose(np.linalg.norm(tg.pos[:, :2], axis=1), r0, atol=1e-9)


def test_thu_nghiem_danh_lua_lay_i_va_q_tu_cung_mot_doan(monkeypatch):
    """Bản cũ ghép phần thực của đoạn này với phần ảo của đoạn khác."""
    import adversarial
    n_calls = []
    real = adversarial.make_segment

    def spy(*a, **kw):
        n_calls.append(1)
        return real(*a, **kw)

    monkeypatch.setattr(adversarial, "make_segment", spy)
    adversarial.run(n_runs=1, n_frames=10)
    assert len(n_calls) == 2          # k = 0 và k = 5, mỗi lần đúng MỘT đoạn


def test_cac_tep_json_doc_duoc_bang_utf8():
    """Mọi JSON trong data/ có tiếng Việt; phải đọc bằng UTF-8 ở mọi nơi."""
    for p in (ROOT / "data").glob("*.json"):
        json.loads(p.read_text(encoding="utf-8"))
    for p in (ROOT / "src").glob("*.py"):
        src = p.read_text(encoding="utf-8")
        for line in src.splitlines():
            if "open(" in line and "json" in line:
                assert "encoding" in line, f"{p.name}: {line.strip()}"


# ------------------------------------------------------------------ máy chủ
@pytest.fixture()
def srv(models, tmp_path, monkeypatch):
    import server
    from fastapi.testclient import TestClient
    monkeypatch.delenv("EDGE_API_TOKEN", raising=False)
    eng = server.Engine(models=models, audit_path=tmp_path / "audit.jsonl", start=False)
    monkeypatch.setattr(server, "ENGINE", eng)
    return server, eng, TestClient(server.app), tmp_path / "audit.jsonl"


def test_chua_khoi_dong_thi_tra_503(monkeypatch):
    import server
    from fastapi.testclient import TestClient
    monkeypatch.setattr(server, "ENGINE", None)
    c = TestClient(server.app)
    assert c.get("/api/state").status_code == 503
    assert c.post("/api/act", json={"action": "bo_qua"}).status_code == 503
    assert c.get("/api/health").status_code == 503


def test_quyet_dinh_duoc_ghi_xuong_dia_va_chi_mot_lan(srv):
    server, eng, c, log = srv
    assert c.post("/api/act", json={"action": "xac_nhan"}).status_code == 409  # chưa có khung
    for _ in range(3):
        eng._step()
    r = c.post("/api/act", json={"action": "xac_nhan", "operator": "ca-dem.2"})
    assert r.status_code == 200 and r.json()["persisted"] is True
    lines = log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["operator"] == "ca-dem.2" and rec["action"] == "xac_nhan"
    assert rec["frame"] == eng.msg["k"]           # khung đang hiển thị, không lệch 1
    # quyết định thứ hai cho cùng vết bám bị từ chối, giống giao diện
    assert c.post("/api/act", json={"action": "bo_qua"}).status_code == 409
    assert len(log.read_text(encoding="utf-8").splitlines()) == 1
    # nhật ký vẫn còn sau khi "khởi động lại" (Engine mới, cùng tệp)
    assert json.loads(log.read_text(encoding="utf-8").splitlines()[0])["kind"]


@pytest.mark.parametrize("body", [
    {"action": "ban_ha"},
    {"action": "xac_nhan", "operator": "a\nb"},
    {"action": "xac_nhan", "operator": "x" * 33},
    {"action": "xac_nhan", "operator": ""},
])
def test_dau_vao_sai_bi_tu_choi(srv, body):
    _, eng, c, log = srv
    eng._step()
    assert c.post("/api/act", json=body).status_code == 422
    assert not log.exists() or log.read_text(encoding="utf-8") == ""


def test_ma_truy_cap_khi_duoc_bat(srv, monkeypatch):
    _, eng, c, _ = srv
    eng._step()
    monkeypatch.setenv("EDGE_API_TOKEN", "thu-nghiem-123")
    assert c.post("/api/act", json={"action": "bo_qua"}).status_code == 401
    assert c.post("/api/act", json={"action": "bo_qua"},
                  headers={"X-API-Token": "sai"}).status_code == 401
    assert c.post("/api/scenario/bird").status_code == 401
    assert c.post("/api/act", json={"action": "bo_qua"},
                  headers={"X-API-Token": "thu-nghiem-123"}).status_code == 200
    assert c.get("/api/state").status_code == 200       # xem thì không cần mã


def test_kich_ban_metrics_header_va_health(srv):
    _, eng, c, _ = srv
    assert c.post("/api/scenario/khong-co").status_code == 404
    assert c.post("/api/scenario/bird").json()["scenario"] == "bird"
    assert c.get("/api/health").status_code == 503       # vòng lặp chưa chạy khung nào
    eng._step()
    h = c.get("/api/health")
    assert h.status_code == 200 and h.json()["models_trained"] is True
    m = c.get("/api/metrics")
    assert m.status_code == 200 and "adversarial" in m.json()
    assert "scenarios" not in m.json()["scenario_results"]
    r = c.get("/api/state")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.json()["scenario"] == "bird"


def test_lifespan_khoi_dong_va_dung_vong_lap(models, tmp_path, monkeypatch):
    import server
    from fastapi.testclient import TestClient
    monkeypatch.setenv("EDGE_AUDIT_LOG", str(tmp_path / "a.jsonl"))
    monkeypatch.setattr(server, "load_models", lambda allow_untrained=False: models)
    with TestClient(server.app) as c:
        eng = server.ENGINE
        assert eng is not None and eng._thread.is_alive()
        assert c.get("/").status_code == 200
    assert server.ENGINE is None
    assert not eng._thread.is_alive()
