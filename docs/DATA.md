# Thiết kế dữ liệu — Edge AI (bước 3)

> Cập nhật: 22/11/2026. Quyết định nền: PRD mục 7 và Q-5.

## 1. Vì sao không dùng cơ sở dữ liệu

Quy trình chuẩn của dự án ưu tiên PostgreSQL. Ở dự án này **không dùng**, vì:

- Chỉ có **một** loại dữ liệu cần lưu bền: nhật ký quyết định của người trực.
- Dữ liệu chỉ ghi nối đuôi, không bao giờ sửa, khoảng vài chục dòng mỗi ca,
  một trạm.
- Nhật ký cần chứng minh được là **không bị sửa**. Tệp chuỗi băm làm việc
  này trực tiếp, kiểm tra bằng một lệnh và không cần phần mềm nào khác.
- Bớt một dịch vụ là bớt một thứ phải cài, sao lưu, vá lỗi và đặt mật khẩu.

**Khi nào phải đổi sang PostgreSQL:**
- nhiều trạm cùng ghi về một nơi;
- tài khoản riêng cho từng chuyên viên (PRD L-3);
- cần tìm kiếm hoặc thống kê nhật ký thường xuyên.

Khi đó giữ nguyên cột `prev`/`hash` để vẫn phát hiện được sửa dòng.

## 2. Các loại dữ liệu

| Dữ liệu | Nơi lưu | Ai ghi | Ai đọc | Cá nhân? | Giữ |
|---|---|---|---|---|---|
| Nhật ký quyết định | `audit-YYYY-MM.jsonl` trong `logs/` (máy dev) hoặc volume `edge-audit` → `/var/lib/edge` (Docker) | Dịch vụ `app` | Kỹ thuật viên, người kiểm tra (qua `docker compose exec`); dashboard hiện 12 dòng gần nhất | **Có** (mã ca trực) | 12 tháng |
| Mốc dọn | `audit.pruned.json` cùng thư mục | Dịch vụ `backup` | Công cụ kiểm tra | Không | Vĩnh viễn |
| Bản sao lưu | `/backups/YYYY-MM-DD/` (volume `edge-backups` hoặc `EDGE_BACKUP_DIR`) | Dịch vụ `backup` | Kỹ thuật viên | Có (bản chép nhật ký) | 12 tháng |
| Trọng số mô hình | `data/models/*.pt` (trong git, < 1 MB) | Người phát triển (huấn luyện) | `app` | Không | Theo phiên bản |
| Số đo đánh giá | `data/results/*.json` (trong git) | Script đánh giá | `app` (`/api/metrics`), báo cáo | Không | Theo phiên bản |
| Trạng thái đang chạy | RAM của `app` | Engine | Dashboard | Không | Mất khi khởi động lại (cố ý) |

Hệ thống **không** lưu ảnh, video hay dữ liệu thô của cảm biến.

## 3. Cấu trúc một dòng nhật ký

Mỗi dòng là một đối tượng JSON, kết thúc bằng `\n`:

| Trường | Kiểu | Ràng buộc | Ý nghĩa |
|---|---|---|---|
| `ts` | số thực | thời điểm UNIX (giây) | Lúc bấm |
| `frame` | số nguyên | ≥ 0 | Khung xử lý lúc bấm |
| `action` | chuỗi | `xac_nhan` \| `bo_qua` | Quyết định |
| `operator` | chuỗi | 1–32 ký tự `[\w.-]` (không xuống dòng) | Mã ca trực |
| `tid` | số nguyên | 0 … 10⁷ | ID vết bám |
| `kind` | chuỗi | `multirotor` \| `fixed_wing` \| `bird` | Hệ thống nhận dạng là gì |
| `confidence` | số thực | 0 … 1 | Độ tin cậy lúc bấm |
| `evidence` | đối tượng | điểm từng cảm biến | Bằng chứng người trực đã thấy |
| `pos` | mảng 3 số | mét, gốc ở trạm | Vị trí lúc bấm |
| `scenario` | chuỗi | tên kịch bản | Bối cảnh |
| `prev` | 64 hex | = `hash` của dòng trước; dòng đầu = 64 số 0 hoặc mốc dọn | Nối chuỗi |
| `hash` | 64 hex | SHA-256(`prev` + JSON khoá sắp xếp của các trường còn lại) | Chống sửa |

**Khoá và ràng buộc** (thay cho khoá chính, khoá ngoại của cơ sở dữ liệu):
- Khoá duy nhất là `hash`.
- Thứ tự được bảo đảm bằng `prev`.
- Máy chủ chặn hai quyết định cho cùng một vết: trả 409.
- Đầu vào sai kiểu bị từ chối: trả 422.

## 4. Chia tháng, giữ 12 tháng, sao lưu

- Mỗi tháng (UTC) một tệp. Dòng đầu tháng mới nối `prev` vào dòng cuối tháng
  trước, nên chuỗi liền qua các tháng.
- **Dọn:** dịch vụ `backup` mỗi ngày xoá nguyên tệp của tháng cũ hơn 12 tháng
  và ghi băm cuối của phần bị xoá vào `audit.pruned.json`. Ai lén xoá thêm
  một tháng ngoài lần dọn hợp lệ thì công cụ kiểm tra báo đứt chuỗi.
- **Sao lưu:** mỗi ngày một thư mục, kèm `MANIFEST.json` gồm SHA-256 từng
  tệp, số dòng và băm cuối.
  - Nhật ký đang bị sửa thì từ chối sao lưu.
  - Bản sao lưu bị sửa thì từ chối khôi phục.
- **Khôi phục:** đã thử thật trong Docker: xoá volume rồi khôi phục, băm cuối
  trùng với trước khi mất (PRD A-16). Lệnh ở README, mục "Sao lưu nhật ký".
- **"Migration":** không có lược đồ để di chuyển. Nhật ký một tệp của bản cũ
  (`audit.jsonl`) được đọc như đoạn đầu của chuỗi, không cần chuyển đổi.

## 5. Quyền truy cập

| Đối tượng | Quyền |
|---|---|
| Thư mục `/var/lib/edge`, `/backups` | `700`, chủ `edge` (uid 10001) |
| Tệp nhật ký, sao lưu, mốc dọn | `600`, chủ `edge` |
| Kỹ thuật viên / người kiểm tra | Đọc qua `docker compose exec app …` (cần quyền Docker trên máy trạm) |
| Chuyên viên trực | Chỉ thấy 12 quyết định gần nhất trên dashboard |

Rủi ro còn lại về dữ liệu nằm ở [SECURITY.md](SECURITY.md).
