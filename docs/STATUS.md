# Tình trạng dự án theo quy trình 10 bước

> Cập nhật: 22/11/2026, sau khi merge PR #1 vào `main` (`1514fb2`).
> Các mức trạng thái: **đã viết** → **đã chạy** → **đã kiểm thử đạt** →
> **đã triển khai** → **người dùng đã nghiệm thu**. Mỗi ô ghi mức cao nhất
> **có bằng chứng**. Chưa bước nào đạt mức "đã triển khai" lên máy trạm thật
> hay "người dùng đã nghiệm thu".

## 1. Bảng tổng hợp

| Bước | Đầu ra | Trạng thái | Còn thiếu | Ai làm phần thiếu |
|---|---|---|---|---|
| 1. Yêu cầu | [PRD.md](PRD.md) 1.4: MVP F-1..F-15, tiêu chí A-1..A-17, quyết định Q-2..Q-7 | Đã viết, chủ dự án đã chốt Q-2..Q-7 | **Q-1 (hạn nộp/bảo vệ) còn mở** | Chủ dự án |
| 2. Kiến trúc | [ARCHITECTURE.md](ARCHITECTURE.md): sơ đồ, lý do chọn công nghệ | Đã viết, khớp mã | — | — |
| 3. Dữ liệu | [DATA.md](DATA.md): nhật ký JSONL chuỗi băm theo tháng, sao lưu, khôi phục, giữ 12 tháng | Đã kiểm thử đạt (test + Docker thật) | Không có CSDL, theo thiết kế. PostgreSQL chỉ cần khi làm tài khoản riêng (L-3) | Chủ dự án quyết L-3 |
| 4. Giao diện | [UI.md](UI.md): màn hình, luồng, trạng thái lỗi/trống/mất kết nối | Đã kiểm thử đạt, **tự động** (Playwright) | Chưa có chuyên viên trực thật dùng thử. Chỉ màn hình máy tính (Q-6) | Chủ dự án + người dùng thật |
| 5. Khởi tạo dự án | git, README, `.gitignore`, `.env.example`, ruff, pre-commit, CI, `requirements.lock` | Đã kiểm thử đạt (CI) | — | — |
| 6. Tính năng MVP | F-1..F-15 | Đã kiểm thử đạt (mô phỏng, x86) | Dữ liệu cảm biến thật (P3) | Cần dữ liệu / phần cứng |
| 7. Bảo mật | [SECURITY.md](SECURITY.md): S-1..S-21, rủi ro còn lại R-1..R-11, dữ liệu cá nhân | Đã kiểm thử đạt | R-1 (mã dùng chung) chờ L-3; phần pháp lý cần người có chuyên môn xác nhận | Chủ dự án / GVHD |
| 8. Kiểm thử | [TEST_PLAN.md](TEST_PLAN.md) | 82 test đơn vị + tích hợp, 6 bài đầu-cuối, chạy dài 40 phút đạt, ONNX khớp PyTorch, CI 6 job | **Đo trên Jetson (A-13)**; chạy liên tục 7 ngày; kiểm thử chấp nhận với người dùng thật | Cần Jetson / máy chạy 7 ngày / người dùng |
| 9. Triển khai | [DEPLOY.md](DEPLOY.md): Docker + Caddy HTTPS, sao lưu, giám sát, rollback, CI | Đã chạy thật trên máy phát triển (project và cổng riêng) | **Chưa triển khai lên máy trạm thật** | Chủ dự án: máy, mạng, quyết định deploy |
| 10. Bảo trì | [MAINTENANCE.md](MAINTENANCE.md): việc định kỳ, danh sách cải tiến P1–P3 | Đã viết | — | — |

## 2. Việc làm được trên máy phát triển: đã làm hết

| Việc | Kết quả | Bằng chứng |
|---|---|---|
| Kiểm thử đầu-cuối tự động (Playwright) | 6 bài đạt, job `e2e` trong CI | `backend/tests/e2e/`, TEST_PLAN mục 3 |
| Chạy dài (soak) | **Tìm ra lỗi L-7**: numpy 2.4.0 trên máy dev rò bộ nhớ khoảng 550 MB/giờ. Với đúng bản trong tệp khoá (numpy 2.5.5): 40 phút, bộ nhớ đứng yên khoảng 409 MB, 102/102 quyết định ghi được, không lỗi 5xx, vòng xử lý không đứng. Đã chặn numpy 2.4.0 và thêm test | `data/results/soak.json`, TEST_PLAN mục 6 |
| Xuất ONNX cho Jetson | Cả 3 mạng xuất được, sai khác ≤ 6e-6 so với PyTorch. ONNX Runtime nhanh hơn khoảng 2–4 lần trên CPU x86. TensorRT FP16 phải làm trên Jetson | `data/results/onnx_export.json`, job `onnx` trong CI |
| CI trên `main` sau merge `1514fb2` | Đạt cả 5 job ([run](https://github.com/trandohaianh/Edge-AI-/actions/runs/45031588730)) | GitHub Actions |

## 3. Việc chờ chủ dự án (không tự làm được)

| # | Việc | Vì sao cần chủ dự án | Cần gì |
|---|---|---|---|
| C-1 | Hạn nộp / bảo vệ khoá luận (Q-1) | Để xếp thứ tự các việc còn lại | Một ngày cụ thể |
| C-2 | Đo trên Jetson Orin (A-13) | Cần phần cứng. Lệnh đo đã sẵn: `bench_edge`, `evaluate_mtt`, `export_onnx` | Một máy Jetson, khoảng 1 ngày |
| C-3 | Triển khai lên máy trạm thật | Deploy production phải có chủ dự án đồng ý; cần máy và mạng của trạm | Máy x86 ≥ 4 GB RAM có Docker; quyết định dùng `localhost` hay tên miền |
| C-4 | Chạy liên tục 7 ngày | Cần một máy để chạy nền suốt 7 ngày | Lệnh: `python -m edge_ai.experiments.soak --minutes 10080` |
| C-5 | Kiểm thử chấp nhận với chuyên viên trực | Cần người dùng thật | 1–2 buổi dùng thử theo TEST_PLAN mục 3 |
| C-6 | Sinh lại DOCX/PDF/slide theo số mới | Tài liệu nộp là của chủ dự án | — |
| C-7 | Có làm tài khoản riêng (L-3, kéo theo PostgreSQL) không | Đổi kiến trúc + nghĩa vụ dữ liệu cá nhân | Quyết định có / không |
| C-8 | Phím tắt và âm báo cho người trực (P3) | Đổi cách người trực ra quyết định; bước 4 yêu cầu chủ dự án duyệt thiết kế | Duyệt: phím nào, có cho phím tắt bấm Xác nhận không |

**Ranh giới giữ nguyên:** hệ thống chỉ giám sát và hỗ trợ quyết định. Không
có chức năng điều khiển khí tài hay gửi lệnh ra ngoài (PRD A-12). Mọi việc ở
trên đều không thay đổi điều này.
