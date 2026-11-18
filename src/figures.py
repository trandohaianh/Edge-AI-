"""Vẽ toàn bộ hình cho báo cáo và slide, song ngữ Việt – Anh.

Chạy:  python3 figures.py        (sinh cả hai ngôn ngữ vào docs/fig)
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

from config import LATENCY_BUDGET_MS, RADAR_CLASSES, RF_CLASSES, SEED

ROOT = Path(__file__).resolve().parent.parent
FIG = ROOT / "docs" / "fig"
FIG.mkdir(parents=True, exist_ok=True)
DATA = ROOT / "data"

RED, INK, MUTED, OK, WARN = "#D7153A", "#111111", "#888888", "#1a9e5c", "#E8A317"
plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9,
    "axes.edgecolor": "#CCCCCC", "axes.linewidth": .8,
    "axes.titlesize": 10, "axes.titleweight": "bold",
    "figure.dpi": 170, "savefig.bbox": "tight", "savefig.facecolor": "white",
})
L = "vi"
def T(vi, en): return en if L == "en" else vi
def out(name): return FIG / f"{name}_{L}.png"


# ------------------------------------------------------------------ 1. kiến trúc
def fig_architecture():
    fig, ax = plt.subplots(figsize=(10.2, 4.5))
    ax.set_xlim(0, 100); ax.set_ylim(0, 46); ax.axis("off")

    def box(x, y, w, h, title, sub, fc="white", ec="#CCCCCC", tc=INK, bold=True):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.5,rounding_size=1.2",
                                    fc=fc, ec=ec, lw=1.2))
        ax.text(x + w / 2, y + h - 3.0, title, ha="center", va="top", fontsize=8.4,
                weight="bold" if bold else "normal", color=tc)
        if sub:
            ax.text(x + w / 2, y + h - 7.2, sub, ha="center", va="top", fontsize=6.6,
                    color=tc if fc != "white" else MUTED, linespacing=1.45)

    def arrow(x1, y1, x2, y2, col="#999999"):
        ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>",
                                     mutation_scale=9, lw=1.0, color=col,
                                     shrinkA=0, shrinkB=0))

    sens = [(T("RADAR băng X", "X-band radar"), T("cự ly · góc\nvận tốc xuyên tâm", "range · angles\nradial velocity")),
            (T("RF (I/Q)", "RF (I/Q)"), T("chỉ phương vị\nlink điều khiển", "bearing only\ncontrol link")),
            (T("EO/IR", "EO/IR"), T("chỉ góc\nảnh ngày & nhiệt", "angles only\nday & thermal")),
            (T("LiDAR", "LiDAR"), T("toạ độ 3D\ntầm ngắn", "3D position\nshort range"))]
    for i, (n, s) in enumerate(sens):
        box(1.5, 35 - i * 9.2, 17, 8, n, s, fc="#F7F7F8")
        arrow(18.5, 39 - i * 9.2, 24, 39 - i * 9.2)

    box(24, 26.5, 20, 17, T("TIỀN XỬ LÝ", "PRE-PROCESSING"),
        T("STFT cho I/Q\nmicro-Doppler cho radar\nchuẩn hoá số đo",
          "STFT for I/Q\nmicro-Doppler for radar\nmeasurement scaling"), fc="#F7F7F8")
    box(24, 6, 20, 17, T("PHÁT HIỆN SỚM", "EARLY DETECTION"),
        T("CNN RF  96,4%\nCNN micro-Doppler  95,4%\n(phi hình ảnh, thấy trước camera)",
          "RF CNN  96.4%\nmicro-Doppler CNN  95.4%\n(non-imaging, sees first)"), fc=RED, ec=RED, tc="white")
    arrow(44, 35, 50, 30); arrow(44, 14.5, 50, 20)

    box(50, 14, 21, 18, T("HỢP NHẤT", "FUSION"),
        T("EKF đa cảm biến\n(mỗi cảm biến một mô hình đo)\n+ cộng bằng chứng nhận dạng\ncó trọng số tin cậy",
          "Multi-sensor EKF\n(per-sensor measurement model)\n+ identity evidence with\nreliability weights"), fc="#F7F7F8")
    arrow(71, 23, 77, 23)
    box(77, 24, 21.5, 15, T("BÁM QUỸ ĐẠO", "TRACKING"),
        T("EKF + Transformer nhẹ\ndự đoán khi mất dấu",
          "EKF + tiny Transformer\npredicts through dropouts"), fc="#F7F7F8")
    box(77, 4, 21.5, 16, T("CHUYÊN VIÊN QUYẾT ĐỊNH", "HUMAN DECIDES"),
        T("toạ độ · nhận dạng\nđiểm tin cậy + bằng chứng\nxác nhận / bỏ qua → nhật ký",
          "position · identity\nconfidence + evidence\nconfirm / dismiss → audit log"), fc=INK, ec=INK, tc="white")
    arrow(87.7, 24, 87.7, 20.5, col=RED)
    ax.text(50, 1.2, T("Hệ thống dừng ở mức đề xuất cho người. Không có tự động chọn mục tiêu hay điều khiển khí tài.",
                       "The system stops at advice for a human. No autonomous targeting or weapon control."),
            ha="center", fontsize=7.4, color=RED, style="italic", weight="bold")
    ax.text(1.5, 44.4, T("LUỒNG XỬ LÝ — ngân sách 50 ms mỗi khung", "PIPELINE — 50 ms budget per frame"),
            fontsize=9.6, weight="bold", color=INK)
    fig.savefig(out("arch")); plt.close(fig)


# -------------------------------------------------- 2. chữ ký micro-Doppler
def fig_signatures():
    from radar_sim import micro_doppler
    rng = np.random.default_rng(7)
    names = {"clutter": T("Nhiễu địa hình", "Ground clutter"),
             "bird": T("Chim", "Bird"),
             "fixed_wing": T("Drone cánh bằng", "Fixed-wing drone"),
             "multirotor": T("Drone đa cánh quạt", "Multirotor drone")}
    fig, axes = plt.subplots(1, 4, figsize=(10.2, 2.7))
    for ax, c in zip(axes, RADAR_CLASSES):
        S = micro_doppler(c, rng, snr_db=18)
        ax.imshow(S, aspect="auto", cmap="magma", origin="lower",
                  extent=[0, 0.35, -10, 10])
        ax.set_title(names[c], fontsize=8.6)
        ax.set_xlabel(T("thời gian (s)", "time (s)"), fontsize=7)
        ax.tick_params(labelsize=6.5)
    axes[0].set_ylabel(T("tần số Doppler (kHz)", "Doppler (kHz)"), fontsize=7)
    fig.suptitle(T("Chữ ký micro-Doppler: cánh quạt trải phổ rộng, chim chỉ là một hình sin chậm",
                   "Micro-Doppler: rotors spread a wide pedestal, a bird is a slow sinusoid"),
                 fontsize=9, y=1.04)
    fig.savefig(out("signatures")); plt.close(fig)


def fig_rfspec():
    from rf_sim import make_segment
    rng = np.random.default_rng(5)
    names = {"noise": T("Nhiễu nền", "Noise floor"), "wifi": "WiFi",
             "bluetooth": "Bluetooth", "drone_ctrl": T("Link điều khiển drone", "Drone control link")}

    def spec(x, nfft=128, hop=16):
        """Lấy mốc 0 dB là TRUNG VỊ của chính ảnh (xấp xỉ nền nhiễu).

        Nếu lấy mốc là giá trị lớn nhất của từng ảnh thì ảnh chỉ có nhiễu
        cũng sáng y như ảnh có tín hiệu, và hình vẽ không nói lên điều gì.
        """
        F = [np.fft.fftshift(np.abs(np.fft.fft(x[i:i + nfft] * np.hanning(nfft))) ** 2)
             for i in range(0, len(x) - nfft, hop)]
        S = 10 * np.log10(np.asarray(F).T + 1e-9)
        return S - np.median(S)

    fig, axes = plt.subplots(1, 4, figsize=(10.2, 2.7))
    for ax, c in zip(axes, RF_CLASSES):
        # Hình minh hoạ vẽ ở SNR cao và chọn mẫu rõ nhất trong 8 mẫu. Mô hình
        # thì vẫn được huấn luyện và chấm điểm trên dải SNR đầy đủ −6..24 dB;
        # đây chỉ là hình cho người đọc nhìn ra dấu hiệu, không phải số liệu.
        cands = [spec(make_segment(c, rng, snr_db=24)) for _ in range(8)]
        S = cands[0] if c == "noise" else max(cands, key=lambda a: np.percentile(a, 99.5))
        ax.imshow(S, aspect="auto", cmap="viridis",
                  origin="lower", extent=[0, 1.02, -1, 1], vmin=-4, vmax=22)
        ax.set_title(names[c], fontsize=8.6)
        ax.set_xlabel(T("thời gian (ms)", "time (ms)"), fontsize=7)
        ax.tick_params(labelsize=6.5)
    axes[0].set_ylabel(T("tần số (MHz)", "frequency (MHz)"), fontsize=7)
    fig.suptitle(T("Tín hiệu vô tuyến (dB trên nền nhiễu): WiFi là khối rộng, Bluetooth hẹp, "
                   "drone nhảy tần nhanh",
                   "RF signals (dB above the noise floor): WiFi a wide block, Bluetooth narrow, "
                   "the drone link hops fast"), fontsize=9, y=1.04)
    fig.text(.5, -.06, T("Hình minh hoạ ở SNR 24 dB. Mô hình được chấm điểm trên dải −6..24 dB.",
                         "Illustration at 24 dB SNR; the model is scored over −6..24 dB."),
             ha="center", fontsize=6.8, color=MUTED, style="italic")
    fig.savefig(out("rfspec")); plt.close(fig)


# ---------------------------------------------------------- 3. độ chính xác
def fig_accuracy():
    rf = json.load(open(DATA / "rf_metrics.json", encoding="utf-8"))
    md = json.load(open(DATA / "md_metrics.json", encoding="utf-8"))
    fig, axes = plt.subplots(1, 3, figsize=(10.2, 3.0))

    def cm(ax, m, classes, title):
        M = np.array(m, dtype=float)
        Mn = M / M.sum(1, keepdims=True)
        ax.imshow(Mn, cmap="Reds", vmin=0, vmax=1)
        for i in range(len(classes)):
            for j in range(len(classes)):
                ax.text(j, i, f"{Mn[i,j]*100:.0f}", ha="center", va="center",
                        fontsize=7, color="white" if Mn[i, j] > .55 else INK)
        lab = [c.replace("_", " ")[:9] for c in classes]
        ax.set_xticks(range(len(classes))); ax.set_xticklabels(lab, rotation=35, fontsize=6.5, ha="right")
        ax.set_yticks(range(len(classes))); ax.set_yticklabels(lab, fontsize=6.5)
        ax.set_title(title, fontsize=8.6)
        ax.set_xlabel(T("mô hình đoán", "predicted"), fontsize=7)

    cm(axes[0], rf["confusion"], RF_CLASSES, T("RF · %.1f%%" % (rf["test_acc"] * 100),
                                               "RF · %.1f%%" % (rf["test_acc"] * 100)))
    axes[0].set_ylabel(T("sự thật", "true"), fontsize=7)
    cm(axes[1], md["confusion"], RADAR_CLASSES,
       T("Micro-Doppler · %.1f%%" % (md["test_acc"] * 100),
         "Micro-Doppler · %.1f%%" % (md["test_acc"] * 100)))

    ax = axes[2]
    ks = list(rf["by_snr"].keys())
    vs = [rf["by_snr"][k] * 100 for k in ks]
    ax.plot(range(len(ks)), vs, "o-", color=RED, lw=2, ms=5)
    ax.set_xticks(range(len(ks))); ax.set_xticklabels(ks, rotation=35, fontsize=6.5, ha="right")
    ax.set_ylim(70, 102); ax.grid(alpha=.25)
    ax.set_title(T("RF: độ chính xác theo SNR", "RF accuracy vs SNR"), fontsize=8.6)
    ax.set_ylabel("%", fontsize=7); ax.tick_params(labelsize=6.5)
    for i, v in enumerate(vs):
        ax.annotate(f"{v:.1f}", (i, v), textcoords="offset points", xytext=(0, 6),
                    ha="center", fontsize=6.3, color=INK)
    fig.savefig(out("accuracy")); plt.close(fig)


# ------------------------------------------------------------- 4. bám & mất dấu
def fig_tracking():
    sc = json.load(open(DATA / "scenario_results.json", encoding="utf-8"))
    tj = json.load(open(DATA / "traj_metrics.json", encoding="utf-8"))
    fig, axes = plt.subplots(1, 2, figsize=(10.2, 3.2))

    ax = axes[0]
    cur = None
    for s in sc["scenarios"]:
        if "blind_curve" in s:
            cur = s["blind_curve"]
    if cur:
        t = [r["t_s"] for r in cur]
        ax.plot(t, [r["const_vel_m"] for r in cur], "--", color=MUTED, lw=2,
                label=T("EKF ngoại suy vận tốc không đổi", "EKF constant-velocity"))
        ax.plot(t, [r["transformer_m"] for r in cur], "-", color=RED, lw=2.2,
                label=T("EKF + Transformer", "EKF + Transformer"))
        ax.set_xlabel(T("thời gian đã mất dấu (giây)", "time since dropout (s)"), fontsize=7.5)
        ax.set_ylabel(T("sai số vị trí (m)", "position error (m)"), fontsize=7.5)
        ax.set_title(T("Khi mất dấu giữa chừng (trong hệ thống thật)",
                       "During a mid-track dropout (in the live system)"), fontsize=8.6)
        ax.legend(fontsize=6.8, frameon=False); ax.grid(alpha=.25); ax.tick_params(labelsize=6.5)

    ax = axes[1]
    hz = tj["horizon_s"]
    ax.plot(hz, tj["ekf_const_vel_rmse_m"], "--", color=MUTED, lw=2,
            label=T("vận tốc không đổi", "constant velocity"))
    ax.plot(hz, tj["transformer_rmse_m"], "-", color=RED, lw=2.2, label="Transformer")
    ax.set_xlabel(T("dự đoán trước bao lâu (giây)", "prediction horizon (s)"), fontsize=7.5)
    ax.set_ylabel("RMSE (m)", fontsize=7.5)
    ax.set_title(T("Trên tập quỹ đạo chuẩn (lịch sử sạch hơn)",
                   "On the benchmark set (cleaner history)"), fontsize=8.6)
    ax.legend(fontsize=6.8, frameon=False); ax.grid(alpha=.25); ax.tick_params(labelsize=6.5)
    fig.savefig(out("tracking")); plt.close(fig)


# ----------------------------------------------------------------- 5. độ trễ
def fig_latency():
    sc = json.load(open(DATA / "scenario_results.json", encoding="utf-8"))
    lat = sc["latency_ms"]
    names = {"preproc": T("tiền xử lý", "pre-process"), "rf_net": T("mạng RF", "RF net"),
             "md_net": T("mạng micro-Doppler", "micro-Doppler net"),
             "assoc": T("liên kết số đo", "association"), "ekf": "EKF",
             "fuse": T("hợp nhất", "fusion"), "traj": T("dự đoán quỹ đạo", "trajectory")}
    ks = [k for k in names if k in lat]
    fig, ax = plt.subplots(figsize=(8.0, 3.1))
    y = np.arange(len(ks))
    ax.barh(y, [lat[k]["p99_ms"] for k in ks], color=RED, height=.55)
    ax.barh(y, [lat[k]["mean_ms"] for k in ks], color=INK, height=.25)
    ax.set_yticks(y); ax.set_yticklabels([names[k] for k in ks], fontsize=7.5)
    ax.invert_yaxis()
    for i, k in enumerate(ks):
        ax.text(lat[k]["p99_ms"] + .1, i, f"{lat[k]['p99_ms']:.2f} ms", va="center", fontsize=6.8)
    tot = lat["total"]
    ax.axvline(LATENCY_BUDGET_MS, color=OK, lw=1.8, ls="--")
    ax.text(LATENCY_BUDGET_MS - .8, len(ks) - .45,
            T("ngân sách 50 ms", "50 ms budget"), color=OK, fontsize=8,
            ha="right", weight="bold")
    ax.axvspan(tot["p99_ms"], LATENCY_BUDGET_MS, color=OK, alpha=.06)
    ax.text((tot["p99_ms"] + LATENCY_BUDGET_MS) / 2, len(ks) / 2.0,
            T(f"còn dư {LATENCY_BUDGET_MS - tot['p99_ms']:.0f} ms",
              f"{LATENCY_BUDGET_MS - tot['p99_ms']:.0f} ms of headroom"),
            color=OK, fontsize=7.6, ha="center", style="italic")
    # Trục phải kéo tới 50 ms, nếu không thì vạch ngân sách nằm ngoài khung và
    # hình mất đi đúng điều nó cần cho thấy: phần đã dùng nhỏ thế nào so với
    # phần được phép dùng.
    ax.set_xlim(0, 54)
    ax.set_xlabel(T("mili giây (cột đậm = trung bình, cột đỏ = p99)",
                    "milliseconds (dark = mean, red = p99)"), fontsize=7.5)
    ax.set_title(T(f"Một khung hợp nhất: tổng p99 = {tot['p99_ms']:.2f} ms / 50 ms",
                   f"One fused frame: total p99 = {tot['p99_ms']:.2f} ms / 50 ms"), fontsize=9)
    ax.grid(axis="x", alpha=.25); ax.tick_params(labelsize=6.8)
    fig.savefig(out("latency")); plt.close(fig)


# ------------------------------------------------------------- 6. kịch bản
def fig_scenarios():
    sc = json.load(open(DATA / "scenario_results.json", encoding="utf-8"))["scenarios"]
    short = {"S1": T("Trời quang", "Clear"), "S2": T("Đêm + sương mù", "Night + fog"),
             "S3": T("Nhiễu RF", "RF jamming"), "S4": T("Mưa to", "Heavy rain"),
             "S5": T("Chim", "Bird"), "S6": T("Nhãn ngụy trang", "Adversarial patch"),
             "S7": T("Mất dấu 4 s", "4 s dropout")}
    lab = [short[s["scenario"][:2]] for s in sc]
    fig, axes = plt.subplots(1, 3, figsize=(10.2, 2.9))
    y = np.arange(len(sc))

    tconf = [s["time_to_confirm_s"] or 0 for s in sc]
    axes[0].barh(y, tconf, color=RED, height=.6)
    axes[0].set_title(T("Thời gian đến khi đủ tin để báo người (giây)",
                        "Time to operator-grade confidence (s)"), fontsize=8.1)
    axes[0].set_xlim(0, max(tconf) * 1.25)
    axes[1].barh(y, [s["rmse_m"] for s in sc], color=INK, height=.6)
    axes[1].set_title(T("Sai số bám trung bình (m)", "Mean track error (m)"), fontsize=8.6)
    axes[2].barh(y, [s["operator_ask_rate"] * 100 for s in sc], color="#555555", height=.6)
    axes[2].set_title(T("Tỉ lệ khung hỏi người trực (%)", "Frames escalated to operator (%)"), fontsize=8.6)
    axes[2].set_xlim(0, 105)
    for i, ax in enumerate(axes):
        ax.set_yticks(y); ax.invert_yaxis(); ax.grid(axis="x", alpha=.25)
        ax.tick_params(labelsize=6.6)
        ax.set_yticklabels(lab if i == 0 else [""] * len(lab), fontsize=7)
    for i, s in enumerate(sc):
        axes[0].text(tconf[i] + max(tconf) * .02, i, f"{tconf[i]:.1f}s",
                     va="center", fontsize=6.4)
        axes[1].text(s["rmse_m"] + .3, i, f"{s['rmse_m']:.1f}", va="center", fontsize=6.4)
        axes[2].text(s["operator_ask_rate"] * 100 + 1.5, i, f"{s['operator_ask_rate']*100:.0f}",
                     va="center", fontsize=6.4)
    fig.suptitle(T("Bảy kịch bản hiện trường · mỗi kịch bản 8 lần chạy độc lập · "
                   "nhận dạng đúng 100% ở cả bảy",
                   "Seven field scenarios · 8 independent runs each · "
                   "identity correct 100% in all seven"), fontsize=9, y=1.05)
    fig.savefig(out("scenarios")); plt.close(fig)


# ---------------------------------------------------- 7. chống đánh lừa camera
def fig_adversarial():
    d = json.load(open(DATA / "adversarial.json", encoding="utf-8"))
    fig, ax = plt.subplots(figsize=(7.2, 3.0))
    names = [T("Hợp nhất có hạ quyền\nkhi phát hiện mâu thuẫn", "Fusion with conflict\ndown-weighting"),
             T("Hợp nhất cộng đều\n(không phòng vệ)", "Naive equal-weight\nfusion"),
             T("Chỉ dùng camera", "Camera only")]
    vals = [d["defended_acc"] * 100, d["naive_acc"] * 100, d["eo_only_acc"] * 100]
    cols = [OK, WARN, RED]
    ax.barh(range(3), vals, color=cols, height=.55)
    for i, v in enumerate(vals):
        ax.text(v + 1.5, i, f"{v:.1f}%", va="center", fontsize=8, weight="bold")
    ax.set_yticks(range(3)); ax.set_yticklabels(names, fontsize=7.4)
    ax.invert_yaxis(); ax.set_xlim(0, 112); ax.grid(axis="x", alpha=.25)
    ax.set_xlabel(T("nhận dạng đúng khi mục tiêu bị dán nhãn ngụy trang (%)",
                    "correct identity when the target wears an adversarial patch (%)"), fontsize=7.4)
    ax.set_title(T("Camera bị đánh lừa, radar và RF thì không",
                   "The camera is fooled; radar and RF are not"), fontsize=9)
    ax.tick_params(labelsize=6.8)
    fig.savefig(out("adversarial")); plt.close(fig)


def main():
    global L
    for lang in ("vi", "en"):
        L = lang
        fig_architecture()
        fig_signatures()
        fig_rfspec()
        fig_accuracy()
        fig_tracking()
        fig_latency()
        fig_scenarios()
        if (DATA / "adversarial.json").exists():
            fig_adversarial()
        print("figures done:", lang, flush=True)


if __name__ == "__main__":
    main()
