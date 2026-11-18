"""Dashboard cho chuyên viên trực ca.

Hệ thống chỉ GIÁM SÁT: nó phát hiện, nhận dạng, bám quỹ đạo, đưa ra điểm
tin cậy kèm bằng chứng từ từng cảm biến, rồi chờ người quyết định. Không có
bất kỳ chức năng chọn mục tiêu tác chiến hay điều khiển khí tài nào, và cũng
không có chỗ nào trong mã nguồn để cắm thêm vào.

Mọi thao tác xác nhận / bỏ qua của chuyên viên đều được ghi vào nhật ký
kèm thời điểm và ảnh chụp bằng chứng tại thời điểm đó — trong RAM để hiện
lên màn hình, và nối thêm vào tệp JSONL trên đĩa để không mất khi khởi động
lại.

Cấu hình qua biến môi trường (không có giá trị bí mật nào nằm trong mã):

  EDGE_API_TOKEN        nếu đặt: mọi lệnh POST phải gửi header X-API-Token
  EDGE_AUDIT_LOG        tệp nhật ký quyết định (mặc định logs/audit.jsonl)
  EDGE_ALLOW_UNTRAINED  =1 cho phép chạy khi thiếu trọng số (chỉ để thử luồng)
"""
from __future__ import annotations

import hmac
import json
import logging
import os
import threading
import time
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

import numpy as np
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from config import FRAME_DT
from evaluate import MD_EVERY, RF_EVERY, lambda_iq
from pipeline import Pipeline, load_models, warmup
from radar_sim import micro_doppler
from scene import Weather, make_scenario, rotate_into_view, sense

ROOT = Path(__file__).resolve().parent.parent
log = logging.getLogger("edge.server")
AUDIT_MEM = 1000          # số bản ghi giữ trong RAM; bản đầy đủ nằm trên đĩa


def _audit_path() -> Path:
    return Path(os.environ.get("EDGE_AUDIT_LOG", ROOT / "logs" / "audit.jsonl"))


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

    def __init__(self, models=None, audit_path: Path | None = None,
                 start: bool = True):
        allow = os.environ.get("EDGE_ALLOW_UNTRAINED") == "1"
        self.models = models or load_models(allow_untrained=allow)
        self.trained = all(getattr(m, "trained", True) for m in self.models)
        warmup(self.models)
        self.lock = threading.Lock()
        self.audit: deque[AuditEntry] = deque(maxlen=AUDIT_MEM)
        self.audit_path = Path(audit_path) if audit_path else _audit_path()
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        self.started_at = time.time()
        self.last_step = 0.0
        self._stop = threading.Event()
        self.name = "clear"
        self.reset("clear")
        self._thread = None
        if start:
            self._thread = threading.Thread(target=self._loop, daemon=True,
                                            name="edge-engine")
            self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

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
        # hẹp, còn mục tiêu thì sinh ra ở phương vị bất kỳ, nên phần lớn lần
        # chạy camera nằm ngoài cuộc — và kịch bản đánh lừa camera trở thành
        # vô nghĩa. Trạm thật cũng quay đầu quang điện về phía có mục tiêu.
        if cfg.get("pattern") == "approach":
            rotate_into_view(self.tg, rng.uniform(-np.deg2rad(25), np.deg2rad(25)))
        self.pipe = Pipeline(self.models)
        self.pipe.ensure_track(0, self.tg.pos[0] + rng.normal(0, 25, 3),
                               self.tg.vel[0] + rng.normal(0, 6, 3))
        self.k = 0
        self.msg = None
        self.trail: list[list[float]] = []
        self.truth_trail: list[list[float]] = []

    def _loop(self):
        while not self._stop.is_set():
            t0 = time.perf_counter()
            try:
                with self.lock:
                    self._step()
            except Exception:                       # một khung hỏng không
                log.exception("lỗi khi xử lý khung")  # được làm chết cả vòng lặp
            self._stop.wait(max(0.0, FRAME_DT - (time.perf_counter() - t0)))

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
        self.last_step = time.time()

    def state(self):
        with self.lock:
            m = dict(self.msg or {})
            m["trail"] = self.trail[-160:]
            m["truth_trail"] = self.truth_trail[-160:]
            lat = self.pipe.latency_report()
            m["latency"] = lat.get("total", {})
            m["stage_latency"] = lat
            m["audit"] = [asdict(a) for a in list(self.audit)[-12:]][::-1]
            m["models_trained"] = self.trained
            return m

    def act(self, action: str, operator: str) -> tuple[int, bool]:
        """Ghi một quyết định của chuyên viên. Trả về (số bản ghi, đã ghi đĩa)."""
        with self.lock:
            if self.msg is None:
                raise HTTPException(409, "chưa có vết bám nào để quyết định")
            tr = self.pipe.tracks[0]
            if tr.operator is not None:
                # Giao diện đã khoá nút sau khi có quyết định; máy chủ phải
                # khoá giống vậy, nếu không hai chuyên viên bấm cùng lúc sẽ
                # ghi hai quyết định trái nhau cho cùng một vết bám.
                raise HTTPException(409, "vết bám này đã có quyết định")
            m = self.msg
            entry = AuditEntry(
                ts=time.time(), frame=int(m.get("k", self.k)), action=action,
                operator=operator, kind=m.get("kind", "?"),
                confidence=float(m.get("confidence", 0)),
                evidence=m.get("evidence", {}), pos=m.get("pos", []))
            tr.operator = action
            self.audit.append(entry)
            return len(self.audit), self._persist(entry)

    def _persist(self, entry: AuditEntry) -> bool:
        """Nối một dòng JSON vào nhật ký trên đĩa.

        Bản cũ chỉ giữ nhật ký trong một list trong RAM: khởi động lại tiến
        trình là mất sạch, trái với cam kết "mọi thao tác đều được ghi nhật
        ký", và list đó lớn lên mãi không giới hạn.
        """
        rec = asdict(entry) | {"scenario": self.name}
        try:
            with open(self.audit_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
            return True
        except OSError:
            log.exception("không ghi được nhật ký %s", self.audit_path)
            return False


ENGINE: Engine | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global ENGINE
    ENGINE = Engine()
    try:
        yield
    finally:
        ENGINE.stop()
        ENGINE = None


app = FastAPI(title="Edge AI Surveillance", lifespan=lifespan)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    resp.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
        "connect-src 'self'; frame-ancestors 'none'")
    if request.url.path.startswith("/api/"):
        resp.headers.setdefault("Cache-Control", "no-store")
    return resp


def engine() -> Engine:
    if ENGINE is None:
        raise HTTPException(503, "hệ thống đang khởi động")
    return ENGINE


def require_token(x_api_token: str | None = Header(default=None)):
    """Bảo vệ các lệnh làm thay đổi trạng thái khi đặt EDGE_API_TOKEN."""
    want = os.environ.get("EDGE_API_TOKEN")
    if not want:
        return
    if not x_api_token or not hmac.compare_digest(x_api_token.encode(), want.encode()):
        raise HTTPException(401, "thiếu hoặc sai mã truy cập (X-API-Token)")


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/health")
def health():
    """Cho bộ giám sát tiến trình (systemd, Docker healthcheck) biết hệ còn sống."""
    e = ENGINE
    if e is None:
        return JSONResponse({"ok": False, "reason": "đang khởi động"}, status_code=503)
    age = time.time() - e.last_step if e.last_step else None
    alive = age is not None and age < 2.0
    body = {"ok": alive and e.trained, "loop_alive": alive,
            "seconds_since_last_frame": None if age is None else round(age, 3),
            "models_trained": e.trained, "scenario": e.name,
            "auth_required": bool(os.environ.get("EDGE_API_TOKEN")),
            "uptime_s": round(time.time() - e.started_at, 1)}
    return JSONResponse(body, status_code=200 if alive else 503)


@app.get("/api/state")
def state(e: Engine = Depends(engine)):
    return JSONResponse(e.state())


class Act(BaseModel):
    action: Literal["xac_nhan", "bo_qua"]
    # Tên ca trực ghi vào nhật ký: giới hạn độ dài và ký tự để không ai nhét
    # được ký tự xuống dòng hay chuỗi dài vô hạn vào tệp nhật ký.
    operator: str = Field(default="truc-ca-1", min_length=1, max_length=32,
                          pattern=r"^[\w.\-]+$")


@app.post("/api/act", dependencies=[Depends(require_token)])
def act(a: Act, e: Engine = Depends(engine)):
    n, persisted = e.act(a.action, a.operator)
    return {"ok": True, "audit_entries": n, "persisted": persisted}


@app.post("/api/scenario/{name}", dependencies=[Depends(require_token)])
def scenario(name: str, e: Engine = Depends(engine)):
    if name not in SCENARIOS:
        return JSONResponse({"error": "không có kịch bản này"}, status_code=404)
    with e.lock:
        e.reset(name)
    return {"ok": True, "scenario": name}


@app.get("/api/metrics")
def metrics():
    # Phải ghi rõ encoding: các tệp JSON có tiếng Việt, còn open() mặc định
    # trên Windows là cp1252 — bản cũ trả lỗi 500 ở đây khi chạy trên Windows.
    out = {}
    for f in ("rf_metrics.json", "md_metrics.json", "traj_metrics.json",
              "scenario_results.json", "adversarial.json"):
        p = ROOT / "data" / f
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8"))
            if f == "scenario_results.json":
                d.pop("scenarios", None)
            out[f.replace(".json", "")] = d
    return out


app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
