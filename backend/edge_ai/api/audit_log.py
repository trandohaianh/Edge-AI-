"""Nhật ký quyết định dạng chuỗi băm: sửa hay xoá một dòng là lộ ngay.

Mỗi dòng JSONL mang ``prev`` (băm của dòng trước) và ``hash`` = SHA-256 của
``prev`` nối với nội dung dòng (khoá sắp xếp cố định). Ai sửa một dòng ở giữa
thì băm của nó không còn khớp; ai xoá một dòng thì ``prev`` của dòng sau
không còn khớp. Không chống được việc xoá CẢ đuôi tệp — muốn chống điều đó
thì định kỳ chép băm cuối cùng ra nơi khác (ví dụ in vào sổ giao ca).

Kiểm tra một tệp:

    python src/audit_log.py logs/audit.jsonl
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

GENESIS = "0" * 64


def _digest(prev: str, body: dict) -> str:
    payload = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256((prev + payload).encode("utf-8")).hexdigest()


def chain(prev: str, rec: dict) -> dict:
    """Trả về bản ghi đã gắn ``prev`` và ``hash``."""
    body = {k: v for k, v in rec.items() if k not in ("prev", "hash")}
    body["prev"] = prev
    return body | {"hash": _digest(prev, body)}


def last_hash(path: Path) -> str:
    """Băm của dòng cuối, để nối tiếp chuỗi sau khi khởi động lại."""
    path = Path(path)
    if not path.exists():
        return GENESIS
    last = GENESIS
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    last = json.loads(line).get("hash", last)
                except json.JSONDecodeError:
                    pass
    return last


def verify(path: Path) -> tuple[bool, int, str]:
    """(hợp lệ, số dòng đã kiểm, mô tả lỗi đầu tiên nếu có)."""
    prev = GENESIS
    n = 0
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                return False, n, f"dòng {i}: không phải JSON"
            if rec.get("prev") != prev:
                return False, n, f"dòng {i}: đứt chuỗi (thiếu hoặc chèn dòng phía trước)"
            body = {k: v for k, v in rec.items() if k != "hash"}
            if _digest(prev, body) != rec.get("hash"):
                return False, n, f"dòng {i}: nội dung đã bị sửa"
            prev = rec["hash"]
            n += 1
    return True, n, ""


if __name__ == "__main__":
    p = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("logs/audit.jsonl")
    ok, n, err = verify(p)
    print(f"{p}: {n} dòng hợp lệ" + ("" if ok else f" — LỖI: {err}"))
    sys.exit(0 if ok else 1)
