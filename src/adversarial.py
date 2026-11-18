"""Thử nghiệm chống đánh lừa: dán nhãn ngụy trang lên thân mục tiêu.

Giả định tấn công: kẻ gian dán nhãn/hoạ tiết ngụy trang khiến bộ nhận dạng
ảnh đọc sai lớp VÀ đọc sai một cách rất tự tin (0,92). Đây là kiểu tấn công
có thật với mô hình thị giác.

Điểm quan trọng: nhãn dán chỉ đánh lừa được ánh sáng nhìn thấy. Nó không đổi
được tiết diện phản xạ radar của cánh quạt đang quay, cũng không làm mất
được sóng điều khiển mà drone phải phát. Vì vậy phép phòng vệ không nằm ở
chỗ làm camera khoẻ hơn, mà ở chỗ phát hiện mâu thuẫn giữa các cảm biến rồi
hạ quyền cảm biến bị tấn công.

So sánh 3 cấu hình trên CÙNG một tập mục tiêu và CÙNG một chuỗi số đo:
  1. chỉ dùng camera
  2. hợp nhất cộng đều, không phòng vệ
  3. hợp nhất có hạ quyền khi phát hiện mâu thuẫn  (bản hệ thống dùng)
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from config import FRAME_DT, RADAR_DWELL, SEED
from fusion import IdentityFuser, reliability
from pipeline import md_logp, rf_logp, load_models
from radar_sim import micro_doppler
from rf_sim import make_segment
from scene import TARGET_KINDS, Weather, make_scenario, rotate_into_view, sense

DATA = Path(__file__).resolve().parent.parent / "data"
MD_EVERY, RF_EVERY = int(round(RADAR_DWELL / FRAME_DT)), 5


class NaiveFuser(IdentityFuser):
    """Cộng đều mọi cảm biến, không nhìn tới mâu thuẫn — bản để so sánh."""

    def update(self, dets, w, rng_m):
        s = self.state
        s.logp *= self.decay
        for d in dets:
            if d.cls_logp is None:
                continue
            s.seen[d.sensor] = s.seen.get(d.sensor, 0) + 1
            lp = np.asarray(d.cls_logp, float)
            s.logp += lp - lp.mean()
        s.logp = np.clip(s.logp, -self.max_abs, self.max_abs)
        return s


def run(n_runs: int = 12, n_frames: int = 200, patch: bool = True):
    rf_net, md_net, _ = load_models()
    w = Weather()
    hit = {"defended": 0, "naive": 0, "eo_only": 0}
    tot = 0
    for r in range(n_runs):
        rng = np.random.default_rng(SEED + 7000 + r)
        # Buộc mục tiêu bay vào tầm camera, nếu không thì nhãn ngụy trang
        # chẳng bao giờ có cơ hội tác động và phép thử thành vô nghĩa.
        tg = make_scenario(n_frames, rng, w, kinds=["multirotor"],
                           patch_ids={0} if patch else set(),
                           patterns=["approach"], r0=900.0)[0]
        # r0 chỉ chốt CỰ LY; phương vị vẫn ngẫu nhiên nên bản cũ có tới 2/3
        # số lần chạy mục tiêu nằm ngoài góc nhìn camera và bị bỏ qua khi
        # chấm điểm — kết quả "100%" thực chất dựa trên 2–4 lần chạy. Xoay
        # mục tiêu vào tầm camera (như dashboard) để cả 12 lần đều tính.
        rotate_into_view(tg, rng.uniform(-np.deg2rad(25), np.deg2rad(25)))
        fd, fn = IdentityFuser(), NaiveFuser()
        eo_lp = np.zeros(3)
        eo_last = -99
        for k in range(n_frames):
            dets = sense(tg, k, w, rng)
            if k % RF_EVERY == 0:
                # I và Q phải lấy từ CÙNG một đoạn tín hiệu. Bản cũ gọi
                # make_segment hai lần, lấy phần thực của đoạn này ghép với
                # phần ảo của đoạn kia: cấu trúc pha giữa I và Q (thứ STFT
                # dựa vào để thấy tần số dương/âm) bị phá, mạng RF nhận một
                # tín hiệu không thể có ngoài đời.
                seg = make_segment("drone_ctrl" if tg.emits_rf else "noise", rng,
                                   snr_db=rng.uniform(4, 20))
                lp = rf_logp(rf_net, np.stack([seg.real.astype(np.float32),
                                               seg.imag.astype(np.float32)]))
                for d in dets:
                    if d.sensor == "rf":
                        d.cls_logp = lp
            if k % MD_EVERY == 0:
                rr = float(np.linalg.norm(tg.pos[k]))
                snr = float(np.clip(30 - 20 * np.log10(max(rr, 100) / 300), 2, 26))
                lp = md_logp(md_net, micro_doppler(tg.kind, rng, snr_db=snr))
                for d in dets:
                    if d.sensor == "radar":
                        d.cls_logp = lp
            rng_m = float(np.linalg.norm(tg.pos[k]))
            fd.update([d for d in dets], w, rng_m)
            fn.update([d for d in dets], w, rng_m)
            for d in dets:
                if d.sensor == "eo" and d.cls_logp is not None:
                    _l = np.asarray(d.cls_logp, float)
                    eo_lp = eo_lp * 0.985 + (_l - _l.mean())
                    eo_last = k
            # Chỉ chấm điểm những khung mà camera ĐANG thật sự đóng góp.
            # Khung camera không nhìn thấy gì thì không nói lên điều gì về
            # chuyện chống đánh lừa cả.
            if k > n_frames // 3 and (k - eo_last) <= 10:
                tot += 1
                hit["defended"] += fd.state.top()[0] == tg.kind
                hit["naive"] += fn.state.top()[0] == tg.kind
                hit["eo_only"] += TARGET_KINDS[int(eo_lp.argmax())] == tg.kind
    return {k: v / max(tot, 1) for k, v in hit.items()}, tot


def main():
    att, n = run(patch=True)
    clean, _ = run(n_runs=6, patch=False)
    res = {
        "defended_acc": round(att["defended"], 4),
        "naive_acc": round(att["naive"], 4),
        "eo_only_acc": round(att["eo_only"], 4),
        "clean_defended_acc": round(clean["defended"], 4),
        "clean_eo_only_acc": round(clean["eo_only"], 4),
        "n_frames_scored": n,
        "n_runs": 12,
        "attack": ("Nhãn ngụy trang khiến bộ nhận dạng ảnh đọc sai lớp với "
                   "độ tự tin 0,92."),
    }
    print(json.dumps(res, indent=1, ensure_ascii=False))
    with open(DATA / "adversarial.json", "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
