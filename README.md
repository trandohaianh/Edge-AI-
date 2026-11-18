# Giám sát và bám quỹ đạo mục tiêu bay bằng AI đa cảm biến tại thiết bị biên

**Multi-Sensor Edge AI Object Surveillance and Tracking System** — Dự án 2.

Hệ thống phát hiện, nhận dạng và bám quỹ đạo drone bay thấp bằng bốn loại cảm
biến (radar, tần số vô tuyến, camera quang học/hồng ngoại, LiDAR), chạy trọn
một khung trong **8,99 ms** so với ngân sách 50 ms của đề bài.

> **Ranh giới đạo đức.** Hệ thống chỉ giám sát, nhận dạng, bám quỹ đạo và đưa
> ra điểm tin cậy kèm bằng chứng cho người trực ca quyết định. Không có và sẽ
> không có cơ chế tự động chọn mục tiêu tác chiến hay điều khiển vũ khí đánh
> chặn. Mọi thao tác xác nhận hay bỏ qua của chuyên viên đều được ghi nhật ký.

---

## Kết quả đo được

| Yêu cầu của đề bài | Mục tiêu | Kết quả đo |
|---|---|---|
| Tổng thời gian nhận tín hiệu → tọa độ bám | < 50 ms | **8,99 ms** (p99), 1,92 ms trung bình; khung chậm nhất 57 ms (xem ghi chú) |
| Phát hiện sớm từ tín hiệu vô tuyến I/Q | Học sâu | **96,4%** trên 2.800 mẫu |
| Phát hiện sớm từ micro-Doppler radar | Học sâu | **95,4%** trên 2.800 mẫu |
| Nhận dạng đúng qua 7 kịch bản mô phỏng điều kiện hiện trường | — | **100%** ở cả 7 |
| Báo động nhầm khi gặp chim | — | **0%** số khung bị đẩy lên người trực |
| Dự đoán quỹ đạo 1 giây tới | EKF + Transformer | sai số thấp hơn **19,8%** so với ngoại suy vận tốc không đổi (trên cửa sổ 1 s) |
| Bám qua quãng mất dấu 4 giây (S7) | — | sai số trung bình 18,3 m so với 26,9 m của ngoại suy vận tốc không đổi (**thấp hơn ~32%**) |
| Chống nhãn ngụy trang đánh lừa camera | — | **100%** đúng trên 1.596 khung / 12 lần chạy (camera đơn lẻ: 0%, hợp nhất với trọng số đều nhau: 10,9%); vết nghi bị đánh lừa **vẫn được đưa lên người trực** (94% số khung) |
| Bám nhiều mục tiêu có báo động giả | — | 4 kịch bản (tới 6 drone, 3 báo động giả/khung): độ phủ **100%**, **0** lần đổi ID, OSPA 0,8–3,9 m, chim không bị đưa lên người |
| Chạy trên SoC nhúng 10–25 W | Jetson Orin | **chưa đo trên phần cứng thật** |

Toàn bộ dữ liệu cảm biến là **mô phỏng theo mô hình vật lý**. Không có dữ liệu
thực địa. Xem mục Hạn chế trong báo cáo.

Ghi chú sau đợt rà soát và phát triển 11/2026 (chi tiết ở `reports/01_…` và `reports/02_…`):

- Con số 19,8% đo trên cửa sổ dự đoán 1 giây; kịch bản mất dấu 4 giây (S7)
  là một con số riêng. Bảng trên đã tách hai con số này.
- Camera nay đúng 60° và đặt trên bệ quay được radar dẫn hướng; RF không còn
  là bằng chứng cho "chim"; vết nghi bị đánh lừa được đưa lên người trực.
  Số liệu S1–S7 đã chạy lại theo mô hình mới. Dòng thời gian xử lý ở bảng
  trên vẫn là số đo gốc trong container; đo lại trên laptop có tải nền cho
  p99 10–38 ms tuỳ lúc, nên cần đo trên phần cứng đích.
- p99 dưới ngân sách rất xa, nhưng khung chậm nhất trong lần đo gốc là 57 ms,
  vượt 50 ms. Một nguồn gai đã được gỡ (dự đoán 9 giây khi mất dấu nay được
  nối dần từng giây). Đo lại trên máy đích bằng `python src/bench_edge.py`.
- Thí nghiệm nhãn ngụy trang có lỗi ghép I/Q từ hai đoạn tín hiệu khác nhau
  và chỉ thực sự chấm 2–4/12 lần chạy; đã sửa, kết quả vẫn 100% nhưng nay trên
  1.596 khung. Báo cáo DOCX/PDF và slide **chưa** sinh lại theo số mới.

## Chạy thử

```bash
pip install -r requirements.txt

# Dashboard cho người trực ca (7 kịch bản bấm chuyển được, có 1 kịch bản nhiều mục tiêu)
cd src && python3 -m uvicorn server:app --port 8099
# mở http://localhost:8099   (Windows: dùng `python` thay `python3`)

python3 -m pytest tests/ -q          # 54 bài kiểm thử
python3 src/bench_edge.py            # đo độ trễ từng mô hình trên máy đích
```

Cấu hình qua biến môi trường (không có giá trị nào bắt buộc khi demo):

| Biến | Ý nghĩa |
|---|---|
| `EDGE_API_TOKEN` | Nếu đặt, mọi lệnh POST (xác nhận/bỏ qua, đổi kịch bản) phải gửi header `X-API-Token`; dashboard sẽ hỏi mã một lần. Nếu **không** đặt, lệnh POST chỉ được nhận từ chính máy chủ (127.0.0.1) — máy khác chỉ xem được. |
| `EDGE_AUDIT_LOG` | Tệp JSONL nhật ký quyết định, mặc định `logs/audit.jsonl`. Mỗi dòng nối chuỗi băm SHA-256 với dòng trước; kiểm tra bằng `python src/audit_log.py logs/audit.jsonl`. |
| `EDGE_ALLOW_UNTRAINED` | `1` cho phép chạy khi thiếu tệp trọng số (chỉ để thử luồng; dashboard hiện cảnh báo đỏ). |

Chạy bằng Docker (CPU): `docker build -t edge-ai . && docker run -p 8099:8099 -e EDGE_API_TOKEN=<mã ca trực> -v edge-audit:/var/lib/edge edge-ai`
(trong Docker, trình duyệt không phải loopback của container nên cần đặt mã để bấm được).
Kiểm tra sống: `GET /api/health`.

## Sinh lại toàn bộ số liệu

Chạy đúng theo thứ tự này sẽ dựng lại mọi con số trong báo cáo và slide:

```bash
python3 src/train_detect.py md    # bộ phát hiện micro-Doppler      (~17 phút)
python3 src/train_rf2.py          # bộ phát hiện RF (STFT + CNN 2D) (~13 phút)
python3 src/ablation_rf.py        # so sánh với CNN 1D trên I/Q thô (~3 phút)
python3 src/train_traj_ekf.py     # Transformer quỹ đạo, trên đầu ra EKF (~3 phút)
python3 src/evaluate.py           # 7 kịch bản + đo thời gian xử lý (~1 phút)
python3 src/adversarial.py        # thử nghiệm chống đánh lừa       (~1 phút)
python3 src/evaluate_mtt.py       # bám nhiều mục tiêu + báo động giả (~4 phút)
python3 src/bench_edge.py         # độ trễ từng mô hình trên máy đang chạy
python3 src/figures.py            # vẽ lại toàn bộ hình, song ngữ
cd docs/build && node report.js vi && node report.js en
cd docs/build && node slides.js vi && node slides.js en
```

## Cấu trúc

```
src/
  config.py          hằng số vật lý và ngưỡng, dùng chung cho code lẫn báo cáo
  rf_sim.py          sinh tín hiệu I/Q: nhiễu nền, WiFi, Bluetooth, link drone
  radar_sim.py       sinh chữ ký micro-Doppler từ công thức f_d = 2v/λ
  scene.py           quỹ đạo 3D, thời tiết, và mô hình đo của 4 cảm biến
  models.py          RFNet (CNN 1D), MicroDopplerNet (CNN 2D), TrajTransformer
  rf_stft.py         bản RF có tầng STFT cố định phía trước
  ekf.py             bộ lọc Kalman mở rộng đa cảm biến, cập nhật tuần tự
  fusion.py          cộng bằng chứng nhận dạng có trọng số tin cậy
  pipeline.py        vòng xử lý một khung, có đo thời gian từng chặng
  sensors.py         lịch chạy cảm biến, dữ liệu thô theo yêu cầu, bệ quay camera, báo động giả
  mtt.py             bám NHIỀU mục tiêu: liên kết GNN + cổng χ², vết tạm/xác nhận M-of-N
  evaluate_mtt.py    đánh giá đa mục tiêu: OSPA, độ phủ, đổi ID, vết giả, độ trễ theo số mục tiêu
  audit_log.py       nhật ký quyết định chuỗi băm + công cụ kiểm tra
  evaluate.py        chạy 7 kịch bản mô phỏng điều kiện hiện trường
  adversarial.py     thử nghiệm nhãn ngụy trang đánh lừa camera
  figures.py         vẽ hình cho báo cáo, song ngữ
  server.py          dashboard FastAPI cho người trực ca, nhật ký JSONL, /api/health
  bench_edge.py      đo tham số, dung lượng, độ trễ từng mô hình trên máy đích
docs/                báo cáo DOCX/PDF và slide PPTX/PDF, song ngữ Việt – Anh
tests/               54 bài kiểm thử tự động
reports/             báo cáo rà soát và lộ trình phát triển
data/                trọng số mô hình và kết quả đo dạng JSON
```

## Ba lỗi đã tìm ra và sửa

Phần này ghi lại vì chúng nói nhiều về cách làm hơn là các con số đẹp.

**1. PRF radar quá thấp làm gập phổ chữ ký cánh quạt.** Lần dựng đầu đặt PRF
4 kHz nên dải Doppler quan sát được chỉ ±2 kHz, trong khi đầu cánh drone cho
Doppler khoảng 5,3 kHz ở băng X. Chữ ký bị gập thành nhiễu và trên ảnh phổ
drone trông y hệt nền nhiễu. Nâng PRF lên 20 kHz thì chữ ký hiện ra.

**2. Cửa sổ quan sát RF cố định làm nhãn sai.** Bản đầu cắt cửa sổ 1,024 ms cố
định. Với tín hiệu nhảy tần có chu kỳ bật tắt vài mili giây, rất nhiều cửa sổ
gán nhãn "có drone" thật ra toàn nhiễu. Độ chính xác kẹt ở 67% và 567/700 mẫu
drone bị đoán thành nhiễu. Thêm tầng STFT đưa lên 96,4% — nhìn qua là thắng 29
điểm nhờ kiến trúc. Nhưng sau khi mô hình hoá đúng máy thu (bắt theo ngưỡng
năng lượng rồi mới cắt cửa sổ) và huấn luyện lại cả hai trên cùng bộ dữ liệu,
CNN 1D đạt 94,9% còn bản STFT đạt 96,4%. **Phần lớn "chiến thắng của kiến
trúc" thực ra là lỗi dữ liệu.**

**3. Mốc so sánh quá yếu làm Transformer trông giỏi hơn thực tế.** Bản huấn
luyện đầu lấy quỹ đạo thật cộng nhiễu 1,5 m rồi lấy đạo hàm số ra vận tốc.
Trên tập đó Transformer hơn phép ngoại suy vận tốc không đổi tới 52%. Đem vào
hệ thống thật thì **không hơn gì cả**, vì mốc so sánh kia lấy vận tốc bằng sai
phân của vị trí nhiễu, còn EKF thật có số đo vận tốc xuyên tâm từ radar nên
vận tốc tốt hơn nhiều. Huấn luyện lại trên chính chuỗi trạng thái do EKF sinh
ra và so với chính phép ngoại suy của EKF đó, mức cải thiện thật là 19,8%.

## Hạn chế

- Chưa đo trên Jetson Orin thật; mọi con số thời gian đo trên CPU x86 2 nhân.
- Toàn bộ dữ liệu là mô phỏng, dù dựng theo mô hình vật lý.
- Nhánh EO/IR mô hình hoá ở mức đầu ra, chưa chạy mô hình thị giác trên video thật.
- Nhật ký quyết định là tệp JSONL nối thêm, chưa ký số chống sửa; dashboard chưa có tài khoản riêng cho từng chuyên viên.

---

Trần Đỗ Hải Anh · 10/2026
