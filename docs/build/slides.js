// node slides.js vi|en -> ../Edge_AI_Surveillance_Slides_<LANG>.pptx
const pptxgen = require('pptxgenjs');
const fs = require('fs');
const path = require('path');
const L = process.argv[2] === 'en' ? 'en' : 'vi';
const T = (vi, en) => (L === 'en' ? en : vi);
const D = f => JSON.parse(fs.readFileSync(path.join(__dirname, '../../data/results/' + f)));
const RF = D('rf_metrics.json'), MD = D('md_metrics.json'), TJ = D('traj_metrics.json');
const SC = D('scenario_results.json'), AD = D('adversarial.json');
const TJS = fs.existsSync(path.join(__dirname, '../../data/results/traj_metrics_synthetic.json')) ? D('traj_metrics_synthetic.json') : null;
const LAT = SC.latency_ms, scen = SC.scenarios;
const byId = id => scen.find(s => s.scenario.startsWith(id));
const blind = (scen.find(s => s.blind_curve) || {}).blind_curve || [];
const bAt = t => blind.reduce((a, r) => (Math.abs(r.t_s - t) < Math.abs(a.t_s - t) ? r : a), blind[0]);
const n = (x, d = 0) => Number(x).toLocaleString(L === 'vi' ? 'vi-VN' : 'en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
const VIDEO = process.env.EDGE_VIDEO_URL || '';

const pres = new pptxgen();
pres.layout = 'LAYOUT_16x9';
pres.author = 'Tran Do Hai Anh';
pres.title = T('Giám sát đa cảm biến tại thiết bị biên', 'Multi-sensor edge AI surveillance');
const RED = 'D7153A', INK = '111111', WHITE = 'FFFFFF', SOFT = 'F2F2F2', MUTED = '6B6B6B', OKC = '1A9E5C', WARN = 'E8A317';
const HEAD = 'Montserrat', BODY = 'Arial';
const F = f => path.join(__dirname, '../fig', f);
let pg = 0;
function tx(s, text, o) { s.addText(text, Object.assign({ isTextBox: true, fontFace: BODY, color: INK, margin: 0, valign: 'top' }, o)); }
function slide(dark, notes) {
  const s = pres.addSlide(); s.background = { color: dark ? INK : WHITE }; pg++;
  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 0.12, h: 5.625, fill: { color: RED }, line: { color: RED, width: 0 } });
  tx(s, String(pg).padStart(2, '0'), { x: 9.0, y: 5.25, w: 0.5, h: 0.25, fontSize: 9, color: dark ? '8A8A8A' : MUTED, align: 'right', bold: true, fontFace: HEAD });
  tx(s, T('Giám sát đa cảm biến tại biên · Dự án 2', 'Multi-sensor edge surveillance · Project 2'), { x: 0.45, y: 5.25, w: 5, h: 0.25, fontSize: 8, color: dark ? '8A8A8A' : MUTED, fontFace: HEAD });
  s.addNotes(notes);
  return s;
}
function title(s, kicker, t, dark) {
  tx(s, kicker, { x: 0.45, y: 0.32, w: 8.6, h: 0.25, fontSize: 9, bold: true, color: RED, fontFace: HEAD, charSpacing: 2 });
  tx(s, t, { x: 0.45, y: 0.58, w: 9.1, h: 0.55, fontSize: 22, bold: true, color: dark ? WHITE : INK, fontFace: HEAD });
}
function bullets(items, size = 13, color = INK) {
  return items.map((t, i) => ({ text: t, options: { bullet: true, fontSize: size, color, paraSpaceAfter: 6, breakLine: i < items.length - 1 } }));
}
function stat(s, x, y, w, v, l, hi) {
  s.addShape(pres.shapes.RECTANGLE, { x, y, w, h: 1.3, fill: { color: hi ? RED : SOFT }, line: { color: hi ? RED : SOFT, width: 0 } });
  tx(s, v, { x: x + 0.15, y: y + 0.14, w: w - 0.25, h: 0.5, fontSize: 21, bold: true, fontFace: HEAD, color: hi ? WHITE : INK });
  tx(s, l, { x: x + 0.15, y: y + 0.68, w: w - 0.25, h: 0.58, fontSize: 9.5, color: hi ? WHITE : MUTED });
}
const img = (s, f, o) => s.addImage(Object.assign({ path: F(f) }, o));

// ---------------------------------------------------------------- 1. bìa
{
  const s = slide(true, T(
    `[~35 giây] "Em xin trình bày Dự án 2: hệ thống giám sát và bám quỹ đạo mục tiêu bay bằng AI đa cảm biến, chạy tại thiết bị biên. Ba ý em muốn anh/chị nhớ: hệ thống chạy được từ đầu đến cuối, mọi con số đều đo chứ không ước lượng, và em nói rõ chỗ nào chưa làm được."
THAO TÁC: Nhìn người nghe, chưa cần nói số liệu.`,
    `[~35 s] "This is Project 2: a multi-sensor edge AI system that watches, identifies and tracks low-flying targets. Three things to remember: it runs end to end, every number is measured rather than estimated, and I am explicit about what is not done."
DELIVERY: Look at the panel, no numbers yet.`));
  tx(s, T('DỰ ÁN 02 · AI TẠI THIẾT BỊ BIÊN', 'PROJECT 02 · EDGE AI'), { x: 0.45, y: 1.15, w: 8, h: 0.3, fontSize: 11, bold: true, color: RED, fontFace: HEAD, charSpacing: 2 });
  tx(s, [{ text: T('GIÁM SÁT & BÁM QUỸ ĐẠO\n', 'SURVEILLANCE & TRACKING\n'), options: { color: WHITE } },
    { text: T('BẰNG AI ĐA CẢM BIẾN', 'WITH MULTI-SENSOR AI'), options: { color: RED, bold: true } }],
  { x: 0.45, y: 1.6, w: 9.1, h: 1.5, fontSize: 34, bold: true, fontFace: HEAD, lineSpacing: 38 });
  tx(s, T('Radar · Tần số vô tuyến · Camera quang học và hồng ngoại · LiDAR\nPhát hiện sớm, hợp nhất cảm biến, bám quỹ đạo khi mất dấu — trong 50 ms',
    'Radar · Radio frequency · Electro-optical and infrared · LiDAR\nEarly detection, sensor fusion, tracking through dropouts — within 50 ms'),
  { x: 0.45, y: 3.25, w: 8.6, h: 0.8, fontSize: 12.5, color: 'C9C9C9', lineSpacing: 19 });
  s.addShape(pres.shapes.RECTANGLE, { x: 0.45, y: 4.3, w: 4.2, h: 0.42, fill: { color: WARN }, line: { color: WARN, width: 0 } });
  tx(s, T('⚠ CHỈ GIÁM SÁT — NGƯỜI QUYẾT ĐỊNH', '⚠ SURVEILLANCE ONLY — A HUMAN DECIDES'), { x: 0.45, y: 4.3, w: 4.2, h: 0.42, fontSize: 9.5, bold: true, color: INK, align: 'center', valign: 'middle', fontFace: HEAD });
  tx(s, T('Trần Đỗ Hải Anh · 10/2026', 'Tran Do Hai Anh · October 2026'), { x: 5.0, y: 4.38, w: 4.5, h: 0.3, fontSize: 11, color: '9A9A9A', fontFace: HEAD });
}

// ---------------------------------------------------------------- 2. đề bài
{
  const s = slide(false, T(
    `[~50 giây] "Đề bài là phát hiện và bám drone bay thấp ngoài thực địa: sương mù, đêm tối, nhiễu địa hình, nhiễu điện từ. Thiết bị chạy độc lập, không có mạng. Bốn nhóm yêu cầu: phát hiện sớm bằng tín hiệu phi hình ảnh, hợp nhất bốn loại cảm biến, bám quỹ đạo kể cả khi mất dấu, và chống bị đánh lừa. Ràng buộc cứng: chip 10 đến 25 W và toàn bộ vòng xử lý dưới 50 ms."
NẾU ĐƯỢC HỎI vì sao không dùng mỗi camera: "Camera không đo được cự ly, và đêm hoặc sương mù là mù."`,
    `[~50 s] "The brief is detecting and tracking low-flying drones in the field: fog, darkness, clutter, jamming. The unit runs offline. Four requirement groups: early detection from non-imaging signals, fusion of four sensors, tracking through dropouts, and adversarial robustness. Hard constraints: a 10–25 W SoC and the whole loop under 50 ms."
IF ASKED why not just a camera: "A camera cannot measure range, and it is blind at night or in fog."`));
  title(s, T('ĐỀ BÀI', 'THE BRIEF'), T('Bốn yêu cầu, hai ràng buộc cứng', 'Four requirements, two hard constraints'));
  const items = [
    [T('Phát hiện sớm bằng tín hiệu PHI HÌNH ẢNH', 'Early detection from NON-IMAGING signals'), T('Phân tích phổ tần số vô tuyến và micro-Doppler của radar để thấy mục tiêu trước khi camera kịp nhìn rõ.', 'Analyse RF spectra and radar micro-Doppler to see targets before a camera can resolve them.')],
    [T('Hợp nhất bốn luồng cảm biến', 'Fuse four sensor streams'), T('Radar, tần số vô tuyến, camera quang học/hồng ngoại và đám mây điểm LiDAR cùng lúc.', 'Radar, RF, electro-optical/infrared and LiDAR point cloud at the same time.')],
    [T('Bám quỹ đạo khi mất dấu', 'Track through dropouts'), T('Bộ lọc Kalman mở rộng kết hợp Transformer nhẹ để dự đoán tiếp đường bay.', 'An extended Kalman filter plus a light Transformer to carry the trajectory.')],
    [T('Kháng nhiễu và chống đánh lừa', 'Robustness and adversarial resistance'), T('Thời tiết, nhiễu địa hình, và nhãn dán ngụy trang đánh lừa mô hình thị giác.', 'Weather, terrain clutter, and adversarial patches that fool vision models.')],
  ];
  items.forEach(([t, d], i) => {
    const x = 0.45 + (i % 2) * 4.65, y = 1.3 + Math.floor(i / 2) * 1.5;
    s.addShape(pres.shapes.RECTANGLE, { x, y, w: 4.4, h: 1.3, fill: { color: SOFT }, line: { color: SOFT, width: 0 } });
    tx(s, String(i + 1).padStart(2, '0'), { x: x + 0.16, y: y + 0.12, w: 0.6, h: 0.22, fontSize: 9, bold: true, color: RED, fontFace: HEAD });
    tx(s, t, { x: x + 0.16, y: y + 0.34, w: 4.1, h: 0.34, fontSize: 11.5, bold: true, fontFace: HEAD });
    tx(s, d, { x: x + 0.16, y: y + 0.7, w: 4.1, h: 0.55, fontSize: 9.2, color: '444444' });
  });
  s.addShape(pres.shapes.RECTANGLE, { x: 0.45, y: 4.42, w: 9.1, h: 0.6, fill: { color: INK }, line: { color: INK, width: 0 } });
  tx(s, T('Ràng buộc cứng:  SoC 10–25 W  ·  toàn bộ vòng xử lý < 50 ms  ·  chạy offline, không dựa vào đám mây',
    'Hard constraints:  10–25 W SoC  ·  whole loop < 50 ms  ·  offline, no cloud dependency'),
  { x: 0.45, y: 4.42, w: 9.1, h: 0.6, fontSize: 11.5, bold: true, color: WHITE, align: 'center', valign: 'middle', fontFace: HEAD });
}

// ---------------------------------------------------------------- 3. kiến trúc
{
  const s = slide(false, T(
    `[~55 giây] "Đây là luồng xử lý. Bốn cảm biến vào bên trái, mỗi cảm biến chỉ đóng góp đúng thứ nó đo được: radar cho cự ly và vận tốc, RF chỉ cho phương vị, camera chỉ cho góc, LiDAR cho toạ độ 3D nhưng chỉ trong 250 mét. Hai mạng nơ-ron ở khối đỏ làm phát hiện sớm. Phần hợp nhất dựng quỹ đạo. Cuối cùng mọi thứ đi tới người trực ca chứ không đi tới bất kỳ cơ cấu chấp hành nào."
NHẤN MẠNH: không cảm biến nào vừa xa vừa chính xác vừa bền thời tiết — đó là lý do phải hợp nhất.`,
    `[~55 s] "This is the pipeline. Four sensors on the left, each contributing only what it truly measures: radar gives range and velocity, RF gives bearing only, the camera gives angles only, LiDAR gives 3D position but only within 250 m. The two networks in the red block do early detection. Fusion builds the track. Everything ends at the duty operator, not at any actuator."
EMPHASISE: no sensor is simultaneously long-range, accurate and weather-proof — hence fusion.`));
  title(s, T('KIẾN TRÚC', 'ARCHITECTURE'), T('Mỗi cảm biến chỉ nói đúng thứ nó biết', 'Each sensor only states what it knows'));
  img(s, `arch_${L}.png`, { x: 0.45, y: 1.2, w: 9.1, h: 4.0 });
}

// ---------------------------------------------------------------- 4. mô phỏng
{
  const s = slide(false, T(
    `[~60 giây] "Em không có phần cứng và không có dữ liệu thực địa, nên toàn bộ tín hiệu được sinh từ mô hình vật lý. Micro-Doppler dựng theo công thức f_d = 2v/lambda: thân mục tiêu cho một vạch, cánh quạt quay cho blade flash lặp lại ở tần số bằng số cánh nhân tốc độ quay. Chim vỗ cánh 2 đến 9 Hz nên chữ ký chậm hơn hẳn và không có blade flash. Đây chính là cơ sở để phân biệt drone với chim."
NẾU BỊ HỎI dữ liệu mô phỏng thì tin được không: xem slide 11.`,
    `[~60 s] "I had no hardware and no field data, so every signal comes from a physical model. Micro-Doppler follows f_d = 2v/lambda: the body gives one line, spinning blades give blade flashes repeating at blades times rotation rate. A bird flaps at 2–9 Hz, so its signature is far slower and has no blade flash. That is exactly what separates a drone from a bird."
IF ASKED whether simulated data can be trusted: see slide 11.`));
  title(s, T('DỮ LIỆU', 'THE DATA'), T('Mô phỏng theo vật lý, không phải nhiễu gắn nhãn', 'Physics-based simulation, not labelled noise'));
  img(s, `signatures_${L}.png`, { x: 0.45, y: 1.15, w: 9.1, h: 2.42 });
  tx(s, T('Chữ ký micro-Doppler mô phỏng — đây chính là ảnh đưa vào mạng nơ-ron',
    'Simulated micro-Doppler — exactly the images fed to the network'), { x: 0.45, y: 3.62, w: 9.1, h: 0.25, fontSize: 9.5, color: MUTED, italic: true });
  s.addShape(pres.shapes.RECTANGLE, { x: 0.45, y: 3.98, w: 9.1, h: 1.05, fill: { color: SOFT }, line: { color: SOFT, width: 0 } });
  tx(s, T('MỘT LỖI PHẢI SỬA', 'A BUG THAT HAD TO BE FIXED'), { x: 0.65, y: 4.1, w: 3, h: 0.22, fontSize: 9, bold: true, color: RED, fontFace: HEAD });
  tx(s, T('Lần dựng đầu đặt PRF 4 kHz nên dải Doppler chỉ ±2 kHz, trong khi đầu cánh drone cho Doppler 5,3 kHz ở băng X. Chữ ký bị gập phổ thành nhiễu — trên ảnh phổ drone trông y hệt nền nhiễu. Nâng PRF lên 20 kHz thì chữ ký hiện ra.',
    'The first build used a 4 kHz PRF, giving only ±2 kHz of Doppler, while a drone blade tip produces 5.3 kHz at X-band. The signature aliased into noise — a drone looked exactly like the noise floor. Raising the PRF to 20 kHz brought it out.'),
  { x: 0.65, y: 4.33, w: 8.7, h: 0.62, fontSize: 9.8, color: '333333' });
}

// ---------------------------------------------------------------- 5. hai bộ phát hiện
{
  const s = slide(false, T(
    `[~55 giây] "Hai bộ phát hiện sớm. Bộ RF đạt ${n(RF.test_acc * 100, 1)} phần trăm, bộ micro-Doppler ${n(MD.test_acc * 100, 1)} phần trăm. Điều em muốn anh/chị nhìn là ma trận nhầm lẫn: nhầm lẫn còn lại nằm đúng ở cặp khó nhất về vật lý là drone cánh bằng với drone đa cánh quạt, vì cả hai đều có cánh quạt quay. Chim và nhiễu địa hình gần như không bị nhầm. Và đường cong bên phải cho thấy độ chính xác RF theo tỉ số tín hiệu trên nhiễu, từ 86 phần trăm ở tín hiệu rất yếu lên 99 phần trăm."
NHẤN MẠNH: mô hình nhỏ, tổng cộng dưới 130 nghìn tham số, vì chạy trên chip nhúng.`,
    `[~55 s] "The two early detectors: RF at ${n(RF.test_acc * 100, 1)} per cent, micro-Doppler at ${n(MD.test_acc * 100, 1)} per cent. What I want you to look at is the confusion: what remains is exactly the physically hardest pair, fixed-wing versus multirotor, because both have spinning propellers. Birds and clutter are almost never confused. The curve on the right shows RF accuracy against signal-to-noise, from 86 per cent in very weak signal up to 99."
EMPHASISE: the models are small, under 130k parameters in total, because they run on an embedded chip.`));
  title(s, T('PHÁT HIỆN SỚM', 'EARLY DETECTION'), T('Hai mạng nhỏ, nhầm lẫn đúng chỗ khó', 'Two small networks, confused only where physics is hard'));
  img(s, `accuracy_${L}.png`, { x: 0.45, y: 1.12, w: 9.1, h: 2.68 });
  stat(s, 0.45, 3.95, 2.18, n(RF.test_acc * 100, 1) + '%', T('phân loại tín hiệu vô tuyến', 'RF signal classification'), true);
  stat(s, 2.76, 3.95, 2.18, n(MD.test_acc * 100, 1) + '%', T('phân loại micro-Doppler', 'micro-Doppler classification'));
  stat(s, 5.07, 3.95, 2.18, n(RF.by_snr[Object.keys(RF.by_snr)[0]] * 100, 0) + '%', T('vẫn đúng ở tín hiệu rất yếu −6…0 dB', 'still correct at −6…0 dB'));
  stat(s, 7.38, 3.95, 2.17, n(RF.params + MD.params), T('tham số cho cả hai mạng', 'parameters for both networks'));
}

// ---------------------------------------------------------------- 6. bài học dữ liệu
{
  const s = slide(true, T(
    `[~60 giây] "Slide này là bài học em thấy đáng giá nhất. Độ chính xác RF ban đầu kẹt ở 67 phần trăm, và 567 trên 700 mẫu drone bị đoán thành nhiễu. Giả thuyết đầu của em là kiến trúc sai nên em thêm tầng STFT, độ chính xác nhảy lên 96 — nhìn qua là thắng 29 điểm. Nhưng nguyên nhân thật là lỗi dữ liệu: em cắt cửa sổ 1 mili giây cố định, mà tín hiệu nhảy tần có chu kỳ bật tắt vài mili giây, nên rất nhiều cửa sổ gán nhãn có drone thật ra toàn nhiễu. Sau khi sửa dữ liệu và huấn luyện lại cả hai trên cùng bộ dữ liệu, CNN 1D đạt ${n(RF.ablation_raw_iq_1dcnn_acc * 100, 1)} và bản STFT ${n(RF.test_acc * 100, 1)}. Phần lớn chiến thắng của kiến trúc hoá ra là lỗi dữ liệu."
ĐÂY LÀ CÂU TRẢ LỜI TỐT cho câu hỏi "bug khó nhất em từng gặp".`,
    `[~60 s] "This slide is the lesson I value most. RF accuracy was stuck at 67 per cent, with 567 of 700 drone samples called noise. My first hypothesis was the architecture, so I added an STFT front end and accuracy jumped to 96 — apparently a 29-point win. But the real cause was a data bug: I cut a fixed 1 ms window, while a frequency-hopping signal has a burst period of several milliseconds, so many windows labelled 'drone' held no signal at all. After fixing the data and retraining both on the same set, the 1D CNN reached ${n(RF.ablation_raw_iq_1dcnn_acc * 100, 1)} and the STFT version ${n(RF.test_acc * 100, 1)}. Most of the architecture win was a data bug."
THIS IS A GOOD ANSWER to "what was your hardest bug".`));
  title(s, T('BÀI HỌC', 'THE LESSON'), T('Tưởng là lỗi kiến trúc, hoá ra là lỗi dữ liệu', 'It looked like an architecture problem; it was a data problem'), true);
  const rows = [
    [T('Ban đầu — cắt cửa sổ 1 ms cố định', 'At first — fixed 1 ms window'), '67,0%'.replace(',', L === 'en' ? '.' : ','), T('567/700 mẫu drone bị đoán là nhiễu', '567/700 drone samples called noise'), RED],
    [T('Thêm tầng STFT (vẫn dữ liệu lỗi)', 'Add an STFT front end (data still wrong)'), '96,4%'.replace(',', L === 'en' ? '.' : ','), T('“thắng 29 điểm” — nhưng là kết luận sai', '"a 29-point win" — but a wrong conclusion'), WARN],
    [T('Sửa dữ liệu, CNN 1D trên I/Q thô', 'Fix the data, 1D CNN on raw I/Q'), n(RF.ablation_raw_iq_1dcnn_acc * 100, 1) + '%', T('cùng dữ liệu, cùng số epoch', 'same data, same epochs'), OKC],
    [T('Sửa dữ liệu, bản STFT', 'Fix the data, STFT version'), n(RF.test_acc * 100, 1) + '%', T('kiến trúc chỉ hơn 1,5 điểm, không phải 29', 'the architecture is worth 1.5 points, not 29'), OKC],
  ];
  rows.forEach(([a, b, c, col], i) => {
    const y = 1.35 + i * 0.86;
    s.addShape(pres.shapes.RECTANGLE, { x: 0.45, y, w: 9.1, h: 0.74, fill: { color: '1C1C1C' }, line: { color: '1C1C1C', width: 0 } });
    s.addShape(pres.shapes.RECTANGLE, { x: 0.45, y, w: 0.06, h: 0.74, fill: { color: col }, line: { color: col, width: 0 } });
    tx(s, a, { x: 0.68, y: y + 0.12, w: 4.0, h: 0.5, fontSize: 11.5, color: WHITE, bold: true, valign: 'middle' });
    tx(s, b, { x: 4.8, y: y + 0.12, w: 1.2, h: 0.5, fontSize: 17, color: col, bold: true, fontFace: HEAD, valign: 'middle' });
    tx(s, c, { x: 6.1, y: y + 0.14, w: 3.3, h: 0.5, fontSize: 9.8, color: 'B4B4B4', valign: 'middle' });
  });
  tx(s, T('Bài học: khi một thay đổi cho kết quả tốt bất thường, hãy nghi dữ liệu trước khi mừng.',
    'Lesson: when a change gives a suspiciously large gain, suspect the data before celebrating.'),
  { x: 0.45, y: 4.88, w: 9.1, h: 0.3, fontSize: 11, color: WARN, italic: true, bold: true });
}

// ---------------------------------------------------------------- 7. hợp nhất
{
  const s = slide(false, T(
    `[~55 giây] "Hợp nhất làm hai việc tách bạch. Vị trí do bộ lọc Kalman mở rộng lo, mỗi cảm biến có hàm đo riêng và được cập nhật tuần tự, nên khung nào có cảm biến nào thì dùng cảm biến đó. Nhận dạng thì cộng bằng chứng, mỗi cảm biến nhân với một trọng số tin cậy thay đổi theo điều kiện: camera trong sương mù hoặc ban đêm bị hạ quyền, RF bị nhiễu thì cũng vậy. Ba chi tiết nhỏ ở dưới đều chỉ lộ ra khi em đo, không phải khi em thiết kế."`,
    `[~55 s] "Fusion does two separate jobs. Position is handled by a multi-sensor extended Kalman filter: each sensor has its own measurement model and updates sequentially, so whichever sensors report are the ones used. Identity is evidence accumulation, each sensor scaled by a reliability weight that moves with conditions: the camera is down-weighted in fog or at night, and so is RF under jamming. The three details at the bottom only surfaced when I measured, not when I designed."`));
  title(s, T('HỢP NHẤT', 'FUSION'), T('Vị trí bằng EKF, nhận dạng bằng bằng chứng có trọng số', 'Position by EKF, identity by weighted evidence'));
  const cards = [
    [T('EKF đa cảm biến', 'Multi-sensor EKF'), T('Trạng thái là vị trí và vận tốc 3D. Radar cho cự ly, góc và vận tốc xuyên tâm; RF chỉ cho phương vị; camera chỉ cho góc; LiDAR cho toạ độ. Cập nhật tuần tự nên cảm biến rớt không làm hỏng vết bám.',
      'The state is 3D position and velocity. Radar gives range, angles and radial velocity; RF bearing only; the camera angles only; LiDAR position. Sequential updates mean a dropped sensor does not break the track.')],
    [T('Bằng chứng nhận dạng', 'Identity evidence'), T('Mỗi cảm biến góp một vector log tỉ lệ khả năng, nhân với độ tin cậy theo sương mù, ban đêm, cự ly và mức nhiễu RF hiện tại.',
      'Each sensor contributes a log-likelihood-ratio vector scaled by a reliability weight that depends on fog, darkness, range and current jamming.')],
  ];
  cards.forEach(([t, d], i) => {
    const x = 0.45 + i * 4.65;
    s.addShape(pres.shapes.RECTANGLE, { x, y: 1.25, w: 4.4, h: 1.75, fill: { color: i ? SOFT : RED }, line: { color: i ? SOFT : RED, width: 0 } });
    tx(s, t, { x: x + 0.18, y: 1.4, w: 4.05, h: 0.3, fontSize: 13, bold: true, fontFace: HEAD, color: i ? INK : WHITE });
    tx(s, d, { x: x + 0.18, y: 1.74, w: 4.05, h: 1.15, fontSize: 9.8, color: i ? '444444' : 'FFE3E8' });
  });
  tx(s, T('Ba chi tiết nhỏ nhưng quyết định — cả ba chỉ lộ ra khi đo', 'Three small details that decide the outcome — all three surfaced only through measurement'),
    { x: 0.45, y: 3.15, w: 9.1, h: 0.25, fontSize: 10.5, bold: true, color: RED, fontFace: HEAD });
  const det = [
    [T('Trừ trung bình, không trừ max', 'Subtract the mean, not the max'), T('Trừ max thì cảm biến chỉ dìm lớp khác xuống chứ không nâng lớp mình tin lên, nên nhân trọng số tin cậy không đảo ngược được gì.', 'Subtracting the max lets a sensor only push others down, never lift its own choice, so reliability weighting cannot counter it.')],
    [T('Trần bằng chứng cho từng cảm biến', 'Cap evidence per sensor'), T('Camera nhìn cùng một nhãn mười khung vẫn là một bằng chứng. Không đặt trần thì cảm biến lấy mẫu dày nhất luôn thắng.', 'A camera seeing the same patch ten times is still one piece of evidence. Without a cap the fastest sampler always wins.')],
    [T('Phát hiện mâu thuẫn rồi siết trần', 'Detect conflict, then tighten the cap'), T('Camera lệch với radar và RF thì trần của nó bị siết dần theo mức mâu thuẫn tích luỹ.', 'When the camera disagrees with radar and RF, its cap shrinks with accumulated conflict.')],
  ];
  det.forEach(([t, d], i) => {
    const x = 0.45 + i * 3.08;
    s.addShape(pres.shapes.RECTANGLE, { x, y: 3.45, w: 2.9, h: 1.6, fill: { color: WHITE }, line: { color: 'DDDDDD', width: 1 } });
    tx(s, String(i + 1), { x: x + 0.14, y: 3.56, w: 0.4, h: 0.22, fontSize: 9, bold: true, color: RED, fontFace: HEAD });
    tx(s, t, { x: x + 0.14, y: 3.78, w: 2.62, h: 0.42, fontSize: 10.2, bold: true, fontFace: HEAD });
    tx(s, d, { x: x + 0.14, y: 4.2, w: 2.62, h: 0.78, fontSize: 8.6, color: '555555' });
  });
}

// ---------------------------------------------------------------- 8. bám quỹ đạo
{
  const s = slide(false, T(
    `[~65 giây] "Khi mục tiêu mất dấu, EKF chỉ biết đi thẳng theo hướng cũ vì nó giả định mô hình chuyển động cố định. Em thêm một Transformer nhỏ nhìn 2 giây quá khứ và dự đoán 1 giây tới, rồi dùng kết quả làm số đo giả kéo vết bám theo đường cong.
Câu chuyện đo đạc ở đây em muốn kể vì suýt nữa báo cáo ghi một con số sai. Bản đầu em huấn luyện trên quỹ đạo thật cộng nhiễu 1,5 mét, Transformer hơn mốc so sánh tới ${TJS ? n(TJS.improvement_pct, 0) : '52'} phần trăm. Đem vào hệ thống thật thì không hơn gì cả. Lý do là mốc so sánh kia quá yếu: nó lấy vận tốc bằng sai phân của vị trí nhiễu, còn EKF thật có số đo vận tốc xuyên tâm từ radar nên vận tốc tốt hơn nhiều. Em huấn luyện lại trên chính chuỗi trạng thái EKF sinh ra, và mức cải thiện thật là ${n(TJ.improvement_pct, 1)} phần trăm."`,
    `[~65 s] "When a target drops out, the EKF can only coast straight, because it assumes a fixed motion model. I added a small Transformer that reads 2 s of history and predicts 1 s ahead, then injected that as a pseudo-measurement to pull the track along the curve.
I want to tell the measurement story, because the report nearly carried a wrong number. My first version trained on true trajectories plus 1.5 m of noise, and the Transformer beat the baseline by ${TJS ? n(TJS.improvement_pct, 0) : '52'} per cent. In the live system it was no better at all. The baseline was too weak: it derived velocity by differencing noisy positions, while the real EKF has radial-velocity measurements from radar. I retrained on the state sequences the EKF itself produces, and the real improvement is ${n(TJ.improvement_pct, 1)} per cent."`));
  title(s, T('BÁM QUỸ ĐẠO', 'TRACKING'), T('Mất dấu 4 giây, và một mốc so sánh suýt nữa sai', 'A 4-second dropout, and a baseline that was nearly wrong'));
  img(s, `tracking_${L}.png`, { x: 0.45, y: 1.15, w: 9.1, h: 2.85 });
  s.addShape(pres.shapes.RECTANGLE, { x: 0.45, y: 4.15, w: 9.1, h: 0.95, fill: { color: SOFT }, line: { color: SOFT, width: 0 } });
  tx(s, T('MỐC SO SÁNH PHẢI CÔNG BẰNG', 'THE BASELINE MUST BE FAIR'), { x: 0.65, y: 4.26, w: 4, h: 0.22, fontSize: 9, bold: true, color: RED, fontFace: HEAD });
  tx(s, T(`Bài kiểm tra đầu cho Transformer hơn ${TJS ? n(TJS.improvement_pct, 0) : '52'}%, nhưng mốc so sánh lấy vận tốc bằng sai phân của vị trí nhiễu. EKF thật có số đo vận tốc xuyên tâm từ radar nên tốt hơn nhiều. So đúng với EKF thật: hơn ${n(TJ.improvement_pct, 1)}%.`,
    `The first benchmark showed ${TJS ? n(TJS.improvement_pct, 0) : '52'}% improvement, but its baseline derived velocity by differencing noisy positions. The real EKF has radar radial-velocity measurements and is far better. Against that: ${n(TJ.improvement_pct, 1)}%.`),
  { x: 0.65, y: 4.49, w: 8.7, h: 0.55, fontSize: 9.8, color: '333333' });
}

// ---------------------------------------------------------------- 9. chống đánh lừa
{
  const s = slide(false, T(
    `[~55 giây] "Tấn công giả định là dán nhãn ngụy trang lên thân drone, khiến bộ nhận dạng ảnh đọc sai lớp và đọc sai rất tự tin. Điểm mấu chốt: nhãn dán chỉ đánh lừa được ánh sáng nhìn thấy. Nó không đổi được tiết diện phản xạ radar của cánh quạt đang quay, và cũng không làm mất được sóng điều khiển mà drone buộc phải phát.
Con số em muốn anh chị nhìn không phải 100 phần trăm mà là ${n(AD.naive_acc * 100, 1)} phần trăm của dòng giữa: hợp nhất không thôi thì không cứu được gì. Nếu cộng đều mọi cảm biến, một camera tự tin và lấy mẫu dày vẫn lật được kết luận của cả radar lẫn RF."`,
    `[~55 s] "The assumed attack is an adversarial patch on the airframe that makes the image classifier read the wrong class, confidently. The key point: a patch only fools visible light. It cannot change the radar cross-section of a spinning rotor, and it cannot suppress the control link the drone must transmit.
The number to look at is not 100 per cent but the ${n(AD.naive_acc * 100, 1)} per cent in the middle row: fusion on its own saves nothing. With equal weighting, one confident, fast-sampling camera still overturns both radar and RF."`));
  title(s, T('CHỐNG ĐÁNH LỪA', 'ADVERSARIAL ROBUSTNESS'), T('Camera bị lừa, radar và RF thì không', 'The camera is fooled; radar and RF are not'));
  img(s, `adversarial_${L}.png`, { x: 1.4, y: 1.2, w: 7.2, h: 3.0 });
  s.addShape(pres.shapes.RECTANGLE, { x: 0.45, y: 4.35, w: 9.1, h: 0.72, fill: { color: INK }, line: { color: INK, width: 0 } });
  tx(s, T(`Hợp nhất không thôi KHÔNG cứu được: cộng đều mọi cảm biến vẫn chỉ đúng ${n(AD.naive_acc * 100, 1)}%. Phải có phát hiện mâu thuẫn và trần bằng chứng thì hợp nhất mới thành phòng vệ.`,
    `Fusion alone does NOT save you: equal weighting still scores only ${n(AD.naive_acc * 100, 1)}%. Only conflict detection plus evidence caps turn fusion into a defence.`),
  { x: 0.65, y: 4.48, w: 8.7, h: 0.48, fontSize: 11, bold: true, color: WHITE, valign: 'middle' });
}

// ---------------------------------------------------------------- 10. kịch bản + độ trễ
{
  const s = slide(false, T(
    `[~60 giây] "Bảy kịch bản, mỗi kịch bản 8 lần chạy độc lập. Hai dòng em muốn anh chị chú ý. Thứ nhất là chim: không khung nào bị đẩy lên cho người trực. Đây là chỉ số quan trọng nhất của một hệ cảnh báo, vì báo động giả nhiều thì người ta sẽ tắt nó đi. Thứ hai là nhiễu RF: thời gian đến khi đủ tin tăng từ ${n(byId('S1').time_to_confirm_s, 1)} lên ${n(byId('S3').time_to_confirm_s, 1)} giây, vì mất một nguồn bằng chứng nên phải chờ radar góp đủ.
Về thời gian xử lý: tổng p99 là ${n(LAT.total.p99_ms, 2)} mili giây trên ngân sách 50, còn dư rất nhiều."`,
    `[~60 s] "Seven scenarios, eight independent runs each. Two rows matter. First, birds: not a single frame escalated to the operator. That is the most important property of an alerting system, because an operator drowned in false alarms switches it off. Second, RF jamming: time to confidence rises from ${n(byId('S1').time_to_confirm_s, 1)} to ${n(byId('S3').time_to_confirm_s, 1)} seconds, because one evidence source is gone and the radar must carry it alone.
On latency: total p99 is ${n(LAT.total.p99_ms, 2)} milliseconds against a 50 ms budget, with a lot of headroom."`));
  title(s, T('KẾT QUẢ', 'RESULTS'), T('Bảy kịch bản mô phỏng · 8 lần chạy mỗi kịch bản', 'Seven simulated scenarios · 8 runs each'));
  img(s, `scenarios_${L}.png`, { x: 0.45, y: 1.12, w: 9.1, h: 2.55 });
  stat(s, 0.45, 3.82, 2.18, '100%', T('nhận dạng đúng ở cả 7 kịch bản', 'identity correct in all 7 scenarios'), true);
  stat(s, 2.76, 3.82, 2.18, '0%', T('khung báo động nhầm khi gặp chim', 'frames escalated on a bird'));
  stat(s, 5.07, 3.82, 2.18, n(LAT.total.p99_ms, 2) + ' ms', T('tổng thời gian p99 / ngân sách 50 ms', 'total p99 latency / 50 ms budget'));
  stat(s, 7.38, 3.82, 2.17, n(scen.reduce((a, b) => a + b.rmse_m, 0) / scen.length, 1) + ' m', T('sai số bám trung bình ở cự ly 1–2 km', 'mean track error at 1–2 km'));
}

// ---------------------------------------------------------------- 11. dashboard
{
  const s = slide(false, T(
    `[~45 giây] "Đây là màn hình cho người trực ca, lúc camera đang bị đánh lừa. Hệ thống vẫn nhận dạng đúng là drone đa cánh quạt, nhưng nó hạ điểm tin cậy xuống và nói thẳng ra lý do: camera chỉ một đằng, radar và RF chỉ một nẻo.
Em thiết kế màn hình quanh một câu hỏi: người trực cần gì để ra quyết định và chịu trách nhiệm về nó. Vì vậy bằng chứng tách theo từng cảm biến chứ không gộp thành một con số, và khi các cảm biến mâu thuẫn thì hệ thống nói ra chứ không im lặng chọn một bên."
NẾU CÒN THỜI GIAN: bấm nút xác nhận để cho thấy nhật ký.`,
    `[~45 s] "This is the operator screen while the camera is being fooled. The system still identifies a multirotor correctly, but it lowers the confidence and states why: the camera disagrees with radar and RF.
I designed this around one question: what does the duty operator need in order to decide and be accountable. So evidence is broken out per sensor rather than collapsed into one number, and when sensors disagree the system says so instead of quietly picking a side."
IF TIME ALLOWS: press confirm to show the audit log.`));
  title(s, T('GIAO DIỆN', 'THE INTERFACE'), T('Người trực ca quyết định, hệ thống chỉ đưa bằng chứng', 'The operator decides; the system only supplies evidence'));
  img(s, 'dash_patch.png', { x: 0.45, y: 1.15, w: 9.1, h: 3.45 });
  tx(s, T('Hệ thống chỉ giám sát, nhận dạng, bám quỹ đạo và đề xuất. Không có cơ chế tự động chọn mục tiêu hay điều khiển khí tài.',
    'The system only watches, identifies, tracks and advises. There is no autonomous target selection or weapon control.'),
  { x: 0.45, y: 4.72, w: 9.1, h: 0.3, fontSize: 10.5, bold: true, color: RED, italic: true });
}

// ---------------------------------------------------------------- 12. hạn chế
{
  const s = slide(true, T(
    `[~55 giây] "Phần em nghĩ quan trọng nhất khi trình bày một dự án mô phỏng: nói rõ chỗ chưa làm được.
Thứ nhất, chưa đo trên Jetson thật, mọi số thời gian là trên CPU x86 hai nhân. Biên còn rất rộng nên nhiều khả năng vẫn lọt, nhưng chưa đo thì chưa được coi là đã chứng minh.
Thứ hai, toàn bộ dữ liệu là mô phỏng. Nó dựng theo vật lý và có nhiễu, thời tiết, đa đường, nhưng vẫn là mô phỏng, và trên tín hiệu thực địa chắc chắn thấp hơn.
Thứ ba, nhánh camera chưa chạy mô hình thị giác thật.
Thứ tư, mỗi lần chỉ bám một mục tiêu — liên kết số đo đa mục tiêu là phần việc lớn tiếp theo."`,
    `[~55 s] "This is the part I think matters most when presenting a simulation-based project: being explicit about what is not done.
First, no measurement on a real Jetson; every timing is from a 2-core x86 CPU. The margin is wide, so it will probably still fit, but until measured it is not demonstrated.
Second, all data is simulated. It is physics-based and includes noise, weather and multipath, but it is still simulation, and real field signals will be harder.
Third, the camera branch runs no real vision model.
Fourth, one target at a time — multi-target data association is the next substantial piece of work."`));
  title(s, T('HẠN CHẾ', 'LIMITATIONS'), T('Những gì dự án này CHƯA chứng minh', 'What this project has NOT demonstrated'), true);
  const lim = [
    [T('Chưa đo trên phần cứng biên thật', 'No measurement on real edge hardware'), T('Mọi con số thời gian đo trên CPU x86 2 nhân, không phải Jetson Orin. Chưa có số liệu điện năng.', 'All timings are from a 2-core x86 CPU, not a Jetson Orin. No power figures.')],
    [T('Toàn bộ dữ liệu là mô phỏng', 'All data is simulated'), T('Dựng theo mô hình vật lý, có nhiễu, thời tiết, đa đường — nhưng vẫn là mô phỏng.', 'Physics-based, with noise, weather and multipath — but still simulation.')],
    [T('Nhánh camera chưa có mô hình thị giác thật', 'No real vision model on the camera branch'), T('Camera mô hình hoá ở mức đầu ra: góc nhìn, tầm, độ tin cậy và khả năng bị đánh lừa.', 'The camera is modelled at its output: field of view, range, confidence and susceptibility.')],
    [T('Mỗi lần chỉ bám một mục tiêu', 'One target at a time'), T('Liên kết số đo đa mục tiêu chưa làm. Đây là phần việc lớn tiếp theo.', 'Multi-target data association is not implemented. That is the next big piece.')],
  ];
  lim.forEach(([t, d], i) => {
    const y = 1.35 + i * 0.92;
    s.addShape(pres.shapes.RECTANGLE, { x: 0.45, y, w: 9.1, h: 0.8, fill: { color: '1C1C1C' }, line: { color: '1C1C1C', width: 0 } });
    s.addShape(pres.shapes.RECTANGLE, { x: 0.45, y, w: 0.06, h: 0.8, fill: { color: WARN }, line: { color: WARN, width: 0 } });
    tx(s, t, { x: 0.7, y: y + 0.11, w: 4.2, h: 0.3, fontSize: 12, bold: true, color: WHITE, fontFace: HEAD });
    tx(s, d, { x: 0.7, y: y + 0.42, w: 8.6, h: 0.32, fontSize: 9.6, color: 'B4B4B4' });
  });
  tx(s, T('Mọi con số trong bộ tài liệu này sinh lại được bằng một chuỗi lệnh ghi trong phụ lục báo cáo.',
    'Every number in this pack can be regenerated with the command sequence listed in the report appendix.'),
  { x: 0.45, y: 5.0, w: 9.1, h: 0.3, fontSize: 10, color: '8A8A8A', italic: true });
}

// ---------------------------------------------------------------- 13. kết
{
  const s = slide(true, T(
    `[~35 giây] "Tóm lại: hệ thống chạy được từ đầu đến cuối với bốn cảm biến, đạt mọi chỉ tiêu thời gian của đề bài với biên rất rộng, loại được chim mà không làm phiền người trực, và chống được tấn công dán nhãn ngụy trang.
Hai điều em muốn anh chị nhớ về cách em làm: em đo chứ không ước lượng, và khi một kết quả đẹp bất thường thì em đi tìm lỗi trước khi mừng. Hai lần trong dự án này em đã suýt báo cáo một con số sai, và cả hai lần đều là do mốc so sánh hoặc dữ liệu chứ không phải mô hình. Em xin sẵn sàng trả lời câu hỏi."`,
    `[~35 s] "In summary: the system runs end to end with four sensors, meets every timing requirement with a wide margin, rejects birds without bothering the operator, and resists the adversarial patch attack.
Two things about how I work: I measure rather than estimate, and when a result looks unusually good I go looking for the bug before celebrating. Twice in this project I nearly reported a wrong number, and both times the cause was the baseline or the data, not the model. I am happy to take questions."`));
  tx(s, T('TÓM LẠI', 'IN SUMMARY'), { x: 0.45, y: 0.85, w: 8, h: 0.3, fontSize: 11, bold: true, color: RED, fontFace: HEAD, charSpacing: 2 });
  tx(s, T('Chạy được, đo được,\nvà nói rõ chỗ chưa được', 'It runs, it is measured,\nand the gaps are stated'),
    { x: 0.45, y: 1.25, w: 9.1, h: 1.3, fontSize: 30, bold: true, color: WHITE, fontFace: HEAD, lineSpacing: 34 });
  const sum = [
    [n(LAT.total.p99_ms, 2) + ' ms', T('tổng p99 / ngân sách 50 ms', 'total p99 / 50 ms budget')],
    [n(RF.test_acc * 100, 1) + '% · ' + n(MD.test_acc * 100, 1) + '%', T('RF · micro-Doppler', 'RF · micro-Doppler')],
    ['0%', T('báo động nhầm khi gặp chim', 'false alerts on birds')],
    [n(AD.defended_acc * 100, 0) + '%', T('đúng khi bị dán nhãn ngụy trang', 'correct under adversarial patch')],
  ];
  sum.forEach(([v, l], i) => {
    const x = 0.45 + i * 2.31;
    s.addShape(pres.shapes.RECTANGLE, { x, y: 2.85, w: 2.18, h: 1.25, fill: { color: i === 0 ? RED : '1C1C1C' }, line: { color: i === 0 ? RED : '1C1C1C', width: 0 } });
    tx(s, v, { x: x + 0.15, y: 3.0, w: 1.95, h: 0.45, fontSize: 18, bold: true, color: WHITE, fontFace: HEAD });
    tx(s, l, { x: x + 0.15, y: 3.48, w: 1.95, h: 0.55, fontSize: 9, color: 'B4B4B4' });
  });
  tx(s, T('Cảm ơn anh/chị đã lắng nghe.', 'Thank you.'), { x: 0.45, y: 4.45, w: 5, h: 0.3, fontSize: 14, bold: true, color: WHITE, fontFace: HEAD });
  tx(s, 'anhhaduc7777@gmail.com  ·  github.com/trandohaianh', { x: 0.45, y: 4.8, w: 6, h: 0.3, fontSize: 10.5, color: '8A8A8A' });
}

const out = path.join(__dirname, `../Edge_AI_Surveillance_Slides_${L.toUpperCase()}.pptx`);
pres.writeFile({ fileName: out }).then(f => console.log('wrote', f, 'slides', pg));
