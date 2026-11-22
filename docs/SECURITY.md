# Bảo mật — checklist và rủi ro còn lại (bước 7)

> Rà ngày 22/11/2026 trên nhánh `audit/danh-gia-phat-trien`. "Có test"
> nghĩa là có bài kiểm thử tự động trong `backend/tests/`, chạy được bằng
> `python -m pytest`.

## 1. Mô hình mối đe doạ (ngắn)

- **Tài sản cần bảo vệ:**
  1. Tính toàn vẹn của nhật ký quyết định: ai đã xác nhận hay bỏ qua cái gì,
     lúc nào.
  2. Quyền ra quyết định: chỉ người trực mới được bấm.
  3. Mã ca trực (dữ liệu cá nhân).
- **Kẻ tấn công đáng tính:**
  - người trong mạng trạm nhưng không có mã;
  - trang web lạ mở trên máy trạm;
  - người có quyền vào máy nhưng muốn sửa hoặc xoá nhật ký.
- **Ngoài phạm vi:** kẻ có quyền root hoặc Docker trên máy trạm (đọc và sửa
  được mọi thứ), tấn công vật lý, tấn công vào cảm biến thật (đang dùng mô
  phỏng).

## 2. Checklist

| # | Hạng mục | Tình trạng | Bằng chứng |
|---|---|---|---|
| S-1 | Bí mật không nằm trong mã, `.env` không vào git, không vào ảnh Docker | ✅ | `.gitignore`, `.dockerignore`, `.env.example` chỉ có chỗ trống; pre-commit `detect-private-key` |
| S-2 | Lệnh ghi (POST) cần mã truy cập; không đặt mã thì chỉ máy chủ được ghi | ✅ Có test | `test_ma_truy_cap_khi_duoc_bat`, `test_khong_dat_ma_thi_chi_may_chu_moi_dieu_khien_duoc` |
| S-3 | So sánh mã chống đo thời gian (`hmac.compare_digest`) | ✅ | `server.py`, hàm `require_token` |
| S-4 | **Chống dò mã:** sai 5 lần trong 5 phút thì khoá IP đó 5 phút (cả mã đúng cũng bị từ chối); IP khác không bị ảnh hưởng | ✅ Có test (mới, 22/11) | `api/auth.py`, `test_sai_ma_nhieu_lan_thi_bi_khoa_tam`, `test_bo_chan_do_ma_het_han_va_xoa_khi_dung` |
| S-5 | **Chống CSRF:** POST từ trang web khác (Origin ≠ Host) bị từ chối | ✅ Có test (mới, 22/11) | `test_lenh_tu_trang_web_khac_bi_tu_choi`; đã thử trình duyệt thật vẫn bấm được |
| S-6 | Kiểm tra đầu vào: hành động chỉ 2 giá trị, mã ca giới hạn ký tự và độ dài, ID trong khoảng | ✅ Có test | `test_dau_vao_sai_bi_tu_choi` |
| S-7 | Chống XSS: mọi chuỗi từ máy chủ được thoát (`esc`) trước khi chèn HTML; CSP `default-src 'self'` | ✅ một phần | Xem R-3 |
| S-8 | Header bảo mật: `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, CSP, HSTS (Caddy), `no-store` cho API | ✅ Có test | `test_kich_ban_metrics_header_va_health` |
| S-9 | HTTPS: Caddy tự lo chứng chỉ; cổng ứng dụng không mở ra ngoài | ✅ Đã chạy thật | `deploy/`, báo cáo 03 mục 10 |
| S-10 | Chạy bằng user không phải root (uid 10001) | ✅ Đã chạy thật | `deploy/Dockerfile` |
| S-11 | Nhật ký chống sửa: chuỗi băm SHA-256, phát hiện sửa/xoá/chèn dòng và xoá cả tháng | ✅ Có test | `test_nhat_ky_chuoi_bam_phat_hien_sua_va_xoa`, `test_xoa_ca_mot_thang_giua_chung_bi_phat_hien` |
| S-12 | Quyền tệp nhật ký và sao lưu `600`, thư mục `700` | ✅ Có test + Docker | `test_quyen_tep_nhat_ky_va_sao_luu_la_600` (chạy trong WSL) |
| S-13 | Sao lưu hằng ngày, khôi phục đã thử thật, từ chối bản bị sửa | ✅ | PRD A-16 |
| S-14 | Nạp trọng số an toàn: không chạy mã pickle | ✅ Có test | `test_tep_trong_so_khong_duoc_chay_ma_pickle` |
| S-15 | Không có chức năng điều khiển khí tài / gửi lệnh ra ngoài | ✅ | PRD A-12; toàn bộ API ở README |
| S-16 | Mã truy cập trên trình duyệt chỉ giữ trong `sessionStorage` của tab, không đưa lên URL | ✅ | `frontend/index.html`, hàm `token()` |
| S-17 | CI chỉ có quyền đọc repo | ✅ | `ci.yml`: `permissions: contents: read` |

## 3. Rủi ro còn lại (chấp nhận hoặc để sau)

| # | Rủi ro | Mức | Vì sao chưa xử lý | Cách xử lý khi cần |
|---|---|---|---|---|
| R-1 | **Mã dùng chung** cho cả ca: không biết ai bấm. Mã ca ghi vào nhật ký do giao diện tự điền, không phải bằng chứng danh tính | Trung bình | Chủ dự án chốt (Q-3) | Tài khoản riêng (L-3) |
| R-2 | **Ai trong mạng trạm cũng xem được** dashboard và 12 quyết định gần nhất (GET không cần mã) | Thấp | Thiết kế: màn hình xem để ở phòng trực | Bắt buộc mã cho cả GET nếu mạng trạm không tin cậy |
| R-3 | CSP vẫn cho `script-src 'unsafe-inline'` (JS viết trong `index.html`) | Thấp | Đã thoát mọi dữ liệu chèn HTML; tách tệp JS cần sửa giao diện | Tách JS ra `app.js`, bỏ `'unsafe-inline'` |
| R-4 | Phụ thuộc Python ghi `>=`, chưa khoá phiên bản; chưa quét lỗ hổng (`pip-audit`) | Trung bình | Cần tải công cụ; chưa có lịch bảo trì | `pip-compile` ra tệp khoá, thêm `pip-audit` vào CI (MAINTENANCE.md) |
| R-5 | Ảnh `caddy:2.8-alpine` gắn theo tag, không theo digest | Thấp | Đơn giản cho người vận hành | Ghim `@sha256:…`, cập nhật có chủ đích |
| R-6 | Không giới hạn tần suất chung cho mọi request (chỉ chặn dò mã) | Thấp | Mạng nội bộ, một trạm | `rate_limit` ở Caddy hoặc tường lửa |
| R-7 | Container chưa `read_only`, chưa `cap_drop: ALL`, chưa `no-new-privileges` | Thấp | Cần chạy thử Docker lại | Thêm 3 dòng vào compose, thử lại |
| R-8 | Xoá **cả đuôi** nhật ký (các dòng mới nhất) chỉ phát hiện được nhờ so với bản sao lưu | Trung bình | Bản chất của chuỗi băm | Chép băm mới nhất ra nơi khác thường xuyên hơn |
| R-9 | Bản sao lưu nằm **cùng ổ đĩa** với máy trạm | Trung bình | Không có ổ thứ hai | Kỹ thuật viên chép ra USB hoặc ổ mạng (README) |
| R-10 | Bộ đếm chống dò mã nằm trong RAM: khởi động lại `app` là xoá | Thấp | Khởi động lại cần quyền Docker, đã nằm ngoài phạm vi | — |
| R-11 | Ảnh Docker tin header `X-Forwarded-For` từ mọi nguồn (để đọc IP thật qua Caddy). Nếu chạy **ảnh đó mà không có Caddy** (`docker run -p 8099:8099`, mục cuối "Triển khai có HTTPS" của README), người trong mạng có thể giả IP để né khoá dò mã (S-4) | Thấp–Trung bình | Cấu hình chuẩn là compose: 8099 không mở ra ngoài, Caddy ghi đè header này | Chỉ dùng `docker run -p` để thử trên máy; hoặc đổi `--forwarded-allow-ips` thành IP của Caddy |

## 4. Dữ liệu cá nhân (pháp luật Việt Nam)

> Phần này là đối chiếu kỹ thuật, **không phải tư vấn pháp lý**. Trước khi
> dùng thật, cần người có chuyên môn (hoặc giảng viên hướng dẫn) xác nhận với
> văn bản gốc: Nghị định 13/2023/NĐ-CP về bảo vệ dữ liệu cá nhân, và Luật Bảo
> vệ dữ liệu cá nhân năm 2025 (hiệu lực từ 01/01/2026).

**Hệ thống có xử lý dữ liệu cá nhân không?**
- Có, nhưng ít:
  - **mã ca trực** trong nhật ký (hiện luôn là `truc-ca-1`, không phải tên
    thật);
  - **địa chỉ IP** của máy bấm, nằm trong log truy cập của uvicorn/Caddy và
    bộ đếm chống dò mã (chỉ trong RAM).
- **Không** xử lý dữ liệu cá nhân nhạy cảm, **không** có ảnh hay video người,
  **không** gửi dữ liệu ra ngoài máy trạm.

**Đã làm theo các nguyên tắc chung:**

| Nguyên tắc | Đã làm |
|---|---|
| Tối thiểu hoá | Chỉ ghi mã ca, không ghi họ tên; không lưu dữ liệu thô cảm biến |
| Giới hạn mục đích | Nhật ký chỉ dùng để truy vết quyết định (PRD Q-5) |
| Giới hạn thời gian lưu | 12 tháng, tự dọn (A-16) |
| Bảo đảm an toàn | Quyền `600`, chuỗi băm, HTTPS, sao lưu có kiểm tra |
| Giới hạn người tiếp cận | Chỉ kỹ thuật viên và người kiểm tra đọc tệp (A-17) |

**Phải làm thêm nếu ghi tên thật hoặc làm tài khoản riêng (L-3):**
1. Thông báo cho người trực về việc ghi nhật ký: ghi gì, để làm gì, giữ bao
   lâu, ai đọc. Lấy xác nhận theo quy định.
2. Có quy trình cho người trực xem dữ liệu của mình.
3. Ghi lại đánh giá tác động xử lý dữ liệu cá nhân nếu quy định yêu cầu.
4. Đặt thời gian giữ log truy cập của Caddy/uvicorn; hiện chúng ra stdout
   của Docker và theo cấu hình log của Docker.

## 5. Cách tự kiểm lại

```bash
python -m pytest -k "ma or khoa or origin or trang_web or dau_vao or header or chuoi_bam or quyen or pickle"
python -m edge_ai.api.audit_log ../logs/audit.jsonl     # trong backend/: kiểm chuỗi băm
```
