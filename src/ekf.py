"""Bộ lọc Kalman mở rộng cho bám quỹ đạo 3D với nhiều loại cảm biến.

Trạng thái: [x, y, z, vx, vy, vz] trong hệ ENU, đơn vị mét và m/s.
Mô hình chuyển động: vận tốc gần như không đổi, gia tốc coi là nhiễu trắng
(nhiễu quá trình). Mỗi cảm biến có hàm đo h(x) và Jacobian riêng, nên cùng
một bộ lọc nhận được số đo rất khác nhau: cự ly + góc từ radar, chỉ góc từ
camera, chỉ phương vị từ RF, tọa độ đầy đủ từ LiDAR.

Cập nhật từng cảm biến một (sequential update) thay vì ghép thành một vector
đo: cảm biến nào có số đo ở khung đó thì dùng, thiếu thì bỏ qua — đúng với
thực tế là cảm biến rơi rụng không đồng bộ.
"""
from __future__ import annotations

import numpy as np


def _wrap(a: float) -> float:
    return (a + np.pi) % (2 * np.pi) - np.pi


class EKF:
    def __init__(self, p0: np.ndarray, v0: np.ndarray, sigma_a: float = 6.0,
                 p_var: float = 400.0, v_var: float = 100.0):
        self.x = np.concatenate([p0, v0]).astype(float)
        self.P = np.diag([p_var] * 3 + [v_var] * 3).astype(float)
        self.sigma_a = sigma_a      # m/s^2, mức cơ động giả định của mục tiêu

    # ------------------------------------------------------------- dự đoán
    def predict(self, dt: float):
        F = np.eye(6)
        F[:3, 3:] = np.eye(3) * dt
        q = self.sigma_a ** 2
        dt2, dt3, dt4 = dt * dt, dt ** 3, dt ** 4
        Q = np.zeros((6, 6))
        Q[:3, :3] = np.eye(3) * dt4 / 4 * q
        Q[:3, 3:] = np.eye(3) * dt3 / 2 * q
        Q[3:, :3] = np.eye(3) * dt3 / 2 * q
        Q[3:, 3:] = np.eye(3) * dt2 * q
        self.x = F @ self.x
        self.P = F @ self.P @ F.T + Q

    # ----------------------------------------------------- hàm đo & Jacobian
    @staticmethod
    def h(sensor: str, x: np.ndarray) -> np.ndarray:
        p, v = x[:3], x[3:]
        r = np.linalg.norm(p)
        r = max(r, 1e-6)
        az = np.arctan2(p[1], p[0])
        el = np.arcsin(np.clip(p[2] / r, -1, 1))
        if sensor == "radar":
            return np.array([r, az, el, float(np.dot(v, p) / r)])
        if sensor == "eo":
            return np.array([az, el])
        if sensor == "rf":
            return np.array([az])
        if sensor == "lidar":
            return p.copy()
        raise ValueError(sensor)

    @staticmethod
    def H(sensor: str, x: np.ndarray) -> np.ndarray:
        """Jacobian tính bằng sai phân trung tâm.

        Sai phân số ở đây rẻ (ma trận 6 cột) và loại bỏ hẳn một nguồn lỗi
        khó tìm là đạo hàm giải tích viết sai.
        """
        n = {"radar": 4, "eo": 2, "rf": 1, "lidar": 3}[sensor]
        J = np.zeros((n, 6))
        eps = 1e-4
        for i in range(6):
            dx = np.zeros(6)
            dx[i] = eps
            hp = EKF.h(sensor, x + dx)
            hm = EKF.h(sensor, x - dx)
            d = hp - hm
            if sensor in ("radar", "eo", "rf"):
                idx = {"radar": [1, 2], "eo": [0, 1], "rf": [0]}[sensor]
                for j in idx:
                    d[j] = _wrap(d[j])
            J[:, i] = d / (2 * eps)
        return J

    # ----------------------------------------------------------- cập nhật
    def update(self, sensor: str, z: np.ndarray, R: np.ndarray,
               gate: float = 16.0) -> bool:
        """Trả về False nếu số đo bị cổng thống kê loại (nghi là nhiễu)."""
        hx = self.h(sensor, self.x)
        y = z - hx
        if sensor == "radar":
            y[1] = _wrap(y[1])
            y[2] = _wrap(y[2])
        elif sensor == "eo":
            y[0] = _wrap(y[0])
            y[1] = _wrap(y[1])
        elif sensor == "rf":
            y[0] = _wrap(y[0])
        H = self.H(sensor, self.x)
        S = H @ self.P @ H.T + R
        try:
            Sinv = np.linalg.inv(S)
        except np.linalg.LinAlgError:
            return False
        d2 = float(y @ Sinv @ y)
        if d2 > gate * len(z):
            return False
        K = self.P @ H.T @ Sinv
        self.x = self.x + K @ y
        A = np.eye(6) - K @ H
        self.P = A @ self.P @ A.T + K @ R @ K.T     # dạng Joseph: giữ đối xứng
        return True

    @property
    def pos(self) -> np.ndarray:
        return self.x[:3].copy()

    @property
    def vel(self) -> np.ndarray:
        return self.x[3:].copy()

    def pos_sigma(self) -> float:
        return float(np.sqrt(np.trace(self.P[:3, :3]) / 3))
