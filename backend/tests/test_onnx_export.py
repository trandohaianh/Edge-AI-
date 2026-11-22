"""Tầng STFT số thực dùng khi xuất ONNX phải cho đúng kết quả của tầng gốc.

Chỉ cần torch (không cần onnx): nếu sai ở đây thì bản ONNX chạy trên Jetson
sẽ nhận dạng RF khác với bản đã đánh giá trong báo cáo.
"""

import torch

from edge_ai.experiments.export_onnx import RFForExport, STFTFrontReal
from edge_ai.ml.rf_stft import RFNetSTFT, STFTFront


def test_stft_so_thuc_bang_stft_so_phuc():
    torch.manual_seed(0)
    src = STFTFront()
    x = torch.randn(3, 2, 2048)
    a, b = src(x), STFTFrontReal(src)(x)
    assert a.shape == b.shape
    assert torch.allclose(a, b, atol=1e-4)


def test_mang_rf_ban_xuat_cho_cung_dau_ra():
    torch.manual_seed(1)
    rf = RFNetSTFT(4).eval()
    x = torch.randn(4, 2, 2048)
    with torch.no_grad():
        assert torch.allclose(rf(x), RFForExport(rf).eval()(x), atol=1e-4)
