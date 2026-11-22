# Giám sát và bám quỹ đạo mục tiêu bay bằng AI đa cảm biến tại thiết bị biên

**Multi-Sensor Edge AI Object Surveillance and Tracking System** — Dự án 2.

Hệ thống phát hiện, nhận dạng và bám quỹ đạo drone bay thấp bằng bốn loại cảm
biến: radar, tần số vô tuyến (RF), camera quang học/hồng ngoại (EO/IR) và
LiDAR. Nó bám được nhiều mục tiêu cùng lúc giữa báo động giả, và mỗi khung xử
lý phải xong trong ngân sách 50 ms của đề bài.

> **Ranh giới đạo đức.** Hệ thống chỉ giám sát, nhận dạng, bám quỹ đạo và đưa
> ra điểm tin cậy kèm bằng chứng cho người trực ca quyết định. Không có và sẽ
> không có cơ chế tự động chọn mục tiêu tác chiến hay điều khiển vũ khí đánh
> chặn. Mọi thao tác xác nhận hay bỏ qua của chuyên viên đều được ghi vào
> nhật ký chuỗi băm.

---

## Mục lục

1. [Kết quả đo được](#kết-quả-đo-được)
2. [Chạy nhanh](#chạy-nhanh)
3. [Cấu trúc thư mục](#cấu-trúc-thư-mục)
4. [Cấu hình](#cấu-hình)
5. [Triển khai có HTTPS](#triển-khai-có-https)
6. [Sao lưu nhật ký](#sao-lưu-nhật-ký)
7. [Phát triển: test, lint, format](#phát-triển-test-lint-format)
8. [Sinh lại toàn bộ số liệu](#sinh-lại-toàn-bộ-số-liệu)
9. [API](#api)
10. [Ba lỗi phương pháp đã tìm ra và sửa](#ba-lỗi-phương-pháp-đã-tìm-ra-và-sửa)
11. [Hạn chế](#hạn-chế)

## Kết quả đo được

| Yêu cầu của đề bài | Mục tiêu | Kết quả đo |
|---|---|---|
| Thời gian nhận tín hiệu → tọa độ bám (1 mục tiêu) | < 50 ms | **8,99 ms** p99, 1,92 ms trung bình (đo gốc trong container); khung chậm nhất 57 ms |
| Thời gian khi bám nhiều mục tiêu | < 50 ms | Có trần số mạng nặng mỗi khung, nên chi phí không tăng theo số mục tiêu. Bảng chi tiết ở `reports/03_Bo_khung_du_an.md` |
| Phát hiện sớm từ tín hiệu vô tuyến I/Q | Học sâu | **96,4%** trên 2.800 mẫu |
| Phát hiện sớm từ micro-Doppler radar | Học sâu | **95,4%** trên 2.800 mẫu |
| Nhận dạng đúng qua 7 kịch bản mô phỏng điều kiện hiện trường | — | **100%** ở cả 7 |
| Báo động nhầm khi gặp chim | — | **0%** số khung bị đẩy lên người trực |
| Dự đoán quỹ đạo 1 giây tới | EKF + Transformer | sai số thấp hơn **19,8%** so với ngoại suy vận tốc không đổi |
| Bám qua quãng mất dấu 4 giây (S7) | — | 18,3 m so với 26,9 m của ngoại suy vận tốc không đổi (**thấp hơn ~32%**) |
| Chống nhãn ngụy trang đánh lừa camera | — | **100%** đúng trên 1.596 khung / 12 lần chạy (camera đơn lẻ: 0%, hợp nhất cộng đều: 10,9%); vết nghi bị đánh lừa **vẫn được đưa lên người trực** |
| Bám nhiều mục tiêu có báo động giả | — | tới 6 drone, 3 báo động giả/khung: độ phủ **100%**, **0** lần đổi ID, OSPA 0,8–3,9 m |
| Chạy trên SoC nhúng 10–25 W | Jetson Orin | **chưa đo trên phần cứng thật** |

Toàn bộ dữ liệu cảm biến là **mô phỏng theo mô hình vật lý**; không có dữ liệu
thực địa. Quá trình rà soát và phát triển được ghi trong `reports/01`, `02`
và `03`. Báo cáo DOCX/PDF và slide trong `docs/` **chưa** sinh lại theo số
mới (cách sinh lại ở mục 7).

## Chạy nhanh

Cần Python ≥ 3.10. Trên máy không có GPU, cài torch bản CPU trước cho nhẹ.

```bash
git clone <repo> && cd <repo>
python -m venv .venv
# Windows: .venv\Scripts\activate      Linux/macOS: source .venv/bin/activate
pip install --index-url https://download.pytorch.org/whl/cpu "torch>=2.2"
pip install -r requirements-dev.txt

# Dashboard cho người trực ca: 7 kịch bản, trong đó 1 kịch bản nhiều mục tiêu
python -m uvicorn edge_ai.api.server:app --app-dir backend --port 8099
# mở http://localhost:8099

python -m pytest            # 73 bài kiểm thử
```

Trọng số đã huấn luyện (< 1 MB) nằm sẵn trong `data/models/` nên dashboard
chạy được ngay sau khi clone, không phải huấn luyện lại.

## Cấu trúc thư mục

```
backend/                     BACKEND — Python, gói "edge_ai"
  edge_ai/
    config.py                hằng số vật lý, ngưỡng, ĐƯỜNG DẪN (một nguồn duy nhất)
    io_utils.py              đọc/ghi JSON (luôn UTF-8)
    sim/                     mô phỏng cảm biến
      rf_sim.py                I/Q: nhiễu nền, WiFi, Bluetooth, link điều khiển drone
      radar_sim.py             chữ ký micro-Doppler từ f_d = 2v/λ
      scene.py                 quỹ đạo 3D, thời tiết, mô hình đo của 4 cảm biến
      sensors.py               lịch chạy cảm biến, dữ liệu thô, bệ quay camera, báo động giả
      scenarios.py             dựng kịch bản nhiều mục tiêu
    ml/                      mạng nơ-ron
      nets.py                  MicroDopplerNet, TrajTransformer, RFNet (CNN 1D, để so sánh)
      rf_stft.py               RF: tầng STFT cố định + CNN 2D
    tracking/                bám quỹ đạo
      ekf.py                   EKF đa cảm biến, Jacobian giải tích, dự đoán theo lô
      fusion.py                hợp nhất nhận dạng có trọng số tin cậy, phát hiện mâu thuẫn
      pipeline.py              vòng xử lý một mục tiêu, nạp mô hình
      mtt.py                   NHIỀU mục tiêu: GNN + cổng χ², M-of-N, trần mạng nặng mỗi khung
    api/                     máy chủ
      server.py                FastAPI: dashboard, /api/*, xác thực, header bảo mật
      audit_log.py             nhật ký quyết định chuỗi băm SHA-256, chia theo tháng + công cụ kiểm tra
      audit_backup.py          sao lưu / khôi phục / dọn 12 tháng
    experiments/             đánh giá (không chạy trên trạm)
      evaluate.py, evaluate_mtt.py, adversarial.py, bench_edge.py, figures.py
    training/                huấn luyện (offline)
      train_detect.py, train_rf2.py, train_traj_ekf.py, train_traj.py, ablation_rf.py
  tests/                     pytest: test_core, test_mtt, test_pipeline_server
frontend/                    FRONTEND — dashboard tĩnh (HTML/CSS/JS thuần, không cần build)
  index.html
data/                        DỮ LIỆU
  models/                    trọng số .pt (commit, tổng < 1 MB)
  results/                   số đo .json mà báo cáo và dashboard đọc
deploy/                      TRIỂN KHAI: Dockerfile, docker-compose.yml, Caddyfile (HTTPS)
docs/                        PRD.md (yêu cầu sản phẩm), CONVENTIONS.md, báo cáo DOCX/PDF, slide, hình
reports/                     báo cáo rà soát 01, phát triển 02, bộ khung 03
.github/workflows/ci.yml     CI: lint → test → build Docker + kiểm tra sống
pyproject.toml               gói, cấu hình pytest và ruff
.pre-commit-config.yaml      ruff, ruff-format, chặn tệp lớn và khoá riêng trước mỗi commit
.env.example                 mẫu biến môi trường (không chứa bí mật)
```

**Cơ sở dữ liệu.** Dự án không dùng DBMS. Thứ duy nhất cần lưu bền là nhật ký
quyết định của chuyên viên, ghi vào tệp JSONL chuỗi băm (`logs/audit.jsonl`,
hoặc volume `edge-audit` khi chạy Docker). Trọng số và số đo là tệp phẳng
trong `data/`. Quy ước đặt tên và quy tắc phụ thuộc giữa các gói nằm ở
[`docs/CONVENTIONS.md`](docs/CONVENTIONS.md).

## Cấu hình

Chép `.env.example` thành `.env` rồi sửa. Khi chạy demo trên máy cá nhân thì
không biến nào là bắt buộc.

| Biến | Ý nghĩa |
|---|---|
| `EDGE_API_TOKEN` | Có giá trị: mọi lệnh POST (xác nhận/bỏ qua, đổi kịch bản) phải gửi header `X-API-Token`; dashboard sẽ hỏi mã một lần. **Không** có: lệnh POST chỉ được nhận từ chính máy chủ (127.0.0.1), máy khác chỉ xem được. Bắt buộc khi chạy Docker/Caddy. |
| `EDGE_AUDIT_LOG` | Tệp nhật ký, mặc định `logs/audit.jsonl`. Kiểm tra chuỗi băm: `python -m edge_ai.api.audit_log logs/audit.jsonl` (chạy trong `backend/`) |
| `EDGE_DATA_DIR`, `EDGE_MODELS_DIR`, `EDGE_RESULTS_DIR`, `EDGE_STATIC_DIR`, `EDGE_LOG_DIR` | Ghi đè đường dẫn (mặc định tính từ gốc repo) |
| `EDGE_ALLOW_UNTRAINED` | `1` cho phép chạy khi thiếu trọng số (chỉ để thử luồng; dashboard hiện băng cảnh báo đỏ) |
| `EDGE_DOMAIN`, `EDGE_HTTP_PORT`, `EDGE_HTTPS_PORT` | Dùng cho Caddy, xem mục dưới |

## Triển khai có HTTPS

`deploy/docker-compose.yml` dựng hai dịch vụ: `app` (FastAPI, cổng 8099,
**không** mở ra ngoài) và `caddy` (cổng 80/443, tự lo chứng chỉ TLS).

```bash
cp .env.example .env
# sửa .env: EDGE_API_TOKEN=<chuỗi ngẫu nhiên>, EDGE_DOMAIN=localhost hoặc tên miền thật
docker compose -f deploy/docker-compose.yml --env-file .env up -d --build
# mở https://localhost   (hoặc https://<tên miền>)
docker compose -f deploy/docker-compose.yml logs -f
```

- `EDGE_DOMAIN=localhost`: Caddy tự tạo CA nội bộ, nên trình duyệt sẽ cảnh
  báo chứng chỉ tự ký. Dùng để thử trên máy.
- `EDGE_DOMAIN=<tên miền thật>`: Caddy tự xin và tự gia hạn chứng chỉ Let's
  Encrypt. Cần DNS trỏ về máy và mở cổng 80/443.
- Không đặt `EDGE_API_TOKEN` thì compose từ chối khởi động. Qua proxy, trình
  duyệt không phải loopback của container nên không có mã thì không bấm được.
- Nhật ký quyết định nằm trong volume `edge-audit`, giữ lại qua các lần khởi
  động lại.

Chỉ chạy container, không Caddy:
`docker build -f deploy/Dockerfile -t edge-ai . && docker run -p 8099:8099 -e EDGE_API_TOKEN=<mã> edge-ai`.

## Sao lưu nhật ký

Nhật ký quyết định được chia theo tháng (`audit-YYYY-MM.jsonl`), nối chuỗi
băm SHA-256 qua các tháng, và **giữ 12 tháng** (PRD Q-5). Khi chạy bằng
compose, dịch vụ `backup` tự làm hai việc mỗi ngày:
- dọn các tháng quá hạn;
- sao lưu vào volume `edge-backups`, hoặc vào thư mục `EDGE_BACKUP_DIR` nếu
  được đặt.

Mỗi bản sao lưu là một thư mục theo ngày, kèm `MANIFEST.json` ghi SHA-256
của từng tệp.

```bash
# kiểm tra nhật ký đang dùng
docker compose -p edge-ai -f deploy/docker-compose.yml exec app \
  python -m edge_ai.api.audit_log /var/lib/edge/audit.jsonl
# xem các bản sao lưu
docker compose -p edge-ai -f deploy/docker-compose.yml exec backup ls -l /backups
# khôi phục: DỪNG app trước (nếu không, app vẫn giữ băm cũ trong bộ nhớ và ghi đứt chuỗi)
docker compose -p edge-ai -f deploy/docker-compose.yml stop app
docker compose -p edge-ai -f deploy/docker-compose.yml run --rm --no-deps backup \
  python -m edge_ai.api.audit_backup restore --snapshot /backups/2026-11-22 \
  --log /var/lib/edge/audit.jsonl          # thêm --force nếu chắc chắn muốn ghi đè
docker compose -p edge-ai -f deploy/docker-compose.yml start app
```

- Khôi phục **từ chối** bản sao lưu đã bị sửa, và từ chối ghi đè nhật ký
  đang có nếu không có `--force`.
- Tệp nhật ký và sao lưu có quyền `600`, thư mục `700`, chủ là user `edge`
  (uid 10001). Kỹ thuật viên và người kiểm tra đọc qua `docker compose exec`
  như trên, nên không cần mở quyền cho ai khác.
- **Bản sao lưu nằm trên cùng ổ đĩa với máy trạm.** Hãy định kỳ chép ra USB
  hoặc ổ mạng, ví dụ:
  `docker run --rm -v edge-ai_edge-backups:/b -v /media/usb:/out alpine cp -a /b/. /out/`
- Trên Windows (Git Bash), đặt `MSYS_NO_PATHCONV=1` trước các lệnh có đường
  dẫn kiểu `/var/lib/...`, nếu không Git Bash sẽ tự đổi chúng thành đường dẫn
  Windows.

## Phát triển: test, lint, format

```bash
python -m pytest                 # toàn bộ test (cấu hình trong pyproject.toml)
ruff check .                     # lint: E,W,F,I,N,B,UP,SIM
ruff format .                    # định dạng
pre-commit install               # một lần: tự chạy ruff + chặn tệp lớn/khoá trước mỗi commit
pre-commit run --all-files
```

CI (`.github/workflows/ci.yml`) chạy cùng các bước đó, rồi build ảnh Docker
và gọi `/api/health` để kiểm tra container sống.

## Sinh lại toàn bộ số liệu

Chạy trong thư mục `backend/`, đúng thứ tự dưới đây:

```bash
cd backend
python -m edge_ai.training.train_detect md      # micro-Doppler           (~17 phút)
python -m edge_ai.training.train_rf2            # RF STFT + CNN 2D        (~13 phút)
python -m edge_ai.training.ablation_rf          # so với CNN 1D I/Q thô   (~3 phút)
python -m edge_ai.training.train_traj_ekf       # Transformer quỹ đạo     (~3 phút)
python -m edge_ai.experiments.evaluate          # 7 kịch bản              (~3 phút)
python -m edge_ai.experiments.adversarial       # chống đánh lừa          (~1 phút)
python -m edge_ai.experiments.evaluate_mtt      # nhiều mục tiêu          (~6 phút)
python -m edge_ai.experiments.bench_edge        # độ trễ từng mô hình trên máy này
python -m edge_ai.experiments.figures           # vẽ lại toàn bộ hình, song ngữ
cd ../docs/build && node report.js vi && node report.js en && node slides.js vi && node slides.js en
```

## API

| Phương thức | Đường dẫn | Mô tả |
|---|---|---|
| GET | `/` | Dashboard |
| GET | `/api/state` | Trạng thái khung mới nhất: các vết bám, bằng chứng, độ trễ, nhật ký |
| GET | `/api/health` | Kiểm tra sống (200 khi vòng xử lý đang chạy) |
| GET | `/api/metrics` | Số đo đã lưu trong `data/results/` |
| POST | `/api/act` | `{"action": "xac_nhan"\|"bo_qua", "tid": <id vết>, "operator": "<tên ca>"}` |
| POST | `/api/scenario/{name}` | Đổi kịch bản: `clear`, `fog_night`, `jamming`, `bird`, `patch`, `dropout`, `swarm` |

## Ba lỗi phương pháp đã tìm ra và sửa

Phần này được giữ lại vì nó nói về cách làm nhiều hơn là về các con số đẹp.

**1. PRF radar quá thấp làm gập phổ chữ ký cánh quạt.** Lần dựng đầu đặt PRF
4 kHz, nên dải Doppler quan sát được chỉ ±2 kHz, trong khi đầu cánh drone cho
Doppler khoảng 5,3 kHz ở băng X. Chữ ký bị gập thành nhiễu: trên ảnh phổ,
drone trông y hệt nền nhiễu. Nâng PRF lên 20 kHz thì chữ ký hiện ra.

**2. Cửa sổ quan sát RF cố định làm nhãn sai.** Bản đầu cắt cửa sổ 1,024 ms cố
định. Với tín hiệu nhảy tần có chu kỳ bật tắt vài mili giây, rất nhiều cửa sổ
gán nhãn "có drone" thật ra toàn nhiễu. Độ chính xác kẹt ở 67%. Sau khi mô
hình hoá đúng máy thu và huấn luyện lại cả hai kiến trúc trên cùng bộ dữ
liệu, CNN 1D đạt 94,9% còn bản STFT đạt 96,4%. **Phần lớn "chiến thắng của
kiến trúc" thực ra là lỗi dữ liệu.**

**3. Mốc so sánh quá yếu làm Transformer trông giỏi hơn thực tế.** Bản đầu so
với phép ngoại suy dùng vận tốc lấy từ sai phân vị trí nhiễu, và thắng tới
52%. Đem vào hệ thống thật thì không hơn gì cả, vì EKF thật có số đo vận tốc
xuyên tâm từ radar. Huấn luyện lại trên chính chuỗi trạng thái do EKF sinh ra
và so với chính phép ngoại suy của EKF đó, mức cải thiện thật là 19,8%.

## Hạn chế

- Chưa đo trên Jetson Orin thật. Mọi con số thời gian đều đo trên CPU x86, và
  laptop dùng chung có tải nền làm số đo dao động mạnh.
- Toàn bộ dữ liệu là mô phỏng, dù dựng theo mô hình vật lý.
- Nhánh EO/IR mới mô hình hoá ở mức đầu ra, chưa chạy mô hình thị giác trên video thật.
- Liên kết đa mục tiêu dùng GNN; chưa thử hai quỹ đạo cắt nhau trong cùng ô phân giải (cần JPDA/MHT).
- Dashboard chưa có tài khoản riêng cho từng chuyên viên (chỉ một mã truy cập dùng chung).

---

Trần Đỗ Hải Anh · 10/2026 — cập nhật 11/2026
