"""Hạ tầng kiểm thử đầu-cuối: máy chủ thật + trình duyệt Chromium thật.

Chỉ chạy khi đặt ``EDGE_E2E=1`` (cần ``pip install playwright`` và
``python -m playwright install chromium``). Không đặt thì các bài này bị bỏ
qua khi thu thập, nên ``python -m pytest`` thường vẫn nhanh và không cần
trình duyệt. Trong CI có job ``e2e`` riêng.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]

if os.environ.get("EDGE_E2E") != "1":
    collect_ignore_glob = ["test_*.py"]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Server:
    """Một tiến trình uvicorn thật, nhật ký ở thư mục tạm; bật/tắt được."""

    def __init__(self, tmp: Path, token: str | None = None):
        self.port = _free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        self.log = tmp / "audit.jsonl"
        self.env = {**os.environ, "EDGE_AUDIT_LOG": str(self.log), "PYTHONUTF8": "1"}
        self.env.pop("EDGE_API_TOKEN", None)
        if token:
            self.env["EDGE_API_TOKEN"] = token
        self.out = tmp / "server.log"
        self.proc: subprocess.Popen | None = None

    def start(self, timeout: float = 90.0) -> None:
        cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            "edge_ai.api.server:app",
            "--app-dir",
            "backend",
            "--host",
            "127.0.0.1",
            "--port",
            str(self.port),
        ]
        with self.out.open("ab") as f:
            self.proc = subprocess.Popen(cmd, cwd=ROOT, env=self.env, stdout=f, stderr=f)
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self.proc.poll() is not None:
                raise RuntimeError("máy chủ thoát sớm:\n" + self.out.read_text("utf-8", "replace"))
            try:
                h = self.get("/api/health")
                if h.get("ok"):
                    return
            except OSError:
                pass
            time.sleep(0.3)
        raise RuntimeError("máy chủ không lên kịp:\n" + self.out.read_text("utf-8", "replace"))

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(10)
        self.proc = None

    def get(self, path: str) -> dict:
        with urllib.request.urlopen(self.url + path, timeout=3) as r:
            return json.loads(r.read())

    def post(self, path: str, token: str | None = None) -> dict:
        req = urllib.request.Request(self.url + path, method="POST", data=b"")
        if token:
            req.add_header("X-API-Token", token)
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())

    def audit_lines(self) -> list[dict]:
        rows = []
        for f in sorted(self.log.parent.glob("audit*.jsonl")):
            rows += [json.loads(x) for x in f.read_text("utf-8").splitlines() if x.strip()]
        return rows


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    s = Server(tmp_path_factory.mktemp("e2e"))
    s.start()
    yield s
    s.stop()


@pytest.fixture
def own_server(tmp_path):
    """Máy chủ riêng cho bài cần tắt/bật lại máy chủ."""
    s = Server(tmp_path)
    s.start()
    yield s
    s.stop()


@pytest.fixture
def token_server(tmp_path):
    s = Server(tmp_path, token="ma-e2e-dung")
    s.start()
    yield s
    s.stop()


@pytest.fixture(scope="session")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def page(browser):
    ctx = browser.new_context(viewport={"width": 1400, "height": 900}, locale="vi-VN")
    pg = ctx.new_page()
    pg.set_default_timeout(20_000)
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.js_errors = errors
    yield pg
    ctx.close()
