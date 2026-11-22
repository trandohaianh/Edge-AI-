"""Chặn dò mã truy cập (PRD bước 7, bảo mật).

Mã truy cập là một chuỗi dùng chung cho cả ca trực (PRD Q-3). Nếu không
giới hạn, ai trong mạng cũng có thể thử hàng nghìn mã mỗi phút. Ở đây mỗi
địa chỉ IP chỉ được sai ``MAX_FAILURES`` lần trong ``WINDOW_S`` giây; quá mức
đó thì bị khoá ``LOCK_S`` giây. Trong lúc bị khoá, gửi cả mã ĐÚNG cũng bị từ
chối (nếu không, kẻ dò vẫn biết được mã nào đúng). Nhập đúng mã khi chưa bị
khoá thì số lần sai được xoá.

IP lấy từ ``request.client.host``. Khi chạy sau Caddy, uvicorn đọc
``X-Forwarded-For`` mà Caddy đặt; Caddy mặc định BỎ header đó nếu trình
duyệt tự gửi lên, nên người ngoài không giả được IP để né khoá.

Bộ đếm nằm trong RAM: khởi động lại thì mất, như vậy là đủ cho một trạm.
"""

from __future__ import annotations

import threading
import time
from collections import deque

MAX_FAILURES = 5
WINDOW_S = 300.0
LOCK_S = 300.0
MAX_CLIENTS = 10_000  # giới hạn bộ nhớ khi bị dò từ rất nhiều IP


class FailureLimiter:
    def __init__(
        self,
        max_failures: int = MAX_FAILURES,
        window_s: float = WINDOW_S,
        lock_s: float = LOCK_S,
        max_clients: int = MAX_CLIENTS,
    ):
        self.max_failures = max_failures
        self.window_s = window_s
        self.lock_s = lock_s
        self.max_clients = max_clients
        self._fails: dict[str, deque[float]] = {}
        self._locked_until: dict[str, float] = {}
        self._lock = threading.Lock()

    def retry_after(self, client: str, now: float | None = None) -> int:
        """Số giây còn bị khoá; 0 nếu được phép thử."""
        now = time.monotonic() if now is None else now
        with self._lock:
            until = self._locked_until.get(client, 0.0)
            if until <= now:
                self._locked_until.pop(client, None)
                return 0
            return max(1, int(until - now + 0.999))

    def failure(self, client: str, now: float | None = None) -> bool:
        """Ghi một lần sai. Trả về True nếu lần sai này làm IP bị khoá."""
        now = time.monotonic() if now is None else now
        with self._lock:
            if client not in self._fails and len(self._fails) >= self.max_clients:
                self._evict(now)
            q = self._fails.setdefault(client, deque())
            q.append(now)
            while q and q[0] <= now - self.window_s:
                q.popleft()
            if len(q) >= self.max_failures:
                if len(self._locked_until) >= self.max_clients:
                    for k in [k for k, u in self._locked_until.items() if u <= now]:
                        del self._locked_until[k]
                self._locked_until[client] = now + self.lock_s
                del self._fails[client]
                return True
            return False

    def success(self, client: str) -> None:
        with self._lock:
            self._fails.pop(client, None)

    def reset(self) -> None:
        with self._lock:
            self._fails.clear()
            self._locked_until.clear()

    def _evict(self, now: float) -> None:
        for k in [k for k, q in self._fails.items() if not q or q[-1] <= now - self.window_s]:
            del self._fails[k]
        if len(self._fails) >= self.max_clients:  # vẫn đầy: bỏ IP sai lâu nhất
            oldest = min(self._fails, key=lambda k: self._fails[k][-1])
            del self._fails[oldest]
