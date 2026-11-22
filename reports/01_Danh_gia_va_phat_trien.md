# Đánh giá và phát triển — Dự án 2: Giám sát đa cảm biến bằng Edge AI

Ngày rà soát: 18/11/2026 · Nhánh: `audit/danh-gia-phat-trien` (tách từ `main`, mốc gốc `1ad2d7e`)

> **Cập nhật đợt 2:** 4 việc ở mục 5 đã được làm theo lựa chọn khuyến nghị,
> và hệ thống đã có bám nhiều mục tiêu. Xem `reports/02_Phat_trien_bam_nhieu_muc_tieu.md`.
> Đề xuất ở mục 6.5 (lệch pha RF) là **sai** và đã được đính chính trong báo cáo 02.

---

## 1. Tóm tắt

Dự án ở trạng thái tốt hơn mức trung bình của một khoá luận: mã gọn, mỗi
quyết định thiết kế đều có chú thích giải thích lý do, và README tự ghi lại
ba lỗi phương pháp đã mắc. Bộ test gốc **20/20 xanh**.

Đợt rà soát tìm ra **10 lỗi** đã sửa kèm test, và **4 vấn đề cần chủ dự án
quyết định**. Lỗi nặng nhất:

1. Thiếu tệp trọng số thì hệ thống **lặng lẽ chạy với mô hình ngẫu nhiên**.
2. `torch.load` không bật `weights_only` — tệp `.pt` có thể chạy mã tuỳ ý.
3. Nhật ký quyết định của chuyên viên **chỉ nằm trong RAM**: khởi động lại là mất, trái với cam kết trong README.
4. Thí nghiệm chống đánh lừa **ghép I và Q từ hai đoạn tín hiệu khác nhau**, và chỉ thật sự chấm 2–4/12 lần chạy.
5. `/api/metrics` và `figures.py` **trả lỗi trên Windows** vì đọc JSON tiếng Việt bằng bảng mã mặc định cp1252.
6. Khung đầu tiên mất dấu gọi Transformer 9 lần liền, tạo **gai thời gian xử lý** đúng lúc hệ thống khó khăn nhất.

Sau khi sửa: **37/37 test xanh**. Kết quả nhận dạng và bám của 7 kịch bản
**giữ nguyên**: chạy lại `evaluate.py` cho đúng các số trong
`data/scenario_results.json`. Riêng thí nghiệm chống đánh lừa được chạy lại
với dữ liệu đúng.

---

## 2. Hiện trạng

### 2.1 Mục tiêu

Phát hiện, nhận dạng (drone đa cánh quạt / cánh bằng / chim) và bám quỹ đạo
3D mục tiêu bay thấp bằng 4 cảm biến (radar băng X, RF I/Q, EO/IR, LiDAR).
Toàn bộ vòng xử lý một khung phải xong trong 50 ms trên SoC nhúng 10–25 W.
Hệ thống **chỉ hỗ trợ quyết định**: con người xác nhận hoặc bỏ qua. Ranh giới
này được giữ nguyên trong mọi thay đổi của đợt rà soát.

### 2.2 Kiến trúc

```
cảm biến mô phỏng (scene.py, rf_sim.py, radar_sim.py)
   │
   ▼  10 Hz
Pipeline.step (pipeline.py)
   ├─ RF: STFT cố định + CNN 2D (rf_stft.py)          mỗi 5 khung
   ├─ Radar: CNN 2D trên micro-Doppler (models.py)     mỗi 3 khung
   ├─ EKF 6 trạng thái, cập nhật tuần tự (ekf.py)      mỗi khung
   ├─ Hợp nhất nhận dạng có trọng số tin cậy (fusion.py)
   └─ Transformer quỹ đạo khi mất dấu ≥ 3 khung
   │
   ▼
server.py (FastAPI) ──► static/index.html (dashboard người trực ca)
```

### 2.3 Kết quả test ban đầu

| Lần chạy | Môi trường | Kết quả |
|---|---|---|
| Trước khi sửa | Windows 11, Python 3.12.4, torch 2.11 CPU | **20 passed** trong 1,8 s |
| Sau khi sửa | như trên | **37 passed** trong 6,8 s |

Lệnh: `python -m pytest tests/ -q`. Trên máy này cần thêm
`--basetemp=<thư mục tạm>` vì thư mục tạm mặc định của pytest bị khoá quyền.
Đây là vấn đề của máy, không phải của dự án.

### 2.4 Số đo mô hình trên thiết bị (đo mới, `src/bench_edge.py`)

Máy đo: CPU x86 Windows, 2 luồng torch, batch 1. **Không phải Jetson.**

| Mô hình | Tham số | Tệp | Trễ trung bình | p99 |
|---|---:|---:|---:|---:|
| RF (STFT + CNN 2D) | 62.452 | 263 KB | 4,9 ms | 9,5 ms |
| Micro-Doppler CNN 2D | 62.452 | 262 KB | 4,3 ms | 8,6 ms |
| Transformer quỹ đạo | 42.798 | 177 KB | 0,8 ms | 1,5 ms |
| Khung xấu nhất (RF + radar cùng khung) | — | — | 8,8 ms | 14,7 ms |
| Mất dấu, bản cũ: dự đoán trọn 9 s trong một khung | — | — | 9,5 ms | 15,2 ms |
| Mất dấu, bản mới: nối thêm 1 s | — | — | 1,1 ms | 2,3 ms |

Tổng dưới 170 nghìn tham số và dưới 1 MB trọng số, nên mô hình rất hợp với
thiết bị biên. Rủi ro về thời gian không nằm ở trung bình mà ở **đuôi
phân bố**: trong `scenario_results.json` gốc, p99 là 8,99 ms nhưng khung chậm
nhất là **57,5 ms**, vượt ngân sách 50 ms.

---

## 3. Đánh giá theo vai trò

### 3.1 Kiến trúc
- **Tốt:** tách rõ mô phỏng, suy luận, EKF, hợp nhất và giao diện. Hai mạng
  nặng chạy theo chu kỳ vật lý của cảm biến chứ không chạy mỗi khung, vừa
  đúng về vật lý vừa giữ được ngân sách. Hằng số tập trung trong `config.py`.
- **Yếu:** `server.py` lấy `lambda_iq` từ `evaluate.py` (module đánh giá),
  và `MD_EVERY` cũng nằm ở đó. Phần lịch chạy cảm biến nên chuyển sang
  `config.py`. Chỉ bám một mục tiêu (tác giả đã tự ghi nhận).
- `Pipeline.step` trả về một `dict` không có kiểu; nên đổi thành dataclass
  hoặc model pydantic để dashboard và nhật ký có hợp đồng dữ liệu rõ ràng.

### 3.2 Độ đúng và mức phù hợp của thuật toán
- **EKF:** mô hình vận tốc gần như không đổi với nhiễu gia tốc trắng, và
  ma trận Q rời rạc hoá đúng công thức. Cập nhật dạng Joseph giữ P đối xứng
  và xác định dương (đã có test). Jacobian tính bằng sai phân trung tâm, có
  xử lý vòng góc. Cổng thống kê `d² > 16·dim` khá lỏng: với 4 chiều, ngưỡng
  64 tương ứng p rất nhỏ so với χ²(4). Chấp nhận được khi chỉ có một mục
  tiêu, nhưng phải siết lại khi làm đa mục tiêu.
- **Hợp nhất nhận dạng:** trừ trung bình log-prob, đặt trần cho từng cảm
  biến và hạ quyền camera khi mâu thuẫn. Thiết kế đúng hướng và có lý lẽ.
  Chỗ cần quyết định là cách ánh xạ đầu ra RF (mục 5.1).
- **Transformer quỹ đạo:** huấn luyện trên chính chuỗi trạng thái EKF và so
  với ngoại suy từ vận tốc EKF, tức mốc so sánh công bằng. Tuy vậy, **con số
  19,8% đo trên cửa sổ 1 giây**, còn README ghi nó ở dòng “Bám quỹ đạo khi
  mất dấu”. Trong kịch bản mất dấu 4 giây thật (S7), sai số là 25,4 m so với
  28,6 m, tức chỉ thấp hơn **~11%**. Đã sửa README cho rõ.
- **Kịch bản S6 trong `evaluate.py`:** mục tiêu sinh ở phương vị và cự ly
  ngẫu nhiên nên camera hầu như không thấy nó. Bằng chứng: thu hẹp góc nhìn
  camera không làm S6 đổi một chữ số nào. Vì vậy “100% ở S6” chưa chứng minh
  khả năng chống đánh lừa. Bằng chứng thật nằm ở `adversarial.py`, nay đã
  sửa (mục 4).
- **Lịch chạy radar:** `MD_EVERY = round(0.35/0.1)` cho ra **3** chứ không
  phải 4, vì `0.35/0.1 = 3.4999…`. Radar thực tế chạy mỗi 0,3 s với cửa sổ
  chiếu 0,35 s, tức các cửa sổ chồng lên nhau. Chú thích trong mã ghi sai
  chu kỳ (mục 5.4).

### 3.3 Hiệu năng trên thiết bị biên
- Mô hình nhỏ, phù hợp. Chưa đo trên Jetson, và tác giả đã nói rõ điều này.
- Gai thời gian khi mất dấu đã được gỡ (mục 4, lỗi 6).
- Bộ nhớ: lịch sử vết bám và mảng thời gian từng chặng **tăng mãi**, nên
  chạy dài ngày trên thiết bị biên sẽ ăn dần RAM. Nay đã giới hạn.
- Chưa có lượng tử hoá hay xuất ONNX/TensorRT. Docstring của `rf_stft.py`
  nói “xuất ONNX được”, nhưng chưa có ai kiểm chứng: máy này không có gói
  `onnx`, và `torch.stft` trên số phức thường gây khó cho exporter. Xem lộ
  trình.

### 3.4 Bảo mật
- `torch.load` không có `weights_only=True`: tệp `.pt` là pickle và chạy mã
  được. **Đã sửa**, có test chứng minh tệp độc bị từ chối.
- API không có xác thực; `operator` nhận chuỗi tuỳ ý, không giới hạn độ dài
  (có thể nhét ký tự xuống dòng vào nhật ký). **Đã sửa:** kiểm tra đầu vào,
  thêm mã truy cập tuỳ chọn và header bảo mật. Bật xác thực mặc định hay
  không là việc cần quyết định (mục 5.3).
- Dashboard chèn dữ liệu vào `innerHTML` mà không thoát ký tự. Hiện dữ liệu
  đều do máy chủ sinh ra, nhưng `operator` là chuỗi người dùng nhập. **Đã
  thêm hàm `esc()`.**

### 3.5 Chất lượng mã
- Chú thích tiếng Việt giải thích *vì sao* chứ không chỉ *cái gì*. Đây là
  điểm mạnh hiếm thấy.
- `open()` không ghi `encoding` ở 15 chỗ trong 9 file (lỗi 5). Docstring sai kích thước
  phổ (`[64,64]` trong khi thực tế là `[64,128]`). Trường `meas_hist` được
  ghi vào nhưng không bao giờ được đọc, và chú thích đi kèm mô tả sai cái
  thật sự đưa vào Transformer. Đã dọn.
- `@app.on_event("startup")` đã lỗi thời trong FastAPI; đổi sang `lifespan`,
  có dừng luồng nền khi tắt.

### 3.6 Test
- 20 test gốc nhắm đúng các lỗi vật lý đã gặp, rất tốt. Còn thiếu test cho
  máy chủ, cho việc nạp mô hình và cho nhánh mất dấu của pipeline. Đã thêm
  **17 test** (`tests/test_pipeline_server.py`).
- Test mới chứng minh nối dự đoán dần cho **kết quả giống hệt** bản cũ. Đã
  kiểm thêm bằng cách chạy song song bản cũ và bản mới trên kịch bản mất dấu:
  vị trí và dự đoán trùng ở mọi khung. Chạy lại `evaluate.py` (56 lần) cũng
  ra đúng các chỉ số nhận dạng và bám như `scenario_results.json` gốc.

### 3.7 UX của `static/`
- **Tốt:** có dải cảnh báo đạo đức song ngữ; bằng chứng hiện theo từng cảm
  biến; có lời giải thích khi phát hiện mâu thuẫn; thời gian xử lý ghi rõ
  là p99.
- **Đã sửa:**
  - Nhãn “● đang chạy” luôn xanh kể cả khi mất máy chủ. Nay chuyển đỏ “mất kết nối”.
  - Bấm xác nhận không có phản hồi, lỗi bị nuốt. Nay hiện thông báo, và báo
    rõ khi không ghi được xuống đĩa.
  - Không có dấu hiệu nào khi hệ thống *đề nghị* xem xét. Nay có dòng nhắc
    theo `needs_operator`.
  - `setInterval` 180 ms có thể dồn yêu cầu khi máy chủ chậm. Nay dùng hẹn
    giờ nối tiếp.
  - Thêm cột “Người trực” trong bảng nhật ký, và băng cảnh báo đỏ khi chạy
    trọng số chưa huấn luyện.
  - Xoá một dòng mã thừa (`fillStyle='#5B6striped'`).
- Đã kiểm tra trên trình duyệt: bấm xác nhận thì thông báo hiện, nút khoá
  lại, nhật ký có dòng mới trên đĩa. Tắt máy chủ thì nhãn chuyển “mất kết nối
  máy chủ”. Không có lỗi trên console.

### 3.8 Khả năng triển khai
- Ban đầu không có Dockerfile, không có health check và không có cấu hình
  qua biến môi trường. **Đã thêm** `Dockerfile` (torch CPU, user không phải
  root, `HEALTHCHECK` gọi `/api/health`, volume cho nhật ký) và `.dockerignore`.
  **Chưa build thử được**: Docker Desktop không chạy trên máy lúc rà soát.
- `requirements.txt` thiếu `httpx` (TestClient cần). Đã thêm, chú thích chỉ
  dùng ASCII để `pip` trên Windows không vấp bảng mã.

---

## 4. Các lỗi đã sửa

| # | File | Lỗi | Vì sao phải sửa | Test |
|---|---|---|---|---|
| 1 | `src/pipeline.py` | Thiếu tệp `.pt` vẫn chạy với trọng số ngẫu nhiên, không báo gì | Hệ giám sát hỏng mà không ai biết là kiểu hỏng nguy hiểm nhất. Nay dừng với thông báo rõ; muốn thử luồng thì phải bật `allow_untrained` (hoặc `EDGE_ALLOW_UNTRAINED=1`), và khi đó dashboard hiện băng đỏ | `test_thieu_trong_so_…` |
| 2 | `src/pipeline.py` | `torch.load` không có `weights_only=True` | Tệp trọng số là pickle, chạy được mã tuỳ ý khi nạp | `test_tep_trong_so_khong_duoc_chay_ma_pickle` |
| 3 | `src/server.py` | Nhật ký quyết định chỉ là `list` trong RAM, không giới hạn | Mất khi khởi động lại, trái với cam kết “mọi thao tác đều được ghi”. Nay ghi nối JSONL + `fsync`, RAM giữ 1.000 bản ghi | `test_quyet_dinh_duoc_ghi_xuong_dia_va_chi_mot_lan` |
| 4 | `src/server.py` | Ghi được nhiều quyết định trái nhau cho cùng một vết bám; số khung ghi lệch 1; nhận `action` và `operator` tuỳ ý | Giao diện khoá nút nhưng máy chủ không khoá, nên hai người bấm cùng lúc sẽ ghi hai quyết định ngược nhau. Chuỗi tự do có thể chèn xuống dòng vào nhật ký. Nay trả 409 khi đã có quyết định, kiểm tra kiểu `Literal`, `operator` 1–32 ký tự `[\w.-]` | `test_dau_vao_sai_bi_tu_choi`, `test_quyet_dinh_…` |
| 5 | 9 file trong `src/` | `open()` không ghi `encoding` khi đọc/ghi JSON có tiếng Việt | Trên Windows `/api/metrics` trả 500 và `figures.py` dừng với `UnicodeDecodeError` (đã tái hiện) | `test_cac_tep_json_doc_duoc_bang_utf8`, `test_kich_ban_metrics_…` |
| 6 | `src/pipeline.py` | Khung đầu mất dấu tính trọn 9 giây dự đoán (9 lần gọi Transformer) | Gai thời gian xử lý (chặng `traj` 15,2 → 4,5 ms trong cùng kịch bản). Nay nối thêm 1 giây mỗi khi cần; kết quả số học giống hệt | `test_du_doan_mat_dau_noi_dan_…` |
| 7 | `src/pipeline.py` | `hist`, `meas_hist`, `timing` tăng không giới hạn | Chạy dài ngày trên thiết bị biên sẽ hết RAM. Nay dùng `deque` có giới hạn (256 khung, 10.000 mẫu); bỏ `meas_hist` vì không bao giờ được đọc | `test_lich_su_va_so_do_thoi_gian_co_gioi_han` |
| 8 | `src/adversarial.py` | I lấy từ một đoạn, Q lấy từ một đoạn **khác** | Mạng RF nhận một tín hiệu không thể có ngoài đời (cấu trúc pha I/Q bị phá) | `test_thu_nghiem_danh_lua_lay_i_va_q_tu_cung_mot_doan` |
| 9 | `src/adversarial.py`, `src/scene.py` | Mục tiêu sinh ở phương vị ngẫu nhiên nên camera chỉ thấy trong 2–4/12 lần chạy | Kết luận “100%” dựa trên ít dữ liệu hơn nhiều so với vẻ ngoài. Thêm `rotate_into_view` (dùng chung với dashboard). Chạy lại: vẫn **100%** nhưng trên **1.596** khung (trước: 532); hợp nhất cộng đều 3,4%; camera đơn lẻ 0% | `test_xoay_vao_tam_camera_giu_nguyen_toc_do` |
| 10 | `src/server.py`, `static/index.html` | `on_event` lỗi thời, luồng nền không bao giờ dừng, một khung lỗi làm chết vòng lặp, API trả 500 khi chưa khởi động xong, không có health check, không có header bảo mật; dashboard nuốt lỗi và luôn báo “đang chạy” | Vận hành và UX (xem 3.7, 3.8) | `test_lifespan_…`, `test_chua_khoi_dong_thi_tra_503`, `test_ma_truy_cap_khi_duoc_bat`, `test_kich_ban_metrics_header_va_health` |

Phần bổ sung (không phải lỗi):
- `src/bench_edge.py` và `data/edge_bench.json`: đo tham số, dung lượng, độ
  trễ từng mô hình và độ trễ khung xấu nhất. Chạy được trên máy đích.
- `Dockerfile`, `.dockerignore`, `.gitignore`.
- README: tách con số 19,8% (cửa sổ 1 s) khỏi ~11% (mất dấu 4 s), ghi khung
  chậm nhất 57 ms, cập nhật số chống đánh lừa, thêm biến môi trường và cách
  chạy Docker.

**Lưu ý:** `docs/*.docx`, `*.pdf`, `*.pptx` **không bị động tới**. Chúng vẫn
mang số cũ của thí nghiệm chống đánh lừa (5,3% / 532 khung) và câu “19,8% khi
mất dấu”. Muốn cập nhật thì chạy `node docs/build/report.js vi|en` và
`slides.js` (xem 6.1).

---

## 5. Việc cần chủ dự án quyết định

### 5.1 Đầu ra RF “không phải drone” đang được tính là bằng chứng “chim” — **khuyến nghị sửa**

`rf_logp` dồn toàn bộ xác suất “nhiễu / WiFi / Bluetooth” vào lớp *chim*.
Nhưng chim không phát sóng, nên một tín hiệu WiFi ở hướng mục tiêu không nói
gì về việc nó là chim. Đo trên mô hình hiện tại:

- 8–11% đoạn tín hiệu **drone thật** bị mạng RF đẩy về phía “chim” (SNR 2–20 dB).
- Đoạn WiFi/Bluetooth/nhiễu cho log-odds chim/drone khoảng **+5 nats**.
  Mức trần mỗi cảm biến là 4 nats, nên một mình RF đủ đẩy kết luận về
  “chim”.

Một drone bay cạnh toà nhà có WiFi, hoặc drone tự hành không có link điều
khiển, có thể bị đánh dấu là chim. `needs_operator` loại trừ chim, nên khi
đó **người trực sẽ không được hỏi**. Đây là lỗi bỏ sót, loại lỗi nguy hiểm
nhất với hệ cảnh báo.

| Lựa chọn | Ưu | Nhược |
|---|---|---|
| **A. RF chỉ được nói “drone” hoặc “không biết”** (khuyến nghị): phần “không phải drone” chia đều cho 3 lớp | Đúng vật lý; an toàn theo hướng hỏi người nhiều hơn; sửa 1 dòng | Phân biệt chim chậm hơn một chút (radar phải tự làm); phải chạy lại `evaluate.py` và sinh lại báo cáo |
| B. Giữ nguyên | Không đổi số liệu đã nộp | Giữ rủi ro bỏ sót nêu trên |
| C. Thêm lớp “nguồn phát khác” và mô hình hoá drone tự hành không phát sóng | Thực tế nhất | Phải sửa bộ mô phỏng, huấn luyện lại, tốn công |

### 5.2 Góc nhìn camera đang là 120° chứ không phải 60°

`scene.py` dùng `abs(az) < EO_FOV_DEG` với `EO_FOV_DEG = 60`, tức nửa góc
60° và toàn góc 120°. Đã đo lại với nửa góc 30°: độ chính xác nhận dạng giữ
100% ở cả 7 kịch bản; RMSE S1 11,05 → 11,62 m, S4 8,96 → 9,79 m, S7
15,13 → 15,80 m; thời gian xác nhận S1 2,59 → 2,95 s.

| Lựa chọn | Ưu | Nhược |
|---|---|---|
| **A. Sửa thành nửa góc (`EO_FOV_DEG/2`) và mô hình hoá đầu quang điện quay theo radar** (khuyến nghị) | Đúng thông số; khớp với chú thích trong `server.py` | Số liệu đổi nhẹ; phải sinh lại báo cáo |
| B. Đổi tên/giá trị thành `EO_FOV_DEG = 120` | Không đổi số liệu | Camera 120° với tầm nhận dạng 1,2 km là khó tin |

### 5.3 Xác thực dashboard

Đã có mã truy cập tuỳ chọn (`EDGE_API_TOKEN`). Hiện **mặc định tắt** để demo
không vướng.

| Lựa chọn | Ưu | Nhược |
|---|---|---|
| A. Giữ tắt mặc định, bật khi triển khai (hiện trạng) | Demo đơn giản | Dễ quên bật |
| **B. Bắt buộc khi máy chủ không nghe ở `127.0.0.1`** (khuyến nghị) | An toàn mặc định cho triển khai | Thêm một bước cấu hình |
| C. Tài khoản riêng cho từng chuyên viên (đăng nhập, phiên) | Nhật ký biết chính xác ai bấm | Tốn công, vượt phạm vi khoá luận |

### 5.4 Chu kỳ chạy radar 0,3 s hay 0,35 s

`MD_EVERY` thực tế là 3 khung (0,3 s), không phải 3,5 khung như chú thích.
Hai cách: (A) giữ 3 và sửa chú thích là “cửa sổ 0,35 s chồng nhau 0,05 s”,
không đổi số liệu, **khuyến nghị**; (B) dùng 4 khung (0,4 s), đổi số liệu và
giảm tần suất nhận dạng radar 25%.

---

## 6. Việc còn lại và cách làm

1. **Sinh lại báo cáo DOCX/PDF và slide** sau khi chốt mục 5: chạy
   `python src/evaluate.py`, `python src/adversarial.py`, `python src/figures.py`,
   rồi `node docs/build/report.js vi|en` và `node docs/build/slides.js vi|en`.
   Chỉ chủ dự án làm bước này vì nó ghi đè tài liệu đã nộp.
2. **Sửa kịch bản S6 trong `evaluate.py`** cho camera thật sự thấy mục tiêu
   (gọi `rotate_into_view` và đặt `r0≈900`, như `adversarial.py`). Hiện S6
   không kiểm tra được gì về chống đánh lừa (xem 3.2).
3. **Build và chạy thử Docker** khi Docker Desktop bật:
   `docker build -t edge-ai .`, rồi `docker run -p 8099:8099 edge-ai` và
   kiểm tra `curl localhost:8099/api/health`.
4. **Đo trên Jetson Orin Nano/NX**: chạy `python src/bench_edge.py --threads 4`
   và `python src/evaluate.py` trên máy. Bật chế độ công suất 10 W và 25 W
   (`nvpmodel`), ghi lại p99, max và điện năng (`tegrastats`).
5. **Lệch pha hai mạng nặng:** chạy RF ở `k % 5 == 2` thay vì `k % 5 == 0`
   để không bao giờ trùng khung với radar (hiện trùng 6,7% số khung). Cách
   này giảm p99 của khung xấu nhất từ khoảng 15 ms xuống khoảng 9–10 ms (p99 của một mạng).
6. **Chuyển `MD_EVERY`, `RF_EVERY`, `lambda_iq` ra khỏi `evaluate.py`**
   (sang `config.py` và `sensors.py`) để `server.py` không phụ thuộc module
   đánh giá.
7. **Nhật ký chống sửa:** mỗi dòng JSONL thêm `prev_hash` (SHA-256 của dòng
   trước) để phát hiện xoá/sửa, và xoay vòng tệp theo ngày.

---

## 7. Lộ trình phát triển tiếp

| Giai đoạn | Nội dung | Kết quả kiểm chứng |
|---|---|---|
| **1. Chốt số liệu** (1 tuần) | Quyết định mục 5, chạy lại toàn bộ, sinh lại báo cáo; sửa S6 | README, DOCX và JSON khớp nhau |
| **2. Phần cứng thật** (2 tuần) | Chạy trên Jetson; xuất ONNX → TensorRT FP16 cho hai CNN (thay STFT bằng conv1d cố định nếu exporter không nhận `torch.stft` phức); đo điện năng | p99 / max / W ở 10 W và 25 W |
| **3. Đa mục tiêu** (3–4 tuần) | Liên kết số đo GNN hoặc JPDA, khởi tạo/xoá vết bám (M-of-N), cổng χ² đúng theo bậc tự do | Kịch bản 2–5 mục tiêu cắt nhau; chỉ số OSPA hoặc MOTA |
| **4. Dữ liệu thật** | Thay mô phỏng RF bằng bộ dữ liệu công khai (DroneRF, RFUAV…); micro-Doppler bằng bản ghi radar FMCW giá rẻ; thêm mô hình thị giác thật (YOLO nhỏ) cho EO | Độ chính xác trên dữ liệu thật, không chỉ mô phỏng |
| **5. Vận hành** | Tài khoản chuyên viên, nhật ký chuỗi băm, giám sát Prometheus (độ trễ, số khung lỡ hạn), service systemd trên Jetson | Chạy liên tục 72 giờ không rò bộ nhớ |

---

## 8. Cách kiểm chứng lại

```bash
python -m pytest tests/ -q                 # 37 passed
cd src && python bench_edge.py --no-save   # số đo của máy đang dùng
cd src && python -m uvicorn server:app --port 8099
curl -s localhost:8099/api/health
```

Kiểm chứng “không đổi kết quả”: chạy `python src/evaluate.py` (ghi đè
`data/scenario_results.json`, nên chạy trên một bản sao) sẽ ra đúng các cột `rmse_m`, `cls_acc_after_warmup`,
`operator_ask_rate` như `data/scenario_results.json` gốc. Riêng cột thời
gian xử lý thì phụ thuộc máy.
