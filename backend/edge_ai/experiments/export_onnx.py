"""Xuất ba mạng sang ONNX và kiểm tra bản ONNX cho cùng kết quả (MAINTENANCE P2).

Đây là hướng dự phòng cho Jetson: nếu PyTorch trên Jetson chậm, chạy bản
ONNX bằng ONNX Runtime, hoặc đưa tiếp vào TensorRT FP16 (``trtexec --onnx=…
--fp16``, việc này phải làm trên chính Jetson). Script này KHÔNG thay đổi cách
dashboard chạy; nó chỉ sinh tệp ``.onnx`` và đo trên máy hiện tại.

    python -m edge_ai.experiments.export_onnx              # trong backend/
    # cần: pip install onnx onnxruntime onnxscript

Mạng RF có tầng STFT số phức (``torch.stft``), toán tử mà ONNX không xuất
thẳng được. Khi xuất, tầng đó được thay bằng bản tương đương chỉ dùng số
thực (nhân ma trận DFT); script so lại với mô hình gốc nên mọi sai khác đều
lộ ra ở cột ``max_abs_diff``.

Kết quả: ``data/results/onnx_export.json``; tệp ``.onnx`` ở
``data/models/onnx/`` (không commit, sinh lại được).
"""

from __future__ import annotations

import argparse
import json
import platform
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

from edge_ai.config import MODELS_DIR, RESULTS_DIR
from edge_ai.io_utils import utf8_stdio
from edge_ai.ml.rf_stft import STFTFront
from edge_ai.tracking.pipeline import HIST, load_models

OUT_DIR = MODELS_DIR / "onnx"
TOL = 1e-3  # sai khác tối đa cho phép trên đầu ra (logit / độ dời quỹ đạo)


class STFTFrontReal(nn.Module):
    """Bản số thực của ``STFTFront``: cùng công thức, xuất ONNX được.

    STFT của z = I + jQ với cửa sổ w: S[f,t] = Σ_n w[n] z[t·hop+n] e^{-j2πfn/N}.
    Tách phần thực/ảo: Re = Σ w(I·cos + Q·sin), Im = Σ w(Q·cos − I·sin).
    Hàng của ma trận DFT được xếp sẵn theo thứ tự fftshift (0 Hz vào giữa).
    """

    def __init__(self, src: STFTFront):
        super().__init__()
        n = src.nfft
        self.nfft, self.hop = n, src.hop
        f = torch.roll(torch.arange(n), n // 2)  # thứ tự tần số sau fftshift
        ang = 2 * np.pi * f[:, None].double() * torch.arange(n)[None].double() / n
        w = src.win.double()[None]
        self.register_buffer("cw", (torch.cos(ang) * w).float().T.contiguous())  # [N, F]
        self.register_buffer("sw", (torch.sin(ang) * w).float().T.contiguous())

    def forward(self, x):
        fi = x[:, 0].unfold(-1, self.nfft, self.hop)  # [B, T, N]
        fq = x[:, 1].unfold(-1, self.nfft, self.hop)
        re = fi @ self.cw + fq @ self.sw
        im = fq @ self.cw - fi @ self.sw
        P = (re * re + im * im).transpose(1, 2)  # [B, F, T]
        P = 10 * torch.log10(P + 1e-8)
        P = P - P.amax(dim=(1, 2), keepdim=True)
        P = (P.clamp(min=-50) / 50.0) + 1.0
        return P.unsqueeze(1)


class RFForExport(nn.Module):
    def __init__(self, rf: nn.Module):
        super().__init__()
        self.front = STFTFrontReal(rf.front)
        self.features, self.head = rf.features, rf.head

    def forward(self, x):
        return self.head(self.features(self.front(x)))


def _export(m: nn.Module, example: torch.Tensor, path: Path) -> str:
    """Thử bộ xuất mới (dynamo) trước, không được thì dùng bộ xuất cũ."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        torch.onnx.export(
            m,
            (example,),
            str(path),
            dynamo=True,
            input_names=["x"],
            output_names=["y"],
            dynamic_shapes={"x": {0: torch.export.Dim("batch", min=1, max=16)}},
        )
        return "dynamo"
    except Exception:  # noqa: BLE001 - ghi lại rồi thử cách khác
        torch.onnx.export(
            m,
            (example,),
            str(path),
            dynamo=False,
            opset_version=17,
            input_names=["x"],
            output_names=["y"],
            dynamic_axes={"x": {0: "batch"}, "y": {0: "batch"}},
        )
        return "torchscript"


def _bench(fn, n: int) -> dict:
    for _ in range(10):
        fn()
    ts = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        ts.append((time.perf_counter() - t0) * 1e3)
    a = np.asarray(ts)
    return {
        "p50_ms": round(float(np.percentile(a, 50)), 3),
        "p99_ms": round(float(np.percentile(a, 99)), 3),
    }


def main(threads: int = 2, n: int = 200, out: Path | None = RESULTS_DIR / "onnx_export.json"):
    import onnx
    import onnxruntime as ort

    torch.set_num_threads(threads)
    rf, md, tj = load_models()
    g = torch.Generator().manual_seed(0)
    cases = (
        # tên, mô hình gốc (tham chiếu), mô hình đem xuất, hàm sinh đầu vào
        ("rf_stft_cnn", rf, RFForExport(rf).eval(), lambda b: torch.randn(b, 2, 2048, generator=g)),
        ("micro_doppler_cnn", md, md, lambda b: torch.rand(b, 1, 64, 128, generator=g)),
        ("traj_transformer", tj, tj, lambda b: torch.randn(b, HIST, 6, generator=g)),
    )
    so = ort.SessionOptions()
    so.intra_op_num_threads = threads
    res = {
        "host": {
            "machine": platform.machine(),
            "system": platform.system(),
            "torch": torch.__version__,
            "onnx": onnx.__version__,
            "onnxruntime": ort.__version__,
            "threads": threads,
        },
        "tolerance": TOL,
        "models": {},
    }
    for name, ref, exp_m, mk in cases:
        path = OUT_DIR / f"{name}.onnx"
        with torch.no_grad():
            # batch 2: torch.export coi kích thước 1 là hằng, sẽ không cho batch khác
            how = _export(exp_m, mk(2), path)
        # Bộ xuất mới để trọng số ở tệp .onnx.data riêng: gộp lại thành MỘT tệp
        # cho dễ chép sang Jetson (trtexec --onnx=...), mô hình nhỏ nên không lo
        # giới hạn 2 GB của protobuf.
        model = onnx.load(str(path))
        onnx.save(model, str(path), save_as_external_data=False)
        Path(str(path) + ".data").unlink(missing_ok=True)
        onnx.checker.check_model(onnx.load(str(path)))
        sess = ort.InferenceSession(str(path), so, providers=["CPUExecutionProvider"])
        diffs = []
        with torch.no_grad():
            for b in (1, 2, 4):
                for _ in range(5):
                    x = mk(b)
                    y_ref = ref(x).numpy()
                    y_onx = sess.run(None, {"x": x.numpy()})[0]
                    diffs.append(float(np.abs(y_ref - y_onx).max()))
                    if y_ref.ndim == 2:  # bộ phân loại: phải cùng lớp thắng
                        assert (y_ref.argmax(1) == y_onx.argmax(1)).all(), name
        x1 = mk(1)
        with torch.no_grad():
            t_torch = _bench(lambda m=ref, x=x1: m(x), n)
        xn = x1.numpy()
        t_ort = _bench(lambda s=sess, x=xn: s.run(None, {"x": x}), n)
        res["models"][name] = {
            "exporter": how,
            "file_kb": round(path.stat().st_size / 1024, 1),
            "max_abs_diff": float(f"{max(diffs):.2e}"),
            "same_output": max(diffs) < TOL,
            "torch_batch1": t_torch,
            "onnxruntime_batch1": t_ort,
        }
    res["passed"] = all(v["same_output"] for v in res["models"].values())
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
        )
    return res


if __name__ == "__main__":
    utf8_stdio()
    ap = argparse.ArgumentParser(description="Xuất ONNX và kiểm tra cùng kết quả")
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--no-save", action="store_true")
    a = ap.parse_args()
    r = main(a.threads, a.n, None if a.no_save else RESULTS_DIR / "onnx_export.json")
    for k, v in r["models"].items():
        print(
            f"{k:18s} {v['exporter']:11s} {v['file_kb']:7.1f} KB  sai khác {v['max_abs_diff']:.1e}"
            f"  torch p50 {v['torch_batch1']['p50_ms']} ms · ORT p50 "
            f"{v['onnxruntime_batch1']['p50_ms']} ms"
        )
    print("KẾT LUẬN:", "bản ONNX cho cùng kết quả" if r["passed"] else "CÓ SAI KHÁC")
    raise SystemExit(0 if r["passed"] else 1)
