"""Kiểm thử cho các lỗi tìm ra trong đợt rà soát 11/2026.

Mỗi bài nhắm đúng một lỗi đã sửa: nạp trọng số thiếu/độc hại, gai thời gian
khi mất dấu, bộ nhớ tăng mãi, I/Q ghép từ hai đoạn khác nhau, nhật ký chỉ
nằm trong RAM, API nhận đầu vào tuỳ ý, và đọc JSON sai bảng mã trên Windows.

Chạy:  python -m pytest tests/ -q
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import torch

ROOT = Path(__file__).resolve().parents[2]

from edge_ai.sim.scene import Weather, make_scenario, rotate_into_view, sense  # noqa: E402
from edge_ai.tracking import pipeline as PL  # noqa: E402

LOCAL = ("127.0.0.1", 50000)


def _log_lines(base) -> list[str]:
    """Mọi dòng nhật ký qua các tệp theo tháng (audit_log.AuditStore)."""
    from edge_ai.api.audit_log import AuditStore

    out = []
    for f in AuditStore(base).files():
        out += f.read_text(encoding="utf-8").splitlines()
    return out


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
    import pickle

    with pytest.raises((pickle.UnpicklingError, RuntimeError)):
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
    return list(tr.hist)[: i0 + 1]


def test_du_doan_mat_dau_noi_dan_cho_ket_qua_giong_het(models):
    """Nối dự đoán dần từng giây phải ra đúng chuỗi như tính trọn 9 giây một lần,
    nhưng khung đầu tiên mất dấu chỉ được gọi Transformer tối đa 2 lần (bản cũ: 9)."""
    expected, got, calls_at_start, _, _ = _blind_run(models)
    assert calls_at_start is not None and calls_at_start <= 2
    assert len(got) >= 40
    np.testing.assert_allclose(got, expected[: len(got)], rtol=0, atol=1e-9)


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
    from edge_ai.experiments import adversarial

    n_calls = []
    real = adversarial.make_segment

    def spy(*a, **kw):
        n_calls.append(1)
        return real(*a, **kw)

    monkeypatch.setattr(adversarial, "make_segment", spy)
    adversarial.run(n_runs=1, n_frames=10)
    assert len(n_calls) == 2  # k = 0 và k = 5, mỗi lần đúng MỘT đoạn


def test_cac_tep_json_doc_duoc_bang_utf8():
    """Mọi JSON trong data/ có tiếng Việt; phải đọc bằng UTF-8 ở mọi nơi."""
    for p in (ROOT / "data" / "results").glob("*.json"):
        json.loads(p.read_text(encoding="utf-8"))
    for p in (ROOT / "backend" / "edge_ai").rglob("*.py"):
        src = p.read_text(encoding="utf-8")
        for line in src.splitlines():
            if "open(" in line and "json" in line:
                assert "encoding" in line, f"{p.name}: {line.strip()}"


# ------------------------------------------------------------------ máy chủ
@pytest.fixture()
def srv(models, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from edge_ai.api import server

    monkeypatch.delenv("EDGE_API_TOKEN", raising=False)
    server.TOKEN_LIMITER.reset()
    eng = server.Engine(models=models, audit_path=tmp_path / "audit.jsonl", start=False)
    monkeypatch.setattr(server, "ENGINE", eng)
    return server, eng, TestClient(server.app, client=LOCAL), tmp_path / "audit.jsonl"


def test_chua_khoi_dong_thi_tra_503(monkeypatch):
    from fastapi.testclient import TestClient

    from edge_ai.api import server

    monkeypatch.setattr(server, "ENGINE", None)
    c = TestClient(server.app, client=LOCAL)
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
    lines = _log_lines(log)
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["operator"] == "ca-dem.2" and rec["action"] == "xac_nhan"
    assert rec["frame"] == eng.msg["k"]  # khung đang hiển thị, không lệch 1
    # quyết định thứ hai cho cùng vết bám bị từ chối, giống giao diện
    assert c.post("/api/act", json={"action": "bo_qua"}).status_code == 409
    assert len(_log_lines(log)) == 1
    # nhật ký vẫn còn sau khi "khởi động lại" (Engine mới, cùng tệp)
    assert json.loads(_log_lines(log)[0])["kind"]


@pytest.mark.parametrize(
    "body",
    [
        {"action": "ban_ha"},
        {"action": "xac_nhan", "operator": "a\nb"},
        {"action": "xac_nhan", "operator": "x" * 33},
        {"action": "xac_nhan", "operator": ""},
    ],
)
def test_dau_vao_sai_bi_tu_choi(srv, body):
    _, eng, c, log = srv
    eng._step()
    assert c.post("/api/act", json=body).status_code == 422
    assert _log_lines(log) == []


def test_ma_truy_cap_khi_duoc_bat(srv, monkeypatch):
    _, eng, c, _ = srv
    eng._step()
    monkeypatch.setenv("EDGE_API_TOKEN", "thu-nghiem-123")
    assert c.post("/api/act", json={"action": "bo_qua"}).status_code == 401
    assert (
        c.post("/api/act", json={"action": "bo_qua"}, headers={"X-API-Token": "sai"}).status_code
        == 401
    )
    assert c.post("/api/scenario/bird").status_code == 401
    assert (
        c.post(
            "/api/act", json={"action": "bo_qua"}, headers={"X-API-Token": "thu-nghiem-123"}
        ).status_code
        == 200
    )
    assert c.get("/api/state").status_code == 200  # xem thì không cần mã


def test_kich_ban_metrics_header_va_health(srv):
    _, eng, c, _ = srv
    assert c.post("/api/scenario/khong-co").status_code == 404
    assert c.post("/api/scenario/bird").json()["scenario"] == "bird"
    assert c.get("/api/health").status_code == 503  # vòng lặp chưa chạy khung nào
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
    from fastapi.testclient import TestClient

    from edge_ai.api import server

    monkeypatch.setenv("EDGE_AUDIT_LOG", str(tmp_path / "a.jsonl"))
    monkeypatch.setattr(server, "load_models", lambda allow_untrained=False: models)
    with TestClient(server.app, client=LOCAL) as c:
        eng = server.ENGINE
        assert eng is not None and eng._thread.is_alive()
        assert c.get("/").status_code == 200
    assert server.ENGINE is None
    assert not eng._thread.is_alive()


# ------------------------------------------------- đợt phát triển thứ hai
def test_nhat_ky_chuoi_bam_phat_hien_sua_va_xoa(tmp_path):
    from edge_ai.api import audit_log

    p = tmp_path / "a.jsonl"
    prev = audit_log.GENESIS
    lines = []
    for i in range(4):
        rec = audit_log.chain(prev, {"frame": i, "action": "xac_nhan", "operator": "ca"})
        prev = rec["hash"]
        lines.append(json.dumps(rec, ensure_ascii=False))
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert audit_log.verify(p) == (True, 4, "")
    assert audit_log.last_hash(p) == prev
    sua = lines.copy()
    sua[1] = sua[1].replace('"xac_nhan"', '"bo_qua"')
    p.write_text("\n".join(sua) + "\n", encoding="utf-8")
    ok, n, err = audit_log.verify(p)
    assert not ok and n == 1 and "sửa" in err
    xoa = lines[:1] + lines[2:]
    p.write_text("\n".join(xoa) + "\n", encoding="utf-8")
    ok, _, err = audit_log.verify(p)
    assert not ok and "đứt chuỗi" in err


def test_may_chu_noi_tiep_chuoi_bam_sau_khi_khoi_dong_lai(srv, models):
    from edge_ai.api import audit_log

    server, eng, c, log = srv
    eng._step()
    assert c.post("/api/act", json={"action": "xac_nhan"}).status_code == 200
    eng2 = server.Engine(models=models, audit_path=log, start=False)  # "khởi động lại"
    eng2._step()
    eng2.act("bo_qua", "ca-2")
    assert audit_log.AuditStore(log).verify() == (True, 2, "")


def test_khong_dat_ma_thi_chi_may_chu_moi_dieu_khien_duoc(srv):
    server, eng, _, _ = srv
    from fastapi.testclient import TestClient

    eng._step()
    xa = TestClient(server.app, client=("10.0.0.7", 40000))
    assert xa.post("/api/act", json={"action": "bo_qua"}).status_code == 403
    assert xa.post("/api/scenario/bird").status_code == 403
    assert xa.get("/api/state").status_code == 200


def test_hai_mang_nang_khong_bao_gio_chung_mot_khung():
    from edge_ai.sim.sensors import md_due, rf_due

    ks = range(3000)
    assert not any(rf_due(k) and md_due(k) for k in ks)
    assert sum(rf_due(k) for k in ks) == 600  # vẫn đúng 2 lần/giây
    assert sum(md_due(k) for k in ks) == 1000


def test_rf_khong_bao_gio_la_bang_chung_cho_chim():
    """Chim không phát sóng: RF chỉ được nói 'drone' hoặc 'không biết'."""
    from edge_ai.config import RF_CLASSES

    for i in range(len(RF_CLASSES)):
        p = np.full(len(RF_CLASSES), 1e-4)
        p[i] = 1.0
        p /= p.sum()
        lp = PL._rf_map(p)
        bird = TARGET_KINDS_IDX["bird"]
        assert lp[bird] <= lp.max() + 1e-12
        assert lp[bird] <= min(lp[0], lp[1]) + 1e-9


def test_camera_60_do_va_be_quay_gioi_han_toc_do():
    from edge_ai.sim.sensors import EOTurret

    rng = np.random.default_rng(0)
    tg = make_scenario(5, rng, Weather(), kinds=["multirotor"], patterns=["approach"], r0=500)[0]
    rotate_into_view(tg, np.deg2rad(40))  # lệch 40° > nửa góc 30°

    def eo_count(eo_az):
        rr = np.random.default_rng(1)
        return sum(
            d.sensor == "eo" for _ in range(30) for d in sense(tg, 0, Weather(), rr, eo_az=eo_az)
        )

    assert eo_count(0.0) == 0
    assert eo_count(np.deg2rad(40)) > 20
    t = EOTurret(0.0)
    t.point(np.pi / 2)
    assert abs(t.az - np.deg2rad(6.0)) < 1e-9  # 60°/s × 0,1 s


TARGET_KINDS_IDX = {"multirotor": 0, "fixed_wing": 1, "bird": 2}


def test_rf_hoa_hai_lop_drone_khong_bi_tinh_la_mau_thuan():
    """RF không phân biệt đa cánh/cánh bằng; camera nói đúng 'cánh bằng' thì
    không được coi là mâu thuẫn (bản cũ: argmax hoà luôn chọn 'đa cánh')."""
    from edge_ai.sim.scene import Detection
    from edge_ai.tracking.fusion import IdentityFuser

    rf_lp = PL._rf_map(np.array([0.01, 0.01, 0.01, 0.97]))
    eo_lp = np.log(np.array([0.05, 0.9, 0.05]))
    f = IdentityFuser()
    for _ in range(60):
        f.update(
            [
                Detection("rf", np.zeros(1), np.eye(1), rf_lp),
                Detection("eo", np.zeros(2), np.eye(2), eo_lp),
            ],
            Weather(),
            500.0,
        )
    assert f.state.conflict == 0.0
    assert f.state.top()[0] == "fixed_wing"


def test_nghi_bi_danh_lua_thi_phai_hoi_nguoi(models):
    """Nhãn ngụy trang không được TẮT cảnh báo: S6 phải đưa lên người trực."""
    from edge_ai.experiments import evaluate as EV

    r = EV.run_scenario(models, "multirotor", Weather(), 160, seed=31, patch=True, r0=900.0)
    late = r["rows"][80:]
    assert any(m["deception_suspected"] for m in late)
    assert np.mean([m["needs_operator"] for m in late]) > 0.5
    assert np.mean([m["kind"] == "multirotor" for m in late]) == 1.0


def test_dashboard_nhieu_muc_tieu_va_quyet_dinh_theo_id(srv):
    server, eng, c, log = srv
    assert c.post("/api/scenario/swarm").status_code == 200
    for _ in range(45):
        eng._step()
    s = c.get("/api/state").json()
    assert s["multi"] is True and s["n_targets_truth"] == 4
    assert len(s["tracks"]) >= 3
    tids = [t["tid"] for t in s["tracks"]]
    assert set(s["trails"]) >= {str(t) for t in tids}
    assert c.post("/api/act", json={"action": "bo_qua", "tid": 999999}).status_code == 404
    r = c.post("/api/act", json={"action": "xac_nhan", "tid": tids[-1]})
    assert r.status_code == 200
    assert c.post("/api/act", json={"action": "bo_qua", "tid": tids[-1]}).status_code == 409
    rec = json.loads(_log_lines(log)[-1])
    assert rec["tid"] == tids[-1]
    eng._step()
    s = c.get("/api/state").json()
    assert {t["tid"]: t["operator"] for t in s["tracks"]}[tids[-1]] == "xac_nhan"


def test_figures_ve_duoc_tu_ket_qua_json(tmp_path, monkeypatch):
    """Smoke test cho script vẽ hình: lỗi đổi tên đường dẫn trong đợt tái cấu
    trúc đã lọt qua vì không test nào chạy tới figures.py."""
    pytest.importorskip("matplotlib")
    from edge_ai.experiments import figures as FG

    monkeypatch.setattr(FG, "FIG", tmp_path)
    for lang in ("vi", "en"):
        monkeypatch.setattr(FG, "L", lang)
        for fn in (FG.fig_accuracy, FG.fig_latency, FG.fig_scenarios, FG.fig_adversarial):
            fn()
    assert len(list(tmp_path.glob("*.png"))) == 8


def test_quy_tac_phu_thuoc_giua_cac_goi():
    """docs/CONVENTIONS.md mục 1: mã chạy trên trạm (api, tracking, sim, ml)
    không được import mã đánh giá/huấn luyện; sim không được biết tracking."""
    import ast

    pkg = ROOT / "backend" / "edge_ai"
    forbidden = {
        "api": ("edge_ai.experiments", "edge_ai.training"),
        "tracking": ("edge_ai.experiments", "edge_ai.training", "edge_ai.api"),
        "sim": ("edge_ai.experiments", "edge_ai.training", "edge_ai.api", "edge_ai.tracking"),
        "ml": ("edge_ai.experiments", "edge_ai.training", "edge_ai.api", "edge_ai.tracking"),
    }
    bad = []
    for sub, banned in forbidden.items():
        for f in (pkg / sub).rglob("*.py"):
            for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
                mods = []
                if isinstance(node, ast.ImportFrom) and node.module:
                    mods = [node.module]
                elif isinstance(node, ast.Import):
                    mods = [a.name for a in node.names]
                bad += [f"{f.name}: {m}" for m in mods if m.startswith(banned)]
    assert not bad, bad


def test_sai_ma_nhieu_lan_thi_bi_khoa_tam(srv, monkeypatch):
    """Bước 7: không dò được mã truy cập dùng chung bằng cách thử liên tục."""
    from fastapi.testclient import TestClient

    server, eng, c, log = srv
    eng._step()
    monkeypatch.setenv("EDGE_API_TOKEN", "ma-dung-123")
    body = {"action": "bo_qua"}
    # Mở trang lần đầu (chưa gửi mã) không tính là sai
    for _ in range(10):
        assert c.post("/api/act", json=body).status_code == 401
    for _ in range(server.TOKEN_LIMITER.max_failures - 1):
        assert c.post("/api/act", json=body, headers={"X-API-Token": "sai"}).status_code == 401
    r = c.post("/api/act", json=body, headers={"X-API-Token": "sai"})
    assert r.status_code == 401  # lần sai thứ 5 vẫn trả 401, rồi khoá
    r = c.post("/api/act", json=body, headers={"X-API-Token": "ma-dung-123"})
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0
    assert "thử lại sau" in r.json()["detail"]
    assert c.post("/api/scenario/bird", headers={"X-API-Token": "ma-dung-123"}).status_code == 429
    assert _log_lines(log) == []  # bị khoá thì không ghi gì
    # Máy khác trong mạng không bị khoá theo
    other = TestClient(server.app, client=("10.0.0.7", 40000))
    r = other.post("/api/act", json=body, headers={"X-API-Token": "ma-dung-123"})
    assert r.status_code == 200
    assert c.get("/api/state").status_code == 200  # vẫn xem được khi bị khoá


def test_bo_chan_do_ma_het_han_va_xoa_khi_dung():
    from edge_ai.api.auth import FailureLimiter

    lim = FailureLimiter(max_failures=3, window_s=10, lock_s=60, max_clients=2)
    assert not lim.failure("a", now=0) and not lim.failure("a", now=1)
    lim.success("a")  # đúng mã thì xoá số lần sai
    assert not lim.failure("a", now=2) and not lim.failure("a", now=3)
    assert lim.failure("a", now=4)  # lần sai thứ 3 liên tiếp: khoá
    assert lim.retry_after("a", now=5) == 59
    assert lim.retry_after("a", now=64.5) == 0  # hết khoá
    # Sai rải rác ngoài cửa sổ 10 s thì không bị khoá
    assert not any(lim.failure("b", now=t) for t in (100, 111, 122, 133))
    # Bị dò từ rất nhiều IP: bộ đếm không phình quá max_clients
    for i in range(50):
        lim.failure(f"ip{i}", now=200 + i)
    assert len(lim._fails) <= 2


def test_trang_dashboard_khong_bi_luu_dem_ban_cu(srv):
    _, _, c, _ = srv
    assert c.get("/").headers["Cache-Control"] == "no-cache"
    assert c.get("/api/health").headers["Cache-Control"] == "no-store"


def test_lenh_tu_trang_web_khac_bi_tu_choi(srv):
    """Bước 7 (CSRF): khi chưa đặt mã, một trang lạ mở trên máy trạm không
    được đổi kịch bản hay ghi quyết định thay người trực."""
    _, eng, c, log = srv
    eng._step()
    evil = {"Origin": "http://trang-la.example"}
    assert c.post("/api/scenario/bird", headers=evil).status_code == 403
    assert c.post("/api/act", json={"action": "bo_qua"}, headers=evil).status_code == 403
    assert _log_lines(log) == []
    same = {"Origin": "http://testserver"}  # chính dashboard
    assert c.post("/api/scenario/bird", headers=same).status_code == 200
