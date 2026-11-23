# Kế hoạch và kết quả kiểm thử (bước 8)

> Cập nhật: 23/11/2026. Trạng thái dùng đúng các mức của dự án: **đã viết**,
> **đã chạy**, **đã kiểm thử đạt**, **đã triển khai**, **người dùng đã nghiệm
> thu**. Chưa mục nào ở mức "người dùng đã nghiệm thu".

## 1. Tổng quan

| Loại | Cách chạy | Số lượng | Kết quả 22/11/2026 |
|---|---|---|---|
| Đơn vị + tích hợp (pytest) | `python -m pytest` | **104** | 104 đạt trong môi trường cài đúng `requirements.lock` (WSL, ổ Linux, 23/11; gồm 14 test sửa lỗi `test_loi_ro_rang.py` và 8 test hiệu chỉnh `test_calibration.py`). Chạy trên ổ D: qua WSL thì bài quyền tệp 600 hỏng vì ổ đó bỏ qua chmod. CI (82 test) đạt 22/11. Trên Python `E:\` của máy dev: 1 bỏ qua (quyền tệp POSIX), 1 **hỏng có chủ đích** vì máy đó cài numpy 2.4.0 (L-7) |
| Lint + định dạng | `pre-commit run --all-files` | ruff, ruff-format, 7 hook | Sạch |
| CI | GitHub Actions: lint → quét lỗ hổng → test → đầu-cuối → ONNX → build Docker + gọi `/api/health` | 6 job | **Đạt cả 4** trên GitHub ngày 22/11/2026, commit `7155efb` ([run](https://github.com/trandohaianh/Edge-AI-/actions/runs/45011499960)); test chạy trên Linux nên bài quyền tệp cũng đạt. Lần chạy trước: `89e7bf5` (20/11) đạt |
| Đầu-cuối trên trình duyệt | **Tự động** bằng Playwright + Chromium (`backend/tests/e2e`), mục 3 | 6 bài, phủ E-1..E-8 + mã truy cập + CSP | 6 đạt trên Windows, 3 lần liên tiếp (~45 s). Trước đó làm tay, tìm ra 4 lỗi |
| Triển khai thật (Docker) | compose với project và cổng riêng | sao lưu → mất → khôi phục | Đạt (A-16) |
| Hiệu năng | `experiments/evaluate*.py`, `bench_edge.py` | p99 / khung xấu nhất | Đạt trên x86 (A-1, A-2); **chưa đo trên Jetson** |
| Chạy dài (soak) | `experiments/soak.py`, mục 6 | 40 phút, như một ca trực | **Tìm ra L-7** trên máy dev; với bản khoá: đạt |
| ONNX | `experiments/export_onnx.py`, mục 6 | 3 mạng | Cùng kết quả với PyTorch (sai khác ≤ 6e-6) |

## 2. Test tự động theo nhóm

| Nhóm | Tệp | Kiểm cái gì |
|---|---|---|
| Lõi thuật toán | `test_core.py` (20) | Mô phỏng vật lý, EKF, hợp nhất, mâu thuẫn cảm biến |
| Bám nhiều mục tiêu | `test_mtt.py` (13) | GNN, cổng χ², M-of-N, không đổi ID, vết giả, trần mạng nặng |
| Pipeline + máy chủ | `test_pipeline_server.py` (33) | Nạp mô hình an toàn, mất dấu, API, xác thực, chống dò mã, CSRF, CSP, header, nhật ký, quy tắc phụ thuộc |
| Hiệu chỉnh xác suất | `test_calibration.py` (8) | T > 0, ECE không tệ hơn, argmax không đổi, thiếu tệp thì T = 1, pipeline áp T vào logit |
| Nhật ký + sao lưu | `test_audit_backup.py` (13) | Chia tháng, sao lưu/khôi phục, dọn 12 tháng, quyền 600, dòng lệnh tiếng Việt |

**Đối chiếu với các loại kiểm thử của quy trình:**

| Loại | Có chưa | Ghi chú |
|---|---|---|
| Unit | ✅ | `test_core`, `test_mtt` |
| Integration | ✅ | `TestClient` gọi API thật với Engine thật |
| E2E | ✅ tự động | Mục 3. Playwright, chạy trong CI (job `e2e`) |
| Phân quyền | ✅ | Có mã / không mã / sai mã / bị khoá / khác trang / máy khác |
| Responsive | ⚠️ | Chỉ màn hình máy tính (Q-6); có một điểm gãy 980 px, chưa thử nhiều cỡ |
| Xử lý lỗi | ✅ | 401/403/404/409/422/429/503, mất kết nối, đĩa không ghi được (máy chủ) |
| Hiệu năng | ✅ x86 / ❌ Jetson | A-1, A-2, A-13 |
| Sao lưu / khôi phục | ✅ | Test + Docker thật |

## 3. Kịch bản kiểm thử đầu-cuối trên trình duyệt

Lần đầu (22/11) làm tay trên Chromium. Nay các bước được tự động hoá trong
`backend/tests/e2e/test_dashboard_e2e.py`: mỗi bài bật **máy chủ thật**
(uvicorn, nhật ký ở thư mục tạm) và **Chromium thật**, rồi bấm như người trực.
Cột "Bài tự động" ghi bài nào kiểm bước đó.

Đã thử độ nhạy: cố ý bỏ dòng làm mờ khi mất kết nối thì bài `e6_e8` báo lỗi
ngay; trả lại thì đạt.

| # | Bước | Mong đợi | Kết quả | Bài tự động |
|---|---|---|---|---|
| E-1 | Mở dashboard | `● đang chạy`, có vết bám, bản đồ vẽ | Đạt | `e1` |
| E-2 | Bấm **Xác nhận** | "Đã ghi quyết định vào nhật ký."; hàng đổi thành `ĐÃ XÁC NHẬN`; nút khoá | Đạt | `e2_e5` |
| E-3 | Chuyển kịch bản **Nhiều mục tiêu** | 3 drone `CHỜ QUYẾT ĐỊNH`, chim chỉ "đang bám" (không làm phiền người) | Đạt | `e3_e4` |
| E-4 | Chọn vết #7, bấm **Bỏ qua** | Chỉ #7 thành `ĐÃ BỎ QUA` | Đạt | `e3_e4` (vết chờ thứ hai) |
| E-5 | Kiểm nhật ký bằng dòng lệnh | 2 dòng hợp lệ, đúng `tid` và kịch bản | **Lỗi → đã sửa** (L-1) | `e2_e5` |
| E-6 | Tắt máy chủ | Báo mất kết nối, làm mờ số liệu cũ, khoá nút | **Lỗi → đã sửa** (L-2) | `e6_e8` |
| E-7 | Bấm Xác nhận khi mất kết nối | Báo tiếng Việt, nói rõ chưa ghi | **Lỗi → đã sửa** (L-2) | `e6_e8` |
| E-8 | Kết nối lại | Tự trở lại bình thường, không cần tải lại trang | Đạt | `e6_e8` |
| E-9 | Cập nhật giao diện rồi mở lại trang | Trình duyệt lấy bản mới | **Lỗi → đã sửa** (L-3) | test API `test_trang_dashboard_khong_bi_luu_dem_ban_cu` |
| E-10 | Bấm thật trên trình duyệt sau khi thêm chống CSRF | Vẫn ghi được (200) | Đạt | mọi bài bấm nút (Origin do trình duyệt gửi) |
| E-11 | Máy chủ có mã: nhập sai rồi nhập đúng | Mã sai bị từ chối, không ghi gì; mã đúng ghi được; lần sau không hỏi lại; mã không lên URL | Đạt (mới) | `ma_truy_cap…` |
| E-12 | Chèn thử script vào trang | Không chạy (CSP) | Đạt | `csp_chan_script…` |

### Lỗi tìm được và đã sửa (commit `4544bb5`, `4266f4e`)

| # | Lỗi | Hậu quả | Sửa | Test chống tái phát |
|---|---|---|---|---|
| L-1 | Lệnh kiểm tra/sao lưu nhật ký **crash** trên Windows khi đầu ra bị chuyển hướng (cp1252 không in được tiếng Việt) | Kỹ thuật viên không kiểm được nhật ký; sao lưu chạy bằng bộ lập lịch Windows sẽ hỏng | Ép UTF-8 cho đầu ra (`io_utils.utf8_stdio`) | `test_lenh_kiem_tra_in_duoc_tieng_viet_khi_chuyen_huong` |
| L-2 | Mất kết nối nhưng màn hình vẫn như đang chạy, vẫn cho bấm, lỗi tiếng Anh "Failed to fetch" | Người trực có thể quyết dựa trên số liệu cũ | Làm mờ, băng đỏ, khoá nút, báo tiếng Việt | Kiểm thử trình duyệt E-6..E-8 |
| L-3 | Trang `/` không có `Cache-Control`, trình duyệt dùng bản cũ đã lưu đệm | Sau khi cập nhật, người trực vẫn thấy giao diện cũ | `Cache-Control: no-cache` cho `/` | `test_trang_dashboard_khong_bi_luu_dem_ban_cu` |
| L-4 | Rà bảo mật: không đặt mã thì trang lạ trên máy trạm đổi được kịch bản (CSRF) | Kịch bản bị đổi ngoài ý muốn | Từ chối POST có Origin khác Host | `test_lenh_tu_trang_web_khac_bi_tu_choi` |

**Lưu ý vận hành từ L-3:** trình duyệt nào đã lưu bản cũ trước bản sửa thì
cần nhấn **Ctrl+F5** một lần.

### Chạy thật trong Docker sau khi siết (22/11/2026)

Ảnh dựng từ `requirements.lock` (pip kiểm SHA-256 từng gói), chạy compose
với project `edge-ai-test`, cổng 18080/18443, rồi dọn sạch bằng `down -v`.

| # | Kiểm | Kết quả |
|---|---|---|
| K-1 | `/api/health` qua HTTPS | `ok: true`, đủ trọng số, `auth_required: true` |
| K-2 | Header qua Caddy | CSP không có `'unsafe-inline'` cho script; HSTS; `no-cache` cho trang |
| K-3 | POST có mã, Origin đúng trang / trang lạ | 200 / **403** |
| K-4 | Sai mã 5 lần rồi gửi mã đúng; thử giả `X-Forwarded-For` | 401×5 rồi **429**; giả IP vẫn **429** |
| K-5 | Siết container | 3 dịch vụ `ReadonlyRootfs=true`, `CapDrop=ALL`, `no-new-privileges`; trong `app`: ghi `/app` bị từ chối, `CapEff=0` |
| K-6 | Sao lưu và quyền | "đã sao lưu" mỗi 15 s; tệp `600`; thư mục bản sao lưu `700` (**lỗi L-5 → đã sửa**) |
| K-7 | Log | Caddy báo lỗi cài CA vào hệ thống (**L-6 → đã sửa** bằng `skip_install_trust`); sau sửa: 0 lỗi |

| # | Lỗi | Sửa | Test |
|---|---|---|---|
| L-5 | Thư mục của từng bản sao lưu có quyền `755` (tệp bên trong vẫn `600`) | `chmod 700` khi tạo | `test_quyen_tep_nhat_ky_va_sao_luu_la_600` (thêm kiểm thư mục) |
| L-6 | Caddy cố cài chứng chỉ gốc vào hệ điều hành của container, ghi lỗi mỗi lần chạy | `skip_install_trust` trong `Caddyfile` | Chạy thật: 0 lỗi |

## 4. Chưa kiểm thử (nói rõ để không hiểu nhầm)

- Đo thời gian trên Jetson Orin (A-13, đã chấp nhận là giới hạn).
- `bash deploy/lock-deps.sh` ở chế độ sinh lại: tệp khoá hiện có được sinh
  bằng đúng các lệnh đó, nhưng chạy thẳng script này mới thử ở chế độ `audit`.
- Trình duyệt ngoài Chromium (Firefox, Safari).
- Giao diện khi thiếu trọng số, khi đĩa đầy (mới kiểm ở phía máy chủ).
- Chạy liên tục **7 ngày** (mới chạy 40 phút, mục 6) và sao lưu qua đêm thật
  với chu kỳ 24 h. Docker mới thử với chu kỳ 15 s.
- TensorRT FP16 trên Jetson (bản ONNX đã sẵn, mục 6).
- Kiểm thử chấp nhận với người dùng thật (chuyên viên trực).

## 5. Cách chạy lại

```bash
python -m pytest                              # 104 test, ~4 phút trên laptop
python -m edge_ai.experiments.calibrate       # trong backend/: học T, ghi ECE trước/sau
python -m edge_ai.experiments.soak --minutes 40   # trong backend/: chạy dài, cần psutil
python -m edge_ai.experiments.export_onnx         # trong backend/: cần extra tools
# đầu-cuối (một lần: pip install -e ".[e2e]" && python -m playwright install chromium)
EDGE_E2E=1 python -m pytest backend/tests/e2e  # 6 bài, ~45 s
pre-commit run --all-files                    # lint
python -m edge_ai.experiments.evaluate_mtt    # trong backend/: hiệu năng nhiều mục tiêu
```

## 6. Chạy dài và xuất ONNX (22–23/11/2026)

### Chạy dài (soak test)

`experiments/soak.py` bật máy chủ thật rồi dùng nó như một ca trực:
- hỏi trạng thái mỗi 0,5 s (như dashboard);
- bấm Xác nhận / Bỏ qua mỗi 20 s;
- đổi kịch bản mỗi 2 phút, vòng qua cả 7 kịch bản, có "Nhiều mục tiêu".

Nhật ký ghi ở thư mục tạm. Kết quả lưu vào `data/results/soak.json`.

| Lần | Môi trường | Bộ nhớ | Quyết định | Lỗi 5xx | Khung đứng lâu nhất | Kết luận |
|---|---|---|---|---|---|---|
| 1 | Windows, Python `E:\` của máy dev (**numpy 2.4.0**) | 262 → 722 MB, tăng đều khoảng **550 MB/giờ** | 87/87 | 0 | 0,15 s | **Không đạt → lỗi L-7** |
| 2 | WSL, cài đúng `requirements.lock` (numpy 2.5.5, torch 2.15.0+cpu, giống Docker) | 409 → 409 MB, đứng yên (max 415) | 102/102 | 0 | 0,11 s | **Đạt** cả 5 tiêu chí |

Ghi chú lần 2: thời gian trả lời `/api/state` có p50 6 ms, p99 54 ms, nhưng có
một lần lên tới 1,8 s. Vòng xử lý không bị ảnh hưởng (khung đứng lâu nhất
0,11 s), nên đó là độ trễ phía HTTP. Chưa rõ nguyên nhân: có thể do WSL hoặc
do lúc đổi kịch bản. Cần theo dõi khi chạy 7 ngày.

| # | Lỗi | Hậu quả | Sửa | Test chống tái phát |
|---|---|---|---|---|
| L-7 | numpy **2.4.0** rò bộ nhớ ở mỗi lần gọi `np.eye` / gán qua `.flat` (EKF gọi mỗi khung). Đã tách riêng: 300.000 lần `np.eye(6)` giữ lại 818 MB trên 2.4.0, 0 MB trên 2.5.5. Mã dự án không có lỗi | Chạy vài ngày là hết RAM. Docker và CI dùng tệp khoá (2.5.5) nên không bị, nhưng ai cài tay numpy 2.4.0 thì bị | `pyproject.toml`: `numpy>=1.26,!=2.4.0` | `test_numpy_khong_ro_bo_nho_o_ma_tran_don_vi` (hỏng trên 2.4.0, đạt trên 2.5.5) |

**Bài học:** phải chạy và đo bằng **đúng các phiên bản trong tệp khoá**. Python
`E:\` của máy dev đang lệch tệp khoá (numpy 2.4.0). Nên nâng lên 2.5.5 hoặc
dùng một venv cài từ `requirements.lock`.

### Xuất ONNX (hướng dự phòng cho Jetson, A-2)

`experiments/export_onnx.py` xuất cả 3 mạng sang ONNX, rồi so đầu ra với
PyTorch trên 15 lô ngẫu nhiên (batch 1, 2 và 4). Với 2 bộ phân loại, kiểm thêm
là lớp thắng phải trùng. Tầng STFT số phức của mạng RF được thay bằng bản số
thực tương đương; có test `test_onnx_export.py` cho phần này. Job `onnx` trong
CI chạy lại mỗi lần push.

| Mạng | Tệp ONNX | Sai khác lớn nhất | PyTorch p50 | ONNX Runtime p50 |
|---|---|---|---|---|
| RF (STFT + CNN) | 554 KB | 6,2e-6 | 3,6 ms | 1,6 ms |
| Micro-Doppler CNN | 284 KB | 3,8e-6 | 2,9 ms | 0,75 ms |
| Transformer quỹ đạo | 317 KB | 2,7e-7 | 0,54 ms | 0,16 ms |

Đo trên CPU x86 trong WSL, 2 luồng, batch 1, 23/11/2026
(`data/results/onnx_export.json`). Số tuyệt đối dao động theo tải máy; tỉ lệ
ONNX Runtime nhanh hơn khoảng 2–4 lần thì ổn định qua 3 lần đo. **Chưa** có
số trên Jetson. Ở đó bước tiếp theo là `trtexec --onnx=... --fp16`.

## 7. Đo lại theo quyết định của chủ dự án (E1–E4, 23/11/2026)

Mọi số ở mục này đo trên **dữ liệu mô phỏng** của chính dự án
(`backend/edge_ai/sim/`), không phải dữ liệu thật. Danh sách bộ dữ liệu thật
ứng viên: [DATASETS_CANDIDATES.md](DATASETS_CANDIDATES.md) (E3, chưa tải).

### E1-A. Temperature scaling cho hai bộ phân loại

`experiments/calibrate.py` sinh lại đúng tập kiểm định và tập test của lúc huấn
luyện (cùng hạt giống). T học bằng cực tiểu NLL trên **tập kiểm định**
(2 000 mẫu), số đo dưới đây trên **tập test** tách riêng (2 800 mẫu). ECE dùng
15 khoảng đều. T lưu ở `data/models/calibration.json`, cạnh trọng số;
`load_models` đọc và `md_logp_batch` / `rf_logp_batch` dùng
`softmax(logit / T)`. Thiếu tệp thì T = 1, tức là đúng hành vi cũ.

| Bộ phân loại | T | ECE trước → sau | NLL trước → sau | Độ chính xác |
|---|---|---|---|---|
| RF (STFT + CNN) | 0,615 | 0,0437 → **0,0098** | 0,132 → 0,107 | 0,9643 → 0,9643 |
| Micro-Doppler CNN | 0,690 | 0,0345 → **0,0125** | 0,124 → 0,102 | 0,9536 → 0,9536 |

T < 1: hai mạng đang **rụt rè** chứ không tự tin quá mức. Nguyên nhân hợp lý
là `label_smoothing=0.05` lúc huấn luyện kéo xác suất lớn nhất xuống. Sau hiệu
chỉnh, xác suất đưa vào bộ hợp nhất nhọn hơn; trần 4 nats mỗi cảm biến
(`fusion.PER_SENSOR_CAP`) vẫn giữ nguyên. Số liệu: `data/results/calibration.json`.
Bản ONNX (mục 6) xuất logit, nên nếu sau này chạy bằng ONNX Runtime thì vẫn
phải chia cho T sau mạng.

### E2-A. Cổng χ² của EKF: đã đo, **CHƯA đổi** (chờ chủ dự án quyết)

Thay đổi đã thử: trong `EKF.update`, ngưỡng `gate * len(z)` (gate = 16, tức
16 / 32 / 48 / 64 cho d = 1..4) đổi thành phân vị χ² 99% theo d = len(z)
(`scipy.stats.chi2.ppf(0.99, d)`: 6,63 / 9,21 / 11,34 / 13,28), ngưỡng cứu vết
của `mtt.py` giữ nguyên giá trị tuyệt đối. Đo trước/sau bằng đúng kịch bản và
hạt giống của `evaluate_mtt.main` (5 lần × 200 khung) và `evaluate.main`
(8 lần × 220 khung). "Vết đứt" = số lần một mục tiêu đang được bám (trong
50 m) ở khung k−1 mà không được bám ở khung k. Số liệu đầy đủ:
`data/results/ekf_gate_compare.json`.

**Nhiều mục tiêu (OSPA, c = 100 m):**

| Kịch bản | OSPA trước → sau | Độ phủ | Đổi ID | Vết đứt | Vết giả/khung | EKF loại số đo |
|---|---|---|---|---|---|---|
| M1 · 3 drone + 1 chim | 1,115 → 1,180 m (+5,8%) | 1,0 → 1,0 | 0 → 0 | 0 → 0 | 0 → 0 | 0% → 1,3% |
| M2 · 2 drone sát nhau | 1,677 → 1,567 m (−6,6%) | 1,0 → 1,0 | 0 → 0 | 0 → 0 | 0,007 → 0 | 0% → 1,6% |
| M3 · bầy 6 drone, mưa | 1,405 → 1,456 m (+3,6%) | 1,0 → 1,0 | 0 → 0 | 0 → 0 | 0 → 0 | 0% → 2,0% |
| M4 · 2 drone + 2 chim, sương đêm | 3,540 → 3,768 m (+6,4%) | 1,0 → 1,0 | 0 → 0 | 0 → 0 | 0 → 0 | 0% → 2,2% |

**Một mục tiêu (RMSE vị trí, bỏ 20 khung đầu):**

| Kịch bản | RMSE trước → sau | EKF loại số đo |
|---|---|---|
| S1 · trời quang | 9,07 → 16,14 m (**+78%**) | 0,2% → 5,1% |
| S2 · đêm + sương mù | 9,09 → 9,87 m (+8,5%) | 0% → 3,1% |
| S3 · nhiễu RF | 8,18 → 9,49 m (+16%) | 0,1% → 5,3% |
| S4 · mưa to | 5,81 → 8,91 m (**+53%**) | 0,7% → 8,4% |
| S5 · chim | 13,70 → 31,96 m (**+133%**) | 0% → 9,9% |
| S6 · dán nhãn ngụy trang | 0,91 → 2,50 m (**+173%**) | 0% → 3,9% |
| S7 · mất dấu 4 s | 13,58 → 15,62 m (+15%) | 0% → 3,7% |

Nhận dạng (độ chính xác phân loại) không đổi ở mọi kịch bản.

**Kết luận:** bám nhiều mục tiêu gần như không đổi (OSPA trong ±7%, không vết
đứt, không đổi ID), nhưng bám một mục tiêu **xấu đi rõ rệt** (RMSE +8% đến
+173%). Theo điều kiện của quyết định E2-A, thay đổi hành vi **không được
commit**; mã vẫn dùng `gate * len(z)`.

Chẩn đoán: nếu bộ lọc nhất quán (sai số đúng như P và R khai báo) thì cổng
99% chỉ loại khoảng 1% số đo đúng. Đo được 3–10% trong bài một mục tiêu,
nghĩa là bộ lọc **tự tin quá mức** (P hoặc R nhỏ hơn sai số thật; mục tiêu
cơ động mạnh hơn `sigma_a = 6 m/s²`, hoặc nhiễu mô phỏng có đuôi dày). Cổng
cũ rộng đã che vấn đề đó. Bài nhiều mục tiêu ít bị vì `mtt.py` đã lọc liên kết
bằng cổng 99,9% riêng và có cơ chế cứu vết. Transformer quỹ đạo cũng được huấn
luyện trên trạng thái EKF với cổng cũ (`training/train_traj_ekf.py`).

Hướng cho chủ dự án chọn: (1) giữ cổng cũ và ghi rõ lý do (E2-B); (2) đổi cổng
**kèm** chỉnh nhất quán bộ lọc (kiểm NIS, tăng `sigma_a` hoặc R), rồi đo lại;
(3) dùng phân vị cao hơn, ví dụ 99,9% hoặc 99,99%, rồi đo lại.
