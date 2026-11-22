"""Chạy dài (soak test): bật máy chủ thật rồi dùng nó như một ca trực.

Kiểm những thứ chỉ lộ ra khi chạy lâu:
- bộ nhớ có tăng mãi không (rò bộ nhớ);
- vòng xử lý có lúc nào đứng quá 2 s không (healthcheck sẽ báo unhealthy);
- có request nào lỗi 5xx không;
- sau hàng trăm quyết định, nhật ký có còn hợp lệ không.

Kịch bản giống ca trực: dashboard hỏi trạng thái liên tục, thỉnh thoảng
người trực bấm Xác nhận / Bỏ qua, và kịch bản được đổi vòng tròn (có cả
"Nhiều mục tiêu", là kịch bản nặng nhất).

    python -m edge_ai.experiments.soak --minutes 30          # trong backend/
    python -m edge_ai.experiments.soak --minutes 10080       # 7 ngày (MAINTENANCE P2)

Cần ``psutil`` để đo bộ nhớ của tiến trình máy chủ (``pip install psutil``).
Kết quả ghi ``data/results/soak.json``. Nhật ký quyết định ghi vào thư mục tạm,
không đụng nhật ký thật.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np

from edge_ai.config import RESULTS_DIR
from edge_ai.io_utils import utf8_stdio

ROOT = Path(__file__).resolve().parents[3]
SCENARIO_CYCLE = ("clear", "swarm", "fog_night", "jamming", "bird", "patch", "dropout")
STALL_S = 2.0  # giống ngưỡng của /api/health
MAX_GROWTH_MB_PER_H = 5.0


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _req(url: str, method: str = "GET", body: dict | None = None, timeout: float = 5.0):
    data = json.dumps(body).encode() if body is not None else (b"" if method == "POST" else None)
    r = urllib.request.Request(url, method=method, data=data)
    if body is not None:
        r.add_header("Content-Type", "application/json")
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            code, payload = resp.status, resp.read()
    except urllib.error.HTTPError as e:
        code, payload = e.code, e.read()
    ms = (time.perf_counter() - t0) * 1e3
    try:
        return code, json.loads(payload), ms
    except ValueError:
        return code, {}, ms


def slope_mb_per_h(t_s: list[float], rss_mb: list[float]) -> float:
    """Độ dốc bộ nhớ (MB/giờ) trên nửa sau của lần chạy.

    Bỏ nửa đầu vì lúc mới chạy bộ nhớ tăng do nạp và cấp phát lần đầu, không
    phải rò. Rò bộ nhớ thật làm nửa sau vẫn dốc lên.
    """
    if len(t_s) < 4:
        return 0.0
    h = len(t_s) // 2
    t = np.asarray(t_s[h:]) / 3600.0
    y = np.asarray(rss_mb[h:])
    if np.ptp(t) == 0:
        return 0.0
    return float(np.polyfit(t, y, 1)[0])


def run(minutes: float, poll_s: float, act_every_s: float, switch_every_s: float, out: Path):
    import psutil

    tmp = Path(tempfile.mkdtemp(prefix="edge-soak-"))
    log_path = tmp / "audit.jsonl"
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    env = {**os.environ, "EDGE_AUDIT_LOG": str(log_path), "PYTHONUTF8": "1"}
    env.pop("EDGE_API_TOKEN", None)  # loopback: chính máy này được bấm
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
        str(port),
        "--log-level",
        "warning",
    ]
    srv_log = (tmp / "server.log").open("wb")
    proc = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=srv_log, stderr=srv_log)
    try:
        for _ in range(300):
            try:
                if _req(url + "/api/health")[0] == 200:
                    break
            except OSError:
                pass
            time.sleep(0.3)
        else:
            raise RuntimeError(f"máy chủ không lên; xem {tmp / 'server.log'}")
        ps = psutil.Process(proc.pid)

        t_start = time.monotonic()
        end = t_start + minutes * 60
        next_act = t_start + act_every_s
        next_switch = t_start + switch_every_s
        next_sample = t_start
        sc_i = 0
        samples: list[dict] = []
        state_ms: list[float] = []
        errors: dict[str, int] = {}
        acts = acts_ok = switches = 0
        max_frame_age = 0.0
        stalls = 0

        while time.monotonic() < end:
            now = time.monotonic()
            try:
                code, st, ms = _req(url + "/api/state")
                state_ms.append(ms)
                if code >= 500:
                    errors[str(code)] = errors.get(str(code), 0) + 1
            except OSError as e:
                errors[type(e).__name__] = errors.get(type(e).__name__, 0) + 1
                st = {}
            if now >= next_sample:
                code, h, _ = _req(url + "/api/health")
                age = h.get("seconds_since_last_frame") or 0.0
                max_frame_age = max(max_frame_age, age)
                stalls += int(code != 200 or age >= STALL_S)
                rss = ps.memory_info().rss / 2**20
                samples.append(
                    {
                        "t_s": round(now - t_start, 1),
                        "rss_mb": round(rss, 2),
                        "frame_age_s": age,
                        "scenario": h.get("scenario"),
                        "loop_p99_ms": (st.get("latency") or {}).get("p99_ms"),
                    }
                )
                next_sample = now + 10.0
            if now >= next_act and st.get("tracks"):
                tr = st["tracks"][0]
                if tr.get("operator") is None:
                    a = "xac_nhan" if acts % 2 == 0 else "bo_qua"
                    code, d, _ = _req(url + "/api/act", "POST", {"action": a, "tid": tr["tid"]})
                    acts += 1
                    acts_ok += int(code == 200 and d.get("persisted") is True)
                next_act = now + act_every_s
            if now >= next_switch:
                sc_i = (sc_i + 1) % len(SCENARIO_CYCLE)
                code, _, _ = _req(url + f"/api/scenario/{SCENARIO_CYCLE[sc_i]}", "POST")
                switches += int(code == 200)
                next_switch = now + switch_every_s
            time.sleep(max(0.0, poll_s - (time.monotonic() - now)))
        dur_s = time.monotonic() - t_start
    finally:
        proc.terminate()
        try:
            proc.wait(15)
        except subprocess.TimeoutExpired:
            proc.kill()
        srv_log.close()

    chk = subprocess.run(
        [sys.executable, "-m", "edge_ai.api.audit_log", str(log_path)],
        cwd=ROOT / "backend",
        capture_output=True,
        env=env,
    )
    chain_out = chk.stdout.decode("utf-8", "replace").strip()
    t = [s["t_s"] for s in samples]
    rss = [s["rss_mb"] for s in samples]
    growth = slope_mb_per_h(t, rss)
    a = np.asarray(state_ms) if state_ms else np.zeros(1)
    checks = {
        "khong_dung_vong_qua_2s": stalls == 0,
        "khong_loi_5xx": not errors,
        "moi_quyet_dinh_ghi_duoc": acts > 0 and acts_ok == acts,
        "nhat_ky_hop_le": chk.returncode == 0,
        f"bo_nho_tang_duoi_{MAX_GROWTH_MB_PER_H:g}MB_moi_gio": growth < MAX_GROWTH_MB_PER_H,
    }
    res = {
        "ran_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "host": {
            "python": sys.version.split()[0],
            "platform": sys.platform,
            "cpu_count": os.cpu_count(),
        },
        "duration_min": round(dur_s / 60, 1),
        "requests_state": len(state_ms),
        "state_latency_ms": {
            "p50": round(float(np.percentile(a, 50)), 2),
            "p99": round(float(np.percentile(a, 99)), 2),
            "max": round(float(a.max()), 2),
        },
        "errors": errors,
        "decisions": {"sent": acts, "persisted": acts_ok},
        "scenario_switches": switches,
        "max_frame_age_s": round(max_frame_age, 3),
        "health_stalls": stalls,
        "rss_mb": {
            "start": rss[0] if rss else None,
            "end": rss[-1] if rss else None,
            "max": max(rss) if rss else None,
            "slope_second_half_mb_per_h": round(growth, 2),
        },
        "audit_chain": chain_out,
        "checks": checks,
        "passed": all(checks.values()),
        "samples": samples,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    return res


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--minutes", type=float, default=30)
    ap.add_argument("--poll", type=float, default=0.5, help="giây giữa hai lần hỏi /api/state")
    ap.add_argument("--act-every", type=float, default=20, help="giây giữa hai quyết định")
    ap.add_argument(
        "--switch-every", type=float, default=120, help="giây giữa hai lần đổi kịch bản"
    )
    ap.add_argument("--out", type=Path, default=RESULTS_DIR / "soak.json")
    a = ap.parse_args(argv)
    r = run(a.minutes, a.poll, a.act_every, a.switch_every, a.out)
    print(
        f"chạy {r['duration_min']} phút, {r['requests_state']} lần hỏi trạng thái, "
        f"{r['decisions']['persisted']}/{r['decisions']['sent']} quyết định ghi được"
    )
    print(
        f"bộ nhớ {r['rss_mb']['start']} → {r['rss_mb']['end']} MB "
        f"(nửa sau: {r['rss_mb']['slope_second_half_mb_per_h']} MB/giờ); "
        f"khung đứng lâu nhất {r['max_frame_age_s']} s; lỗi: {r['errors'] or 'không'}"
    )
    print("nhật ký:", r["audit_chain"])
    for k, v in r["checks"].items():
        print(("  ĐẠT  " if v else "  HỎNG ") + k)
    print("KẾT LUẬN:", "ĐẠT" if r["passed"] else "KHÔNG ĐẠT")
    return 0 if r["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
