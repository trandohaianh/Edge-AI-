"""Đọc/ghi JSON dùng chung: luôn UTF-8, luôn đóng tệp.

Các tệp kết quả có tiếng Việt; ``open()`` không ghi ``encoding`` thì trên
Windows mặc định là cp1252 và đọc lỗi (lỗi đã gặp ở đợt rà soát 1). Gom về
một chỗ để không ai phải nhớ điều đó nữa.
"""

from __future__ import annotations

import contextlib
import json
import sys
from pathlib import Path
from typing import Any


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, obj: Any, indent: int = 1) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # newline="\n": xuống dòng LF cả trên Windows, khớp .gitattributes
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, indent=indent, ensure_ascii=False)
        f.write("\n")  # kết thúc bằng xuống dòng, như mọi tệp văn bản khác


def utf8_stdio() -> None:
    """Cho các lệnh dòng lệnh in được tiếng Việt trên Windows.

    Khi đầu ra không phải cửa sổ console (chuyển hướng ra tệp, chạy qua ống
    dẫn, Git Bash, bộ lập lịch), Python trên Windows dùng cp1252 và ``print``
    tiếng Việt làm lệnh CRASH với UnicodeEncodeError — lỗi tìm thấy khi kiểm
    thử đầu-cuối (bước 8). Ép về UTF-8.
    """
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, ValueError):
            stream.reconfigure(encoding="utf-8", errors="replace")
