"""Kiểm thử nhật ký theo tháng, sao lưu, khôi phục, dọn 12 tháng (PRD A-16, A-17)."""

from __future__ import annotations

import json
import os
import sys
import time

import pytest

from edge_ai.api import audit_backup as AB
from edge_ai.api.audit_log import GENESIS, AuditStore, chain


def _ts(year: int, month: int, day: int = 15) -> float:
    return time.mktime((year, month, day, 12, 0, 0, 0, 0, 0)) - time.timezone


def _fill(base, months: list[tuple[int, int]], per_month: int = 3) -> AuditStore:
    store = AuditStore(base)
    prev = store.last_hash()
    for y, m in months:
        for i in range(per_month):
            prev = store.append(
                prev, {"action": "xac_nhan", "frame": i, "operator": "ca"}, ts=_ts(y, m, 1 + i)
            )["hash"]
    return store


def test_chuoi_bam_lien_qua_cac_thang(tmp_path):
    store = _fill(tmp_path / "audit.jsonl", [(2026, 11), (2026, 12), (2027, 1)])
    assert [p.name for p in store.files()] == [
        "audit-2026-11.jsonl",
        "audit-2026-12.jsonl",
        "audit-2027-01.jsonl",
    ]
    assert store.verify() == (True, 9, "")
    # dòng đầu tháng 12 phải nối vào dòng cuối tháng 11
    nov_last = json.loads(store.files()[0].read_text(encoding="utf-8").splitlines()[-1])
    dec_first = json.loads(store.files()[1].read_text(encoding="utf-8").splitlines()[0])
    assert dec_first["prev"] == nov_last["hash"]


def test_xoa_ca_mot_thang_giua_chung_bi_phat_hien(tmp_path):
    store = _fill(tmp_path / "audit.jsonl", [(2026, 11), (2026, 12), (2027, 1)])
    store.files()[1].unlink()
    ok, _, err = store.verify()
    assert not ok and "đứt chuỗi" in err


def test_tep_mot_khoi_cua_ban_cu_duoc_noi_tiep(tmp_path):
    """Nhật ký của bản trước (một tệp audit.jsonl) là đoạn đầu của chuỗi."""
    base = tmp_path / "audit.jsonl"
    rec = chain(GENESIS, {"action": "bo_qua"})
    base.write_text(json.dumps(rec) + "\n", encoding="utf-8")
    store = _fill(base, [(2026, 12)])
    assert store.verify() == (True, 4, "")


def test_sao_luu_roi_khoi_phuc_vao_may_moi(tmp_path):
    log = tmp_path / "tram" / "audit.jsonl"
    _fill(log, [(2026, 11), (2026, 12)])
    snap = AB.backup(log, tmp_path / "backups", now=_ts(2026, 12, 20))
    assert snap.name == "2026-12-20"
    man = AB.verify_snapshot(snap)
    assert man["lines"] == 6
    new = tmp_path / "may-moi" / "audit.jsonl"
    assert AB.restore(snap, new) == 6
    assert AuditStore(new).verify() == (True, 6, "")
    assert AuditStore(new).last_hash() == man["chain_head"]


def test_khong_sao_luu_nhat_ky_da_bi_sua(tmp_path):
    log = tmp_path / "audit.jsonl"
    store = _fill(log, [(2026, 11)])
    f = store.files()[0]
    f.write_text(f.read_text(encoding="utf-8").replace("xac_nhan", "bo_qua", 1), encoding="utf-8")
    with pytest.raises(AB.BackupError, match="KHÔNG hợp lệ"):
        AB.backup(log, tmp_path / "backups")
    assert not (tmp_path / "backups").exists() or not any((tmp_path / "backups").iterdir())


def test_khong_khoi_phuc_ban_sao_luu_bi_sua(tmp_path):
    log = tmp_path / "audit.jsonl"
    _fill(log, [(2026, 11)])
    snap = AB.backup(log, tmp_path / "backups", now=_ts(2026, 11, 20))
    f = snap / "audit-2026-11.jsonl"
    f.write_text(f.read_text(encoding="utf-8").replace("xac_nhan", "bo_qua", 1), encoding="utf-8")
    with pytest.raises(AB.BackupError, match="bị sửa"):
        AB.restore(snap, tmp_path / "moi" / "audit.jsonl")
    assert (
        not (tmp_path / "moi").exists() or not AuditStore(tmp_path / "moi" / "audit.jsonl").files()
    )


def test_khoi_phuc_khong_ghi_de_nhat_ky_dang_co_tru_khi_force(tmp_path):
    log = tmp_path / "audit.jsonl"
    _fill(log, [(2026, 11)])
    snap = AB.backup(log, tmp_path / "backups", now=_ts(2026, 11, 20))
    with pytest.raises(AB.BackupError, match="không ghi đè"):
        AB.restore(snap, log)
    assert AB.restore(snap, log, force=True) == 3


def test_sao_luu_bo_dong_dang_ghi_do(tmp_path):
    """Dòng cuối chưa có xuống dòng là dòng dịch vụ đang ghi dở: bỏ qua."""
    log = tmp_path / "audit.jsonl"
    store = _fill(log, [(2026, 11)])
    with open(store.files()[0], "a", encoding="utf-8") as f:
        f.write('{"action": "xac_nh')
    assert store.verify()[0]
    snap = AB.backup(log, tmp_path / "backups", now=_ts(2026, 11, 20))
    assert AB.verify_snapshot(snap)["lines"] == 3


def test_don_giu_dung_12_thang_va_van_kiem_duoc(tmp_path):
    log = tmp_path / "audit.jsonl"
    months = [(2025, m) for m in range(9, 13)] + [(2026, m) for m in range(1, 12)]  # 15 tháng
    store = _fill(log, months, per_month=2)
    backups = tmp_path / "backups"
    old_snap = backups / "2025-09-30"
    old_snap.mkdir(parents=True)
    r = AB.prune(log, backups, now=_ts(2026, 11, 22))
    assert r["log_files_removed"] == [
        "audit-2025-09.jsonl",
        "audit-2025-10.jsonl",
        "audit-2025-11.jsonl",
    ]
    assert r["snapshots_removed"] == ["2025-09-30"]
    assert len(store.monthly_files()) == 12
    assert store.verify() == (True, 24, "")
    assert store.pruned()["anchor"] != GENESIS
    # Lén xoá thêm tháng cũ nhất còn lại (ngoài lần dọn hợp lệ) thì bị phát hiện
    store.monthly_files()[0].unlink()
    assert not store.verify()[0]


def test_dua_tren_ban_sao_luu_sau_khi_don_van_khoi_phuc_duoc(tmp_path):
    log = tmp_path / "audit.jsonl"
    months = [(2025, 10), (2025, 11)] + [(2026, m) for m in range(1, 12)]
    _fill(log, months, per_month=1)
    AB.prune(log, None, now=_ts(2026, 11, 22))
    snap = AB.backup(log, tmp_path / "b", now=_ts(2026, 11, 22))
    new = tmp_path / "moi" / "audit.jsonl"
    assert AB.restore(snap, new) == 11
    assert AuditStore(new).verify()[0]


@pytest.mark.skipif(sys.platform == "win32", reason="quyền tệp POSIX chỉ có trên Linux/macOS")
def test_quyen_tep_nhat_ky_va_sao_luu_la_600(tmp_path):
    log = tmp_path / "audit.jsonl"
    store = _fill(log, [(2026, 11)])
    snap = AB.backup(log, tmp_path / "b", now=_ts(2026, 11, 20))
    for p in [*store.files(), *snap.iterdir()]:
        assert oct(os.stat(p).st_mode & 0o777) == "0o600", p


def test_lenh_dong_lenh(tmp_path, capsys):
    log = tmp_path / "audit.jsonl"
    _fill(log, [(2026, 11)])
    dest = tmp_path / "b"
    assert AB.main(["backup", "--log", str(log), "--dest", str(dest)]) == 0
    snap = next(dest.iterdir())
    assert AB.main(["verify-snapshot", "--snapshot", str(snap)]) == 0
    assert AB.main(["restore", "--snapshot", str(snap), "--log", str(log)]) == 1  # không ghi đè
    assert "LỖI" in capsys.readouterr().err
