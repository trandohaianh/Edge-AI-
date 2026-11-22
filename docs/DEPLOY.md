# Triển khai và vận hành (bước 9)

> Dành cho kỹ thuật viên trạm. Mục tiêu triển khai đã chốt: **demo Docker
> tại chỗ** (PRD Q-7), một máy, không cloud, không chi phí.
> Trạng thái 22/11/2026: **đã build và chạy thật** trên máy phát triển
> (Docker Desktop, project và cổng riêng). **Chưa triển khai** lên máy trạm
> thật.

## 1. Cần chuẩn bị

| Thứ | Yêu cầu |
|---|---|
| Máy | x86-64, ≥ 4 GB RAM, ≥ 10 GB đĩa trống (ảnh Docker cỡ vài GB vì có PyTorch CPU) |
| Phần mềm | Docker Engine hoặc Docker Desktop, có `docker compose` |
| Mạng | Cổng 443 (và 80 nếu dùng tên miền thật) trong mạng trạm |
| Tên miền | Không bắt buộc. `localhost` dùng chứng chỉ tự ký (trình duyệt cảnh báo) |
| Ổ sao lưu ngoài | USB hoặc ổ mạng để chép bản sao lưu định kỳ (SECURITY R-9) |

## 2. Biến môi trường

Chép `.env.example` thành `.env` ở **gốc repo**. File này **không** commit.

| Biến | Bắt buộc | Ghi chú |
|---|---|---|
| `EDGE_API_TOKEN` | **Có** | Thiếu thì compose dừng ngay. Sinh: `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Giao cho người trực qua kênh riêng, không gửi qua chat nhóm |
| `EDGE_DOMAIN` | Không | `localhost` (mặc định) hoặc tên miền thật |
| `EDGE_HTTP_PORT`, `EDGE_HTTPS_PORT` | Không | Đổi khi 80/443 đã bị dùng |
| `EDGE_BACKUP_DIR` | Không | Thư mục máy chủ cho bản sao lưu; phải thuộc uid 10001 |
| `EDGE_BACKUP_INTERVAL_S` | Không | Mặc định 86400 (1 ngày) |

## 3. Triển khai lần đầu

```bash
git clone <repo> edge-ai && cd edge-ai
cp .env.example .env            # rồi sửa EDGE_API_TOKEN, EDGE_DOMAIN
docker compose -f deploy/docker-compose.yml --env-file .env up -d --build
docker compose -f deploy/docker-compose.yml ps     # app: healthy; backup, caddy: running
```

Sau đó làm **danh sách kiểm tra sau triển khai** ở mục 6.

## 4. Cập nhật lên bản mới (có đường lui)

Dự án không có cơ sở dữ liệu nên **không có migration**. Định dạng nhật ký
tương thích ngược: bản mới đọc được nhật ký của bản cũ.

```bash
# 0. Sao lưu ngay trước khi cập nhật
docker compose -f deploy/docker-compose.yml exec backup \
  python -m edge_ai.api.audit_backup backup --log /var/lib/edge/audit.jsonl --dest /backups
# 1. Giữ lại ảnh đang chạy để có đường lui
docker tag edge-ai:latest edge-ai:rollback
# 2. Lấy mã mới và dựng lại
git pull
docker compose -f deploy/docker-compose.yml --env-file .env up -d --build
# 3. Làm danh sách kiểm tra ở mục 6; người trực nhấn Ctrl+F5 một lần
```

## 5. Quay lại bản cũ (rollback)

Làm khi bản mới không qua được mục 6:

```bash
docker tag edge-ai:rollback edge-ai:latest
docker compose -f deploy/docker-compose.yml --env-file .env up -d --no-build
git checkout <commit cũ>          # để mã nguồn khớp với ảnh đang chạy
```

Nhật ký **không** cần quay lại: các dòng bản mới đã ghi vẫn hợp lệ với bản
cũ. Chỉ khôi phục từ sao lưu khi nhật ký thật sự hỏng (README, mục "Sao lưu
nhật ký"). **Phải dừng `app` trước khi khôi phục.**

## 6. Danh sách kiểm tra sau triển khai

| # | Kiểm | Lệnh / cách | Đạt khi |
|---|---|---|---|
| D-1 | Ba dịch vụ chạy | `docker compose … ps` | `app` healthy; `backup`, `caddy` running |
| D-2 | Sức khoẻ | Mở `https://<domain>/api/health` | `"ok": true`, `"models_trained": true`, `"auth_required": true` |
| D-3 | HTTPS | Mở `https://<domain>` | Có ổ khoá (hoặc cảnh báo tự ký nếu `localhost`) |
| D-4 | Không mở cổng thừa | `docker compose … ps` | Chỉ 80/443 ra ngoài, **không** có 8099 |
| D-5 | Bấm được với mã | Bấm Xác nhận, nhập mã | "Đã ghi quyết định vào nhật ký." |
| D-6 | Không mã thì không bấm được | Thử từ máy khác, nhập mã sai | Bị từ chối |
| D-7 | Nhật ký hợp lệ | `docker compose … exec app python -m edge_ai.api.audit_log /var/lib/edge/audit.jsonl` | "N dòng hợp lệ…" |
| D-8 | Sao lưu chạy | `docker compose … logs backup` | Có dòng "đã sao lưu" |
| D-9 | Quyền tệp | `docker compose … exec app ls -l /var/lib/edge` | `-rw-------  edge` |

## 7. Giám sát hằng ngày (5 phút)

Không dùng hệ thống giám sát riêng (chi phí 0, một máy). Những gì đã có:
- **Docker healthcheck** gọi `/api/health` mỗi 15 s. Vòng xử lý đứng quá 2 s
  thì `app` thành `unhealthy`, và `restart: unless-stopped` dựng lại khi
  container chết.
- **Dashboard** tự báo "mất kết nối máy chủ" bằng băng đỏ.
- **Log:** `docker compose … logs --since 24h app backup`.

Mỗi ngày kỹ thuật viên kiểm:
1. `docker compose … ps`: cả ba đều Up, `app` healthy.
2. `docker compose … logs --since 24h backup | grep -E "đã sao lưu|THẤT BẠI"`:
   phải có "đã sao lưu", không có "THẤT BẠI".
3. `docker compose … logs --since 24h app | grep "khoá"`: có dòng nào nghĩa
   là có người nhập sai mã nhiều lần. Hỏi lại ca trực.

Mỗi tuần: chép bản sao lưu ra ổ ngoài (lệnh ở README).

## 8. CI/CD

- **CI** (`.github/workflows/ci.yml`): lint → test → build Docker + gọi
  `/api/health`. Đã viết, **chưa chạy** vì repo chưa push.
- **CD:** không tự động triển khai, có chủ đích. Máy trạm nằm trong mạng
  riêng, và cập nhật phải có người làm theo mục 4 và mục 6.

## 9. Sự cố thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Xử lý |
|---|---|---|
| `compose up` báo thiếu `EDGE_API_TOKEN` | Chưa có `.env` hoặc thiếu `--env-file .env` | Mục 2 |
| `app` unhealthy | Thiếu trọng số, máy quá tải | `logs app`; kiểm `data/models/` |
| Người trực thấy giao diện cũ | Trình duyệt lưu đệm bản trước 22/11 | Ctrl+F5 |
| "sai mã quá nhiều lần" | Nhập sai 5 lần trong 5 phút | Chờ 5 phút, hoặc `restart app` (xoá bộ đếm) |
| Sao lưu "THẤT BẠI: nhật ký KHÔNG hợp lệ" | Nhật ký bị sửa hoặc hỏng | **Không** xoá gì; giữ nguyên làm bằng chứng, báo người kiểm tra, so với bản sao lưu gần nhất |
| Lệnh có `/var/lib/...` chạy sai trên Git Bash | Git Bash tự đổi đường dẫn | `export MSYS_NO_PATHCONV=1` |
