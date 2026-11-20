# Quy ước của dự án

Quy ước ở đây được **máy kiểm tra** khi có thể (ruff, pre-commit, CI), nên
không phải nhớ. Phần còn lại là thoả thuận giữa người viết mã.

## 1. Cấu trúc thư mục

```
backend/edge_ai/        mã Python (gói cài được, tên gói: edge_ai)
  config.py             MỌI hằng số vật lý, ngưỡng và đường dẫn — một nguồn duy nhất
  io_utils.py           đọc/ghi JSON (luôn UTF-8)
  sim/                  mô phỏng cảm biến (thay bằng driver phần cứng khi lên trạm thật)
  ml/                   kiến trúc mạng nơ-ron
  tracking/             EKF, hợp nhất, vòng xử lý một/nhiều mục tiêu
  api/                  FastAPI + nhật ký quyết định
  experiments/          đánh giá, đo hiệu năng, vẽ hình (không chạy trên trạm)
  training/             huấn luyện (offline)
backend/tests/          pytest
frontend/               dashboard tĩnh (HTML/CSS/JS thuần, không cần build)
data/models/            trọng số .pt (commit — tổng < 1 MB)
data/results/           số đo .json mà báo cáo và dashboard đọc
deploy/                 Dockerfile, docker-compose.yml, Caddyfile
docs/                   tài liệu, hình, mã sinh báo cáo DOCX/PPTX
reports/                báo cáo rà soát và phát triển
```

**Quy tắc phụ thuộc giữa các gói** (mũi tên = được phép import):

```
config, io_utils  ←  sim  ←  tracking  ←  api
                     ml   ←  tracking
experiments, training  →  mọi gói ở trên
```

- `api/` không được import `experiments/` hay `training/`. Máy chủ trên trạm
  không cần mã đánh giá. (Đợt 1 phát hiện `server.py` import `evaluate.py`
  và đã sửa.)
- `sim/` không được import `tracking/`. Mô phỏng không được biết bộ bám làm gì.
- Bộ bám **không bao giờ** đọc `meta["truth_id"]`; trường đó chỉ dùng để chấm điểm.

## 2. Đặt tên

| Loại | Quy tắc | Ví dụ |
|---|---|---|
| Module, gói | `snake_case`, danh từ ngắn | `radar_sim.py`, `tracking/` |
| Hàm, biến | `snake_case`, động từ cho hàm | `predict_many`, `run_nets`, `pos_sigma` |
| Lớp | `PascalCase` | `MultiTracker`, `EOTurret` |
| Hằng số | `UPPER_SNAKE_CASE`, đặt ở `config.py` hoặc đầu module | `FRAME_DT`, `MAX_SPEC_PER_FRAME` |
| Biến toán học | Giữ đúng ký hiệu trong công thức: `H`, `P`, `R`, `Q`, `F`, `S`, `K` (ruff được cấu hình bỏ qua N802/N803/N806 cho trường hợp này) | `S = H @ P @ H.T + R` |
| Đơn vị | Hậu tố khi không hiển nhiên | `latency_ms`, `r0` (m), `slew_deg_s` |
| Test | `test_<điều được bảo đảm>`, viết tiếng Việt không dấu, mô tả HÀNH VI | `test_rf_khong_bao_gio_la_bang_chung_cho_chim` |
| Biến môi trường | `EDGE_` + `UPPER_SNAKE_CASE` | `EDGE_API_TOKEN`, `EDGE_DATA_DIR` |
| Endpoint | `/api/<danh-từ>`, thao tác bằng động từ HTTP | `GET /api/state`, `POST /api/act` |
| Tệp kết quả | `data/results/<thí_nghiệm>.json` | `mtt_results.json` |
| Nhánh git | `<loại>/<mô-tả-ngắn>` | `feat/jpda`, `fix/latency-spike`, `audit/danh-gia-phat-trien` |

## 3. Chú thích và ngôn ngữ

- Chú thích và docstring viết **tiếng Việt**; tên trong mã viết tiếng Anh.
- Chú thích giải thích **vì sao**, không lặp lại mã làm gì. Khi sửa một lỗi
  thật, giữ một câu nói bản cũ sai thế nào. Các chú thích dạng “Bản cũ …” là
  có chủ đích: chúng là hồ sơ phương pháp của khoá luận.

## 4. Định dạng và lint

- **ruff** cho cả lint lẫn format (cấu hình ở `pyproject.toml`): độ dài dòng
  100, nhóm luật E, W, F, I, N, B, UP, SIM.
- Chạy tay: `ruff check . && ruff format .`
- Tự động trước mỗi commit: `pre-commit install` (một lần), sau đó mọi
  commit đều qua ruff, ruff-format, chặn tệp > 1 MB và chặn khoá riêng.
- CI (`.github/workflows/ci.yml`) chạy lint, test và build Docker cho mỗi lần
  push.
- Xuống dòng LF (`.gitattributes`), UTF-8 (`.editorconfig`).

## 5. Kích thước tệp

- Một tệp mã nên dưới **~500 dòng**; quá **800 dòng** thì phải tách theo trách
  nhiệm. Hiện tại tệp lớn nhất là `experiments/figures.py` (~630 dòng, mỗi
  hình một hàm độc lập).
- Không gom cả phần mềm vào một tệp: mỗi gói con một trách nhiệm (mục 1).

## 6. Test

- Mỗi lỗi đã sửa có một test nhắm đúng lỗi đó; docstring của test nói bản cũ
  sai thế nào.
- Test không được phụ thuộc thời gian thực hay tải máy (không assert độ trễ
  tuyệt đối). Độ trễ đo bằng `experiments/bench_edge.py` và `evaluate_mtt.py`.
- Chạy: `python -m pytest` ở gốc repo.

## 7. Commit

- Commit tại các **mốc ổn định**: trước một thay đổi rủi ro (tái cấu trúc, đổi
  mô hình) và sau khi test xanh. Không commit khi test đỏ.
- Thông điệp: dòng đầu ≤ 72 ký tự, mệnh lệnh, nói *cái gì*; thân nói *vì sao*
  và số liệu nếu có.
- Không commit `.env`, khoá, nhật ký chạy, dữ liệu sinh ra (`data/cache/`).
  Trọng số mới lớn hơn 1 MB thì dùng Git LFS (`git lfs track "*.pt"`) thay vì
  commit thẳng.
- Không force-push lên nhánh dùng chung.
