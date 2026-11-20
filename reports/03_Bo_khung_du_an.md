# Bộ khung dự án — Edge AI (Dự án 2)

Ngày: 20/11/2026 · Nhánh: `audit/danh-gia-phat-trien` · Tiếp nối báo cáo `01` và `02`

Yêu cầu của đợt này có hai phần. Thứ nhất, sửa nốt các việc ở báo cáo 02,
mục 7 mà không cần phần cứng Jetson. Thứ hai, đưa dự án về một bộ khung **chạy
được và quản lý phiên bản được**, theo danh sách kiểm tra của chủ dự án. Mỗi
mục bên dưới ứng với một dòng trong danh sách đó và gồm: hiện trạng trước
đợt này, những gì đã thay đổi, đường dẫn, cách chạy, và kết quả kiểm tra.

---

## 0. Tóm tắt

| Mục kiểm tra | Trước | Sau |
|---|---|---|
| Cấu trúc thư mục rõ ràng | `src/` phẳng 24 tệp, `static/`, `data/` lẫn trọng số với số đo | `backend/edge_ai/{sim,ml,tracking,api,experiments,training}`, `frontend/`, `data/{models,results}`, `deploy/` |
| Tách frontend / backend / dữ liệu / module | Chưa tách | Đã tách. Quy tắc phụ thuộc giữa các gói được **test** bắt buộc |
| README | Có, nhưng thiếu cách cài, cấu hình, triển khai, API | Viết lại đầy đủ 10 mục |
| `.gitignore` | Tối thiểu | Đầy đủ: bí mật, dữ liệu sinh ra, nhật ký, công cụ |
| `.env.example` không chứa bí mật | Không có | Có, mọi giá trị nhạy cảm để trống |
| Quy tắc đặt tên | Không có văn bản | `docs/CONVENTIONS.md`; phần đặt tên được ruff (luật `N`) kiểm tra |
| Lint + format | Không có | ruff lint + format, pre-commit, CI. **0 lỗi** |
| Không viết cả phần mềm trong một tệp lớn | Tệp lớn nhất 424 dòng | Tệp lớn nhất 631 dòng (`figures.py`, mỗi hình một hàm), không tệp nào > 800 |
| Commit tại các mốc ổn định | Có từ đợt 1 | 6 commit trong đợt này, mỗi commit sau khi test xanh và trước mỗi thay đổi rủi ro |
| HTTPS riêng | Không có | `deploy/docker-compose.yml` + Caddy; **đã build và chạy thật** |
| Đầu ra: khung chạy được, có quản lý phiên bản | — | 61/61 test xanh, ruff sạch, pre-commit sạch; container và HTTPS qua Caddy đã chạy thật |

Bổ sung về kỹ thuật (báo cáo 02, mục 7):
- Trần số mạng nặng mỗi khung (2 ảnh phổ + 1 đoạn I/Q), ưu tiên vết chưa chắc nhãn.
- Dự đoán EKF theo lô bằng numpy.

Docker và Caddy đã được **build và chạy thử thật** (mục 10). Lần chạy thử này
bắt được một lỗi cấu hình Caddy. Khi đo lại cũng tìm và sửa thêm hai lỗi của
bộ bám (mục 9.5).

---

## 1. Cấu trúc thư mục rõ ràng, tách theo chức năng

**Hiện trạng trước.** 24 tệp Python nằm phẳng trong `src/`, trộn lẫn mô phỏng,
mạng nơ-ron, bộ bám, máy chủ, đánh giá và huấn luyện. Trọng số `.pt` và kết
quả `.json` nằm chung trong `data/`. Test thêm `src/` vào `sys.path` bằng tay.

**Thay đổi.** Dùng `git mv` để giữ lịch sử từng tệp (commit `4f87841`):

```
backend/edge_ai/           gói Python cài được (pyproject.toml)
  config.py                + mọi ĐƯỜNG DẪN, ghi đè được bằng biến môi trường EDGE_*
  io_utils.py              mới: read_json / write_json (UTF-8)
  sim/       rf_sim, radar_sim, scene, sensors, scenarios(mới)
  ml/        nets (đổi tên từ models.py), rf_stft
  tracking/  ekf, fusion, pipeline, mtt
  api/       server, audit_log
  experiments/ evaluate, evaluate_mtt, adversarial, bench_edge, figures
  training/  train_detect, train_rf2, train_traj, train_traj_ekf, ablation_rf
backend/tests/
frontend/index.html        (từ static/)
data/models/*.pt           data/results/*.json
deploy/                    Dockerfile, docker-compose.yml, Caddyfile
```

Import viết lại tự động bằng script, đường dẫn dữ liệu gom về `config.py`.
`docs/build/*.js` (mã sinh DOCX/PPTX) được sửa để đọc `data/results/`.

**Quy tắc phụ thuộc** (ghi trong `docs/CONVENTIONS.md`, kiểm bằng
`test_quy_tac_phu_thuoc_giua_cac_goi`):
- `api`, `tracking`, `sim`, `ml` không được import `experiments`/`training`.
- `sim` không được biết `tracking`.

Khi viết test này thì phát hiện ngay một vi phạm: `api/server.py` import
`experiments/evaluate_mtt` để lấy hàm dựng kịch bản. Hàm đó đã được chuyển
sang `sim/scenarios.py`.

**Cơ sở dữ liệu.** Dự án không có DBMS và không cần. Thứ duy nhất phải lưu
bền là nhật ký quyết định (JSONL chuỗi băm, volume `edge-audit`). README nói
rõ điều này để không ai đi tìm thư mục `database/`.

**Kiểm tra.** 56/56 test xanh ngay sau khi di chuyển (hiện 61/61). Lệnh chạy dashboard:
`python -m uvicorn edge_ai.api.server:app --app-dir backend --port 8099`.

## 2. README

**Trước.** Có kết quả và “ba lỗi đã sửa”, nhưng lệnh chạy là `cd src && …`,
không có hướng dẫn venv, cấu hình, triển khai, API.

**Sau.** `README.md` gồm 10 mục: kết quả đo, chạy nhanh (venv, torch CPU,
lệnh dashboard, test), cấu trúc thư mục có chú thích, bảng biến môi trường,
triển khai HTTPS, lint/format/pre-commit/CI, sinh lại số liệu theo thứ tự,
bảng API, ba lỗi phương pháp, hạn chế.

## 3. `.gitignore`

**Trước.** 10 dòng.

**Sau.** Chia nhóm: Python và công cụ; **bí mật** (`.env`, `.env.*` trừ
`.env.example`, `TAI-KHOAN.md`, `*.pem`, `*.key`); dữ liệu sinh ra
(`data/cache/`, `*.npz`); nhật ký (`logs/`, `*.jsonl`, dữ liệu Caddy); IDE/OS.

Trọng số `data/models/*.pt` **được commit có chủ đích**: tổng 712 KB, cần cho
test và cho dashboard chạy ngay sau khi clone. Hook `check-added-large-files`
chặn mọi tệp > 1 MB, nên trọng số lớn hơn sau này buộc phải đi qua Git LFS.

## 4. `.env.example` không chứa khóa bí mật

**Trước.** Không có.

**Sau.** `.env.example` liệt kê mọi biến `EDGE_*`, `EDGE_DOMAIN`, `ACME_EMAIL`,
có chú thích tiếng Việt. Giá trị nhạy cảm (`EDGE_API_TOKEN`) để trống, kèm
lệnh sinh mã ngẫu nhiên. Hook `detect-private-key` của pre-commit chặn lỡ tay
commit khoá.

## 5. Quy tắc đặt tên

**Sau.** `docs/CONVENTIONS.md` gồm: cấu trúc thư mục và quy tắc phụ thuộc,
bảng đặt tên (module, hàm, lớp, hằng, ký hiệu toán học, hậu tố đơn vị, test,
biến môi trường, endpoint, nhánh git), ngôn ngữ chú thích, lint, kích thước
tệp, test, commit.

Phần máy kiểm được thì đã giao cho ruff (nhóm luật `N`, pep8-naming). Có ba
ngoại lệ có lý do và đều ghi trong `pyproject.toml`:
- Ký hiệu ma trận viết hoa trong công thức (`H`, `P`, `R`…).
- `l`/`I` trong công thức vật lý.
- Bí danh module trong test (`PL`, `EM`).

## 6. Lint và format

**Trước.** Không có công cụ nào. Lần chạy ruff đầu tiên báo **140 lỗi**
trên 26 tệp chưa được định dạng:

| Luật | Số lỗi | Ý nghĩa |
|---|---:|---|
| E702 | 35 | nhiều câu lệnh trên một dòng (dấu `;`) |
| I001 | 26 | thứ tự import |
| E501 | 21 | dòng quá 100 ký tự |
| F401 | 17 | import thừa |
| SIM115 | 14 | `open()` không dùng `with` |
| **F821** | **8** | **tên chưa định nghĩa: lỗi thật** |
| N812, B008, … | 19 | còn lại |

**F821 là lỗi thật, do chính bước tái cấu trúc gây ra.** `figures.py` dùng
`RESULTS_DIR` nhưng lại import nó dưới tên `DATA`; chạy script vẽ hình sẽ
`NameError`. Test không bắt được vì không test nào chạy qua `figures.py`.
Đã sửa, và thêm `test_figures_ve_duoc_tu_ket_qua_json` vẽ 8 hình vào thư mục
tạm.

**Thay đổi.**
- Cấu hình ruff trong `pyproject.toml`: dòng 100, luật E, W, F, I, N, B, UP, SIM.
- `ruff check --fix` và `ruff format` cho toàn bộ mã.
- Sửa tay phần còn lại. 14 chỗ `open()` thay bằng `io_utils.read_json` /
  `write_json` (dùng `ast` để thay đúng vị trí).
- FastAPI `Depends`/`Header` khai báo là lời gọi bất biến cho luật B008.
- `.pre-commit-config.yaml`: trailing-whitespace, end-of-file-fixer,
  check-yaml/toml, merge-conflict, detect-private-key,
  check-added-large-files (1 MB), ruff, ruff-format.
- `.gitattributes` chuẩn hoá xuống dòng LF (hết cảnh báo CRLF trên Windows),
  `.editorconfig`.
- CI `.github/workflows/ci.yml`: job `lint` → `test` (torch CPU) → `docker`
  (build và gọi `/api/health`).

**Kết quả hiện tại.**

```
$ ruff check .            → All checks passed!
$ ruff format --check .   → 40 files already formatted
$ pre-commit run --all-files  (chạy trong WSL)
trim trailing whitespace ......... Passed
fix end of files ................. Passed
check yaml ....................... Passed
check toml ....................... Passed
check for merge conflicts ........ Passed
detect private key ............... Passed
check for added large files ...... Passed
ruff ............................. Passed
ruff format ...................... Passed
```

Trên Windows, `pre-commit` không tạo được virtualenv do Python cài ở ổ `E:`
(lỗi của virtualenv với đường dẫn này, không phải của cấu hình), nên đã chạy
trong WSL. Ruff chạy được trực tiếp trên Windows.

## 7. Không viết toàn bộ phần mềm trong một file lớn

**Trước.** Tệp lớn nhất là `server.py` 424 dòng.

**Sau khi format** (ruff tách các dòng dài nên số dòng tăng):

| Tệp | Dòng |
|---|---:|
| `experiments/figures.py` | 631 |
| `api/server.py` | ~510 |
| `tracking/pipeline.py` | ~420 |
| `tracking/mtt.py` | ~370 |

Không tệp nào vượt ngưỡng 800 dòng nên **không cần tách thêm**. `figures.py`
dài nhất nhưng gồm 8 hàm độc lập, mỗi hàm vẽ một hình, nên tách ra không làm
nó dễ đọc hơn. Ngưỡng 500/800 dòng được ghi trong `docs/CONVENTIONS.md`.

## 8. Commit tại các mốc ổn định

Mỗi commit đều được tạo **sau khi** test xanh. Các thay đổi rủi ro (tái cấu
trúc, format toàn bộ) đều có một commit mốc **ngay trước** đó:

| Commit | Nội dung | Vai trò |
|---|---|---|
| `e57d3c1` | Trần mạng nặng mỗi khung, EKF theo lô | Mốc ổn định **trước** tái cấu trúc |
| `4f87841` | Tái cấu trúc sang `backend/edge_ai/…` | Rủi ro; 56/56 xanh rồi mới commit, và là mốc **trước** format toàn bộ |
| `806999b` | ruff, pre-commit, CI, `.env.example` | 57/57 xanh |
| `dd59b40` | Dockerfile mới + compose + Caddy | — |
| `039f1da` | Tối ưu phần bám, phương pháp đo bằng phát lại, `scenarios.py`, quy tắc phụ thuộc, README, CONVENTIONS | 59/59 xanh |
| `1c859db` | Sửa vết trùng và vết rác tìm ra khi đo lại; sửa lỗi email của Caddy; Docker đã kiểm thật | 61/61 xanh |
| *(cuối)* | Hoàn thiện báo cáo này, `write_json` ghi LF | 61/61 xanh |

## 9. Sửa nốt việc của báo cáo 02, mục 7 (không cần Jetson)

### 9.1 Trần số mạng nặng mỗi khung

**Vấn đề.** Bản chia lượt theo pha `(k + tid) % chu kỳ` vẫn để số lần chạy
mạng mỗi khung tăng theo N/3. Với 6–10 mục tiêu, đuôi phân bố chạm ngân sách
50 ms.

**Cách làm** (`tracking/mtt.py`, `_request_raw`). Mỗi khung chạy tối đa
`MAX_SPEC_PER_FRAME = 2` ảnh phổ (một batch) và `MAX_IQ_PER_FRAME = 1` đoạn
I/Q. Trong các vết đã đủ một chu kỳ kể từ lần phân loại trước, vết **chưa
chắc nhãn nhất** đi trước, hoà thì vết chờ lâu nhất. Đánh đổi: với nhiều mục
tiêu, mỗi vết được phân loại thưa hơn 0,3 s/lần; vết đã chắc 99% gần như
không mất gì.

**Test.** `test_tran_mang_nang_moi_khung_voi_10_muc_tieu`: với 10 mục tiêu,
không khung nào vượt trần, và cả 10 vết đều đã được phân loại ít nhất một lần.

### 9.2 Dự đoán EKF theo lô

`tracking/ekf.py::predict_many` tính `x' = F x`, `P' = F P Fᵀ + Q` cho cả lô
bằng `einsum`. Kết quả trùng tuyệt đối với gọi `predict` từng cái
(`test_du_doan_ekf_theo_lo_trung_tung_cai`).

Phần cập nhật EKF và tính Mahalanobis vẫn chạy theo vòng lặp. Lý do: sau khi
có lọc thô vector hoá và Jacobian giải tích (đợt 2), chúng không còn là chặng
tốn nhất. Đo bằng cProfile với 10 mục tiêu: mạng nơ-ron chiếm ~14 ms mỗi
khung, toàn bộ EKF chỉ ~2 ms.

### 9.3 Đo lại độ trễ

**Vấn đề của phép đo.** Máy đo là laptop Windows dùng chung, trong lúc làm
việc tải nền dao động 28–87% CPU (trình duyệt, các phiên đang xử lý 3 dự án
khác). Trong một lần đo, microbenchmark “2 ảnh phổ + 1 I/Q” cho p99 tới
**1.180 ms**, dù từng mạng riêng lẻ chỉ ~5 ms. Thời gian wall trên máy này
không dùng làm số liệu được.

**Phương pháp mới** (`experiments/evaluate_mtt.py::replay_latency`):
1. Ghi lại một chuỗi 120 khung (số đo và dữ liệu thô).
2. Phát lại đúng chuỗi đó qua 5 bộ bám mới.
3. Lấy thời gian **nhỏ nhất của từng khung** qua 5 lần phát lại.

Bộ bám là tất định (có test `test_bo_bam_tat_dinh_nen_phat_lai_do_duoc_do_tre`),
nên chênh lệch giữa các lần phát lại chỉ do tiến trình khác chen vào; `timeit`
của Python cũng lấy min theo cùng lý do. Đã thử đo CPU-time của luồng
(`time.thread_time`), nhưng trên Windows độ phân giải chỉ 15,6 ms nên bỏ.

**Kết quả: khung xấu nhất (max của chuỗi min), 2 lần chạy cùng mã**
(báo động giả 1/khung, torch 2 luồng, CPU x86, đã trừ thời gian mô phỏng cảm biến):

| Số mục tiêu | Trung bình | p99 | Khung xấu nhất | p99 thô (không lấy min) | Khung > 50 ms |
|---:|---:|---:|---:|---:|---:|
| 1 | 3,2–5,9 ms | 9,2–19,1 ms | 9,9–19,2 ms | 10–22 ms | 0 |
| 3 | 9,1–15,2 ms | 17,1–27,5 ms | 18,7–28,1 ms | 25–39 ms | 0 |
| 6 | 22,0–35,9 ms | 29,1–49,2 ms | 29,9–49,4 ms | 54–90 ms | 0 |
| 10 | 20,2–38,5 ms | 30,6–50,9 ms | 30,9–52,7 ms | 49–92 ms | 0 / 4 trên 117 |

Microbenchmark (`data/results/edge_bench.json`, min / trung vị / p99):

| Phép đo | min | p50 | p99 |
|---|---:|---:|---:|
| Mạng RF (1 đoạn) | 3,6 ms | 6,0 ms | 9,3 ms |
| Mạng micro-Doppler (1 ảnh) | 3,4 ms | 6,5 ms | 11,2 ms |
| Khung có trần: 2 ảnh phổ + 1 I/Q | 10,4 ms | 17,3 ms | 27,0 ms |
| Mất dấu, bản cũ (dự đoán trọn 9 s) | 7,2 ms | 8,6 ms | 14,3 ms |
| Mất dấu, bản mới (nối thêm 1 s) | 0,8 ms | 1,3 ms | 2,5 ms |

**Kết luận, nói đúng mức.**
- **Đến 3 mục tiêu** hệ thống nằm trong ngân sách 50 ms với biên rộng, kể cả
  ở số đo thô.
- **Từ 6 đến 10 mục tiêu**, khi máy bớt tải, khung xấu nhất khoảng 30 ms.
  Khi máy bị tải liên tục, nó chạm 50 ms (4/117 khung vượt ở lần đo xấu hơn).
- Nhờ có trần mạng nặng, chi phí phần mạng nơ-ron **không còn tăng theo số
  mục tiêu**.
- Phần còn tăng tuyến tính là phần bám bằng Python. Phần này đã được tối ưu
  (xem 9.4).
- Câu trả lời dứt khoát chỉ có trên phần cứng đích, chạy riêng.

### 9.4 Tối ưu phần bám (không đổi kết quả)

cProfile cho thấy phần bám tốn chủ yếu ở hàng chục nghìn lời gọi numpy trên
**số vô hướng**. Ví dụ `np.clip` bị gọi 16.497 lần cho 120 khung, mỗi lần mất
cỡ micro giây chỉ cho chi phí gọi. Đã sửa ba chỗ:
- `h()`, `H()`, `pos_sigma()` của EKF tính bằng `math`.
- Phép kẹp trong `fusion.py` dùng hàm `_clip` vô hướng.
- Kiểm tra trùng vết tính khoảng cách mọi cặp trong một phép numpy.

Đo **cùng lúc, cùng máy**, chạy bản cũ trong worktree tạm: phần bám 10 mục
tiêu (không tính mạng) giảm từ **6,68 xuống 4,44 ms (−34%)**. Đầu ra trùng
tuyệt đối với trước: cùng ID vết, chênh lệch vị trí 0,0 m.

### 9.5 Hai lỗi bám tìm ra nhờ đo lại

Lần đo lại sau khi thêm trần cho thấy M1 có 0,4 lần đổi ID và M2 có 0,05 vết
giả mỗi khung (trước đó đều là 0). Kiểm từng lượt:

| Lỗi | Nguyên nhân | Sửa | Kết quả |
|---|---|---|---|
| M1, 1/5 lượt: 2 lần đổi ID, 14 khung có vết trùng | Vết đã xác nhận trượt cổng radar 2 khung; vết tạm sinh từ chính các số đo đó nhận tiếp chúng rồi được xác nhận. Bước “cứu vết” chỉ xét số đo thừa | Cứu vết được **giành lại** số đo đang nằm ở vết tạm | 0 đổi ID (`test_cuu_vet_gianh_lai_so_do_tu_vet_tam`) |
| M2, 1/5 lượt: 0,24 vết giả/khung | Vết rác cách mục tiêu 2,2 km, được xác nhận nhờ 3 báo động giả tình cờ rơi vào cổng, rồi được chờ 4 s như vết thật | Vết “non” (< 10 lần đo vị trí) chỉ được chờ 0,5 s; vết “chín” giữ 4 s cho dự đoán khi mất dấu | 0,24 → 0,035 (`test_vet_non_bi_xoa_nhanh_vet_chin_duoc_cho_lau`) |

Trần mạng *không* trực tiếp gây ra hai lỗi trên. Nó chỉ làm đổi chuỗi số
ngẫu nhiên, nên các sự kiện hiếm này lộ ra ở seed khác. Đánh giá đầy đủ cuối
cùng (`data/results/mtt_results.json`, 5 lượt × 200 khung mỗi kịch bản):

| Kịch bản | OSPA (KTC 95%) | Độ phủ | Đổi ID | Vết giả/khung | Nhận dạng |
|---|---|---|---|---|---|
| M1 · 3 drone + 1 chim | 1,14 m (1,03–1,25) | 100% | 0 | 0 | 100% |
| M2 · 2 drone cách 2° | 1,68 m (0,69–2,66) | 100% | 0 | 0,007 | 100% |
| M3 · 6 drone, mưa, 3 báo động giả/khung | 1,41 m (1,32–1,50) | 100% | 0 | 0 | 100% |
| M4 · 2 drone + 2 chim, sương mù đêm | 3,54 m (3,26–3,82) | 100% | 0 | 0 | 99,9% |

## 10. HTTPS riêng: Docker + Caddy

**Tệp.**
- `deploy/Dockerfile`:
  - build từ gốc repo;
  - torch bản CPU;
  - tầng phụ thuộc tách riêng để đổi mã không phải cài lại torch;
  - chạy bằng user không phải root;
  - `HEALTHCHECK` gọi `/api/health`;
  - uvicorn bật `--proxy-headers`.
- `deploy/docker-compose.yml`:
  - `app` chỉ `expose` cổng 8099 trong mạng nội bộ, không mở ra ngoài;
  - `caddy:2.8-alpine` mở 80/443 (kể cả HTTP/3);
  - `caddy` chỉ khởi động khi `app` đã khoẻ;
  - volume `edge-audit` giữ nhật ký, `caddy-data` giữ chứng chỉ;
  - **thiếu `EDGE_API_TOKEN` thì compose từ chối chạy**, với thông báo
    hướng dẫn đặt biến.
- `deploy/Caddyfile`:
  - `{$EDGE_DOMAIN:localhost}`: localhost thì dùng CA nội bộ, tên miền thật
    thì tự xin chứng chỉ Let's Encrypt;
  - bật HSTS, nén zstd/gzip, health check ngược về app.
- `EDGE_API_TOKEN` giữ nguyên hành vi. Phía sau proxy, trình duyệt không còn
  là loopback của container, nên cần mã để thao tác. Đây đúng là mục đích của
  thiết kế ở đợt 2.

**Cách chạy.**

```bash
cp .env.example .env     # đặt EDGE_API_TOKEN, EDGE_DOMAIN
docker compose -f deploy/docker-compose.yml --env-file .env up -d --build
# https://localhost
```

**Đã kiểm tra.**
- `docker compose config` hợp lệ; thiếu `EDGE_API_TOKEN` thì báo lỗi đúng
  thông điệp đã viết.
- Chạy **đúng lệnh khởi động của container** trên máy, với `EDGE_API_TOKEN`
  được đặt:
  - `/api/health`, `/` và `/api/metrics` đều trả 200;
  - POST thiếu mã trả 401, POST có mã trả 200.

**Build và chạy thật** (Docker 29.8.0, project `edge-ai-test`, cổng
18080/18443 để không đụng dịch vụ khác):

| Kiểm tra | Kết quả |
|---|---|
| `docker build -f deploy/Dockerfile` | Thành công sau 7 phút 15 giây; ảnh 1,71 GB (phần lớn là torch CPU) |
| Container chạy bằng user nào | `uid=10001(edge)`, không phải root |
| `HEALTHCHECK` của Docker | `healthy` |
| `/api/health`, `/` qua container | 200, `models_trained: true`, `auth_required: true` |
| POST không mã / có mã | 401 / 200 |
| Compose + Caddy: `https://localhost:18443/api/health` | 200; chứng chỉ do CA nội bộ của Caddy cấp (`issuer: local`) |
| Header qua HTTPS | `Strict-Transport-Security`, `Content-Security-Policy`, `X-Frame-Options: DENY` |
| `http://localhost:18080/` | 308 chuyển sang `https://` |
| POST qua Caddy không mã / có mã | 401 / 200 |
| Nhật ký qua lần khởi động lại `app` | Chuỗi băm nối tiếp; `audit_log` báo hợp lệ |
| Dọn dẹp | `docker compose … down -v`, xoá ảnh thử; không dừng Docker Desktop |

**Lỗi tìm ra nhờ build thật.** Bản đầu đặt `email {$ACME_EMAIL:…}` trong
Caddyfile và `ACME_EMAIL: ${ACME_EMAIL:-}` trong compose. Compose truyền
**chuỗi rỗng** khi biến không được đặt; giá trị mặc định của Caddy chỉ áp
dụng khi biến *không tồn tại*. Kết quả là Caddy nhận `email` không có đối số
và khởi động lại liên tục. Đã bỏ chỉ thị email dựa trên biến môi trường;
chú thích trong Caddyfile hướng dẫn thêm tay khi cần.

Job `docker` trong CI chạy lại chuỗi build và kiểm tra sống này ở mỗi lần push.

## 11. Đẩy lên GitHub

Repo chưa có remote. Mọi commit hiện chỉ có trên máy. Khi có tên repo:

```bash
git remote add origin git@github.com:<chủ>/<tên>.git
git push -u origin main
git push -u origin audit/danh-gia-phat-trien   # không force-push
```

Trước khi push đã kiểm:
- Tệp lớn nhất được theo dõi là `data/models/rf_model.pt` (263 KB).
- Không có tệp > 1 MB nào ngoài tài liệu trong `docs/`: DOCX/PDF/PPTX, tổng
  khoảng 16 MB. Các tệp này là sản phẩm nộp của khoá luận nên được giữ lại;
  chúng có từ commit gốc, tức là trước khi có hook chặn tệp lớn.
- Không có `.env` hay khoá nào.

## 12. Việc còn lại

1. Đo trên Jetson Orin, máy chạy riêng:
   `python -m edge_ai.experiments.bench_edge --threads 4` và
   `python -m edge_ai.experiments.evaluate_mtt`. Đây là cách duy nhất trả lời
   dứt khoát câu hỏi 6–10 mục tiêu có nằm trong 50 ms hay không.
2. Nếu trên Jetson 10 mục tiêu vẫn chạm ngân sách, có hai hướng:
   - hạ trần xuống 1 ảnh phổ mỗi khung;
   - xuất hai CNN sang ONNX Runtime hoặc TensorRT FP16.
3. Sinh lại DOCX/PDF/slide theo số mới (README, mục 7). Việc này do chủ dự án làm.
4. Cân nhắc chuyển `docs/*.docx|pdf|pptx` (tệp lớn nhất ~2 MB, tổng ~16 MB)
   sang GitHub Releases nếu chúng còn được cập nhật thường xuyên.
5. Đẩy lên GitHub khi có tên repo (mục 11).
