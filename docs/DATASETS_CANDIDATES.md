# Bộ dữ liệu công khai ứng viên để kiểm chứng trên dữ liệu thật (E3-A)

> **Trạng thái: CHƯA TẢI. Cần chủ dự án duyệt việc tải và tự kiểm giấy phép
> trên trang gốc trước khi dùng.** Soạn 23/11/2026 từ hiểu biết sẵn có và tìm
> kiếm web (chế độ tiêu chuẩn). Ô "giấy phép" ghi "chưa xác nhận" nghĩa là
> trang kết quả tìm kiếm không hiện trường giấy phép, phải mở trang gốc để
> đọc. Dung lượng là ước tính.

Toàn bộ số đo hiện có của dự án (độ chính xác, ECE, OSPA, ...) đều trên dữ
liệu **mô phỏng** (`backend/edge_ai/sim/`). Mục tiêu của danh sách này là tìm
dữ liệu thật để đo lại, **chỉ thu thụ động / dùng bản ghi có sẵn**, đúng ranh
giới "chỉ giám sát".

## Danh sách

| # | Tên | Nguồn | Giấy phép | Dung lượng (ước) | Cảm biến | Phù hợp |
|---|---|---|---|---|---|---|
| 1 | **DroneRF** (Qatar University, 2019) | https://data.mendeley.com/datasets/f4c2b4n755 · bài báo Data in Brief, doi 10.1016/j.dib.2019.104313 | Chưa xác nhận. Mendeley Data thường dùng CC BY 4.0, phải đọc trường "Licence" trên trang | Hàng chục GB (227 đoạn ghi; chưa xác nhận) | RF, 2 bộ thu USRP băng 2,4 GHz (mỗi bộ một nửa băng); 3 drone (Bebop, AR, Phantom) + nền không drone | **Cao** cho bộ phân loại RF (`drone_ctrl` hay không). Lưu ý: băng thông thu (cỡ 40 MHz mỗi bộ, theo hiểu biết, cần kiểm) khác hẳn `RF_FS = 2 MS/s` của dự án, nên phải hạ tần/lấy mẫu lại; lớp WiFi/Bluetooth phải tách riêng vì bộ này chỉ có "nền" |
| 2 | **DroneRFa** (2024) | Bài báo *Journal of Electronics & Information Technology* 46(4), doi 10.11999/JEIT230570; trang tải ghi trong bài | Chưa xác nhận (bộ dẫn xuất DroneRFx-FCSIQ yêu cầu tuân theo điều khoản của bản gốc) | Lớn (hàng chục–hàng trăm GB, chưa xác nhận) | RF I/Q; ~25 loại drone (9 ngoài trời, 15 trong nhà) + nền | **Cao** nếu giấy phép cho phép: nhiều loại drone hơn DroneRF, có I/Q |
| 3 | **KTH 77 GHz FMCW: drone, chim, người** (2021) | https://zenodo.org/records/5511912 (đã có phiên bản mới hơn) | Chưa xác nhận, ghi "Open" trên Zenodo; đọc ô "Licenses" của cả phiên bản mới | ~1,5 GB, 75 868 mẫu `.mat` | Radar FMCW 77 GHz (SAAB SIRS 1600); 6 loại drone + chim + người | **Trung bình**: đúng bài toán phân biệt drone/chim bằng radar, nhưng mỗi mẫu là một lát quét cự ly–phương vị (5×256), không phải ảnh phổ micro-Doppler 64×128 như `MicroDopplerNet`; phải đổi đầu vào hoặc chỉ dùng để kiểm phần liên kết/bám |
| 4 | **Millimeter Wave 60 GHz Radar Measurements: UAS and Birds** | https://ieee-dataport.org/open-access/millimeter-wave-60-ghz-radar-measurements-uas-and-birds (doi 10.21227/c8r5-6h79) | Chưa xác nhận, mục giấy phép để trống; tải cần tài khoản IEEE miễn phí | Chưa rõ | Radar 60 GHz; UAS và chim | **Trung bình**: có cặp drone/chim; băng tần khác X-band của dự án nên chữ ký Doppler phải quy đổi theo bước sóng |
| 5 | **DIAT-µSAT** (micro-Doppler của UAV nhỏ) | https://ieee-dataport.org/node/9814 | **Hạn chế**: chỉ dùng cho học thuật, phải gửi thư xin tác giả | ~4 849 ảnh micro-Doppler (cỡ vài trăm MB) | Radar CW băng X; nhiều loại drone + chim máy | **Cao về mặt kỹ thuật** (cùng băng X, đã là ảnh micro-Doppler), nhưng điều khoản "chỉ học thuật" có thể không hợp với mục đích của dự án; cần chủ dự án quyết |
| 6 | **DroneAudioSet** (NeurIPS 2025, Datasets & Benchmarks) | https://huggingface.co/datasets/ahlab-drone-project/DroneAudioSet · mã: https://github.com/augmented-human-lab/DroneAudioSet-code | MIT (theo bài báo; cần đối chiếu trên trang Hugging Face) | ~23,5 giờ âm thanh (cỡ vài chục GB) | Âm thanh (micro gắn trên drone) | **Thấp–trung bình**: dự án hiện **không có cảm biến âm thanh**; bộ này ghi tiếng ồn của chính drone để tìm người, không phải phát hiện drone từ mặt đất. Chỉ hữu ích nếu sau này thêm micro |

Ghi chú thêm (không đưa vào bảng vì giấy phép không rõ hoặc gộp nhiều nguồn):
**DADS – Drone Audio Detection Samples** trên Hugging Face gộp nhiều nguồn âm
thanh drone/không drone (16 kHz mono); mỗi nguồn con có điều khoản riêng nên
phải kiểm từng nguồn.

## Đề xuất thứ tự (chờ chủ dự án duyệt)

1. **DroneRF** trước: giấy phép nhiều khả năng mở, khớp trực tiếp bộ phân loại
   RF, đủ để đo lại độ chính xác và ECE (E1) trên dữ liệu thật.
2. **KTH 77 GHz** hoặc **DIAT-µSAT** cho nhánh radar, tuỳ chủ dự án chấp nhận
   điều khoản "chỉ học thuật" hay không.
3. Âm thanh để sau, vì kiến trúc hiện tại không có micro.

## Trước khi tải (việc của chủ dự án)

- [ ] Mở trang gốc, đọc và lưu lại nguyên văn giấy phép (ảnh chụp hoặc tệp).
- [ ] Xác nhận mục đích dùng nằm trong điều khoản (học thuật/thương mại).
- [ ] Duyệt dung lượng và nơi lưu (không commit dữ liệu thô vào git).
- [ ] Ghi trích dẫn bắt buộc vào báo cáo.
