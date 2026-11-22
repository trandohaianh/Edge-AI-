"""Nhật ký quyết định dạng chuỗi băm, chia theo tháng.

Mỗi dòng JSONL mang ``prev`` (băm của dòng trước) và ``hash`` = SHA-256 của
``prev`` nối với nội dung dòng (khoá sắp xếp cố định). Ai sửa một dòng ở giữa
thì băm của nó không còn khớp; ai xoá một dòng thì ``prev`` của dòng sau
không còn khớp.

**Chia theo tháng** (PRD Q-5: giữ 12 tháng). Nếu chỉ có một tệp thì muốn bỏ
dữ liệu cũ phải xoá dòng ở đầu tệp, và chuỗi băm sẽ đứt. Vì vậy mỗi tháng
một tệp ``<tên>-YYYY-MM.jsonl``; dòng đầu của tháng mới nối băm với dòng
cuối của tháng trước, nên chuỗi liền qua các tháng. Bỏ dữ liệu quá hạn là
xoá NGUYÊN tệp của tháng cũ, đồng thời ghi băm cuối của phần bị xoá vào
``pruned.json``. Khi kiểm tra, tệp cũ nhất còn lại phải nối đúng vào mốc
đó; nhờ vậy ai lén xoá thêm một tháng ngoài lần dọn hợp lệ cũng bị phát hiện.

Vẫn không chống được việc xoá CẢ đuôi nhật ký (các dòng mới nhất). Muốn
chống điều đó thì định kỳ chép băm mới nhất ra nơi khác — bản sao lưu hằng
ngày (``audit_backup.py``) làm đúng việc này.

Kiểm tra toàn bộ nhật ký (chạy trong ``backend/``):

    python -m edge_ai.api.audit_log ../logs/audit.jsonl
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

from edge_ai.io_utils import utf8_stdio

GENESIS = "0" * 64
PRUNED_FILE = "pruned.json"
FILE_MODE = 0o600  # PRD A-17: chỉ user của dịch vụ đọc/ghi được


def _digest(prev: str, body: dict) -> str:
    payload = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256((prev + payload).encode("utf-8")).hexdigest()


def chain(prev: str, rec: dict) -> dict:
    """Trả về bản ghi đã gắn ``prev`` và ``hash``."""
    body = {k: v for k, v in rec.items() if k not in ("prev", "hash")}
    body["prev"] = prev
    return body | {"hash": _digest(prev, body)}


def _records(path: Path):
    """Các dòng đầy đủ của tệp. Bỏ qua dòng cuối CHƯA có ký tự xuống dòng:
    đó là dòng đang được ghi dở (đọc trúng lúc dịch vụ đang ghi)."""
    with open(path, encoding="utf-8", newline="") as f:
        for i, line in enumerate(f, 1):
            if not line.endswith("\n"):
                return
            if line.strip():
                yield i, line


def last_hash(path: Path) -> str:
    """Băm của dòng cuối một tệp, để nối tiếp chuỗi sau khi khởi động lại."""
    path = Path(path)
    if not path.exists():
        return GENESIS
    last = GENESIS
    for _, line in _records(path):
        with contextlib.suppress(json.JSONDecodeError):
            last = json.loads(line).get("hash", last)
    return last


def verify(path: Path, start_prev: str | None = GENESIS) -> tuple[bool, int, str]:
    """Kiểm một tệp: (hợp lệ, số dòng đã kiểm, mô tả lỗi đầu tiên nếu có).

    ``start_prev``: băm mà dòng đầu phải nối vào; ``None`` = chấp nhận bất kỳ.
    """
    ok, n, err, _ = _verify_file(Path(path), start_prev)
    return ok, n, err


def _verify_file(path: Path, start_prev: str | None) -> tuple[bool, int, str, str]:
    prev = start_prev
    n = 0
    for i, line in _records(path):
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            return False, n, f"{path.name} dòng {i}: không phải JSON", prev or ""
        if prev is None:
            prev = rec.get("prev", "")
        if rec.get("prev") != prev:
            return (
                False,
                n,
                f"{path.name} dòng {i}: đứt chuỗi (thiếu hoặc chèn dòng phía trước)",
                prev,
            )
        body = {k: v for k, v in rec.items() if k != "hash"}
        if _digest(prev, body) != rec.get("hash"):
            return False, n, f"{path.name} dòng {i}: nội dung đã bị sửa", prev
        prev = rec["hash"]
        n += 1
    return True, n, "", prev if prev is not None else GENESIS


class AuditStore:
    """Bộ nhật ký gồm nhiều tệp theo tháng, cùng thư mục với ``base``.

    ``base`` là đường dẫn cấu hình (``EDGE_AUDIT_LOG``), ví dụ
    ``logs/audit.jsonl``; các tệp thật là ``logs/audit-2026-11.jsonl``…
    Nếu tồn tại tệp ``base`` của phiên bản cũ (một tệp duy nhất) thì nó được
    coi là đoạn đầu tiên của chuỗi.
    """

    def __init__(self, base: str | Path):
        self.base = Path(base)
        self.dir = self.base.parent
        self.stem = self.base.stem
        self._rx = re.compile(rf"^{re.escape(self.stem)}-(\d{{4}})-(\d{{2}})\.jsonl$")

    # --------------------------------------------------------------- tệp
    def month_of(self, ts: float) -> str:
        return time.strftime("%Y-%m", time.gmtime(ts))

    def path_for(self, ts: float) -> Path:
        return self.dir / f"{self.stem}-{self.month_of(ts)}.jsonl"

    def monthly_files(self) -> list[Path]:
        if not self.dir.exists():
            return []
        return sorted(p for p in self.dir.iterdir() if self._rx.match(p.name))

    def files(self) -> list[Path]:
        """Mọi đoạn của chuỗi theo đúng thứ tự thời gian."""
        legacy = [self.base] if self.base.exists() else []
        return legacy + self.monthly_files()

    def month_key(self, path: Path) -> str | None:
        m = self._rx.match(path.name)
        return f"{m.group(1)}-{m.group(2)}" if m else None

    # ----------------------------------------------------------- mốc dọn
    @property
    def pruned_path(self) -> Path:
        return self.dir / f"{self.stem}.{PRUNED_FILE}"

    def pruned(self) -> dict:
        p = self.pruned_path
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    # ------------------------------------------------------------- ghi
    def last_hash(self) -> str:
        for p in reversed(self.files()):
            h = last_hash(p)
            if h != GENESIS:
                return h
        return self.pruned().get("anchor", GENESIS)

    def append(self, prev: str, rec: dict, ts: float | None = None) -> dict:
        """Nối một bản ghi vào tệp của tháng hiện tại. Trả về bản ghi đã nối băm."""
        ts = time.time() if ts is None else ts
        out = chain(prev, rec)
        path = self.path_for(ts)
        self.dir.mkdir(parents=True, exist_ok=True)
        new = not path.exists()
        with open(path, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(out, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        if new:
            secure(path)
        return out

    # ------------------------------------------------------------ kiểm
    def verify(self) -> tuple[bool, int, str]:
        """Kiểm toàn bộ chuỗi qua mọi tệp. Tệp cũ nhất phải nối vào GENESIS,
        hoặc vào mốc ``anchor`` của lần dọn gần nhất."""
        prev = self.pruned().get("anchor", GENESIS)
        total = 0
        for p in self.files():
            ok, n, err, prev = _verify_file(p, prev)
            total += n
            if not ok:
                return False, total, err
        return True, total, ""


def secure(path: Path) -> None:
    """Đặt quyền 600. Trên Windows ``chmod`` gần như không có tác dụng; quyền
    thật được bảo đảm trong container Linux (PRD A-17)."""
    with contextlib.suppress(OSError):
        os.chmod(path, FILE_MODE)


def main(argv: list[str]) -> int:
    utf8_stdio()
    target = Path(argv[1]) if len(argv) > 1 else Path("logs/audit.jsonl")
    store = AuditStore(target)
    files = store.files()
    if not files:
        print(f"{target}: không có tệp nhật ký nào")
        return 1
    ok, n, err = store.verify()
    names = ", ".join(p.name for p in files)
    print(f"{n} dòng hợp lệ trong {len(files)} tệp ({names})" + ("" if ok else f" — LỖI: {err}"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
