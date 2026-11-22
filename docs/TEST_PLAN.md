# Kế hoạch và kết quả kiểm thử (bước 8)

> Cập nhật: 22/11/2026. Trạng thái dùng đúng các mức của dự án: **đã viết**,
> **đã chạy**, **đã kiểm thử đạt**, **đã triển khai**, **người dùng đã nghiệm
> thu**. Chưa mục nào ở mức "người dùng đã nghiệm thu".

## 1. Tổng quan

| Loại | Cách chạy | Số lượng | Kết quả 22/11/2026 |
|---|---|---|---|
| Đơn vị + tích hợp (pytest) | `python -m pytest` | **79** | 78 đạt trên Windows, 1 bỏ qua (quyền tệp POSIX); bài đó đạt trong WSL |
| Lint + định dạng | `pre-commit run --all-files` | ruff, ruff-format, 7 hook | Sạch |
| CI | GitHub Actions: lint → test → build Docker + gọi `/api/health` | 3 job | Đã viết; **chưa chạy trên GitHub** vì chưa push |
| Đầu-cuối trên trình duyệt | Thủ công có kịch bản, mục 3 | 9 bước | Đạt sau khi sửa 4 lỗi |
| Triển khai thật (Docker) | compose với project và cổng riêng | sao lưu → mất → khôi phục | Đạt (A-16) |
| Hiệu năng | `experiments/evaluate*.py`, `bench_edge.py` | p99 / khung xấu nhất | Đạt trên x86 (A-1, A-2); **chưa đo trên Jetson** |

## 2. Test tự động theo nhóm

| Nhóm | Tệp | Kiểm cái gì |
|---|---|---|
| Lõi thuật toán | `test_core.py` (20) | Mô phỏng vật lý, EKF, hợp nhất, mâu thuẫn cảm biến |
| Bám nhiều mục tiêu | `test_mtt.py` (13) | GNN, cổng χ², M-of-N, không đổi ID, vết giả, trần mạng nặng |
| Pipeline + máy chủ | `test_pipeline_server.py` (33) | Nạp mô hình an toàn, mất dấu, API, xác thực, chống dò mã, CSRF, CSP, header, nhật ký, quy tắc phụ thuộc |
| Nhật ký + sao lưu | `test_audit_backup.py` (13) | Chia tháng, sao lưu/khôi phục, dọn 12 tháng, quyền 600, dòng lệnh tiếng Việt |

**Đối chiếu với các loại kiểm thử của quy trình:**

| Loại | Có chưa | Ghi chú |
|---|---|---|
| Unit | ✅ | `test_core`, `test_mtt` |
| Integration | ✅ | `TestClient` gọi API thật với Engine thật |
| E2E | ✅ thủ công | Mục 3. Chưa tự động hoá (cần Playwright, phải tải trình duyệt) |
| Phân quyền | ✅ | Có mã / không mã / sai mã / bị khoá / khác trang / máy khác |
| Responsive | ⚠️ | Chỉ màn hình máy tính (Q-6); có một điểm gãy 980 px, chưa thử nhiều cỡ |
| Xử lý lỗi | ✅ | 401/403/404/409/422/429/503, mất kết nối, đĩa không ghi được (máy chủ) |
| Hiệu năng | ✅ x86 / ❌ Jetson | A-1, A-2, A-13 |
| Sao lưu / khôi phục | ✅ | Test + Docker thật |

## 3. Kịch bản kiểm thử đầu-cuối trên trình duyệt

Chạy trên trình duyệt Chromium tích hợp, máy chủ cục bộ, nhật ký ở thư mục tạm.

| # | Bước | Mong đợi | Kết quả |
|---|---|---|---|
| E-1 | Mở dashboard | `● đang chạy`, có vết bám, bản đồ vẽ | Đạt |
| E-2 | Bấm **Xác nhận** | "Đã ghi quyết định vào nhật ký."; hàng đổi thành `ĐÃ XÁC NHẬN`; nút khoá | Đạt |
| E-3 | Chuyển kịch bản **Nhiều mục tiêu** | 3 drone `CHỜ QUYẾT ĐỊNH`, chim chỉ "đang bám" (không làm phiền người) | Đạt |
| E-4 | Chọn vết #7, bấm **Bỏ qua** | Chỉ #7 thành `ĐÃ BỎ QUA` | Đạt |
| E-5 | Kiểm nhật ký bằng dòng lệnh | 2 dòng hợp lệ, đúng `tid` và kịch bản | **Lỗi → đã sửa** (L-1) |
| E-6 | Tắt máy chủ | Báo mất kết nối, làm mờ số liệu cũ, khoá nút | **Lỗi → đã sửa** (L-2) |
| E-7 | Bấm Xác nhận khi mất kết nối | Báo tiếng Việt, nói rõ chưa ghi | **Lỗi → đã sửa** (L-2) |
| E-8 | Kết nối lại | Tự trở lại bình thường, không cần tải lại trang | Đạt |
| E-9 | Cập nhật giao diện rồi mở lại trang | Trình duyệt lấy bản mới | **Lỗi → đã sửa** (L-3) |
| E-10 | Bấm thật trên trình duyệt sau khi thêm chống CSRF | Vẫn ghi được (200) | Đạt |

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
- CI trên GitHub: chưa push nên chưa chạy lần nào (kể cả job `audit` mới).
- `bash deploy/lock-deps.sh` ở chế độ sinh lại: tệp khoá hiện có được sinh
  bằng đúng các lệnh đó, nhưng chạy thẳng script này mới thử ở chế độ `audit`.
- Trình duyệt ngoài Chromium (Firefox, Safari).
- Dashboard ở chế độ có mã truy cập trên trình duyệt thật: luồng hỏi mã dùng
  `prompt()`, mới kiểm qua API.
- Giao diện khi thiếu trọng số, khi đĩa đầy (mới kiểm ở phía máy chủ).
- Chạy liên tục nhiều ngày: rò bộ nhớ, sao lưu qua đêm thật với chu kỳ 24 h.
  Docker mới thử với chu kỳ 15 s.
- Kiểm thử chấp nhận với người dùng thật (chuyên viên trực).

## 5. Cách chạy lại

```bash
python -m pytest                              # 79 test, ~4 phút trên laptop
pre-commit run --all-files                    # lint
python -m edge_ai.experiments.evaluate_mtt    # trong backend/: hiệu năng nhiều mục tiêu
```
