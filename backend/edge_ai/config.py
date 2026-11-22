"""Cấu hình chung cho hệ giám sát đa cảm biến ở thiết bị biên.

Mọi hằng số vật lý đặt ở đây để báo cáo và code dùng chung một nguồn.
"""

from __future__ import annotations

import os
from pathlib import Path

# ------------------------------------------------------------- đường dẫn
# Mọi đường dẫn đều tính từ gốc repo và ghi đè được bằng biến môi trường, để
# cùng một mã chạy được trên laptop, trong Docker và trên Jetson.
ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("EDGE_DATA_DIR", ROOT / "data"))
MODELS_DIR = Path(os.environ.get("EDGE_MODELS_DIR", DATA_DIR / "models"))  # trọng số .pt
RESULTS_DIR = Path(os.environ.get("EDGE_RESULTS_DIR", DATA_DIR / "results"))  # số đo .json
CACHE_DIR = DATA_DIR / "cache"  # tập dữ liệu sinh ra, không commit
STATIC_DIR = Path(os.environ.get("EDGE_STATIC_DIR", ROOT / "frontend"))
LOG_DIR = Path(os.environ.get("EDGE_LOG_DIR", ROOT / "logs"))

# ---------------------------------------------------------------- RF (I/Q)
RF_FS = 2_000_000  # Hz, tần số lấy mẫu băng gốc của bộ thu RF
RF_SEG = 2048  # mẫu/đoạn  -> 1,024 ms một quyết định
RF_CLASSES = ["noise", "wifi", "bluetooth", "drone_ctrl"]

# ------------------------------------------------------------ Radar (X-band)
RADAR_F0 = 10e9  # Hz, radar sóng vi ba băng X
C = 299_792_458.0  # m/s
RADAR_LAMBDA = C / RADAR_F0  # ~3 cm
RADAR_PRF = 20000  # Hz, PRF cao: Doppler ±10 kHz phủ hết vận tốc đầu cánh
RADAR_DWELL = 0.35  # s, đủ dài để thấy 1 nhịp vỗ cánh chim, đủ ngắn để không nhòe blade flash
RADAR_NFFT = 128  # cửa sổ STFT -> 128 bin Doppler, gộp đôi còn 64
MD_SHAPE = (64, 128)  # spectrogram micro-Doppler (tần số x thời gian)
RADAR_CLASSES = ["clutter", "bird", "fixed_wing", "multirotor"]

# ------------------------------------------------------------------- Mục tiêu
# Thông số quay cánh quạt: v_tip = 2*pi*R*f_rot
MULTIROTOR = dict(n_blades=2, n_rotors=4, f_rot=(70.0, 110.0), radius=(0.10, 0.18))
FIXED_WING = dict(n_blades=2, n_rotors=1, f_rot=(80.0, 140.0), radius=(0.12, 0.20))
BIRD = dict(wingbeat=(2.5, 9.0), amp=(0.6, 2.2))

# --------------------------------------------------------------- Cảm biến EO
EO_FOV_DEG = 60.0  # TOÀN góc nhìn; mục tiêu thấy được khi |lệch| < 30°
EO_RANGE_CLEAR = 1200.0  # m, tầm nhận dạng tốt khi trời quang
LIDAR_RANGE = 250.0  # m, LiDAR chỉ thấy gần
RADAR_RANGE = 3000.0
RF_RANGE = 4000.0  # RF thấy xa nhất: bắt được link điều khiển

# ------------------------------------------------------------- Vòng xử lý
FRAME_DT = 0.1  # s, một khung hợp nhất 10 Hz
LATENCY_BUDGET_MS = 50.0  # yêu cầu đề bài

# Lịch chạy hai bộ phát hiện nặng (tính theo khung 10 Hz).
# Radar: một chữ ký micro-Doppler cần 0,35 s chiếu; lấy mỗi 3 khung (0,3 s)
# nên hai cửa sổ liền nhau chồng lên nhau 0,05 s. (Bản cũ viết
# round(0.35/0.1) và ghi chú "0,35 s", nhưng 0.35/0.1 = 3.4999… nên thực tế
# vẫn là 3 — giờ ghi thẳng ra cho khỏi hiểu nhầm.)
MD_EVERY, MD_PHASE = 3, 0
# RF: một đoạn I/Q mỗi 0,5 s. Khi trùng khung với radar thì RF HOÃN sang
# khung kế tiếp (sensors.rf_due), để hai mạng nặng không bao giờ chạy cùng
# một khung. Bản cũ trùng ở 1/15 = 6,7% số khung — chính là những khung chậm
# nhất. (Chỉ lệch pha thì không đủ: 5 và 3 nguyên tố cùng nhau nên lệch pha
# nào cũng vẫn trùng 1/15 số khung.)
RF_EVERY, RF_PHASE = 5, 0

# Đầu quang điện EO/IR đặt trên bệ quay, được radar dẫn hướng.
EO_SLEW_DEG_S = 60.0  # tốc độ quay tối đa của bệ

# --------------------------------------------------------------- Ngưỡng báo
CONFIRM_THRESHOLD = 0.75  # trên ngưỡng này: đề nghị chuyên viên xác nhận
ALERT_THRESHOLD = 0.45  # trên ngưỡng này: hiện lên bảng theo dõi

SEED = 20261008
