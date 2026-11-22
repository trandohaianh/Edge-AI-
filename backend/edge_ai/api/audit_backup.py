"""Sao lưu, khôi phục và dọn nhật ký quyết định (PRD A-16, Q-5).

Các lệnh (chạy trong ``backend/``):

    python -m edge_ai.api.audit_backup backup  --log ../logs/audit.jsonl --dest ../backups
    python -m edge_ai.api.audit_backup restore --snapshot ../backups/2026-11-22 \
                                               --log ../logs/audit.jsonl
    python -m edge_ai.api.audit_backup prune   --log ../logs/audit.jsonl --dest ../backups
    python -m edge_ai.api.audit_backup daily   --log ... --dest ...   # chạy mãi, mỗi ngày một lần

* **backup** chép mọi tệp nhật ký sang ``<dest>/<YYYY-MM-DD>/``, kèm
  ``MANIFEST.json`` (SHA-256 từng tệp, số dòng, băm cuối chuỗi). Chuỗi băm
  được kiểm **trước** khi chép (nhật ký đã bị sửa thì từ chối và báo lỗi),
  và kiểm lại trên **bản chép** (khớp số dòng và băm cuối với bản gốc). Chép
  vào thư mục tạm rồi mới đổi tên, nên không bao giờ có một bản sao lưu dở.
* **restore** kiểm bản sao lưu (SHA-256 theo manifest và chuỗi băm) rồi mới
  chép vào chỗ nhật ký. Bản sao lưu bị sửa thì từ chối. Chỗ đích đã có nhật
  ký thì cũng từ chối, trừ khi gọi ``--force`` (tránh ghi đè dữ liệu thật).
* **prune** xoá tệp của các tháng cũ hơn 12 tháng (giữ đúng 12 tháng gần
  nhất), ghi băm cuối của phần bị xoá làm mốc (``pruned.json``); đồng thời
  xoá các bản sao lưu cũ hơn 12 tháng.

Bản sao lưu nằm trên cùng ổ đĩa với máy trạm: chống được lỡ tay xoá hay tệp
hỏng, KHÔNG chống được hỏng cả ổ. Hãy định kỳ chép thư mục sao lưu sang USB
hoặc ổ mạng (README, mục “Sao lưu nhật ký”).
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import logging
import shutil
import sys
import time
from pathlib import Path

from edge_ai.api.audit_log import PRUNED_FILE, AuditStore, last_hash, secure
from edge_ai.io_utils import read_json, utf8_stdio, write_json

log = logging.getLogger("edge.audit_backup")
KEEP_MONTHS = 12
MANIFEST = "MANIFEST.json"


class BackupError(RuntimeError):
    pass


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _month_index(key: str) -> int:
    y, m = key.split("-")
    return int(y) * 12 + int(m) - 1


# ------------------------------------------------------------------ backup
def backup(log_base: Path, dest: Path, now: float | None = None) -> Path:
    """Tạo bản sao lưu ``dest/<ngày>``. Trả về đường dẫn thư mục bản sao lưu."""
    now = time.time() if now is None else now
    store = AuditStore(log_base)
    files = store.files()
    ok, n, err = store.verify()
    if not ok:
        raise BackupError(f"nhật ký KHÔNG hợp lệ, không sao lưu: {err}")
    head = store.last_hash()

    day = time.strftime("%Y-%m-%d", time.gmtime(now))
    final = dest / day
    tmp = dest / f".{day}.tmp"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    # Thư mục bản sao lưu cũng chỉ user dịch vụ vào được (PRD A-17); thiếu
    # dòng này thì nó là 755 theo umask — tìm thấy khi chạy thử Docker.
    with contextlib.suppress(OSError):
        tmp.chmod(0o700)
    copied = []
    for f in files + ([store.pruned_path] if store.pruned_path.exists() else []):
        target = tmp / f.name
        # Chỉ chép các dòng ĐẦY ĐỦ: dòng cuối có thể đang được dịch vụ ghi dở.
        data = f.read_bytes()
        if f.suffix == ".jsonl" and data and not data.endswith(b"\n"):
            data = data[: data.rfind(b"\n") + 1]
        target.write_bytes(data)
        secure(target)
        copied.append(target)

    copy_store = AuditStore(tmp / log_base.name)
    ok2, n2, err2 = copy_store.verify()
    if not ok2 or n2 < n or copy_store.last_hash() != head:
        shutil.rmtree(tmp)
        raise BackupError(f"bản chép không khớp bản gốc ({n2}/{n} dòng): {err2}")
    write_json(
        tmp / MANIFEST,
        {
            "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
            "log_name": log_base.name,
            "lines": n2,
            "chain_head": head,
            "files": {p.name: _sha256(p) for p in copied},
        },
    )
    secure(tmp / MANIFEST)
    if final.exists():  # sao lưu lại trong cùng ngày: thay bản cũ của ngày đó
        shutil.rmtree(final)
    tmp.rename(final)
    log.info("đã sao lưu %d dòng, %d tệp vào %s", n2, len(copied), final)
    return final


# ----------------------------------------------------------------- restore
def verify_snapshot(snapshot: Path) -> dict:
    """Kiểm một bản sao lưu; trả về manifest nếu hợp lệ, ngược lại ném lỗi."""
    mpath = snapshot / MANIFEST
    if not mpath.exists():
        raise BackupError(f"{snapshot}: thiếu {MANIFEST}")
    man = read_json(mpath)
    for name, digest in man["files"].items():
        p = snapshot / name
        if not p.exists():
            raise BackupError(f"{snapshot}: thiếu tệp {name}")
        if _sha256(p) != digest:
            raise BackupError(f"{snapshot}: tệp {name} đã bị sửa sau khi sao lưu")
    store = AuditStore(snapshot / man["log_name"])
    ok, n, err = store.verify()
    if not ok:
        raise BackupError(f"{snapshot}: chuỗi băm không hợp lệ: {err}")
    if n != man["lines"] or store.last_hash() != man["chain_head"]:
        raise BackupError(f"{snapshot}: số dòng hoặc băm cuối không khớp manifest")
    return man


def restore(snapshot: Path, log_base: Path, force: bool = False) -> int:
    """Khôi phục bản sao lưu vào chỗ của nhật ký. Trả về số dòng đã khôi phục."""
    man = verify_snapshot(snapshot)
    target = AuditStore(log_base)
    if target.files() and not force:
        raise BackupError(
            f"{log_base.parent} đã có nhật ký; không ghi đè (dùng --force nếu chắc chắn)"
        )
    log_base.parent.mkdir(parents=True, exist_ok=True)
    src = AuditStore(snapshot / man["log_name"])
    for f in target.files() + ([target.pruned_path] if target.pruned_path.exists() else []):
        f.unlink()
    for f in src.files():
        name = f.name.replace(src.stem, target.stem, 1)
        shutil.copyfile(f, log_base.parent / name)
        secure(log_base.parent / name)
    if src.pruned_path.exists():
        shutil.copyfile(src.pruned_path, target.pruned_path)
        secure(target.pruned_path)
    ok, n, err = target.verify()
    if not ok:
        raise BackupError(f"khôi phục xong nhưng chuỗi băm không hợp lệ: {err}")
    log.info("đã khôi phục %d dòng từ %s", n, snapshot)
    return n


# ------------------------------------------------------------------- prune
def prune(
    log_base: Path,
    dest: Path | None = None,
    now: float | None = None,
    keep_months: int = KEEP_MONTHS,
) -> dict:
    """Xoá dữ liệu cũ hơn ``keep_months`` tháng (tính cả tháng hiện tại)."""
    now = time.time() if now is None else now
    store = AuditStore(log_base)
    ok, _, err = store.verify()
    if not ok:
        raise BackupError(f"nhật ký KHÔNG hợp lệ, không dọn (giữ nguyên làm bằng chứng): {err}")
    cur = _month_index(store.month_of(now))
    old = [
        p for p in store.monthly_files() if cur - _month_index(store.month_key(p)) >= keep_months
    ]
    removed = []
    if old:
        # Mốc mới = băm cuối của tệp cũ nhất bị xoá cuối cùng; tệp còn lại
        # đầu tiên phải nối vào đúng mốc này.
        anchor = last_hash(old[-1])
        info = store.pruned()
        history = info.get("history", [])
        history.append(
            {
                "at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
                "months": [store.month_key(p) for p in old],
                "anchor": anchor,
            }
        )
        if store.base.exists():  # tệp một-khối của bản cũ luôn cũ hơn mọi tháng
            old.insert(0, store.base)
        write_json(store.pruned_path, {"anchor": anchor, "history": history})
        secure(store.pruned_path)
        for p in old:
            p.unlink()
            removed.append(p.name)
        ok, _, err = store.verify()
        if not ok:
            raise BackupError(f"sau khi dọn chuỗi băm không hợp lệ: {err}")

    snaps = []
    if dest is not None and dest.exists():
        cutoff = now - keep_months * 31 * 86400
        for d in sorted(dest.iterdir()):
            if not d.is_dir() or d.name.startswith("."):
                continue
            try:
                t = time.mktime(time.strptime(d.name, "%Y-%m-%d"))
            except ValueError:
                continue
            if t < cutoff:
                shutil.rmtree(d)
                snaps.append(d.name)
    return {"log_files_removed": removed, "snapshots_removed": snaps}


# --------------------------------------------------------------------- CLI
def daily(log_base: Path, dest: Path, interval: float = 86400.0) -> None:
    """Vòng lặp cho dịch vụ sao lưu trong Docker: dọn rồi sao lưu, mỗi ngày."""
    while True:
        try:
            r = prune(log_base, dest)
            if r["log_files_removed"] or r["snapshots_removed"]:
                log.info("đã dọn: %s", r)
            if AuditStore(log_base).files():
                backup(log_base, dest)
            else:
                log.info("chưa có nhật ký nào để sao lưu")
        except BackupError:
            # Không nuốt lỗi: ghi rõ để giám sát thấy, rồi thử lại lần sau.
            log.exception("SAO LƯU THẤT BẠI")
        time.sleep(interval)


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(prog="audit_backup", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("backup", "prune", "daily"):
        s = sub.add_parser(name)
        s.add_argument("--log", type=Path, required=True)
        s.add_argument("--dest", type=Path, required=True)
        if name == "daily":
            s.add_argument("--interval", type=float, default=86400.0)
    s = sub.add_parser("restore")
    s.add_argument("--snapshot", type=Path, required=True)
    s.add_argument("--log", type=Path, required=True)
    s.add_argument("--force", action="store_true")
    s = sub.add_parser("verify-snapshot")
    s.add_argument("--snapshot", type=Path, required=True)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "backup":
            print(backup(a.log, a.dest))
        elif a.cmd == "prune":
            print(json.dumps(prune(a.log, a.dest), ensure_ascii=False))
        elif a.cmd == "restore":
            print(f"đã khôi phục {restore(a.snapshot, a.log, a.force)} dòng")
        elif a.cmd == "verify-snapshot":
            m = verify_snapshot(a.snapshot)
            print(f"hợp lệ: {m['lines']} dòng, băm cuối {m['chain_head'][:16]}")
        elif a.cmd == "daily":
            daily(a.log, a.dest, a.interval)
    except BackupError as e:
        print(f"LỖI: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["backup", "restore", "prune", "verify_snapshot", "BackupError", "PRUNED_FILE"]
