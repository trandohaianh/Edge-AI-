"""Đọc/ghi JSON dùng chung: luôn UTF-8, luôn đóng tệp.

Các tệp kết quả có tiếng Việt; ``open()`` không ghi ``encoding`` thì trên
Windows mặc định là cp1252 và đọc lỗi (lỗi đã gặp ở đợt rà soát 1). Gom về
một chỗ để không ai phải nhớ điều đó nữa.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, obj: Any, indent: int = 1) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=indent, ensure_ascii=False)
        f.write("\n")  # kết thúc bằng xuống dòng, như mọi tệp văn bản khác
