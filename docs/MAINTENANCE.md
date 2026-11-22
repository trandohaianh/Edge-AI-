# Kế hoạch bảo trì và danh sách cải tiến (bước 10)

> Cập nhật: 22/11/2026. Ưu tiên P1 (nên làm trước khi đem lên trạm thật),
> P2 (nên làm trong vài tháng đầu), P3 (khi có điều kiện).

## 1. Việc định kỳ

| Tần suất | Việc | Ai | Tài liệu |
|---|---|---|---|
| Hằng ngày | Kiểm 3 dịch vụ chạy, sao lưu "đã sao lưu", không có cảnh báo khoá mã | Kỹ thuật viên | DEPLOY mục 7 |
| Hằng tuần | Chép bản sao lưu ra USB / ổ mạng | Kỹ thuật viên | README "Sao lưu nhật ký" |
| Hằng tháng | Kiểm toàn bộ chuỗi băm; thử khôi phục một bản sao lưu vào thư mục tạm (`verify-snapshot`) | Người kiểm tra | DATA mục 4 |
| Hằng tháng | Quét lỗ hổng: `bash deploy/lock-deps.sh audit`. Có lỗ hổng thì nâng bản: `bash deploy/lock-deps.sh` | Người phát triển | SECURITY R-4 |
| Hằng tháng | Cập nhật ảnh nền: lấy digest mới của `python:3.12-slim` và `caddy` (`docker pull …` rồi `docker inspect --format '{{index .RepoDigests 0}}' …`), sửa `deploy/Dockerfile` và `deploy/docker-compose.yml`, chạy lại test, triển khai theo DEPLOY mục 4 | Người phát triển | DEPLOY mục 4–6 |
| Mỗi 3 tháng | Đổi `EDGE_API_TOKEN`; đổi ngay khi có người rời ca | Trưởng trạm | DEPLOY mục 2 |
| Khi đổi mô hình | Chạy lại toàn bộ đánh giá, so số với PRD mục 9 trước khi thay trọng số | Người phát triển | README "Sinh lại toàn bộ số liệu" |

## 2. Danh sách cải tiến theo ưu tiên

| Ưu tiên | Việc | Lý do | Công sức ước lượng |
|---|---|---|---|
| **P1** | Đo trên Jetson Orin thật (`bench_edge`, `evaluate_mtt`) | Câu hỏi lớn nhất còn mở của đề tài (A-13) | 1 ngày nếu có máy |
| ~~**P1**~~ ✅ 22/11 | Push lên GitHub để CI chạy | Đã push nhánh `audit/danh-gia-phat-trien` lên `trandohaianh/Edge-AI-`; CI đạt cả 4 job | — |
| ~~**P1**~~ ✅ 22/11 | Khoá phiên bản phụ thuộc (`pip-compile`) và thêm `pip-audit` vào CI | Bản dựng lặp lại được; biết khi thư viện có lỗ hổng (SECURITY R-4) | Nửa ngày |
| **P1** | Sinh lại DOCX/PDF/slide theo số mới | Tài liệu nộp đang dùng số cũ | Chủ dự án làm |
| ~~P2~~ ✅ 22/11 | Siết container: `read_only`, `cap_drop: ALL`, `no-new-privileges`; ghim digest ảnh | SECURITY R-5, R-7 | Nửa ngày + chạy thử Docker |
| ~~P2~~ ✅ 22/11 | Tách JS khỏi `index.html`, bỏ `'unsafe-inline'` trong CSP | SECURITY R-3 | Nửa ngày |
| ~~P2~~ ✅ 22/11 | Kiểm thử đầu-cuối tự động bằng Playwright, cho vào CI | Đã có 6 bài trong `backend/tests/e2e`, job `e2e` trong CI (TEST_PLAN mục 3) | — |
| P2 | Chạy liên tục 7 ngày: theo dõi bộ nhớ, sao lưu thật mỗi 24 h | Chưa thử chạy dài (TEST_PLAN mục 4) | 7 ngày chạy nền |
| P2 | Xuất hai CNN sang ONNX Runtime / TensorRT FP16 nếu Jetson chậm | Hướng dự phòng cho A-2 với 6–10 mục tiêu | 2–3 ngày |
| P3 | Tài khoản riêng cho từng chuyên viên (L-3); khi đó chuyển nhật ký sang PostgreSQL, giữ cột băm | SECURITY R-1; kéo theo nghĩa vụ dữ liệu cá nhân (SECURITY mục 4) | 1–2 tuần |
| P3 | JPDA/MHT cho quỹ đạo cắt nhau | Giới hạn của GNN (ARCHITECTURE mục 5) | 1–2 tuần |
| P3 | Dữ liệu thật: DroneRF/RFUAV cho RF, radar FMCW giá rẻ cho micro-Doppler, YOLO nhỏ cho EO | Hiện toàn bộ là mô phỏng | Nhiều tuần |
| P3 | Phím tắt, âm báo vết mới chờ quyết định | Giảm thời gian phản ứng của người trực (UI mục 5) | 1 ngày |

## 3. Quy tắc khi sửa về sau

1. Mọi thay đổi đi qua quy trình 10 bước. Không sửa thẳng trên máy trạm.
2. Sửa lỗi thì viết test tái hiện lỗi trước, sửa sau.
3. Không đổi định dạng dòng nhật ký theo cách làm hỏng chuỗi băm cũ. Muốn
   thêm trường thì chỉ **thêm**, không đổi tên hay xoá trường.
4. Trước khi push: `pre-commit run --all-files` và `python -m pytest` phải
   sạch.
5. Ghi lại thay đổi lớn vào `reports/` và cập nhật PRD mục 9 nếu đổi kết quả
   nghiệm thu.
