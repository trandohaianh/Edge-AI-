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
| Tổng thời gian nhận tín hiệu → tọa độ bám | < 50 ms | **8,99 ms** (p99), 1,92 ms trung bình |
| Phát hiện sớm từ tín hiệu vô tuyến I/Q | Học sâu | **96,4%** trên 2.800 mẫu |
| Phát hiện sớm từ micro-Doppler radar | Học sâu | **95,4%** trên 2.800 mẫu |
| Nhận dạng đúng qua 7 kịch bản mô phỏng điều kiện hiện trường | — | **100%** ở cả 7 |
| Báo động nhầm khi gặp chim | — | **0%** số khung bị đẩy lên người trực |
| Bám quỹ đạo khi mất dấu | EKF + Transformer | sai số thấp hơn **19,8%** so với ngoại suy vận tốc không đổi |
| Chống nhãn ngụy trang đánh lừa camera | — | **100%** đúng (camera đơn lẻ: 0%, hợp nhất với trọng số đều nhau: 5,3%) |
| Chạy trên SoC nhúng 10–25 W | Jetson Orin | **chưa đo trên phần cứng thật** |

Toàn bộ dữ liệu cảm biến là **mô phỏng theo mô hình vật lý**. Không có dữ liệu
thực địa. Xem mục Hạn chế trong báo cáo.

## Chạy thử

```bash
pip install -r requirements.txt

# Dashboard cho người trực ca (có 6 kịch bản bấm chuyển được)
cd src && python3 -m uvicorn server:app --port 8099
# mở http://localhost:8099

python3 -m pytest tests/ -q          # 20 bài kiểm thử
```

## Sinh lại toàn bộ số liệu

Chạy đúng theo thứ tự này sẽ dựng lại mọi con số trong báo cáo và slide:

```bash
python3 src/train_detect.py md    # bộ phát hiện micro-Doppler      (~17 phút)
python3 src/train_rf2.py          # bộ phát hiện RF (STFT + CNN 2D) (~13 phút)
python3 src/ablation_rf.py        # so sánh với CNN 1D trên I/Q thô (~3 phút)
python3 src/train_traj_ekf.py     # Transformer quỹ đạo, trên đầu ra EKF (~3 phút)
python3 src/evaluate.py           # 7 kịch bản + đo thời gian xử lý (~1 phút)
python3 src/adversarial.py        # thử nghiệm chống đánh lừa       (~1 phút)
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
  evaluate.py        chạy 7 kịch bản mô phỏng điều kiện hiện trường
  adversarial.py     thử nghiệm nhãn ngụy trang đánh lừa camera
  figures.py         vẽ hình cho báo cáo, song ngữ
  server.py          dashboard FastAPI cho người trực ca
docs/                báo cáo DOCX/PDF và slide PPTX/PDF, song ngữ Việt – Anh
tests/               20 bài kiểm thử tự động
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
- Mỗi lần chỉ bám một mục tiêu; liên kết số đo đa mục tiêu chưa làm.

---

Trần Đỗ Hải Anh · 10/2026
