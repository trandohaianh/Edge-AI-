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

import math

import numpy as np


def _wrap(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


_H_LIDAR = np.hstack([np.eye(3), np.zeros((3, 3))])


class EKF:
    def __init__(
        self,
        p0: np.ndarray,
        v0: np.ndarray,
        sigma_a: float = 6.0,
        p_var: float = 400.0,
        v_var: float = 100.0,
    ):
        self.x = np.concatenate([p0, v0]).astype(float)
        self.P = np.diag([p_var] * 3 + [v_var] * 3).astype(float)
        self.sigma_a = sigma_a  # m/s^2, mức cơ động giả định của mục tiêu

    # ------------------------------------------------------------- dự đoán
    def predict(self, dt: float):
        F = np.eye(6)
        F[:3, 3:] = np.eye(3) * dt
        q = self.sigma_a**2
        dt2, dt3, dt4 = dt * dt, dt**3, dt**4
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
        # Phép toán trên số vô hướng viết bằng ``math`` chứ không bằng numpy:
        # mỗi lời gọi numpy trên một số tốn cỡ micro giây chỉ cho chi phí gọi,
        # và khi bám 10 mục tiêu h()/H() bị gọi hàng chục nghìn lần mỗi giây.
        px, py, pz, vx, vy, vz = x.tolist()
        if sensor == "lidar":
            return np.array([px, py, pz])
        r = max(math.sqrt(px * px + py * py + pz * pz), 1e-6)
        az = math.atan2(py, px)
        if sensor == "rf":
            return np.array([az])
        el = math.asin(min(1.0, max(-1.0, pz / r)))
        if sensor == "eo":
            return np.array([az, el])
        if sensor == "radar":
            return np.array([r, az, el, (vx * px + vy * py + vz * pz) / r])
        raise ValueError(sensor)

    @staticmethod
    def H(sensor: str, x: np.ndarray) -> np.ndarray:
        """Jacobian giải tích của h(x).

        Bản đầu dùng sai phân trung tâm (12 lần gọi h) để tránh viết sai đạo
        hàm. Khi bám nhiều mục tiêu, Jacobian được gọi hàng nghìn lần mỗi
        giây và trở thành chặng tốn nhất, nên đổi sang công thức giải tích.
        Nỗi lo "viết sai đạo hàm" được giữ lại dưới dạng một bài test so
        từng phần tử với ``H_numeric`` ở nhiều trạng thái ngẫu nhiên.
        """
        if sensor == "lidar":
            return _H_LIDAR.copy()
        px, py, pz, vx, vy, vz = x.tolist()
        rho2 = max(px * px + py * py, 1e-12)
        d_az = [-py / rho2, px / rho2, 0.0, 0.0, 0.0, 0.0]
        if sensor == "rf":
            return np.array([d_az])
        r2 = max(px * px + py * py + pz * pz, 1e-12)
        r = math.sqrt(r2)
        rho = math.sqrt(rho2)
        d_el = [-px * pz / (r2 * rho), -py * pz / (r2 * rho), rho / r2, 0.0, 0.0, 0.0]
        if sensor == "eo":
            return np.array([d_az, d_el])
        if sensor == "radar":
            vp = (vx * px + vy * py + vz * pz) / (r2 * r)
            d_r = [px / r, py / r, pz / r, 0.0, 0.0, 0.0]
            d_rr = [vx / r - vp * px, vy / r - vp * py, vz / r - vp * pz, px / r, py / r, pz / r]
            return np.array([d_r, d_az, d_el, d_rr])
        raise ValueError(sensor)

    @staticmethod
    def H_numeric(sensor: str, x: np.ndarray) -> np.ndarray:
        """Jacobian bằng sai phân trung tâm — chỉ để kiểm tra ``H``."""
        n = {"radar": 4, "eo": 2, "rf": 1, "lidar": 3}[sensor]
        J = np.zeros((n, 6))
        eps = 1e-4
        for i in range(6):
            dx = np.zeros(6)
            dx[i] = eps
            d = EKF.h(sensor, x + dx) - EKF.h(sensor, x - dx)
            if sensor in ("radar", "eo", "rf"):
                for j in {"radar": [1, 2], "eo": [0, 1], "rf": [0]}[sensor]:
                    d[j] = _wrap(d[j])
            J[:, i] = d / (2 * eps)
        return J

    # ----------------------------------------------------------- cập nhật
    def innovation(self, sensor: str, z: np.ndarray) -> np.ndarray:
        y = z - self.h(sensor, self.x)
        idx = {"radar": [1, 2], "eo": [0, 1], "rf": [0]}.get(sensor, [])
        for j in idx:
            y[j] = _wrap(y[j])
        return y

    def gate_terms(self, sensor: str):
        """(h(x), H, H P Hᵀ) tính MỘT lần cho mỗi vết bám và mỗi loại cảm
        biến, rồi dùng lại cho mọi số đo khi liên kết. Jacobian sai phân số
        tốn 12 lần gọi h(); tính lại cho từng cặp vết–số đo là chỗ tốn nhất
        của bản đầu."""
        H = self.H(sensor, self.x)
        return self.h(sensor, self.x), H, H @ self.P @ H.T

    @staticmethod
    def mahalanobis_from(sensor: str, terms, z: np.ndarray, R: np.ndarray) -> float:
        hx, _, HPH = terms
        y = z - hx
        for j in {"radar": [1, 2], "eo": [0, 1], "rf": [0]}.get(sensor, []):
            y[j] = _wrap(y[j])
        try:
            return float(y @ np.linalg.solve(HPH + R, y))
        except np.linalg.LinAlgError:
            return float("inf")

    def mahalanobis(self, sensor: str, z: np.ndarray, R: np.ndarray) -> float:
        """Khoảng cách Mahalanobis bình phương của số đo so với dự đoán, dùng
        để LIÊN KẾT số đo với vết bám mà không cập nhật bộ lọc."""
        y = self.innovation(sensor, z)
        H = self.H(sensor, self.x)
        S = H @ self.P @ H.T + R
        try:
            return float(y @ np.linalg.solve(S, y))
        except np.linalg.LinAlgError:
            return float("inf")

    def update(self, sensor: str, z: np.ndarray, R: np.ndarray, gate: float = 16.0) -> bool:
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
        self.P = A @ self.P @ A.T + K @ R @ K.T  # dạng Joseph: giữ đối xứng
        return True

    @property
    def pos(self) -> np.ndarray:
        return self.x[:3].copy()

    @property
    def vel(self) -> np.ndarray:
        return self.x[3:].copy()

    def pos_sigma(self) -> float:
        P = self.P
        return math.sqrt((P[0, 0] + P[1, 1] + P[2, 2]) / 3)


def predict_many(filters: list[EKF], dt: float) -> None:
    """Dự đoán cho NHIỀU bộ lọc trong một phép tính numpy theo lô.

    Mọi vết bám dùng chung F và (nếu cùng sigma_a) chung Q, nên x' = F x và
    P' = F P Fᵀ + Q tính được cho cả lô bằng einsum thay vì N vòng lặp Python.
    Kết quả trùng với gọi ``predict`` từng cái (có test).
    """
    if not filters:
        return
    F = np.eye(6)
    F[:3, 3:] = np.eye(3) * dt
    X = np.stack([f.x for f in filters])  # [N,6]
    P = np.stack([f.P for f in filters])  # [N,6,6]
    q = np.array([f.sigma_a**2 for f in filters])  # [N]
    Q1 = np.zeros((6, 6))
    Q1[:3, :3] = np.eye(3) * dt**4 / 4
    Q1[:3, 3:] = Q1[3:, :3] = np.eye(3) * dt**3 / 2
    Q1[3:, 3:] = np.eye(3) * dt**2
    X = X @ F.T
    P = np.einsum("ij,njk,lk->nil", F, P, F) + q[:, None, None] * Q1
    for f, x, p in zip(filters, X, P):
        f.x, f.P = x, p
