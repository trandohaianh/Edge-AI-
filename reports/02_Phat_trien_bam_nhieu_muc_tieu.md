# Phát triển đợt 2 — Bám nhiều mục tiêu, sửa mô hình hoá và chống “tắt cảnh báo”

Ngày: 18/11/2026 · Nhánh: `audit/danh-gia-phat-trien` · Tiếp nối `reports/01_Danh_gia_va_phat_trien.md`

---

## 1. Tóm tắt

Đợt 1 sửa lỗi và để lại 4 việc cần chủ dự án quyết định. Ở đợt này chủ dự
án yêu cầu “làm tiếp, phát triển đi lên”, nên cả 4 việc đều được làm theo
**lựa chọn khuyến nghị**. Ngoài ra đợt này làm thêm phần lớn nhất còn thiếu
của hệ thống là **bám nhiều mục tiêu**.

Khi camera đã được mô hình hoá đúng (góc nhìn 60° thật, đặt trên bệ quay được
radar dẫn hướng), mục tiêu mới thật sự lọt vào khung hình camera. Nhờ đó
lộ ra **hai lỗi mà số liệu cũ che mất**:

1. **Nhãn ngụy trang tắt được cảnh báo.** Nhận dạng vẫn đúng 100%, nhưng
   mâu thuẫn giữa các cảm biến kéo điểm tin cậy xuống dưới ngưỡng, nên hệ
   thống chỉ đưa vết bám lên người trực ở **0,3%** số khung. Kẻ tấn công
   không lừa được hệ thống, nhưng làm hệ thống im lặng.
2. **Drone cánh bằng bị coi là “mâu thuẫn” vô cớ.** RF không phân biệt được
   đa cánh quạt với cánh bằng, nên hai lớp đó hoà nhau. `argmax` khi hoà
   luôn chọn lớp đứng đầu (đa cánh quạt). Vì vậy mỗi lần camera nói đúng
   “cánh bằng” lại bị hạ quyền như thể camera đang bị lừa.

Cả hai đã sửa, kèm test.

(Phần số liệu ở mục 4 và 5.)

---

## 2. Bốn quyết định đã áp dụng (theo khuyến nghị ở báo cáo 01, mục 5)

| # | Vấn đề | Đã làm | File |
|---|---|---|---|
| 5.1 | RF “không phải drone” bị tính là bằng chứng “chim” | RF chỉ còn nói “drone” hoặc “không biết”. Phần xác suất không phải link điều khiển được chia đều cho 3 lớp, nên bằng chứng “là chim” chỉ còn đến từ micro-Doppler | `pipeline._rf_map` |
| 5.2 | Camera “60°” thật ra nhìn 120° | So với **nửa** góc (30°). Camera đặt trên **bệ quay** 60°/s, mỗi khung được dẫn về phương vị của vết bám (vết bám chứ không phải sự thật mô phỏng). Kịch bản S6 cho mục tiêu xuất phát ở 900 m để camera thật sự vào cuộc | `scene.sense`, `sensors.EOTurret`, `evaluate.py`, `server.py` |
| 5.3 | Xác thực dashboard | Không đặt `EDGE_API_TOKEN` thì lệnh POST **chỉ nhận từ chính máy chủ (loopback)**; máy khác chỉ xem được. Đặt mã thì bắt buộc mã | `server.require_token` |
| 5.4 | Chu kỳ radar ghi 0,35 s nhưng thực tế là 0,3 s | Ghi thẳng `MD_EVERY = 3` (0,3 s, cửa sổ 0,35 s chồng nhau 0,05 s) vào `config.py`, sửa chú thích | `config.py` |

**Đính chính báo cáo 01, mục 6.5.** Ở đó tôi đề xuất “lệch pha RF sang
`k % 5 == 2` để không trùng khung với radar”. Đề xuất này **sai**: chu kỳ 5
và 3 nguyên tố cùng nhau, nên lệch pha kiểu gì cũng vẫn trùng 1/15 số khung
(định lý số dư Trung Hoa). Cách đã làm là: khung nào radar đến lịch thì RF
hoãn sang khung kế tiếp (`sensors.rf_due`). Test kiểm trên 3.000 khung cho
thấy không có khung nào trùng, và RF vẫn chạy đúng 2 lần/giây.

---

## 3. Các việc khác đã làm

| Việc | Vì sao | File | Test |
|---|---|---|---|
| Tách lịch cảm biến, sinh I/Q, ảnh phổ ra `sensors.py` | `server.py` không còn phải import module đánh giá | `sensors.py` | — |
| Nhật ký **chuỗi băm SHA-256** | Sửa hay xoá một dòng là lộ ngay; khởi động lại thì nối tiếp chuỗi; có công cụ `python src/audit_log.py <tệp>` để kiểm tra | `audit_log.py`, `server.py` | `test_nhat_ky_chuoi_bam_…`, `test_may_chu_noi_tiep_chuoi_bam_…` |
| Sửa luật mâu thuẫn: ba trạng thái *mâu thuẫn / đồng thuận / không đủ thông tin* | Lỗi 2 ở mục 1 | `fusion.py` | `test_rf_hoa_hai_lop_drone_…` |
| Nghi bị đánh lừa (mâu thuẫn ≥ 0,5) và tin cậy ≥ 0,45 thì **phải hỏi người**; thêm cờ `deception_suspected` | Lỗi 1 ở mục 1. Bị đánh lừa là lý do để hỏi người, không phải để im lặng | `pipeline.py`, `static/index.html` | `test_nghi_bi_danh_lua_thi_phai_hoi_nguoi` |
| Jacobian **giải tích** thay cho sai phân số | Bám nhiều mục tiêu gọi Jacobian hàng nghìn lần/giây. Bản sai phân tốn 12 lần gọi `h()`. Nỗi lo “viết sai đạo hàm” được giữ lại thành test so với bản sai phân trên 300 trạng thái ngẫu nhiên (khớp tới ~1e-8) | `ekf.py` | `test_jacobian_giai_tich_khop_sai_phan_so` |
| Suy luận theo **batch** | Nhiều ảnh phổ / đoạn I/Q chạy một lần mạng; kết quả giống hệt chạy từng cái | `pipeline.md_logp_batch`, `rf_logp_batch` | `test_batch_cho_cung_ket_qua_…` |

---

## 4. Bám nhiều mục tiêu (`src/mtt.py`)

### 4.1 Bài toán

Bản cũ chỉ có `Pipeline.step(tid=0, …)`: biết trước có đúng một mục tiêu và
coi mọi số đo là của nó. Ngoài thực địa, radar trả về một danh sách điểm
**trộn lẫn** của nhiều drone, chim và báo động giả, và không ai cho biết
điểm nào của ai. Đây là hạn chế lớn nhất mà tác giả đã tự ghi trong README.

### 4.2 Cách làm

1. **Dự đoán** mọi vết bám tới khung hiện tại.
2. **Liên kết toàn cục (GNN).** Với từng loại cảm biến (LiDAR → radar → EO → RF):
   - Lọc thô vector hoá theo khoảng cách. Bộ lọc này chỉ bỏ những cặp đằng
     nào cũng trượt cổng; có test chứng minh nó không bỏ sót cặp nào qua
     được cổng χ².
   - Tính khoảng cách Mahalanobis. `H` và `HPHᵀ` tính một lần cho mỗi vết.
   - Cắt bằng cổng χ² mức 99,9% theo số chiều số đo (radar 4 chiều: 18,47;
     LiDAR 3: 16,27; EO 2: 13,82; RF 1: 10,83).
   - Gán một-một bằng thuật toán Hungarian (`scipy.optimize.linear_sum_assignment`).
   - Số đo chỉ-có-góc (EO, RF) chỉ được gán cho vết **đã xác nhận**.
3. **Cứu vết.** Số đo vị trí chưa ai nhận được thử lại với cổng nới rộng ×4,
   nhưng chỉ cho các vết đã xác nhận mà khung này thiếu số đo vị trí. Nhờ đó
   mục tiêu đổi hướng gấp không bị đẻ thêm vết thứ hai.
4. **Dữ liệu thô theo yêu cầu, chia lượt.** Chỉ vết đã xác nhận mới được lấy
   ảnh phổ micro-Doppler / đoạn I/Q, như radar thật chỉ dừng chùm tia trên
   các vết đang bám. Mỗi vết có pha riêng `(k + tid) % chu kỳ`, nên mỗi khung
   chỉ khoảng N/3 vết chạy mạng radar và N/5 vết chạy mạng RF.
5. **EKF + hợp nhất + dự đoán khi mất dấu**: dùng lại nguyên
   `Pipeline.advance`, giống bản một mục tiêu.
6. **Quản lý vết M-of-N:**
   - Số đo radar/LiDAR thừa thì sinh ra vết **tạm**.
   - Vết tạm có số đo **vị trí** ở ≥ 3/5 khung gần nhất thì được **xác nhận**;
     quá 6 khung chưa xác nhận thì xoá.
   - Vết đã xác nhận bị xoá khi 4 s không có số đo vị trí, hoặc khi σ > 250 m.
   - Hai vết cách nhau < 12 m suốt 5 khung thì gộp lại.
7. **Dẫn camera lần lượt** qua các vết chưa phải chim, mỗi vết 1 s.

### 4.3 Ba lỗi của chính bản đầu `mtt.py` (giữ lại vì đáng học)

| Triệu chứng | Nguyên nhân | Cách sửa |
|---|---|---|
| Kịch bản bầy 6 drone: **4,3 vết giả mỗi khung** | Vết rác nằm cùng hướng với drone thật nhận được số đo GÓC (RF/EO) của drone đó, và góc không ràng buộc cự ly. Vì vậy vết rác “có số đo” mỗi khung và sống mãi | Chỉ đếm số đo vị trí cho M-of-N và cho việc xoá vết; số đo góc chỉ gán cho vết đã xác nhận. Kết quả: còn **0,1**, rồi về **0** sau khi thêm bước cứu vết |
| Trung bình **50 ms/khung** chỉ với 4 mục tiêu | Jacobian sai phân số bị tính lại cho từng cặp vết–số đo | Tính H một lần cho mỗi vết, chuyển sang Jacobian giải tích, thêm lọc thô vector hoá |
| Đuôi p99 **> 150 ms** với 6 mục tiêu | Ở khung đến lịch, cả N vết cùng chạy mạng nặng | Chia lượt theo pha từng vết, và chỉ vết đã xác nhận mới được chạy mạng |

Ngoài ra, khi đo thời gian phải trừ thời gian **mô phỏng** sinh ảnh phổ
(~20 ms mỗi ảnh). Đó là việc của “phần cứng” radar, không thuộc vòng xử lý
của thiết bị biên.

### 4.4 Kết quả (`python src/evaluate_mtt.py` → `data/mtt_results.json`)

Mỗi kịch bản chạy 5 lần × 200 khung (20 s). Bỏ 30 khung đầu để vết bám kịp
hình thành. OSPA dùng c = 100 m; một mục tiêu được coi là “được phủ” khi có
vết đã xác nhận cách nó ≤ 50 m.

| Kịch bản | OSPA (KTC 95%) | Độ phủ | Đổi ID | Vết giả/khung | Nhận dạng đúng | Chim bị đưa lên người |
|---|---|---|---|---|---|---|
| M1 · 3 drone + 1 chim, báo động giả 1/khung | 1,19 m (1,09–1,28) | 100% | 0 | 0 | 100% | 0 khung |
| M2 · 2 drone bay sát nhau (cách 2°) | 0,81 m (0,75–0,88) | 100% | 0 | 0 | 100% | — |
| M3 · bầy 6 drone trong mưa, báo động giả 3/khung | 2,22 m (0,58–3,86) | 100% | 0 | 0,06 | 100% | — |
| M4 · 2 drone + 2 chim, sương mù đêm | 3,86 m (3,55–4,17) | 100% | 0 | 0 | 100% | 0 khung |

Kiểm tra riêng: chỉ có báo động giả (3 điểm/khung) trong 120 khung thì sinh
ra hơn 200 vết tạm, nhưng **không vết nào được xác nhận**.

**Thời gian xử lý theo số mục tiêu** (báo động giả 1/khung):

| Số mục tiêu | Trung bình | p99 | max |
|---:|---:|---:|---:|
| 1 | 7,3 ms | 20,8 ms | 23,5 ms |
| 3 | 11,0 ms | 23,5 ms | 40,0 ms |
| 6 | 22,2 ms | 52,4 ms | 55,3 ms |
| 10 | 37,9 ms | 75,5 ms | 112,9 ms |

**Đọc con số này cho đúng.** Máy đo là laptop Windows dùng chung, có tải nền
28–87% CPU từ trình duyệt và các ứng dụng khác. Cùng một mô hình RF, chỉ cách
nhau vài phút, p99 đo được lúc 9,5 ms, lúc 23 ms. Vì vậy các số ở bảng này là
**cận trên bi quan**, không phải năng lực của thuật toán. Có thể kết luận
chắc chắn hai điều:
- Chi phí tăng gần **tuyến tính** theo số mục tiêu (khoảng 3–4 ms trung bình
  mỗi mục tiêu).
- Đến **3 mục tiêu**, p99 vẫn dưới ngân sách 50 ms với biên rộng. Từ 6 mục
  tiêu trở lên, trên máy này đuôi phân bố chạm ngân sách.

Hướng xử lý nằm ở mục 7.

---

## 5. Số liệu một mục tiêu sau đợt 2 (`data/scenario_results.json`)

| Kịch bản | Sai số bám (trước → sau) | Nhận dạng | Tỉ lệ khung đưa lên người (trước → sau) | Thời gian tới xác nhận (trước → sau) |
|---|---|---|---|---|
| S1 trời quang | 11,05 → 9,07 m | 100% | 0,88 → 0,90 | 2,59 → 2,24 s |
| S2 đêm + sương mù | 9,54 → 9,09 m | 100% | 0,88 → 0,88 | 2,63 → 2,69 s |
| S3 nhiễu RF | 9,56 → 8,18 m | 100% | 0,81 → 0,86 | 4,13 → 3,08 s |
| S4 mưa to (cánh bằng) | 8,96 → 5,81 m | 100% | 0,77 → 0,92 | 3,01 → 1,86 s |
| S5 chim | 14,43 → 13,70 m | 100% | **0 → 0** | — |
| S6 nhãn ngụy trang | 11,37 → 0,91 m | 100% | 0,79 → **0,94** (bản trung gian chỉ 0,003, xem mục 1) | 2,83 → 1,34 s |
| S7 mất dấu 4 s | 15,13 → 13,58 m | 100% | 0,87 → 0,87 | 2,94 → 2,95 s |

- **S6 lần này mới thật sự là phép thử chống đánh lừa.** Camera nay nhìn thấy
  mục tiêu (sai số 0,9 m nhờ số đo góc của camera). Độ tin cậy trung bình
  0,65 phản ánh đúng việc hệ thống thấy mâu thuẫn, nhưng nó vẫn đưa mục tiêu
  lên người trực, kèm dòng “nghi bị đánh lừa”.
- **S7, quãng mất dấu 4 s:** Transformer sai 18,3 m so với 26,9 m của ngoại
  suy vận tốc không đổi (**thấp hơn 32%**; trước đợt này là 25,4 so với
  28,6 m). Lý do: camera trên bệ quay cho vết bám trước lúc mất dấu chính xác
  hơn, nên Transformer có lịch sử tốt hơn để dự đoán.
- **Thí nghiệm đánh lừa (`adversarial.py`):** hợp nhất có phòng vệ 100%,
  camera đơn lẻ 0%, hợp nhất cộng đều 10,9% (trên 1.596 khung / 12 lần chạy).
- **Thời gian xử lý một mục tiêu:** trung bình 5,1 ms, p99 37,7 ms. Lần đo
  này bị nhiễu nặng (tôi lỡ chạy test song song cùng lúc, cộng tải nền của
  máy), nên không so được với con số 8,99 ms đo trong container ở báo cáo
  gốc. Cần đo lại trên phần cứng đích.

Báo cáo DOCX/PDF và slide **chưa** được sinh lại. Các file đó vẫn mang số
cũ; muốn đồng bộ thì chạy theo thứ tự ở README, mục “Sinh lại toàn bộ số liệu”.

---

## 6. Test

**54/54 xanh** (`python -m pytest tests/ -q`). So với đợt 1 có thêm 17 test:

| Nhóm | Nội dung |
|---|---|
| Bám nhiều mục tiêu (`tests/test_mtt.py`) | Jacobian giải tích khớp sai phân số; lọc thô không bỏ sót cặp nào qua cổng χ²; batch cho kết quả giống chạy từng cái; 3 mục tiêu trong báo động giả 2/khung luôn đúng 3 vết, sai số < 30 m, đúng nhãn, chim không bị hỏi; chỉ có báo động giả thì không xác nhận vết nào; 2 drone sát nhau giữ 2 vết, không đổi ID; chỉ vết đã xác nhận mới lấy dữ liệu thô; OSPA |
| Máy chủ, hợp nhất (`tests/test_pipeline_server.py`) | Chuỗi băm phát hiện sửa và xoá dòng; nối tiếp chuỗi sau khi khởi động lại; không đặt mã thì máy khác bị 403; hai mạng nặng không bao giờ chung khung; RF không bao giờ là bằng chứng cho chim; camera 60° và giới hạn tốc độ bệ quay; RF hoà hai lớp drone không bị tính là mâu thuẫn; nghi bị lừa thì phải hỏi người; dashboard nhiều mục tiêu và quyết định theo ID vết |

Dashboard đã kiểm tra trên trình duyệt:
- Kịch bản “Nhiều mục tiêu” hiện 4 vết bám ứng với 4 mục tiêu, có hình quạt
  góc nhìn camera và viền vàng cho vết chờ quyết định.
- Chọn vết #2 rồi bấm xác nhận: nhật ký ghi đúng `tid = 2`, và công cụ
  `audit_log.py` báo chuỗi băm hợp lệ.
- Kịch bản nhãn ngụy trang: `deception_suspected = true`, `needs_operator = true`.
- Bảng vết bám nay sắp theo ID. Bản đầu sắp theo mức ưu tiên nên các hàng
  nhảy chỗ liên tục, dễ bấm nhầm.

---

## 7. Việc còn lại và lộ trình

1. **Đo trên Jetson Orin.** Chạy `python src/bench_edge.py --threads 4` và
   `python src/evaluate_mtt.py` ở chế độ 10 W / 25 W, kèm `tegrastats`. Đây
   vẫn là lỗ hổng lớn nhất của luận điểm “chạy được trên thiết bị biên”.
2. **Giữ ngân sách khi ≥ 6 mục tiêu**, theo thứ tự đáng làm:
   - (a) Đặt trần số mạng nặng mỗi khung (ví dụ tối đa 2 ảnh phổ + 1 đoạn
     I/Q), ưu tiên vết chưa chắc nhãn; vết đã chắc 99% không cần phân loại lại.
   - (b) Xuất hai CNN sang ONNX Runtime hoặc TensorRT FP16 (`onnxruntime`
     1.20 đã có sẵn trong môi trường).
   - (c) Chuyển phần EKF/liên kết sang mảng numpy theo lô thay cho vòng lặp Python.
3. **Sinh lại báo cáo DOCX/PDF và slide** theo số mới (việc của chủ dự án).
4. **Liên kết mềm (JPDA) hoặc MHT** cho hai mục tiêu cắt nhau ngay trên cùng
   ô phân giải. GNN + cứu vết đủ cho các kịch bản đã thử (2 drone cách 2°),
   nhưng chưa thử hai quỹ đạo thật sự giao nhau.
5. **Báo động giả có cấu trúc** (cây đung đưa, xe trên đường) chứ không chỉ
   rải đều ngẫu nhiên. Loại này có thể qua được luật M-of-N; khi đó lớp
   `clutter` của mạng micro-Doppler mới phát huy tác dụng.
6. **Dữ liệu thật**: RF từ bộ dữ liệu công khai, micro-Doppler từ radar FMCW
   giá rẻ, mô hình thị giác thật cho EO.
