"""Kiểm thử cho ba nhóm lỗi rõ ràng sửa trong đợt rà soát 23/11/2026.

1. Số đo NaN/Inf làm EKF (và nhận dạng) thành NaN vĩnh viễn.
2. Vết bám bị khoá dù quyết định chưa ghi được xuống đĩa.
3. Nhật ký kiểm toán: dòng ghi dở, tệp mốc dọn hỏng, đồng hồ chạy lùi.
"""

from __future__ import annotations

import calendar
import json
import logging

import numpy as np
import pytest

from edge_ai.api import audit_log
from edge_ai.sim.scene import Detection, Weather
from edge_ai.tracking import pipeline as PL
from edge_ai.tracking.ekf import EKF
from edge_ai.tracking.fusion import IdentityFuser
from edge_ai.tracking.mtt import MultiTracker

LOCAL = ("127.0.0.1", 50000)
NOV = float(calendar.timegm((2026, 11, 20, 12, 0, 0)))
DEC = float(calendar.timegm((2026, 12, 2, 12, 0, 0)))


@pytest.fixture(scope="module")
def models():
    return PL.load_models()


# ------------------------------------------------------------ 1. NaN / Inf
@pytest.mark.parametrize(
    "z, R",
    [
        (np.array([np.nan, 0.0, 100.0]), np.eye(3)),
        (np.array([np.inf, 0.0, 100.0]), np.eye(3)),
        (np.array([500.0, 0.0, 100.0]), np.eye(3) * np.nan),
        (np.array([500.0, 0.0, 100.0]), np.diag([1.0, np.inf, 1.0])),
    ],
)
def test_ekf_tu_choi_so_do_khong_huu_han(z, R):
    f = EKF(np.array([500.0, 0.0, 100.0]), np.zeros(3))
    x0, P0 = f.x.copy(), f.P.copy()
    assert f.update("lidar", z, R) is False
    np.testing.assert_array_equal(f.x, x0)
    np.testing.assert_array_equal(f.P, P0)
    # số đo tốt sau đó vẫn dùng được: bộ lọc không bị "nhiễm" NaN
    assert f.update("lidar", np.array([501.0, 1.0, 99.0]), np.eye(3))
    assert np.all(np.isfinite(f.x)) and np.all(np.isfinite(f.P))


def test_hop_nhat_nhan_dang_bo_qua_cls_logp_nan():
    f = IdentityFuser()
    good = np.log(np.array([0.7, 0.2, 0.1]))
    f.update([Detection("radar", np.zeros(4), np.eye(4), good)], Weather(), 300.0)
    bad = np.array([np.nan, 0.0, -1.0])
    s = f.update([Detection("radar", np.zeros(4), np.eye(4), bad)], Weather(), 300.0)
    assert np.all(np.isfinite(s.logp)) and np.all(np.isfinite(s.probs()))


def test_pipeline_loai_va_dem_so_do_nan(models):
    pipe = PL.Pipeline(models)
    pipe.ensure_track(0, np.array([800.0, 100.0, 120.0]), np.zeros(3))
    dets = [
        Detection("lidar", np.array([np.nan, 100.0, 120.0]), np.eye(3)),
        Detection("radar", np.array([815.0, 0.124, 0.148, 0.0]), np.diag([25, 1e-4, 1e-4, 1])),
        Detection("eo", np.array([0.124, 0.148]), np.eye(2) * 1e-4, np.array([np.nan, 0, 0])),
    ]
    m = pipe.step(0, dets, Weather(), 0)
    tr = pipe.tracks[0]
    assert np.all(np.isfinite(tr.ekf.x)) and np.all(np.isfinite(tr.ekf.P))
    assert np.all(np.isfinite(m["probs"])) and np.isfinite(m["confidence"])
    assert pipe.dropped["measurement"] == 1 and pipe.dropped["class_logp"] == 1
    assert "radar" in m["sensors"]  # số đo tốt vẫn được dùng


def test_mtt_khong_sinh_vet_tu_so_do_nan(models):
    mt = MultiTracker(models)
    for k in range(6):
        mt.step(
            [
                Detection("radar", np.array([np.nan, 0.1, 0.1, 0.0]), np.diag([25, 1e-4, 1e-4, 1])),
                Detection("lidar", np.array([300.0, np.inf, 50.0]), np.eye(3)),
            ],
            Weather(),
            k,
        )
    assert mt.tracks == {} and mt.stats["spawned"] == 0
    assert mt.pipe.dropped["measurement"] == 12


# ------------------------------------------------------------------ server
@pytest.fixture()
def srv(models, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from edge_ai.api import server

    monkeypatch.delenv("EDGE_API_TOKEN", raising=False)
    server.TOKEN_LIMITER.reset()
    eng = server.Engine(models=models, audit_path=tmp_path / "audit.jsonl", start=False)
    monkeypatch.setattr(server, "ENGINE", eng)
    return server, eng, TestClient(server.app, client=LOCAL), tmp_path / "audit.jsonl"


def test_state_hien_so_do_bi_loai(srv):
    _, eng, c, _ = srv
    eng._step()
    eng.pipe.dropped["measurement"] += 3
    assert c.get("/api/state").json()["dropped_nonfinite"]["measurement"] == 3


def test_ghi_nhat_ky_hong_thi_khong_khoa_vet_va_tra_503(srv, monkeypatch):
    _, eng, c, log = srv
    eng._step()
    tid = eng.msg["tid"]
    real = eng.audit_store.append

    def broken(*a, **kw):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(eng.audit_store, "append", broken)
    r = c.post("/api/act", json={"action": "xac_nhan"})
    assert r.status_code == 503 and "CHƯA bị khoá" in r.json()["detail"]
    assert eng.tracks[tid].operator is None  # vết chưa bị khoá
    assert len(eng.audit) == 0
    # đĩa trở lại bình thường: người trực bấm lại là ghi được
    monkeypatch.setattr(eng.audit_store, "append", real)
    r = c.post("/api/act", json={"action": "xac_nhan"})
    assert r.status_code == 200 and r.json()["persisted"] is True
    assert eng.tracks[tid].operator == "xac_nhan"
    assert audit_log.AuditStore(log).verify() == (True, 1, "")


def test_pruned_hong_thi_dich_vu_van_chay_nhung_tu_choi_ghi(models, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from edge_ai.api import server

    base = tmp_path / "audit.jsonl"
    audit_log.AuditStore(base).pruned_path.write_text("{hỏng", encoding="utf-8")
    with pytest.raises(audit_log.AuditLogError, match="mốc dọn"):
        audit_log.AuditStore(base).pruned()
    monkeypatch.delenv("EDGE_API_TOKEN", raising=False)
    server.TOKEN_LIMITER.reset()
    eng = server.Engine(models=models, audit_path=base, start=False)  # không ném lỗi
    monkeypatch.setattr(server, "ENGINE", eng)
    c = TestClient(server.app, client=LOCAL)
    eng._step()
    assert c.get("/api/health").json()["audit_ok"] is False
    r = c.post("/api/act", json={"action": "bo_qua"})
    assert r.status_code == 503
    assert eng.tracks[eng.msg["tid"]].operator is None


def test_pruned_sai_cau_truc_bi_bao_ro(tmp_path):
    st = audit_log.AuditStore(tmp_path / "audit.jsonl")
    st.pruned_path.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(audit_log.AuditLogError, match="sai cấu trúc"):
        st.verify()


# ------------------------------------------------------------- nhật ký
def _append_n(st, n, ts, prev=None):
    prev = st.last_hash() if prev is None else prev
    for i in range(n):
        rec = {"frame": i, "action": "bo_qua", "operator": "ca", "ts": ts}
        prev = st.append(prev, rec, ts=ts)["hash"]
    return prev


def test_dong_ghi_do_bi_cat_truoc_khi_ghi_tiep(tmp_path, caplog):
    st = audit_log.AuditStore(tmp_path / "audit.jsonl")
    _append_n(st, 2, NOV)
    f = st.files()[-1]
    with open(f, "ab") as fh:  # tiến trình chết giữa lúc ghi, cắt giữa ký tự UTF-8
        fh.write('{"frame": 2, "operator": "ca", "ghi_chú": "đ'.encode()[:-1])
    assert audit_log.verify(f) == (True, 2, "")  # đọc lúc này vẫn không lỗi
    with caplog.at_level(logging.WARNING, logger="edge_ai.api.audit_log"):
        _append_n(st, 1, NOV)
    assert any("ghi dở" in r.getMessage() for r in caplog.records)
    assert st.verify() == (True, 3, "")
    assert f.read_bytes().endswith(b"\n")


def test_ghi_loi_khong_de_lai_dong_do(tmp_path, monkeypatch):
    st = audit_log.AuditStore(tmp_path / "audit.jsonl")
    _append_n(st, 1, NOV)
    f = st.files()[-1]
    size = f.stat().st_size

    def no_fsync(_fd):
        raise OSError(5, "I/O error")

    monkeypatch.setattr(audit_log.os, "fsync", no_fsync)
    with pytest.raises(OSError):
        _append_n(st, 1, NOV)
    monkeypatch.undo()
    assert f.stat().st_size == size
    assert st.verify() == (True, 1, "")


def test_dong_ho_lui_qua_ranh_gioi_thang_khong_dut_chuoi(tmp_path):
    st = audit_log.AuditStore(tmp_path / "audit.jsonl")
    _append_n(st, 2, NOV)
    _append_n(st, 1, DEC)
    _append_n(st, 1, NOV)  # đồng hồ bị chỉnh lùi về tháng 11
    assert [p.name for p in st.files()] == ["audit-2026-11.jsonl", "audit-2026-12.jsonl"]
    assert st.verify() == (True, 4, "")
    last = json.loads(st.files()[-1].read_text(encoding="utf-8").splitlines()[-1])
    assert last["ts"] == NOV  # ts thật trong bản ghi không bị sửa
