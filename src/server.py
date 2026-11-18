"""Dashboard cho chuyên viên trực ca.

Hệ thống chỉ GIÁM SÁT: nó phát hiện, nhận dạng, bám quỹ đạo, đưa ra điểm
tin cậy kèm bằng chứng từ từng cảm biến, rồi chờ người quyết định. Không có
bất kỳ chức năng chọn mục tiêu tác chiến hay điều khiển khí tài nào, và cũng
không có chỗ nào trong mã nguồn để cắm thêm vào.

Mọi thao tác xác nhận / bỏ qua của chuyên viên đều được ghi vào nhật ký
kèm thời điểm và ảnh chụp bằng chứng tại thời điểm đó.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import FRAME_DT, RADAR_DWELL
from evaluate import MD_EVERY, RF_EVERY, lambda_iq
from pipeline import Pipeline, load_models
from radar_sim import micro_doppler
from scene import Weather, make_scenario, sense

ROOT = Path(__file__).resolve().parent.parent
app = FastAPI(title="Edge AI Surveillance")

# "start_m" ép mục tiêu bắt đầu ở cự ly nào. Cần cho các kịch bản liên quan
# tới camera: EO/IR chỉ nhận dạng được trong khoảng 1,2 km khi trời quang, nên
# nếu để mục tiêu sinh ngẫu nhiên ở 2,6 km thì camera không bao giờ vào cuộc
# và kịch bản "đánh lừa camera" chẳng chứng minh được gì.
SCENARIOS = {
    "clear": dict(label="Trời quang · drone đa cánh quạt",
                  kind="multirotor", w=Weather(), patch=False, drop=None,
                  pattern="approach", start_m=900),
    "fog_night": dict(label="Đêm + sương mù dày",
                      kind="multirotor", w=Weather(fog=0.85, night=True),
                      patch=False, drop=None, pattern="approach", start_m=900),
    "jamming": dict(label="Bị nhiễu dải RF",
                    kind="multirotor", w=Weather(jamming=0.9), patch=False, drop=None,
                    pattern="approach", start_m=900),
    "bird": dict(label="Chim — phải loại, không báo động",
                 kind="bird", w=Weather(), patch=False, drop=None,
                 pattern="approach", start_m=800),
    "patch": dict(label="Dán nhãn ngụy trang đánh lừa camera",
                  kind="multirotor", w=Weather(), patch=True, drop=None,
                  pattern="approach", start_m=900),
    "dropout": dict(label="Mất dấu 4 giây giữa chừng",
                    kind="multirotor", w=Weather(), patch=False, drop=(110, 150),
                    pattern="approach", start_m=1000),
}


@dataclass
class AuditEntry:
    ts: float
    frame: int
    action: str
    operator: str
    kind: str
    confidence: float
    evidence: dict
    pos: list


class Engine:
    """Chạy một kịch bản theo thời gian thực, 10 khung/giây."""

    def __init__(self):
        self.models = load_models()
        self.lock = threading.Lock()
        self.audit: list[AuditEntry] = []
        self.name = "clear"
        self.reset("clear")
        threading.Thread(target=self._loop, daemon=True).start()

    def reset(self, name: str):
        cfg = SCENARIOS[name]
        rng = np.random.default_rng(int(time.time()) % 100000)
        self.name = name
        self.cfg = cfg
        self.rng = rng
        self.w = cfg["w"]
        self.n = 260
        self.tg = make_scenario(self.n, rng, self.w, kinds=[cfg["kind"]],
                                patch_ids={0} if cfg["patch"] else set(),
                                patterns=[cfg.get("pattern")] if cfg.get("pattern") else None,
                                r0=cfg.get("start_m"))[0]
        # Xoay quỹ đạo về đúng hướng camera đang nhìn. EO/IR chỉ có góc nhìn
        # 60 độ, còn mục tiêu thì sinh ra ở phương vị bất kỳ, nên phần lớn lần
        # chạy camera nằm ngoài cuộc — và kịch bản đánh lừa camera trở thành
        # vô nghĩa. Trạm thật cũng quay đầu quang điện về phía có mục tiêu.
        if cfg.get("pattern") == "approach":
            az0 = np.arctan2(self.tg.pos[0, 1], self.tg.pos[0, 0])
            want = rng.uniform(-np.deg2rad(25), np.deg2rad(25))
            c, s_ = np.cos(want - az0), np.sin(want - az0)
            R = np.array([[c, -s_], [s_, c]])
            self.tg.pos[:, :2] = self.tg.pos[:, :2] @ R.T
            self.tg.vel[:, :2] = self.tg.vel[:, :2] @ R.T
        self.pipe = Pipeline(self.models)
        self.pipe.ensure_track(0, self.tg.pos[0] + rng.normal(0, 25, 3),
                               self.tg.vel[0] + rng.normal(0, 6, 3))
        self.k = 0
        self.msg = None
        self.trail: list[list[float]] = []
        self.truth_trail: list[list[float]] = []

    def _loop(self):
        while True:
            t0 = time.perf_counter()
            with self.lock:
                self._step()
            time.sleep(max(0.0, FRAME_DT - (time.perf_counter() - t0)))

    def _step(self):
        if self.k >= self.n:
            self.reset(self.name)
            return
        k = self.k
        drop = self.cfg["drop"]
        blind = drop is not None and drop[0] <= k < drop[1]
        dets = [] if blind else sense(self.tg, k, self.w, self.rng)
        iq = spec = None
        if not blind and k % RF_EVERY == 0 and any(d.sensor == "rf" for d in dets):
            iq = np.stack(lambda_iq(self.tg, self.rng))
        if not blind and k % MD_EVERY == 0 and any(d.sensor == "radar" for d in dets):
            r = float(np.linalg.norm(self.tg.pos[k]))
            snr = float(np.clip(30 - 20 * np.log10(max(r, 100) / 300), 2, 26))
            spec = micro_doppler(self.tg.kind, self.rng, snr_db=snr, rain=self.w.rain)
        m = self.pipe.step(0, dets, self.w, k, iq=iq, spec=spec)
        m["truth"] = self.tg.pos[k].tolist()
        m["truth_kind"] = self.tg.kind
        m["weather"] = self.w.label()
        m["blind"] = blind
        m["operator"] = self.pipe.tracks[0].operator
        m["scenario"] = self.name
        m["scenario_label"] = self.cfg["label"]
        self.trail.append(m["pos"])
        self.truth_trail.append(m["truth"])
        self.msg = m
        self.k += 1

    def state(self):
        with self.lock:
            m = dict(self.msg or {})
            m["trail"] = self.trail[-160:]
            m["truth_trail"] = self.truth_trail[-160:]
            m["latency"] = self.pipe.latency_report().get("total", {})
            m["stage_latency"] = self.pipe.latency_report()
            m["audit"] = [asdict(a) for a in self.audit[-12:]][::-1]
            return m

    def act(self, action: str, operator: str):
        with self.lock:
            tr = self.pipe.tracks[0]
            tr.operator = action
            m = self.msg or {}
            self.audit.append(AuditEntry(
                ts=time.time(), frame=self.k, action=action, operator=operator,
                kind=m.get("kind", "?"), confidence=float(m.get("confidence", 0)),
                evidence=m.get("evidence", {}), pos=m.get("pos", [])))
            return len(self.audit)


ENGINE: Engine | None = None


@app.on_event("startup")
def _start():
    global ENGINE
    ENGINE = Engine()


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/state")
def state():
    return JSONResponse(ENGINE.state())


class Act(BaseModel):
    action: str
    operator: str = "truc-ca-1"


@app.post("/api/act")
def act(a: Act):
    if a.action not in ("xac_nhan", "bo_qua"):
        return JSONResponse({"error": "hành động không hợp lệ"}, status_code=400)
    n = ENGINE.act(a.action, a.operator)
    return {"ok": True, "audit_entries": n}


@app.post("/api/scenario/{name}")
def scenario(name: str):
    if name not in SCENARIOS:
        return JSONResponse({"error": "không có kịch bản này"}, status_code=404)
    with ENGINE.lock:
        ENGINE.reset(name)
    return {"ok": True, "scenario": name}


@app.get("/api/metrics")
def metrics():
    out = {}
    for f in ("rf_metrics.json", "md_metrics.json", "traj_metrics.json",
              "scenario_results.json"):
        p = ROOT / "data" / f
        if p.exists():
            d = json.load(open(p))
            d.pop("scenarios", None) if f == "scenario_results.json" else None
            out[f.replace(".json", "")] = d
    return out


app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
