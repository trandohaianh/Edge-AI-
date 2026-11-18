"""Ba mạng nơ-ron nhỏ, đủ nhẹ để chạy trên SoC nhúng 10–25 W.

Tất cả đều cố ý nhỏ: tổng dưới 120 nghìn tham số. Trên thiết bị biên, một
mô hình chạy được trong ngân sách 50 ms quan trọng hơn một mô hình lớn hơn
vài phần trăm độ chính xác.
"""
from __future__ import annotations

import torch
import torch.nn as nn


class RFNet(nn.Module):
    """Phân loại tín hiệu vô tuyến từ chuỗi I/Q thô [B,2,2048].

    CNN 1D trên I/Q thô (không qua FFT thủ công): các lớp tích chập đầu học
    lấy bộ lọc băng tần, các lớp sau học dạng burst và nhịp nhảy tần.
    """

    def __init__(self, n_class: int = 4):
        super().__init__()
        ch = [2, 24, 32, 48, 64]
        layers = []
        for i in range(4):
            layers += [
                nn.Conv1d(ch[i], ch[i + 1], 7, padding=3, bias=False),
                nn.BatchNorm1d(ch[i + 1]),
                nn.ReLU(inplace=True),
                nn.MaxPool1d(4),
            ]
        self.features = nn.Sequential(*layers)
        self.head = nn.Sequential(
            nn.AdaptiveAvgPool1d(1), nn.Flatten(),
            nn.Dropout(0.2), nn.Linear(64, n_class))

    def forward(self, x):
        return self.head(self.features(x))


class MicroDopplerNet(nn.Module):
    """Phân loại chữ ký micro-Doppler từ spectrogram [B,1,64,128]."""

    def __init__(self, n_class: int = 4):
        super().__init__()

        def blk(i, o):
            return nn.Sequential(
                nn.Conv2d(i, o, 3, padding=1, bias=False),
                nn.BatchNorm2d(o), nn.ReLU(inplace=True),
                nn.Conv2d(o, o, 3, padding=1, bias=False),
                nn.BatchNorm2d(o), nn.ReLU(inplace=True),
                nn.MaxPool2d(2))

        self.features = nn.Sequential(blk(1, 16), blk(16, 24), blk(24, 32), blk(32, 48))
        self.head = nn.Sequential(
            nn.AdaptiveAvgPool2d(1), nn.Flatten(),
            nn.Dropout(0.2), nn.Linear(48, n_class))

    def forward(self, x):
        return self.head(self.features(x))


class TrajTransformer(nn.Module):
    """Transformer chuỗi thời gian siêu nhẹ dự đoán quỹ đạo khi mất dấu.

    Vào: H bước quá khứ, mỗi bước (x, y, z, vx, vy, vz) đã chuẩn hóa.
    Ra:  K bước tương lai (dx, dy, dz) so với vị trí cuối cùng quan sát được.

    Bộ lọc Kalman mở rộng giả định mô hình chuyển động cố định, nên khi mục
    tiêu lượn vòng mà tín hiệu mất dấu thì EKF trôi theo hướng cũ.
    Transformer học được các khuôn chuyển động cong từ dữ liệu, nên bù được
    chính giai đoạn đó.
    """

    def __init__(self, d_in: int = 6, d_model: int = 48, n_head: int = 4,
                 n_layer: int = 2, horizon: int = 10):
        super().__init__()
        self.horizon = horizon
        self.inp = nn.Linear(d_in, d_model)
        self.pos = nn.Parameter(torch.zeros(1, 64, d_model))
        enc = nn.TransformerEncoderLayer(
            d_model, n_head, dim_feedforward=96, dropout=0.1,
            batch_first=True, norm_first=True)
        self.enc = nn.TransformerEncoder(enc, n_layer)
        self.out = nn.Linear(d_model, horizon * 3)

    def forward(self, x):                      # x: [B,H,6]
        h = self.inp(x) + self.pos[:, :x.shape[1]]
        h = self.enc(h)[:, -1]                 # lấy bước cuối
        return self.out(h).view(-1, self.horizon, 3)


def count_params(m: nn.Module) -> int:
    return sum(p.numel() for p in m.parameters())
