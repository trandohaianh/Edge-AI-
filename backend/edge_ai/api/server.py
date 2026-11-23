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

  EDGE_API_TOKEN        nếu đặt: mọi lệnh POST phải gửi header X-API-Token;
                        nếu không đặt: lệnh POST chỉ nhận từ chính máy chủ
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
from urllib.parse import urlsplit

import numpy as np
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from edge_ai.api import audit_log
from edge_ai.api.auth import FailureLimiter
from edge_ai.config import FRAME_DT, LOG_DIR, RESULTS_DIR, STATIC_DIR
from edge_ai.sim.scenarios import build_targets, fan_targets
from edge_ai.sim.scene import Weather, make_scenario, sense
from edge_ai.sim.sensors import EOTurret, RawProvider, attach_raw, sense_all
from edge_ai.tracking.mtt import MultiTracker
from edge_ai.tracking.pipeline import Pipeline, load_models, warmup

log = logging.getLogger("edge.server")
AUDIT_MEM = 1000  # số bản ghi giữ trong RAM; bản đầy đủ nằm trên đĩa


def _audit_path() -> Path:
    return Path(os.environ.get("EDGE_AUDIT_LOG", LOG_DIR / "audit.jsonl"))


# "start_m" ép mục tiêu bắt đầu ở cự ly nào. Cần cho các kịch bản liên quan
# tới camera: EO/IR chỉ nhận dạng được trong khoảng 1,2 km khi trời quang, nên
# nếu để mục tiêu sinh ngẫu nhiên ở 2,6 km thì camera không bao giờ vào cuộc
# và kịch bản "đánh lừa camera" chẳng chứng minh được gì.
SCENARIOS = {
    "clear": dict(
        label="Trời quang · drone đa cánh quạt",
        kind="multirotor",
        w=Weather(),
        patch=False,
        drop=None,
        pattern="approach",
        start_m=900,
    ),
    "fog_night": dict(
        label="Đêm + sương mù dày",
        kind="multirotor",
        w=Weather(fog=0.85, night=True),
        patch=False,
        drop=None,
        pattern="approach",
        start_m=900,
    ),
    "jamming": dict(
        label="Bị nhiễu dải RF",
        kind="multirotor",
        w=Weather(jamming=0.9),
        patch=False,
        drop=None,
        pattern="approach",
        start_m=900,
    ),
    "bird": dict(
        label="Chim — phải loại, không báo động",
        kind="bird",
        w=Weather(),
        patch=False,
        drop=None,
        pattern="approach",
        start_m=800,
    ),
    "patch": dict(
        label="Dán nhãn ngụy trang đánh lừa camera",
        kind="multirotor",
        w=Weather(),
        patch=True,
        drop=None,
        pattern="approach",
        start_m=900,
    ),
    "dropout": dict(
        label="Mất dấu 4 giây giữa chừng",
        kind="multirotor",
        w=Weather(),
        patch=False,
        drop=(110, 150),
        pattern="approach",
        start_m=1000,
    ),
    # Nhiều mục tiêu: bộ bám không được biết trước có bao nhiêu mục tiêu,
    # radar trả về số đo trộn lẫn cùng báo động giả (mtt.py).
    "swarm": dict(
        label="Nhiều mục tiêu · 3 drone + 1 chim + báo động giả",
        targets=fan_targets(["multirotor", "fixed_wing", "multirotor", "bird"], spread=60.0),
        w=Weather(),
        clutter=1.5,
    ),
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
    tid: int = 0


class Engine:
    """Chạy một kịch bản theo thời gian thực, 10 khung/giây."""

    def __init__(self, models=None, audit_path: Path | None = None, start: bool = True):
        allow = os.environ.get("EDGE_ALLOW_UNTRAINED") == "1"
        self.models = models or load_models(allow_untrained=allow)
        self.trained = all(getattr(m, "trained", True) for m in self.models)
        warmup(self.models)
        self.lock = threading.Lock()
        self.audit: deque[AuditEntry] = deque(maxlen=AUDIT_MEM)
        self.audit_path = Path(audit_path) if audit_path else _audit_path()
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        # Nhật ký chia theo tháng: audit_path là tên gốc, tệp thật là
        # <tên>-YYYY-MM.jsonl cùng thư mục (xem audit_log.AuditStore).
        self.audit_store = audit_log.AuditStore(self.audit_path)
        # Nhật ký hỏng tới mức không biết nối chuỗi vào đâu (vd. pruned.json
        # hỏng): dịch vụ GIÁM SÁT vẫn chạy, nhưng từ chối ghi quyết định với
        # lỗi 503 nói rõ nguyên nhân, thay vì chết lúc khởi động hoặc ghi
        # tiếp vào một chuỗi sai.
        self.audit_error: str | None = None
        try:
            self._last_hash = self.audit_store.last_hash()
        except audit_log.AuditLogError as e:
            log.error("%s", e)
            self.audit_error = str(e)
            self._last_hash = ""
        self.started_at = time.time()
        self.last_step = 0.0
        self._stop = threading.Event()
        self.name = "clear"
        self.reset("clear")
        self._thread = None
        if start:
            self._thread = threading.Thread(target=self._loop, daemon=True, name="edge-engine")
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
        self.k = 0
        self.msg = None
        self.trails: dict[int, deque] = {}
        self.truth_trails: dict[int, deque] = {}
        self.multi = "targets" in cfg
        if self.multi:
            self.tgs = build_targets(cfg["targets"], self.n, rng)
            self.mt = MultiTracker(self.models, raw_provider=RawProvider(self.tgs, self.w, rng))
            self.mt.turret = EOTurret(0.0)
            self.pipe = self.mt.pipe
            return
        self.tg = make_scenario(
            self.n,
            rng,
            self.w,
            kinds=[cfg["kind"]],
            patch_ids={0} if cfg["patch"] else set(),
            patterns=[cfg.get("pattern")] if cfg.get("pattern") else None,
            r0=cfg.get("start_m"),
        )[0]
        self.tgs = [self.tg]
        self.pipe = Pipeline(self.models)
        tr = self.pipe.ensure_track(
            0, self.tg.pos[0] + rng.normal(0, 25, 3), self.tg.vel[0] + rng.normal(0, 6, 3)
        )
        # Camera trên bệ quay, được radar dẫn tới phương vị của vết bám.
        self.turret = EOTurret(float(np.arctan2(tr.ekf.pos[1], tr.ekf.pos[0])))

    @property
    def tracks(self) -> dict:
        return self.mt.tracks if self.multi else self.pipe.tracks

    def _loop(self):
        while not self._stop.is_set():
            t0 = time.perf_counter()
            try:
                with self.lock:
                    self._step()
            except Exception:  # một khung hỏng không
                log.exception("lỗi khi xử lý khung")  # được làm chết cả vòng lặp
            self._stop.wait(max(0.0, FRAME_DT - (time.perf_counter() - t0)))

    def _step(self):
        if self.k >= self.n:
            self.reset(self.name)
            return
        k = self.k
        drop = self.cfg.get("drop")
        blind = drop is not None and drop[0] <= k < drop[1]
        if self.multi:
            dets = sense_all(
                self.tgs,
                k,
                self.w,
                self.rng,
                eo_az=self.mt.turret.az,
                clutter_rate=self.cfg.get("clutter", 0.0),
                raw=False,
            )
            msgs = self.mt.step(dets, self.w, k)
            eo_az = self.mt.point_camera(k)
            self.n_raw_dets = len(dets)
        else:
            dets = [] if blind else sense(self.tg, k, self.w, self.rng, eo_az=self.turret.az)
            attach_raw(dets, self.tg, k, self.w, self.rng)
            m0 = self.pipe.step(0, dets, self.w, k)
            m0["operator"] = self.pipe.tracks[0].operator
            m0["confirmed"] = True
            eo_az = self.turret.point(float(np.arctan2(m0["pos"][1], m0["pos"][0])))
            msgs = [m0]
        for m in msgs:
            self.trails.setdefault(m["tid"], deque(maxlen=160)).append(m["pos"])
        for t in self.tgs:
            self.truth_trails.setdefault(t.tid, deque(maxlen=160)).append(t.pos[k].tolist())
        live = {m["tid"] for m in msgs}
        for tid in list(self.trails):
            if tid not in live and tid not in self.tracks:
                del self.trails[tid]
        # Vết hiển thị chính: vết đang chờ người quyết định trước, rồi tới vết
        # tin cậy cao nhất mà không phải chim.
        order = sorted(
            msgs, key=lambda m: (not m["needs_operator"], m["kind"] == "bird", -m["confidence"])
        )
        main = dict(order[0]) if order else {"tid": None, "k": k}
        main.update(
            {
                "eo_az": eo_az,
                "weather": self.w.label(),
                "blind": blind,
                "scenario": self.name,
                "scenario_label": self.cfg["label"],
                "multi": self.multi,
                "n_targets_truth": len(self.tgs),
                "tracks": [self._compact(m) for m in order],
            }
        )
        if not self.multi:
            main["truth"] = self.tg.pos[k].tolist()
            main["truth_kind"] = self.tg.kind
        else:
            main["tentative"] = sum(not t.confirmed for t in self.mt.tracks.values())
        self.msgs = {m["tid"]: m for m in msgs}
        self.msg = main
        self.k += 1
        self.last_step = time.time()

    @staticmethod
    def _compact(m: dict) -> dict:
        keys = (
            "tid",
            "pos",
            "vel",
            "sigma",
            "kind",
            "kind_p",
            "probs",
            "confidence",
            "status",
            "sensors",
            "evidence",
            "conflict",
            "needs_operator",
            "deception_suspected",
            "operator",
            "predicted",
        )
        return {k: m.get(k) for k in keys}

    def state(self):
        with self.lock:
            m = dict(self.msg or {})
            m["trails"] = {str(t): list(v) for t, v in self.trails.items()}
            m["truth_trails"] = [list(v) for v in self.truth_trails.values()]
            # tương thích bản giao diện một mục tiêu
            m["trail"] = list(self.trails.get(m.get("tid"), []))
            m["truth_trail"] = m["truth_trails"][0] if m["truth_trails"] else []
            lat = self.pipe.latency_report()
            if self.multi and len(self.mt.timing["total"]):
                a = np.asarray(self.mt.timing["total"])
                lat["total"] = {
                    "mean_ms": round(float(a.mean()), 3),
                    "p99_ms": round(float(np.percentile(a, 99)), 3),
                    "max_ms": round(float(a.max()), 3),
                    "n": len(a),
                }
            m["latency"] = lat.get("total", {})
            m["stage_latency"] = lat
            m["audit"] = [asdict(a) for a in list(self.audit)[-12:]][::-1]
            m["models_trained"] = self.trained
            m["dropped_nonfinite"] = dict(self.pipe.dropped)
            return m

    def act(self, action: str, operator: str, tid: int | None = None) -> tuple[int, bool]:
        """Ghi một quyết định của chuyên viên. Trả về (số bản ghi, đã ghi đĩa).

        Vết bám chỉ bị khoá SAU KHI quyết định đã ghi bền xuống đĩa. Ghi
        không được thì vết KHÔNG bị khoá, không có gì được thêm vào nhật ký
        trong RAM, và trả 503 để người trực biết mà thử lại. Bản cũ khoá vết
        trước rồi mới ghi: ghi hỏng thì quyết định mất mà vết vẫn bị khoá,
        không ai ghi lại được nữa."""
        with self.lock:
            if self.msg is None or self.msg.get("tid") is None:
                raise HTTPException(409, "chưa có vết bám nào để quyết định")
            tid = self.msg["tid"] if tid is None else tid
            tr = self.tracks.get(tid)
            m = getattr(self, "msgs", {}).get(tid)
            if tr is None or m is None or not tr.confirmed:
                raise HTTPException(404, "không có vết bám này")
            if tr.operator is not None:
                # Giao diện đã khoá nút sau khi có quyết định; máy chủ phải
                # khoá giống vậy, nếu không hai chuyên viên bấm cùng lúc sẽ
                # ghi hai quyết định trái nhau cho cùng một vết bám.
                raise HTTPException(409, "vết bám này đã có quyết định")
            entry = AuditEntry(
                ts=time.time(),
                frame=int(m.get("k", self.k)),
                action=action,
                operator=operator,
                kind=m.get("kind", "?"),
                confidence=float(m.get("confidence", 0)),
                evidence=m.get("evidence", {}),
                pos=m.get("pos", []),
                tid=int(tid),
            )
            if not self._persist(entry):
                raise HTTPException(
                    503,
                    "không ghi được quyết định xuống nhật ký, vết bám CHƯA bị khoá "
                    "— thử lại; nếu vẫn lỗi, báo kỹ thuật",
                )
            tr.operator = action
            self.audit.append(entry)
            return len(self.audit), True

    def _persist(self, entry: AuditEntry) -> bool:
        """Nối một dòng JSON vào nhật ký trên đĩa.

        Bản cũ chỉ giữ nhật ký trong một list trong RAM: khởi động lại tiến
        trình là mất sạch, trái với cam kết "mọi thao tác đều được ghi nhật
        ký", và list đó lớn lên mãi không giới hạn.
        """
        if self.audit_error is not None:
            log.error("từ chối ghi nhật ký: %s", self.audit_error)
            return False
        try:
            rec = self.audit_store.append(
                self._last_hash, asdict(entry) | {"scenario": self.name}, ts=entry.ts
            )
            self._last_hash = rec["hash"]
            return True
        except (OSError, ValueError, TypeError):
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
        "default-src 'self'; script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
        "connect-src 'self'; frame-ancestors 'none'",
    )
    if request.url.path.startswith("/api/"):
        resp.headers.setdefault("Cache-Control", "no-store")
    elif request.url.path == "/" or request.url.path.startswith("/static/"):
        # Trang dashboard và app.js phải luôn hỏi lại máy chủ: nếu không, sau khi cập
        # nhật, trình duyệt có thể dùng bản giao diện cũ đã lưu đệm (lỗi tìm
        # thấy khi kiểm thử đầu-cuối, bước 8).
        resp.headers.setdefault("Cache-Control", "no-cache")
    return resp


def engine() -> Engine:
    if ENGINE is None:
        raise HTTPException(503, "hệ thống đang khởi động")
    return ENGINE


LOOPBACK = {"127.0.0.1", "::1", "localhost"}
TOKEN_LIMITER = FailureLimiter()


def require_token(request: Request, x_api_token: str | None = Header(default=None)):
    """Bảo vệ các lệnh làm thay đổi trạng thái.

    * Có EDGE_API_TOKEN: mọi lệnh POST phải gửi đúng mã.
    * Không có: chỉ chấp nhận lệnh từ chính máy đó (loopback). Demo trên
      laptop vẫn bấm được ngay, nhưng đem lên trạm mà quên đặt mã thì máy
      khác trong mạng KHÔNG thể ghi quyết định hay đổi kịch bản.
    """
    # Chống CSRF: trình duyệt luôn gửi Origin với POST từ trang web. Trang
    # khác (vd. một trang lạ mở trên chính máy trạm) gửi lệnh tới dashboard
    # thì Origin khác Host: từ chối. Công cụ dòng lệnh không gửi Origin.
    origin = request.headers.get("origin")
    if origin and urlsplit(origin).netloc != request.headers.get("host", ""):
        raise HTTPException(403, "lệnh đến từ trang web khác, bị từ chối")
    want = os.environ.get("EDGE_API_TOKEN")
    host = request.client.host if request.client else ""
    if not want:
        if host not in LOOPBACK:
            raise HTTPException(403, "điều khiển từ máy khác cần đặt EDGE_API_TOKEN trên máy chủ")
        return
    # Chống dò mã: bị khoá thì từ chối cả mã đúng (auth.py).
    wait = TOKEN_LIMITER.retry_after(host)
    if wait:
        raise HTTPException(
            429,
            f"sai mã quá nhiều lần, thử lại sau {wait} giây",
            headers={"Retry-After": str(wait)},
        )
    if not x_api_token or not hmac.compare_digest(x_api_token.encode(), want.encode()):
        # Không gửi mã (lần đầu mở trang) không tính là sai; gửi mã sai mới tính.
        if x_api_token and TOKEN_LIMITER.failure(host):
            log.warning("khoá %s vì sai mã truy cập nhiều lần", host)
        raise HTTPException(401, "thiếu hoặc sai mã truy cập (X-API-Token)")
    TOKEN_LIMITER.success(host)


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health():
    """Cho bộ giám sát tiến trình (systemd, Docker healthcheck) biết hệ còn sống."""
    e = ENGINE
    if e is None:
        return JSONResponse({"ok": False, "reason": "đang khởi động"}, status_code=503)
    age = time.time() - e.last_step if e.last_step else None
    alive = age is not None and age < 2.0
    # Nhật ký kiểm toán hỏng: vòng giám sát vẫn chạy, nhưng quyết định của người trực
    # không ghi được. Trả 503 để Docker/systemd đánh dấu "unhealthy" và kỹ thuật viên
    # được báo, thay vì im lặng 200.
    audit_ok = e.audit_error is None
    body = {
        "ok": alive and e.trained and audit_ok,
        "loop_alive": alive,
        "seconds_since_last_frame": None if age is None else round(age, 3),
        "models_trained": e.trained,
        "scenario": e.name,
        "auth_required": bool(os.environ.get("EDGE_API_TOKEN")),
        "audit_chain_head": e._last_hash[:16],
        "audit_ok": audit_ok,
        "uptime_s": round(time.time() - e.started_at, 1),
    }
    if not audit_ok:
        body["reason"] = "nhật ký kiểm toán hỏng: không ghi được quyết định (xem log dịch vụ)"
    return JSONResponse(body, status_code=200 if alive and audit_ok else 503)


@app.get("/api/state")
def state(e: Engine = Depends(engine)):
    return JSONResponse(e.state())


class Act(BaseModel):
    action: Literal["xac_nhan", "bo_qua"]
    tid: int | None = Field(default=None, ge=0, le=10_000_000)
    # Tên ca trực ghi vào nhật ký: giới hạn độ dài và ký tự để không ai nhét
    # được ký tự xuống dòng hay chuỗi dài vô hạn vào tệp nhật ký.
    operator: str = Field(default="truc-ca-1", min_length=1, max_length=32, pattern=r"^[\w.\-]+$")


@app.post("/api/act", dependencies=[Depends(require_token)])
def act(a: Act, e: Engine = Depends(engine)):
    n, persisted = e.act(a.action, a.operator, a.tid)
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
    for f in (
        "rf_metrics.json",
        "md_metrics.json",
        "traj_metrics.json",
        "scenario_results.json",
        "adversarial.json",
    ):
        p = RESULTS_DIR / f
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8"))
            if f == "scenario_results.json":
                d.pop("scenarios", None)
            out[f.replace(".json", "")] = d
    return out


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
