# Tài liệu yêu cầu sản phẩm (PRD) — Edge AI giám sát mục tiêu bay

| | |
|---|---|
| Sản phẩm | Hệ thống giám sát và bám quỹ đạo mục tiêu bay thấp bằng AI đa cảm biến tại thiết bị biên |
| Loại | Khoá luận tốt nghiệp — Dự án 2 |
| Phiên bản PRD | 1.0 — **bản nháp, chờ chủ dự án xác nhận** |
| Ngày | 22/11/2026 |
| Trạng thái dự án | Đã lập trình xong MVP (bước 6) trước khi có PRD. PRD này được **viết bù** để làm căn cứ nghiệm thu những gì đã có và giới hạn phạm vi các bước 7–10 |

> **Đọc nhanh.** Mục 1–4 nói *làm gì, cho ai*. Mục 5–6 là *danh sách tính
> năng*. Mục 9 là *tiêu chí nghiệm thu* kèm tình trạng hiện tại. Mục 11 là
> **những câu hỏi chỉ chủ dự án trả lời được**; các con số ở mục 7–8 đang là
> giả định cho đến khi có câu trả lời.

---

## 1. Vấn đề cần giải quyết

Drone nhỏ bay thấp rất khó phát hiện kịp thời:

- Camera chỉ nhận ra được drone khi nó đã ở gần (khoảng 1,2 km khi trời
  quang), và mất tác dụng khi có sương mù, trời tối hoặc khi drone dán
  nhãn ngụy trang.
- Radar thấy được xa nhưng dễ nhầm drone với **chim**.
- Mỗi loại cảm biến riêng lẻ đều có điểm mù.

Hệ thống cần **kết hợp bốn loại cảm biến** (radar, sóng vô tuyến RF,
camera quang học/hồng ngoại, LiDAR) để phát hiện **sớm**, nhận dạng **đúng
loại** (drone đa cánh quạt / drone cánh bằng / chim) và **bám quỹ đạo** mục
tiêu. Mọi việc phải chạy ngay trên một thiết bị nhỏ, công suất thấp đặt tại
trạm, không phụ thuộc máy chủ ở xa.

**Ranh giới bắt buộc.** Hệ thống chỉ **giám sát và đề xuất**. Mọi quyết định
do con người đưa ra và đều được ghi nhật ký. Hệ thống không có, và sẽ không
bao giờ có, chức năng tự động chọn mục tiêu hay điều khiển khí tài.

## 2. Người sử dụng

| Vai trò | Họ làm gì với hệ thống | Mức độ kỹ thuật |
|---|---|---|
| **Chuyên viên trực ca** (người dùng chính) | Theo dõi màn hình; xem mục tiêu, độ tin cậy và bằng chứng; bấm **Xác nhận** hoặc **Bỏ qua** | Không cần biết lập trình |
| **Kỹ thuật viên trạm** | Cài đặt, khởi động, đặt mã truy cập, kiểm tra hệ thống còn sống, sao lưu nhật ký | Biết dùng dòng lệnh, Docker |
| **Người kiểm tra / thanh tra** | Đọc nhật ký quyết định, kiểm tra nhật ký có bị sửa hay không | Biết chạy một lệnh kiểm tra |
| **Hội đồng chấm khoá luận** (bên liên quan) | Xem kết quả đo, báo cáo, demo | — |

## 3. Loại sản phẩm và môi trường chạy

- **Web app** (dashboard) chạy trên chính thiết bị biên tại trạm. Chuyên
  viên mở bằng trình duyệt trên máy tính trong mạng nội bộ của trạm.
- **Không phải** website công khai, cũng **không phải** ứng dụng điện thoại.
- Thiết bị đích: SoC nhúng công suất 10–25 W (NVIDIA Jetson Orin). Hiện chạy
  được trên PC/laptop và trong Docker.
- Dữ liệu cảm biến hiện là **mô phỏng theo mô hình vật lý**. Chưa nối với
  cảm biến thật (xem mục 6).

## 4. Phạm vi

**Trong phạm vi:** phát hiện, nhận dạng, bám quỹ đạo, hợp nhất cảm biến, chống
đánh lừa, hiển thị cho người trực, ghi nhật ký quyết định, chạy trong giới hạn
thời gian của thiết bị biên.

**Ngoài phạm vi (cố ý không làm):**
- Bất kỳ hành động tự động nào lên mục tiêu.
- Điều khiển khí tài, gây nhiễu, đánh chặn.
- Tự động chọn mục tiêu ưu tiên để xử lý.
- Lưu video/ảnh của người dân.
- Truy cập từ Internet công cộng.

## 5. Tính năng bắt buộc (MVP)

Mã `F-x` dùng để đối chiếu với tiêu chí nghiệm thu ở mục 9.

| Mã | Tính năng | Nguồn yêu cầu | Tình trạng |
|---|---|---|---|
| F-1 | Phát hiện sớm từ tín hiệu RF (I/Q) bằng học sâu | Đề bài | Đã làm |
| F-2 | Phát hiện sớm từ chữ ký micro-Doppler của radar bằng học sâu | Đề bài | Đã làm |
| F-3 | Hợp nhất 4 luồng cảm biến: radar, RF, EO/IR, LiDAR | Đề bài | Đã làm |
| F-4 | Bám quỹ đạo 3D bằng bộ lọc Kalman mở rộng (EKF) | Đề bài | Đã làm |
| F-5 | Dự đoán quỹ đạo khi mất dấu tạm thời bằng Transformer siêu nhẹ | Đề bài | Đã làm |
| F-6 | Chịu được thời tiết xấu (mưa, sương mù, đêm) và nhiễu địa hình | Đề bài | Đã làm |
| F-7 | Chống đánh lừa camera bằng nhãn ngụy trang; khi nghi bị lừa thì **báo cho người**, không im lặng | Đề bài + rà soát đợt 2 | Đã làm |
| F-8 | Phân biệt chim với drone; **không** làm phiền người trực vì chim | Đề bài (kháng nhiễu) | Đã làm |
| F-9 | Bám **nhiều mục tiêu** cùng lúc giữa báo động giả | Rà soát đợt 2 (hạn chế lớn nhất của bản gốc) | Đã làm |
| F-10 | Dashboard cho người trực: bản đồ, danh sách vết bám, độ tin cậy, bằng chứng theo từng cảm biến, cảnh báo mâu thuẫn | Đề bài (người giữ quyền quyết định) | Đã làm |
| F-11 | Nút **Xác nhận / Bỏ qua** cho từng vết bám; mỗi vết chỉ nhận một quyết định | Đề bài | Đã làm |
| F-12 | Nhật ký quyết định lưu bền, phát hiện được nếu bị sửa hay xoá dòng | Đề bài + rà soát | Đã làm |
| F-13 | Mã truy cập cho các thao tác thay đổi; không có mã thì chỉ chính máy trạm được thao tác | Rà soát bảo mật | Đã làm |
| F-14 | Kiểm tra sống (`/api/health`) cho kỹ thuật viên và Docker | Vận hành | Đã làm |
| F-15 | Chạy được bằng Docker, có HTTPS qua Caddy | Yêu cầu chủ dự án 20/11 | Đã làm, đã chạy thử |

## 6. Tính năng làm sau (không thuộc MVP)

| Mã | Tính năng | Vì sao để sau |
|---|---|---|
| L-1 | Nối với **cảm biến thật** (driver radar, SDR cho RF, camera, LiDAR) | Cần phần cứng; mô phỏng đủ để chứng minh thuật toán trong khoá luận |
| L-2 | Mô hình thị giác thật cho camera (ví dụ YOLO nhỏ) | Hiện camera mới được mô hình hoá ở mức đầu ra |
| L-3 | **Tài khoản riêng cho từng chuyên viên** (đăng nhập, phiên) | Hiện dùng một mã chung; chờ câu hỏi Q-3 |
| L-4 | Liên kết số đo nâng cao (JPDA/MHT) cho hai mục tiêu cắt nhau trong cùng ô phân giải | Các kịch bản hiện tại đã đạt với thuật toán đơn giản hơn (GNN) |
| L-5 | Tăng tốc bằng ONNX/TensorRT trên Jetson | Chỉ cần nếu đo trên Jetson cho thấy thiếu thời gian |
| L-6 | Xuất báo cáo ca trực (PDF/CSV) từ nhật ký | Tiện ích, chưa phải yêu cầu |
| L-7 | Giao diện tiếng Anh | Báo cáo đã song ngữ; dashboard mới có tiếng Việt |

## 7. Đăng nhập, phân quyền và dữ liệu

**Đăng nhập, phân quyền (hiện tại):**
- Xem màn hình: không cần đăng nhập, vì chỉ có trong mạng nội bộ của trạm.
- Thao tác (xác nhận, bỏ qua, đổi kịch bản): cần **mã truy cập dùng chung**
  (`EDGE_API_TOKEN`). Khi không đặt mã thì chỉ chính máy trạm được thao tác.
- Chưa phân biệt từng chuyên viên. Tên ca trực do người dùng tự nhập, nên
  chưa phải bằng chứng xác thực danh tính.

**Dữ liệu cần lưu:**

| Dữ liệu | Ở đâu | Có tính cá nhân? | Giữ bao lâu |
|---|---|---|---|
| Nhật ký quyết định (thời điểm, vết bám, hành động, tên ca trực, bằng chứng) | Tệp JSONL có chuỗi băm (`logs/audit.jsonl` hoặc volume Docker) | **Có**: tên/mã ca trực | Chưa quy định (câu hỏi Q-5) |
| Trọng số mô hình | `data/models/` | Không | Theo phiên bản phần mềm |
| Kết quả đo | `data/results/` | Không | Theo phiên bản phần mềm |

- Không dùng hệ quản trị cơ sở dữ liệu. Với một trạm và vài người trực, một
  tệp nhật ký là đủ và dễ kiểm tra.
- Không lưu ảnh, video hay dữ liệu thô của cảm biến.

## 8. Quy mô, ngân sách, thời gian

Các con số dưới đây là **giả định**, chờ xác nhận ở mục 11.

| Hạng mục | Giả định hiện tại |
|---|---|
| Số trạm | 1 (demo khoá luận) |
| Số người dùng đồng thời | 1–3 chuyên viên trong một ca |
| Số mục tiêu cùng lúc | Thiết kế cho tối đa 10; bảo đảm trong ngân sách thời gian tới 3 (đã đo) |
| Ngân sách | 0 đồng cho dịch vụ trả phí. Mọi thứ chạy tại chỗ; không dùng cloud hay dịch vụ AI bên ngoài |
| Phần cứng | Jetson Orin Nano/NX (chưa có trong tay — câu hỏi Q-2) |
| Thời hạn | Chưa rõ (câu hỏi Q-1) |

## 9. Tiêu chí nghiệm thu

Mỗi tiêu chí đều **đo được**. Cột “Tình trạng” dùng đúng các mức đã thống
nhất: *chưa làm / đã viết / đã chạy thử / đã kiểm thử đạt / đã triển khai /
đã được nghiệm thu*. Chưa tiêu chí nào ở mức “đã được nghiệm thu”, vì việc
đó do chủ dự án quyết định.

| Mã | Tiêu chí | Ngưỡng đạt | Kết quả hiện có | Tình trạng | Bằng chứng |
|---|---|---|---|---|---|
| A-1 | Thời gian một khung, 1 mục tiêu | p99 < 50 ms | 8,99 ms p99 (container x86); 9–19 ms khung xấu nhất (laptop có tải nền) | Đã kiểm thử đạt **trên x86**; **chưa đo trên Jetson** | `data/results/scenario_results.json`, `reports/03` mục 9.3 |
| A-2 | Thời gian một khung, nhiều mục tiêu | Khung xấu nhất < 50 ms với số mục tiêu tối đa ở Q-4 | ≤ 3 mục tiêu: 19–28 ms. 6–10 mục tiêu: 30–53 ms tuỳ tải máy | Đạt tới 3 mục tiêu; **6–10 chưa chắc**, phải đo trên Jetson | `data/results/mtt_results.json` |
| A-3 | Phát hiện RF bằng học sâu | Độ chính xác ≥ 90% trên tập kiểm thử riêng | 96,4% / 2.800 mẫu | Đã kiểm thử đạt (mô phỏng) | `data/results/rf_metrics.json` |
| A-4 | Phát hiện radar micro-Doppler bằng học sâu | ≥ 90% | 95,4% / 2.800 mẫu | Đã kiểm thử đạt (mô phỏng) | `data/results/md_metrics.json` |
| A-5 | Nhận dạng đúng loại trong 7 kịch bản hiện trường (trời quang, đêm–sương mù, nhiễu RF, mưa, chim, nhãn ngụy trang, mất dấu) | ≥ 95% số khung sau giai đoạn khởi động | 100% ở cả 7 | Đã kiểm thử đạt (mô phỏng) | `scenario_results.json` |
| A-6 | Không làm phiền người trực vì chim | 0 khung chim bị đưa lên người | 0 (một mục tiêu và nhiều mục tiêu) | Đã kiểm thử đạt | `scenario_results.json`, `mtt_results.json`, test `test_rf_khong_bao_gio_la_bang_chung_cho_chim` |
| A-7 | Chống nhãn ngụy trang | Nhận dạng đúng ≥ 95% khi camera bị lừa **và** vết nghi bị lừa vẫn được đưa lên người | 100% đúng / 1.596 khung; đưa lên người 94% số khung | Đã kiểm thử đạt | `adversarial.json`, test `test_nghi_bi_danh_lua_thi_phai_hoi_nguoi` |
| A-8 | Dự đoán khi mất dấu tốt hơn ngoại suy đường thẳng | Sai số thấp hơn ≥ 10% trong quãng mất dấu 4 s | 18,3 m so với 26,9 m (thấp hơn 32%) | Đã kiểm thử đạt (mô phỏng) | `scenario_results.json` (S7) |
| A-9 | Bám nhiều mục tiêu | Độ phủ ≥ 95%, đổi ID ≤ 1 mỗi lượt, vết giả ≤ 0,05/khung | Phủ 100%, đổi ID 0, vết giả ≤ 0,007 | Đã kiểm thử đạt (mô phỏng) | `mtt_results.json` |
| A-10 | Mọi quyết định của người đều được ghi lại | Mỗi lần bấm sinh đúng 1 dòng nhật ký; còn nguyên sau khi khởi động lại; sửa/xoá dòng thì bị phát hiện | Đạt cả ba | Đã kiểm thử đạt | test `test_quyet_dinh_duoc_ghi_xuong_dia…`, `test_nhat_ky_chuoi_bam…`; thử Docker trong `reports/03` mục 10 |
| A-11 | Không ai ngoài trạm thao tác được khi không có mã | POST từ máy khác bị từ chối (403/401) | Đạt | Đã kiểm thử đạt | test `test_khong_dat_ma…`, `test_ma_truy_cap…` |
| A-12 | Không có chức năng tự động hành động | Không có API hay mã nào gửi lệnh ra ngoài hệ thống | Đạt (đã rà toàn bộ API: chỉ xem, xác nhận, bỏ qua, đổi kịch bản) | Đã kiểm tra | `README.md` mục API |
| A-13 | Chạy được trên SoC 10–25 W | Khởi động được và A-1/A-2 đạt trên Jetson | Chưa có phần cứng | **Chưa làm** | — |
| A-14 | Dashboard dùng được trên màn hình máy tính trạm | Thao tác đủ F-10, F-11 không lỗi; báo rõ khi mất kết nối | Đạt trên Chrome máy tính | Đã chạy thử | Kiểm tra trên trình duyệt (`reports/02` mục 6) |
| A-15 | Cài đặt lại được từ đầu | Clone repo → làm theo README → dashboard chạy, test xanh | Đạt trên Windows; Docker build đạt | Đã chạy thử | `README.md`, CI |

## 10. Giả định

1. Dữ liệu mô phỏng theo mô hình vật lý được chấp nhận làm bằng chứng cho
   khoá luận. Nối cảm biến thật là việc sau (L-1).
2. Dashboard chỉ dùng trong mạng nội bộ của trạm, không mở ra Internet.
3. Người trực dùng máy tính để bàn hoặc laptop. Không cần giao diện điện
   thoại; tiêu chí A-14 vì vậy chỉ yêu cầu màn hình máy tính.
4. Một mã truy cập dùng chung là đủ cho giai đoạn khoá luận.

## 11. Câu hỏi mở — cần chủ dự án trả lời

| Mã | Câu hỏi | Ảnh hưởng tới | Đề xuất của tôi |
|---|---|---|---|
| Q-1 | Hạn nộp / bảo vệ khoá luận là khi nào? | Ưu tiên các việc ở bước 7–10 | — |
| Q-2 | Có mượn được Jetson Orin để đo không? Nếu không, có chấp nhận kết luận chỉ dựa trên đo x86 không? | A-2, A-13 | Nếu không có Jetson: ghi rõ trong khoá luận là “chưa kiểm chứng trên thiết bị đích”, như báo cáo hiện tại đang làm |
| Q-3 | Có cần **tài khoản riêng** cho từng chuyên viên không, hay một mã chung là đủ? | L-3, bước 7 (bảo mật) | Mã chung là đủ cho khoá luận; ghi tài khoản riêng vào hướng phát triển |
| Q-4 | Hệ thống phải bảo đảm tối đa bao nhiêu mục tiêu cùng lúc trong 50 ms? | A-2 | 3 mục tiêu (đã đạt chắc chắn); 10 là mục tiêu mở rộng |
| Q-5 | Nhật ký quyết định cần giữ bao lâu, và ai được xem? Tên ca trực là dữ liệu cá nhân nên cần quy định | Bước 3 (sao lưu), bước 7 (quyền riêng tư) | Giữ 12 tháng; chỉ kỹ thuật viên và thanh tra được đọc tệp; sao lưu hằng ngày |
| Q-6 | Dashboard có cần dùng được trên điện thoại / máy tính bảng không? | Giả định 3, bước 4 và 8 | Không cần |
| Q-7 | Có cần demo trực tuyến cho hội đồng (một địa chỉ HTTPS công khai) không? | Bước 9 | Chỉ demo tại chỗ bằng Docker; nếu cần công khai thì phải bật mã truy cập và chọn hosting |

## 12. Lịch sử thay đổi

| Phiên bản | Ngày | Nội dung |
|---|---|---|
| 1.0 | 22/11/2026 | Bản nháp đầu, viết bù sau khi đã có MVP. Tổng hợp từ đề bài (`docs/build/report.js` mục 1), `README.md` và các báo cáo `reports/01–03` |
