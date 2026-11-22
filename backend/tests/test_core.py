"""Kiểm thử tự động cho hệ giám sát đa cảm biến.

Các bài kiểm thử ở đây cố ý nhắm vào những chỗ đã từng sai thật trong lúc
làm, chứ không phải viết cho đủ số: dải Doppler của radar, cửa sổ quan sát
RF, biên của phép làm trơn quỹ đạo, và luật cộng bằng chứng.

Chạy:  python -m pytest   (ở gốc repo; cấu hình trong pyproject.toml)
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]

from edge_ai import config as C  # noqa: E402
from edge_ai.sim.radar_sim import micro_doppler  # noqa: E402
from edge_ai.sim.rf_sim import make_segment  # noqa: E402
from edge_ai.sim.scene import (  # noqa: E402
    TARGET_KINDS,
    Detection,
    Weather,
    make_scenario,
    make_trajectory,
    sense,
    spherical,
)
from edge_ai.tracking.ekf import EKF  # noqa: E402
from edge_ai.tracking.fusion import PER_SENSOR_CAP, IdentityFuser, reliability, track_confidence  # noqa: E402


# ----------------------------------------------------------------- vật lý
def test_prf_phu_duoc_doppler_dau_canh():
    """PRF phải đủ cao để không gập phổ chữ ký cánh quạt.

    Đây chính là lỗi đã mắc: PRF 4 kHz cho dải ±2 kHz, trong khi đầu cánh
    drone cho Doppler khoảng 5,3 kHz ở băng X, nên chữ ký biến thành nhiễu.
    """
    f_rot = max(C.MULTIROTOR["f_rot"])
    radius = max(C.MULTIROTOR["radius"])
    v_tip = 2 * np.pi * radius * f_rot
    f_d = 2 * v_tip / C.RADAR_LAMBDA
    assert f_d < C.RADAR_PRF / 2, (
        f"dải Doppler ±{C.RADAR_PRF / 2:.0f} Hz không phủ nổi {f_d:.0f} Hz"
    )


def test_canh_quat_trai_pho_rong_hon_chim():
    """Drone phải trải ra một "bệ" phổ rộng, chim và nhiễu địa hình thì không.

    Đo mức năng lượng ở các ô Doppler NẰM NGOÀI vạch thân mục tiêu. Đặt vận
    tốc xuyên tâm bằng 0 để vạch thân luôn ở giữa, nhờ vậy phép đo không phụ
    thuộc mục tiêu đang bay nhanh hay chậm.
    """
    rng = np.random.default_rng(0)

    def pedestal(kind):
        vals = []
        for _ in range(8):
            S = micro_doppler(kind, rng, snr_db=20, v_radial=0.0)
            prof = S.mean(axis=1)
            c = len(prof) // 2
            vals.append(float(np.concatenate([prof[: c - 8], prof[c + 8 :]]).mean()))
        return float(np.mean(vals))

    assert pedestal("multirotor") > pedestal("bird") * 4
    assert pedestal("fixed_wing") > pedestal("clutter") * 4


def test_micro_doppler_dung_hinh_dang_va_khoang_gia_tri():
    rng = np.random.default_rng(1)
    S = micro_doppler("multirotor", rng, snr_db=15)
    assert S.shape == C.MD_SHAPE
    assert S.dtype == np.float32
    assert S.min() >= 0.0 and S.max() <= 1.0 + 1e-6


# -------------------------------------------------------------------- RF
def test_cua_so_rf_luon_chua_tin_hieu():
    """Mọi lớp có phát sóng phải thật sự có năng lượng trong cửa sổ.

    Lỗi cũ: cắt cửa sổ 1 ms cố định nên nhiều đoạn gán nhãn "có drone" lại
    toàn nhiễu — nhãn sai thì không mô hình nào học được.
    """
    rng = np.random.default_rng(2)
    for label in ("wifi", "bluetooth", "drone_ctrl"):
        weak = 0
        for _ in range(25):
            x = make_segment(label, rng, snr_db=20)
            env = np.abs(x)
            on = float((env > env.mean()).mean())
            if on < 0.03:
                weak += 1
        assert weak == 0, f"{label}: {weak}/25 cửa sổ gần như không có tín hiệu"


def test_rf_dung_dinh_dang():
    rng = np.random.default_rng(3)
    x = make_segment("drone_ctrl", rng, snr_db=10)
    assert x.shape == (C.RF_SEG,)
    assert x.dtype == np.complex64
    assert np.isfinite(x).all()


# -------------------------------------------------------------- quỹ đạo
@pytest.mark.parametrize("kind", TARGET_KINDS)
def test_toc_do_quy_dao_hop_ly(kind):
    """Không được có mục tiêu bay nhanh vô lý.

    Lỗi cũ: đặt thẳng tốc độ góc mà quên nhân với cự ly, nên ở 2 km mục tiêu
    "bay" vài trăm m/s.
    """
    rng = np.random.default_rng(4)
    sp = []
    for pat in ("approach", "orbit", "zigzag", "hover_dash", "pop_up"):
        for _ in range(4):
            _, v = make_trajectory(kind, 150, rng, pat)
            sp.append(np.linalg.norm(v, axis=1))
    sp = np.concatenate(sp)
    assert np.percentile(sp, 99) < 60.0, f"{kind}: p99 = {np.percentile(sp, 99):.1f} m/s"


def test_lam_tron_khong_keo_tut_hai_dau():
    """Phép làm trơn phải đệm biên.

    Lỗi cũ: dùng convolve mode='same' nên hai đầu chuỗi bị kéo tụt về gốc,
    vận tốc đầu/cuối vọt lên và EKF phân kỳ.
    """
    rng = np.random.default_rng(5)
    p, v = make_trajectory("multirotor", 150, rng, "approach")
    r = np.linalg.norm(p[:, :2], axis=1)
    assert abs(r[0] - r[:6].mean()) < 25.0
    assert np.linalg.norm(v[0]) < 60.0 and np.linalg.norm(v[-1]) < 60.0


def test_r0_dat_duoc_cu_ly_xuat_phat_ma_khong_doi_toc_do():
    """Đặt cự ly xuất phát không được làm co giãn vận tốc.

    Lỗi cũ: co giãn toạ độ để đổi cự ly, kéo theo vận tốc giảm cùng tỉ lệ,
    drone 15 m/s hoá ra bay 3 m/s.
    """
    rng = np.random.default_rng(6)
    pa, va = make_trajectory("multirotor", 150, rng, "approach", r0=2400)
    rng = np.random.default_rng(6)
    pb, vb = make_trajectory("multirotor", 150, rng, "approach", r0=800)
    assert abs(np.linalg.norm(pb[0, :2]) - 800) < 30
    assert abs(np.linalg.norm(pa[0, :2]) - 2400) < 30
    sa, sb = np.linalg.norm(va, axis=1).mean(), np.linalg.norm(vb, axis=1).mean()
    assert abs(sa - sb) / max(sa, 1e-6) < 0.25


# ------------------------------------------------------------------ EKF
def test_ekf_bam_duoc_muc_tieu():
    rng = np.random.default_rng(7)
    w = Weather()
    tg = make_scenario(200, rng, w, kinds=["multirotor"], patterns=["approach"])[0]
    f = EKF(tg.pos[0] + rng.normal(0, 25, 3), tg.vel[0] + rng.normal(0, 6, 3))
    errs = []
    for k in range(200):
        f.predict(C.FRAME_DT)
        for d in sense(tg, k, w, rng):
            f.update(d.sensor, d.z, d.R)
        errs.append(np.linalg.norm(f.pos - tg.pos[k]))
    assert np.mean(errs[50:]) < 40.0


def test_ekf_loai_so_do_bat_thuong():
    """Cổng thống kê phải chặn số đo lệch quá xa."""
    f = EKF(np.array([1000.0, 0, 100]), np.array([-10.0, 0, 0]))
    f.predict(0.1)
    r, az, el = spherical(f.pos)
    good = np.array([r, az, el, -10.0])
    R = np.diag([5.0**2, 1e-4, 1e-4, 0.5**2])
    assert f.update("radar", good, R) is True
    bad = np.array([r + 900.0, az, el, -10.0])
    assert f.update("radar", bad, R) is False


def test_hiep_phuong_sai_luon_doi_xung_va_xac_dinh_duong():
    rng = np.random.default_rng(8)
    w = Weather()
    tg = make_scenario(80, rng, w, kinds=["fixed_wing"])[0]
    f = EKF(tg.pos[0], tg.vel[0])
    for k in range(80):
        f.predict(C.FRAME_DT)
        for d in sense(tg, k, w, rng):
            f.update(d.sensor, d.z, d.R)
        assert np.allclose(f.P, f.P.T, atol=1e-6)
        assert np.all(np.linalg.eigvalsh(f.P) > -1e-6)


# --------------------------------------------------------------- hợp nhất
def test_do_tin_cay_giam_theo_dieu_kien():
    clear, fog = Weather(), Weather(fog=0.9, night=True)
    assert reliability("eo", fog, 500) < reliability("eo", clear, 500)
    assert reliability("rf", Weather(jamming=0.9)) < reliability("rf", clear)
    assert reliability("lidar", fog) < reliability("lidar", clear)


def test_bang_chung_moi_cam_bien_bi_chan_tran():
    """Một cảm biến lặp lại mãi một kết luận không được dồn vô hạn."""
    f = IdentityFuser()
    lp = np.log(np.array([0.9, 0.05, 0.05]))
    for _ in range(300):
        f.update([Detection("eo", np.zeros(2), np.eye(2), lp)], Weather(), 300.0)
    assert float(np.abs(f.state.by_sensor["eo"]).max()) <= PER_SENSOR_CAP + 1e-6


def test_radar_va_rf_thang_duoc_camera_bi_danh_lua():
    """Hai cảm biến vật lý đồng thuận phải thắng một camera bị lừa."""
    f = IdentityFuser()
    true_i = TARGET_KINDS.index("multirotor")
    wrong_i = TARGET_KINDS.index("fixed_wing")
    good = np.full(3, np.log(0.1))
    good[true_i] = np.log(0.8)
    bad = np.full(3, np.log(0.04))
    bad[wrong_i] = np.log(0.92)
    for k in range(120):
        dets = [Detection("eo", np.zeros(2), np.eye(2), bad)]
        if k % 4 == 0:
            dets.append(Detection("radar", np.zeros(4), np.eye(4), good))
        if k % 5 == 0:
            dets.append(Detection("rf", np.zeros(1), np.eye(1), good))
        f.update(dets, Weather(), 600.0)
    assert f.state.top()[0] == "multirotor"
    assert f.state.conflict > 0.3


def test_do_tin_cay_can_thoi_gian_quan_sat():
    """Không được 'đủ tin để báo người' ngay ở khung đầu tiên."""
    f = IdentityFuser()
    lp = np.log(np.array([0.95, 0.025, 0.025]))
    dets = [
        Detection("radar", np.zeros(4), np.eye(4), lp),
        Detection("rf", np.zeros(1), np.eye(1), lp),
    ]
    f.update(dets, Weather(), 400.0)
    assert track_confidence(f.state, 5.0, 2) < C.CONFIRM_THRESHOLD
    for _ in range(40):
        f.update(dets, Weather(), 400.0)
    assert track_confidence(f.state, 5.0, 2) >= C.CONFIRM_THRESHOLD


# --------------------------------------------------------------- cảm biến
def test_chim_khong_phat_song_rf():
    rng = np.random.default_rng(9)
    w = Weather()
    tg = make_scenario(120, rng, w, kinds=["bird"])[0]
    assert tg.emits_rf is False
    for k in range(120):
        assert all(d.sensor != "rf" for d in sense(tg, k, w, rng))


def test_suong_mu_lam_cam_lidar_va_camera():
    rng = np.random.default_rng(10)
    tg = make_scenario(150, rng, Weather(), kinds=["multirotor"], patterns=["approach"], r0=600)[0]
    # Xoay mục tiêu vào đúng góc nhìn camera: EO/IR chỉ có 60 độ, mục tiêu
    # sinh ở phương vị ngẫu nhiên thì phần lớn lần chạy camera không thấy gì
    # và phép so sánh trở thành 0 với 0.
    az0 = np.arctan2(tg.pos[0, 1], tg.pos[0, 0])
    c_, s_ = np.cos(-az0), np.sin(-az0)
    R_ = np.array([[c_, -s_], [s_, c_]])
    tg.pos[:, :2] = tg.pos[:, :2] @ R_.T
    tg.vel[:, :2] = tg.vel[:, :2] @ R_.T

    def count(w):
        rr = np.random.default_rng(11)
        n = 0
        for k in range(150):
            n += sum(d.sensor in ("eo", "lidar") for d in sense(tg, k, w, rr))
        return n

    assert count(Weather(fog=0.95, night=True)) < count(Weather()) * 0.5


def test_camera_o_xa_tien_ve_phan_bo_deu_chu_khong_chi_sai():
    """Camera nhìn kém phải trở nên KHÔNG BIẾT, không được trỏ sang lớp sai.

    Lỗi cũ: đặt p(lớp đúng) = q và chia đều phần còn lại, nên khi q < 1/3 thì
    lớp đúng lại thành lớp ít khả năng nhất.
    """
    rng = np.random.default_rng(12)
    w = Weather()
    tg = make_scenario(200, rng, w, kinds=["multirotor"], patterns=["approach"], r0=1150)[0]
    seen = 0
    for k in range(200):
        for d in sense(tg, k, w, rng):
            if d.sensor == "eo" and d.cls_logp is not None:
                seen += 1
                assert int(np.argmax(d.cls_logp)) == TARGET_KINDS.index("multirotor")
    assert seen > 0


def test_numpy_khong_ro_bo_nho_o_ma_tran_don_vi():
    """EKF gọi np.eye mỗi khung. numpy 2.4.0 rò bộ nhớ ở đó (khoảng 550 MB/giờ
    khi chạy dashboard, tìm ra bằng experiments/soak.py). Bài này hỏng nếu ai
    đó cài nhầm một bản numpy như vậy."""
    import tracemalloc

    import numpy as np

    tracemalloc.start()
    try:
        for _ in range(2000):
            np.eye(6)
        before = tracemalloc.get_traced_memory()[0]
        for _ in range(20000):
            np.eye(6)
        grown = tracemalloc.get_traced_memory()[0] - before
    finally:
        tracemalloc.stop()
    assert grown < 1_000_000, f"numpy {np.__version__} giữ lại {grown / 1e6:.1f} MB"
