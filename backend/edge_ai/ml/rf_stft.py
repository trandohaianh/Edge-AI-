"""Bộ phân loại RF phiên bản 2: tầng đầu là STFT cố định, sau đó là CNN 2D.

Vì sao đổi: phiên bản 1 cho CNN 1D ăn thẳng I/Q thô. Nó phải tự học ra phép
biến đổi Fourier từ dữ liệu, trong khi dấu hiệu phân biệt các lớp (bề rộng
phổ, nhịp nhảy tần, chu kỳ burst) vốn là cấu trúc trên mặt phẳng thời gian –
tần số. Đặt sẵn một tầng STFT không có tham số học chính là đưa đúng kiến
thức vật lý vào mô hình, thay vì bắt mô hình học lại.

Tầng STFT viết bằng toán tử torch nên vẫn nằm trong đồ thị tính toán và
xuất ONNX được như mọi lớp khác.
"""
from __future__ import annotations

import torch
import torch.nn as nn

NFFT, HOP = 128, 32


class STFTFront(nn.Module):
    """I/Q [B,2,N] -> log-công suất thời gian–tần số [B,1,NFFT,T]."""

    def __init__(self, nfft: int = NFFT, hop: int = HOP):
        super().__init__()
        self.nfft, self.hop = nfft, hop
        self.register_buffer("win", torch.hann_window(nfft))

    def forward(self, x):
        z = torch.complex(x[:, 0], x[:, 1])
        S = torch.stft(z, n_fft=self.nfft, hop_length=self.hop,
                       window=self.win, center=False, return_complex=True)
        P = S.abs() ** 2
        P = torch.fft.fftshift(P, dim=1)           # 0 Hz vào giữa
        P = 10 * torch.log10(P + 1e-8)
        P = P - P.amax(dim=(1, 2), keepdim=True)
        P = (P.clamp(min=-50) / 50.0) + 1.0
        return P.unsqueeze(1)


class RFNetSTFT(nn.Module):
    def __init__(self, n_class: int = 4):
        super().__init__()
        self.front = STFTFront()

        def blk(i, o, pool=(2, 2)):
            return nn.Sequential(
                nn.Conv2d(i, o, 3, padding=1, bias=False),
                nn.BatchNorm2d(o), nn.ReLU(inplace=True),
                nn.Conv2d(o, o, 3, padding=1, bias=False),
                nn.BatchNorm2d(o), nn.ReLU(inplace=True),
                nn.MaxPool2d(pool))

        self.features = nn.Sequential(blk(1, 16), blk(16, 24), blk(24, 32), blk(32, 48))
        self.head = nn.Sequential(nn.AdaptiveAvgPool2d(1), nn.Flatten(),
                                  nn.Dropout(0.2), nn.Linear(48, n_class))

    def forward(self, x):
        return self.head(self.features(self.front(x)))
