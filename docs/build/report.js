// node report.js vi|en  -> ../Edge_AI_Surveillance_Report_<LANG>.docx
const fs = require('fs');
const path = require('path');
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType, Table, TableRow, TableCell,
  WidthType, ShadingType, BorderStyle, ImageRun, LevelFormat, PageNumber, Footer, PageBreak,
} = require('docx');

const L = process.argv[2] === 'en' ? 'en' : 'vi';
const T = (vi, en) => (L === 'en' ? en : vi);
const D = f => JSON.parse(fs.readFileSync(path.join(__dirname, '../../data/results/' + f)));
const RF = D('rf_metrics.json'), MD = D('md_metrics.json'), TJ = D('traj_metrics.json');
const SC = D('scenario_results.json'), AD = D('adversarial.json');
const TJS = fs.existsSync(path.join(__dirname, '../../data/results/traj_metrics_synthetic.json'))
  ? D('traj_metrics_synthetic.json') : null;
const LAT = SC.latency_ms;
const RED = 'D7153A', INK = '111111', GREY = 'F2F2F2';
const num = (x, d = 0) => (L === 'vi'
  ? Number(x).toLocaleString('vi-VN', { maximumFractionDigits: d, minimumFractionDigits: d })
  : Number(x).toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: d }));
const pct = (x, d = 1) => num(x, d) + '%';
const W = 9026;

const p = (text, o = {}) => new Paragraph({ spacing: { after: 120, line: 300 }, ...o, children: runs(text, o.run) });
function runs(text, ro = {}) {
  return String(text).split(/(\*\*[^*]+\*\*)/).filter(Boolean).map(s =>
    s.startsWith('**') ? new TextRun({ text: s.slice(2, -2), bold: true, ...ro }) : new TextRun({ text: s, ...ro }));
}
const h1 = t => new Paragraph({ heading: HeadingLevel.HEADING_1, spacing: { before: 360, after: 160 }, children: [new TextRun(t)] });
const h2 = t => new Paragraph({ heading: HeadingLevel.HEADING_2, spacing: { before: 240, after: 120 }, children: [new TextRun(t)] });
const bullet = t => new Paragraph({ numbering: { reference: 'b', level: 0 }, spacing: { after: 80, line: 288 }, children: runs(t) });
const caption = t => new Paragraph({ spacing: { after: 200 }, children: [new TextRun({ text: t, italics: true, size: 18, color: '555555' })] });
const img = (file, w, h) => new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 60 }, children: [new ImageRun({ type: 'png', data: fs.readFileSync(path.join(__dirname, '../fig', file)), transformation: { width: w, height: h } })] });
const border = { style: BorderStyle.SINGLE, size: 4, color: 'BBBBBB' };
const borders = { top: border, bottom: border, left: border, right: border };
function table(head, rows, widths, opts = {}) {
  const sum = widths.reduce((a, b) => a + b, 0);
  const ws = widths.map(w => Math.round(w / sum * W));
  ws[ws.length - 1] += W - ws.reduce((a, b) => a + b, 0);
  const cell = (t, i, isHead, shade) => new TableCell({
    width: { size: ws[i], type: WidthType.DXA }, borders,
    shading: isHead ? { fill: INK, type: ShadingType.CLEAR, color: 'auto' } : (shade ? { fill: shade, type: ShadingType.CLEAR, color: 'auto' } : undefined),
    margins: { top: 60, bottom: 60, left: 100, right: 100 },
    children: [new Paragraph({ alignment: (!isHead && i > 0 && opts.rightNum) ? AlignmentType.RIGHT : AlignmentType.LEFT, children: runs(t, isHead ? { bold: true, color: 'FFFFFF', size: 19 } : { size: 19 }) })],
  });
  return new Table({
    width: { size: W, type: WidthType.DXA }, columnWidths: ws,
    rows: [new TableRow({ tableHeader: true, children: head.map((t, i) => cell(t, i, true)) }),
      ...rows.map((r, k) => new TableRow({ children: r.map((t, i) => cell(t, i, false, k % 2 ? GREY : null)) }))],
  });
}
const gap = () => new Paragraph({ spacing: { after: 120 }, children: [] });
const y = '✔ ', wq = '◐ ', nq = '✘ ';
const ok = T('Đạt', 'Met'), part = T('Một phần', 'Partly'), no = T('Chưa đạt', 'Not met');

const scen = SC.scenarios;
const byId = id => scen.find(s => s.scenario.startsWith(id));
const blind = (scen.find(s => s.blind_curve) || {}).blind_curve || [];
const bAt = t => blind.reduce((a, r) => (Math.abs(r.t_s - t) < Math.abs(a.t_s - t) ? r : a), blind[0]);
const meanBy = k => scen.reduce((a, s) => a + (s[k] || 0), 0) / scen.length;

const C = [];
// ---------------------------------------------------------------- bìa
C.push(new Paragraph({ spacing: { after: 80 }, children: [new TextRun({ text: T('BÁO CÁO KỸ THUẬT · DỰ ÁN 2', 'TECHNICAL REPORT · PROJECT 2'), bold: true, color: RED, size: 20 })] }));
C.push(new Paragraph({ spacing: { after: 120 }, children: [new TextRun({ text: T('Giám sát và bám quỹ đạo mục tiêu bay bằng AI đa cảm biến tại thiết bị biên', 'Multi-Sensor Edge AI Object Surveillance and Tracking System'), bold: true, size: 40 })] }));
C.push(new Paragraph({ spacing: { after: 240 }, border: { bottom: { style: BorderStyle.SINGLE, size: 12, color: RED, space: 6 } }, children: [new TextRun({ text: T('Trần Đỗ Hải Anh · 10/2026 · Mã nguồn, dữ liệu mô phỏng và kết quả đo đi kèm trong thư mục dự án', 'Tran Do Hai Anh · October 2026 · Code, simulated data and measurements are included in the project folder'), size: 19, color: '555555' })] }));

C.push(new Paragraph({
  shading: { fill: 'FFF4E5', type: ShadingType.CLEAR, color: 'auto' },
  spacing: { after: 220 }, border: { left: { style: BorderStyle.SINGLE, size: 18, color: 'E8A317', space: 8 } },
  children: runs(T('**Ranh giới đạo đức.** Hệ thống chỉ giám sát, nhận dạng, bám quỹ đạo và đưa ra điểm tin cậy kèm bằng chứng để con người quyết định. Không có và sẽ không có cơ chế tự động chọn mục tiêu tác chiến hay điều khiển vũ khí đánh chặn. Mọi thao tác xác nhận hay bỏ qua của chuyên viên đều được ghi nhật ký.',
    '**Ethical boundary.** The system only watches, identifies, tracks and produces a confidence score with supporting evidence for a human to act on. It contains no mechanism for autonomous target selection or weapon control, and will not gain one. Every operator confirmation or dismissal is written to an audit log.'), { size: 19 }),
}));

// ---------------------------------------------------------------- tóm tắt
C.push(h1(T('Tóm tắt', 'Executive summary')));
C.push(p(T(
  `Hệ thống chạy được từ đầu đến cuối: bốn luồng cảm biến mô phỏng theo mô hình vật lý đi vào một vòng xử lý 10 Hz, hai mạng nơ-ron nhỏ phát hiện mục tiêu từ tín hiệu phi hình ảnh, một bộ lọc Kalman mở rộng đa cảm biến dựng quỹ đạo 3D, và mọi kết luận đều kèm bằng chứng tách theo từng cảm biến cho người trực ca. Toàn bộ chỉ tiêu thời gian của đề bài đều đạt với biên rất rộng: **${num(LAT.total.p99_ms, 2)} ms** ở mức p99 so với ngân sách 50 ms.`,
  `The system runs end to end: four physics-based simulated sensor streams feed a 10 Hz processing loop, two small neural networks detect targets from non-imaging signals, a multi-sensor extended Kalman filter builds the 3D track, and every conclusion carries per-sensor evidence for the operator. The brief's timing requirement is met with a wide margin: **${num(LAT.total.p99_ms, 2)} ms** at p99 against a 50 ms budget.`)));

C.push(table([T('Yêu cầu của đề bài', 'Requirement'), T('Mục tiêu', 'Target'), T('Kết quả đo', 'Measured'), T('Đánh giá', 'Status')], [
  [T('Tổng thời gian từ nhận tín hiệu đến ra toạ độ bám', 'End-to-end latency, signal to track coordinates'), '< 50 ms', `${num(LAT.total.p99_ms, 2)} ms (p99), ${num(LAT.total.mean_ms, 2)} ms ${T('trung bình', 'mean')}`, y + ok],
  [T('Phát hiện sớm bằng tín hiệu phi hình ảnh — RF (I/Q)', 'Early detection from non-imaging signals — RF (I/Q)'), T('Học sâu', 'Deep learning'), `${pct(RF.test_acc * 100, 1)} ${T('trên', 'on')} ${num(RF.n_test)} ${T('mẫu', 'samples')}`, y + ok],
  [T('Phát hiện sớm — radar micro-Doppler', 'Early detection — radar micro-Doppler'), T('Học sâu', 'Deep learning'), `${pct(MD.test_acc * 100, 1)} ${T('trên', 'on')} ${num(MD.n_test)} ${T('mẫu', 'samples')}`, y + ok],
  [T('Hợp nhất 4 luồng: radar, RF, EO/IR, LiDAR', 'Fusion of 4 streams: radar, RF, EO/IR, LiDAR'), T('Bắt buộc', 'Required'), T('EKF đa cảm biến + cộng bằng chứng có trọng số', 'Multi-sensor EKF + weighted evidence'), y + ok],
  [T('Bám quỹ đạo khi mất dấu: EKF + Transformer', 'Tracking through dropouts: EKF + Transformer'), T('Bắt buộc', 'Required'), T(`sai số nhỏ hơn ${pct(TJ.improvement_pct, 0)} so với ngoại suy vận tốc không đổi`, `${pct(TJ.improvement_pct, 0)} lower error than constant-velocity extrapolation`), y + ok],
  [T('Kháng nhiễu thời tiết và nhiễu địa hình', 'Robust to weather and clutter'), T('Bắt buộc', 'Required'), T(`nhận dạng đúng 100% ở cả 7 kịch bản, kể cả đêm + sương mù và mưa to`, 'identity correct in 100% of all 7 scenarios, including night + fog and heavy rain'), y + ok],
  [T('Chống tấn công đối kháng đánh lừa AI', 'Adversarial robustness'), T('Bắt buộc', 'Required'), T(`${pct(AD.defended_acc * 100, 1)} đúng khi bị dán nhãn ngụy trang (camera đơn lẻ: ${pct(AD.eo_only_acc * 100, 1)})`, `${pct(AD.defended_acc * 100, 1)} correct under an adversarial patch (camera alone: ${pct(AD.eo_only_acc * 100, 1)})`), y + ok],
  [T('Người giữ quyền quyết định (human-in-the-loop)', 'Human-in-the-loop'), T('Bắt buộc', 'Required'), T('đề xuất + bằng chứng + nhật ký; không có tự động hành động', 'advice + evidence + audit log; no autonomous action'), y + ok],
  [T('Chạy trên SoC nhúng 10–25 W (Jetson Orin)', 'Runs on a 10–25 W embedded SoC (Jetson Orin)'), T('Bắt buộc', 'Required'), T('chưa đo trên phần cứng thật — xem mục hạn chế', 'not measured on real hardware — see limitations'), nq + no],
], [3.0, 1.5, 3.3, 1.1]));
C.push(caption(T('Bảng 1. Kết quả chính. Toàn bộ dữ liệu cảm biến là mô phỏng theo mô hình vật lý; không có dữ liệu thực địa.',
  'Table 1. Headline results. All sensor data is physics-based simulation; no field data was used.')));
C.push(p(T(
  `Điểm chưa làm được là đo trên phần cứng biên thật. Mọi con số thời gian trong báo cáo đo trên CPU x86 2 nhân trong container, không phải trên Jetson Orin Nano/NX. Vì biên hiện tại rất rộng (${num(LAT.total.p99_ms, 2)} ms so với 50 ms) nên nhiều khả năng vẫn còn dư địa trên chip nhúng, nhưng chưa đo thì chưa được coi là đã chứng minh.`,
  `What is missing is a measurement on real edge hardware. Every timing number here was measured on a 2-core x86 CPU in a container, not on a Jetson Orin Nano/NX. The margin is wide (${num(LAT.total.p99_ms, 2)} ms against 50 ms), so headroom on an embedded SoC is likely, but until it is measured it is not demonstrated.`)));

// ---------------------------------------------------------------- 1
C.push(h1(T('1. Bối cảnh và yêu cầu', '1. Context and requirements')));
C.push(p(T(
  'Bài toán là phát hiện, nhận dạng và bám quỹ đạo các mục tiêu bay tầm thấp — UAV, drone, vật thể xâm nhập — trong điều kiện thực địa khắc nghiệt: sương mù, đêm tối, nhiễu địa hình, nhiễu điện từ. Thiết bị đặt tại hiện trường, hoạt động độc lập, không dựa vào kết nối đám mây.',
  'The task is to detect, identify and track low-altitude flying targets — UAVs, drones, intruding objects — in harsh field conditions: fog, darkness, terrain clutter and electromagnetic interference. The equipment sits in the field, works on its own, and cannot depend on a cloud link.')));
C.push(p(T('Bốn nhóm yêu cầu kỹ thuật:', 'Four groups of technical requirements:')));
C.push(bullet(T('**Phát hiện sớm bằng tín hiệu phi hình ảnh:** phân tích chuỗi thời gian phổ tần số vô tuyến (RF I/Q) và radar vi ba (micro-Doppler) để nhận ra mục tiêu từ xa, trước khi camera quang học kịp nhìn rõ.', '**Early detection from non-imaging signals:** analyse RF I/Q spectra and microwave radar micro-Doppler to spot targets at range, before an optical camera can resolve them.')));
C.push(bullet(T('**Hợp nhất đa cảm biến:** kết hợp đồng thời radar, RF, video quang học/hồng ngoại (EO/IR) và đám mây điểm LiDAR.', '**Multi-sensor fusion:** combine radar, RF, electro-optical/infrared video and a LiDAR point cloud at the same time.')));
C.push(bullet(T('**Bám quỹ đạo:** bộ lọc Kalman mở rộng kết hợp mô hình Transformer chuỗi thời gian siêu nhẹ, dự đoán đường bay cả khi tín hiệu mất dấu tạm thời.', '**Trajectory tracking:** an extended Kalman filter plus an ultra-light time-series Transformer that predicts the flight path even when the signal is briefly lost.')));
C.push(bullet(T('**Kháng nhiễu và chống đánh lừa:** chịu được nhiễu thời tiết, nhiễu phản xạ địa hình và các hình thức tấn công đối kháng như nhãn dán ngụy trang.', '**Robustness:** withstand weather, terrain clutter and adversarial attacks such as camouflage patches.')));
C.push(p(T('Ràng buộc phần cứng: SoC công suất thấp 10–25 W, và tổng thời gian từ khi nhận tín hiệu, tiền xử lý, hợp nhất cảm biến đến khi đưa ra toạ độ bám phải dưới 50 ms.',
  'Hardware constraint: a low-power 10–25 W SoC, and a total budget of 50 ms from signal reception through pre-processing and fusion to the output track coordinates.')));

// ---------------------------------------------------------------- 2
C.push(h1(T('2. Kiến trúc', '2. Architecture')));
C.push(img(`arch_${L}.png`, 600, 265));
C.push(caption(T('Hình 1. Luồng xử lý. Hai mạng nơ-ron chạy theo nhịp riêng của cảm biến, phần còn lại chạy mỗi khung 10 Hz.',
  'Figure 1. Processing flow. The two networks run at their sensors\' own rate; everything else runs every 10 Hz frame.')));
C.push(p(T('Điểm thiết kế quan trọng nhất là **mỗi cảm biến chỉ đóng góp đúng thứ nó thật sự đo được**:', 'The key design point is that **each sensor contributes only what it actually measures**:')));
C.push(table([T('Cảm biến', 'Sensor'), T('Đo được gì', 'What it measures'), T('Tầm', 'Range'), T('Điểm yếu', 'Weakness')], [
  ['Radar ' + T('băng X', 'X-band'), T('cự ly, phương vị, góc tà, vận tốc xuyên tâm', 'range, azimuth, elevation, radial velocity'), '≈ 3 km', T('mưa làm tăng nền nhiễu; mục tiêu bay thấp lẫn vào nhiễu địa hình', 'rain raises clutter; low flyers hide in ground clutter')],
  ['RF (I/Q)', T('chỉ phương vị, và chỉ khi mục tiêu phát sóng điều khiển', 'bearing only, and only when the target emits a control link'), '≈ 4 km', T('bị nhiễu dải RF làm mù; chim không phát sóng nên vô hình', 'blinded by jamming; birds emit nothing and stay invisible')],
  ['EO/IR', T('chỉ phương vị và góc tà (camera không đo được cự ly)', 'azimuth and elevation only (a camera cannot measure range)'), T('≈ 1,2 km khi trời quang', '≈ 1.2 km in clear air'), T('sương mù và đêm tối; bị nhãn ngụy trang đánh lừa', 'fog and darkness; fooled by adversarial patches')],
  ['LiDAR', T('toạ độ 3D chính xác', 'accurate 3D position'), '≈ 250 m', T('tầm rất ngắn, sương mù làm giảm mạnh', 'very short range, badly degraded by fog')],
], [1.1, 2.6, 0.9, 2.4]));
C.push(caption(T('Bảng 2. Không cảm biến nào vừa xa, vừa chính xác, vừa bền với thời tiết — đó chính là lý do phải hợp nhất.',
  'Table 2. No single sensor is simultaneously long-range, accurate and weather-proof — which is exactly why fusion is needed.')));

// ---------------------------------------------------------------- 3
C.push(h1(T('3. Mô phỏng cảm biến theo mô hình vật lý', '3. Physics-based sensor simulation')));
C.push(p(T(
  'Không có phần cứng và không có dữ liệu thực địa, nên toàn bộ tín hiệu được sinh từ mô hình vật lý chứ không phải từ các phân bố ngẫu nhiên gán sẵn nhãn. Điều này quyết định giá trị của mọi con số phía sau: nếu dữ liệu chỉ là nhiễu có nhãn, mô hình sẽ học được những thứ không tồn tại ngoài đời.',
  'With no hardware and no field data, every signal is generated from a physical model rather than from labelled random distributions. This decides the worth of every number that follows: if the data were just labelled noise, the models would learn things that do not exist in reality.')));
C.push(h2(T('Micro-Doppler của radar', 'Radar micro-Doppler')));
C.push(p(T(
  'Dấu hiệu micro-Doppler được dựng từ công thức chuẩn f_d = 2·v_r/λ. Thân mục tiêu cho một vạch Doppler ổn định. Cánh quạt quay thêm thành phần vận tốc hình sin; khi cánh vuông góc tia radar sẽ có **blade flash** lặp lại ở tần số bằng số cánh nhân tốc độ quay, trải rộng tới ±2·v_tip/λ. Chim vỗ cánh ở 2,5–9 Hz nên cho hình sin chậm hơn hẳn và không có blade flash.',
  'Micro-Doppler signatures are built from the standard relation f_d = 2·v_r/λ. The body gives a steady Doppler line. Rotating blades add a sinusoidal velocity component, and when a blade is perpendicular to the beam there is a **blade flash** repeating at blades × rotation rate, spread out to ±2·v_tip/λ. A bird flaps at 2.5–9 Hz, giving a much slower sinusoid and no blade flash.')));
C.push(p(T(
  '**Một lỗi phải sửa trong quá trình làm.** Ở lần dựng đầu tiên, PRF đặt 4 kHz nên dải Doppler quan sát được chỉ ±2 kHz. Vận tốc đầu cánh của một drone đa cánh quạt khoảng 79 m/s, tương đương Doppler 5,3 kHz ở băng X — vượt xa dải đó nên chữ ký bị gập phổ thành nhiễu, và trên ảnh phổ drone trông y hệt nhiễu nền. Đây là hiện tượng có thật với radar PRF thấp, nhưng nó xoá mất đúng thứ cần phân biệt. Sau khi nâng PRF lên 20 kHz, chữ ký hiện ra rõ. Một lỗi nữa là gộp ô trên thang dB rồi lấy giá trị lớn nhất, làm nền nhiễu bị kéo lên che mất vạch tín hiệu; phải gộp trên công suất tuyến tính rồi mới đổi sang dB.',
  '**A bug that had to be fixed.** The first build used a 4 kHz PRF, giving only ±2 kHz of unambiguous Doppler. A multirotor\'s blade-tip speed is around 79 m/s, i.e. 5.3 kHz of Doppler at X-band — far outside that window, so the signature aliased into noise and a drone looked exactly like the noise floor. Low-PRF radars really do suffer this, but it erased the very thing that needed distinguishing. Raising the PRF to 20 kHz brought the signature out. A second bug: pooling in dB and taking the maximum lifted the noise floor over the signal lines; pooling must happen in linear power before converting to dB.')));
C.push(img(`signatures_${L}.png`, 600, 159));
C.push(caption(T('Hình 2. Chữ ký micro-Doppler mô phỏng. Đây chính là ảnh đưa vào mạng nơ-ron.',
  'Figure 2. Simulated micro-Doppler signatures — exactly the images fed to the network.')));

C.push(h2(T('Tín hiệu vô tuyến I/Q', 'RF I/Q signals')));
C.push(p(T(
  'Bốn lớp được dựng theo đúng đặc điểm mà một bộ phân loại RF thật sự dựa vào: bề rộng phổ chiếm dụng, nhịp nhảy tần, chu kỳ bật tắt của burst và đường bao biên độ. WiFi là một burst OFDM băng rộng giữ nguyên tần số; Bluetooth nhảy tần với khe 625 µs trên kênh rộng 1 MHz; link điều khiển drone nhảy nhanh hơn nhiều, dwell 0,08–0,35 ms, mỗi hop rộng vài MHz.',
  'The four classes are built from the features a real RF classifier actually uses: occupied bandwidth, hop rate, burst duty cycle and amplitude envelope. WiFi is a wideband OFDM burst that holds its centre frequency; Bluetooth hops in 625 µs slots on 1 MHz channels; the drone control link hops far faster, dwelling 0.08–0.35 ms, each hop several MHz wide.')));
C.push(p(T(
  '**Lỗi thứ hai, và là lỗi đáng giá nhất của dự án này.** Bản đầu cắt cửa sổ quan sát 1,024 ms một cách cố định. Với tín hiệu nhảy tần có chu kỳ bật tắt vài mili giây, rất nhiều cửa sổ gán nhãn "có drone" thật ra không chứa chút tín hiệu nào — toàn nhiễu. Nhãn sai thì không mô hình nào học được: độ chính xác dừng ở 67%, và 567/700 mẫu drone bị đoán thành nhiễu. Cách sửa không phải là đổi mô hình mà là mô hình hoá đúng máy thu: máy quét thật bắt theo ngưỡng năng lượng rồi mới cắt cửa sổ quanh burst. Sau khi sửa, cùng một kiến trúc cũ đạt 94,9%.',
  '**The second bug, and the most valuable one in this project.** The first version cut a fixed 1.024 ms observation window. For a frequency-hopping signal with a burst period of several milliseconds, many windows labelled "drone present" contained no signal at all — pure noise. No model can learn from wrong labels: accuracy stalled at 67%, with 567 of 700 drone samples called noise. The fix was not a different model but modelling the receiver correctly: a real scanner triggers on energy and then cuts a window around the burst. With that fixed, the very same architecture reached 94.9%.')));
C.push(img(`rfspec_${L}.png`, 600, 159));
C.push(caption(T('Hình 3. Tín hiệu vô tuyến mô phỏng, tính theo dB trên nền nhiễu.',
  'Figure 3. Simulated RF signals, in dB above the noise floor.')));

// ---------------------------------------------------------------- 4
C.push(h1(T('4. Hai bộ phát hiện sớm', '4. The two early detectors')));
C.push(p(T(
  `Hai mạng đều cố ý nhỏ: ${num(RF.params)} và ${num(MD.params)} tham số. Trên thiết bị biên, một mô hình chạy lọt ngân sách quan trọng hơn vài phần trăm độ chính xác.`,
  `Both networks are deliberately small: ${num(RF.params)} and ${num(MD.params)} parameters. On an edge device, fitting the time budget matters more than a few points of accuracy.`)));
C.push(img(`accuracy_${L}.png`, 600, 176));
C.push(caption(T('Hình 4. Ma trận nhầm lẫn (theo %) và độ chính xác RF theo tỉ số tín hiệu trên nhiễu.',
  'Figure 4. Confusion matrices (in %) and RF accuracy against signal-to-noise ratio.')));
C.push(p(T(
  `Nhầm lẫn còn lại của bộ micro-Doppler nằm đúng ở cặp khó nhất về mặt vật lý: drone cánh bằng và drone đa cánh quạt, vì cả hai đều có cánh quạt quay. Nhiễu địa hình và chim gần như không bị nhầm. Bộ RF đạt ${pct(RF.by_snr[Object.keys(RF.by_snr)[0]] * 100, 1)} ngay ở dải tín hiệu yếu −6…0 dB và vượt 99% khi tín hiệu trên 6 dB.`,
  `The micro-Doppler confusion that remains sits exactly on the physically hardest pair: fixed-wing versus multirotor, since both have spinning propellers. Clutter and birds are essentially never confused. The RF classifier reaches ${pct(RF.by_snr[Object.keys(RF.by_snr)[0]] * 100, 1)} even in the weak −6…0 dB band and passes 99% above 6 dB.`)));
C.push(h2(T('Một phép so sánh kiến trúc, và bài học rút ra', 'An architecture comparison, and what it taught')));
C.push(p(T(
  `Khi độ chính xác còn kẹt ở 67%, giả thuyết đầu tiên là kiến trúc sai: CNN 1D ăn thẳng I/Q thô phải tự học ra phép biến đổi Fourier. Thêm một tầng STFT cố định phía trước rồi dùng CNN 2D nâng độ chính xác lên 96,4% — nhìn qua là một bước nhảy 29 điểm. Nhưng sau khi sửa lỗi dữ liệu nói ở mục 3 và huấn luyện lại cả hai trên cùng một bộ dữ liệu, cùng số epoch, thì CNN 1D trên I/Q thô đạt ${pct(RF.ablation_raw_iq_1dcnn_acc * 100, 1)} còn bản STFT đạt ${pct(RF.test_acc * 100, 1)}. Phần lớn "chiến thắng của kiến trúc" thực ra là lỗi dữ liệu. Tầng STFT vẫn hơn, nhưng hơn 1,5 điểm chứ không phải 29.`,
  `While accuracy was stuck at 67%, the first hypothesis was the architecture: a 1D CNN on raw I/Q has to learn the Fourier transform for itself. Adding a fixed STFT front end and a 2D CNN lifted accuracy to 96.4% — apparently a 29-point jump. But after fixing the data bug described in section 3 and retraining both on the same data for the same number of epochs, the raw-I/Q 1D CNN reached ${pct(RF.ablation_raw_iq_1dcnn_acc * 100, 1)} and the STFT version ${pct(RF.test_acc * 100, 1)}. Most of the "architecture win" was really a data bug. The STFT front end still helps, but by 1.5 points, not 29.`)));

// ---------------------------------------------------------------- 5
C.push(h1(T('5. Hợp nhất đa cảm biến', '5. Multi-sensor fusion')));
C.push(p(T('Hợp nhất tách làm hai việc độc lập.', 'Fusion does two independent jobs.')));
C.push(h2(T('Hợp nhất vị trí: bộ lọc Kalman mở rộng', 'Position fusion: an extended Kalman filter')));
C.push(p(T(
  'Trạng thái là vị trí và vận tốc 3D. Mỗi cảm biến có hàm đo riêng và được cập nhật tuần tự, nên khung nào có cảm biến nào thì dùng cảm biến đó — đúng với thực tế cảm biến rơi rụng không đồng bộ. Jacobian tính bằng sai phân trung tâm: rẻ với ma trận 6 cột và loại bỏ hẳn một nguồn lỗi khó tìm là đạo hàm giải tích viết sai. Cập nhật dùng dạng Joseph để ma trận hiệp phương sai luôn đối xứng.',
  'The state is 3D position and velocity. Each sensor has its own measurement function and is applied sequentially, so whichever sensors report in a frame are the ones used — matching the reality that sensors drop out independently. Jacobians come from central differences: cheap for a 6-column matrix, and it removes a notoriously hard-to-find class of bug, the mis-derived analytic Jacobian. Updates use the Joseph form so the covariance stays symmetric.')));
C.push(h2(T('Hợp nhất nhận dạng: cộng bằng chứng có trọng số tin cậy', 'Identity fusion: evidence weighted by reliability')));
C.push(p(T(
  'Mỗi cảm biến góp một vector log tỉ lệ khả năng, nhân với trọng số tin cậy thay đổi theo điều kiện hiện trường: trọng số của camera giảm theo sương mù, theo ban đêm và theo cự ly; trọng số RF giảm khi bị nhiễu dải. Ba chi tiết nhỏ nhưng quyết định, cả ba đều chỉ lộ ra khi đo:',
  'Each sensor contributes a log-likelihood-ratio vector scaled by a reliability weight that depends on the conditions: the camera\'s weight falls with fog, with darkness and with range; the RF weight falls under jamming. Three small details decide the outcome, and all three only surfaced through measurement:')));
C.push(bullet(T('**Trừ giá trị trung bình, không trừ giá trị lớn nhất.** Nếu chuẩn hoá bằng cách trừ max thì cảm biến chỉ biết dìm các lớp khác xuống chứ không nâng lớp mình tin lên, và nhân với trọng số tin cậy chỉ làm việc dìm chậm lại chứ không đảo ngược được.',
  '**Subtract the mean, not the maximum.** Normalising by the maximum means a sensor can only push other classes down, never push its own choice up, so scaling by reliability merely slows the suppression instead of countering it.')));
C.push(bullet(T('**Đặt trần bằng chứng cho từng cảm biến.** Camera nhìn cùng một nhãn ngụy trang mười khung liền thì đó vẫn là một bằng chứng, không phải mười bằng chứng độc lập. Không đặt trần thì cảm biến nào lấy mẫu dày nhất sẽ thắng, bất kể đúng sai — và camera 10 Hz lấy mẫu dày hơn radar (0,35 giây một chữ ký) gấp mấy lần.',
  '**Cap each sensor\'s accumulated evidence.** A camera seeing the same adversarial patch for ten frames is still one piece of evidence, not ten independent ones. Without a cap the fastest-sampling sensor wins regardless of correctness — and a 10 Hz camera samples several times faster than the radar, which needs 0.35 s per signature.')));
C.push(bullet(T('**Phát hiện mâu thuẫn rồi siết trần của cảm biến đang lệch.** Khi camera chỉ một đằng còn radar và RF chỉ một nẻo, trần của camera bị siết dần theo mức mâu thuẫn tích luỹ.',
  '**Detect conflict and tighten the dissenting sensor\'s cap.** When the camera disagrees with radar and RF, its cap shrinks in proportion to the accumulated conflict.')));

// ---------------------------------------------------------------- 6
C.push(h1(T('6. Bám quỹ đạo khi mất dấu', '6. Tracking through dropouts')));
C.push(p(T(
  'EKF giả định mô hình chuyển động cố định, nên khi mục tiêu đang lượn vòng mà tín hiệu mất dấu thì nó trôi thẳng theo hướng cũ. Một Transformer chuỗi thời gian siêu nhẹ nhìn 20 bước quá khứ (2 giây) và dự đoán 10 bước tới (1 giây); kết quả được dùng làm số đo giả để kéo vết bám theo đường cong đã học.',
  'An EKF assumes a fixed motion model, so when a turning target drops out it coasts straight along the old heading. A tiny time-series Transformer reads 20 past steps (2 s) and predicts 10 ahead (1 s); the prediction is injected as a pseudo-measurement to pull the track along the learned curve.')));
C.push(p(T(
  `**Câu chuyện đo đạc ở đây đáng kể lại, vì suýt nữa thì báo cáo này ghi một con số sai.** Bản huấn luyện đầu tiên lấy quỹ đạo thật, cộng nhiễu Gauss 1,5 m rồi lấy đạo hàm số ra vận tốc. Trên tập đó Transformer hơn phép ngoại suy vận tốc không đổi tới ${TJS ? pct(TJS.improvement_pct, 0) : '52%'}. Đem vào hệ thống thật thì nó **không hơn gì cả**. Lý do là mốc so sánh trong bài kiểm tra kia quá yếu: nó lấy vận tốc bằng sai phân của chuỗi vị trí nhiễu, trong khi EKF thật có hẳn số đo vận tốc xuyên tâm từ radar nên vận tốc tốt hơn nhiều. Nói cách khác, bài kiểm tra đã tự dựng một đối thủ yếu rồi tuyên bố thắng. Sau khi huấn luyện lại trên chính chuỗi trạng thái do EKF sinh ra, và so với chính phép ngoại suy của EKF đó, mức cải thiện thật là ${pct(TJ.improvement_pct, 1)}.`,
  `**This measurement story is worth telling, because this report nearly carried a wrong number.** The first training run took true trajectories, added 1.5 m of Gaussian noise and differentiated for velocity. On that set the Transformer beat constant-velocity extrapolation by ${TJS ? pct(TJS.improvement_pct, 0) : '52%'}. In the live system it was **no better at all**. The reason: the benchmark's baseline was too weak — it derived velocity by differencing noisy positions, while the real EKF has direct radial-velocity measurements from radar and therefore a far better velocity estimate. The benchmark had built a weak opponent and declared victory. After retraining on the state sequences the EKF itself produces, and comparing against that same EKF's extrapolation, the real improvement is ${pct(TJ.improvement_pct, 1)}.`)));
C.push(img(`tracking_${L}.png`, 600, 188));
C.push(caption(T(`Hình 5. Trái: trong hệ thống thật, mất dấu 4 giây. Phải: trên tập quỹ đạo chuẩn. Ở mốc ${num(bAt(2.0).t_s, 1)} giây mất dấu, sai số ${num(bAt(2.0).transformer_m, 1)} m so với ${num(bAt(2.0).const_vel_m, 1)} m.`,
  `Figure 5. Left: a 4-second dropout in the live system. Right: on the benchmark set. At ${num(bAt(2.0).t_s, 1)} s of blackout the error is ${num(bAt(2.0).transformer_m, 1)} m against ${num(bAt(2.0).const_vel_m, 1)} m.`)));

// ---------------------------------------------------------------- 7
C.push(h1(T('7. Kháng nhiễu và chống đánh lừa', '7. Robustness and adversarial resistance')));
C.push(p(T(
  'Giả định tấn công: kẻ gian dán nhãn ngụy trang lên thân drone khiến bộ nhận dạng ảnh đọc sai lớp, và đọc sai một cách rất tự tin. Điểm mấu chốt là nhãn dán chỉ đánh lừa được ánh sáng nhìn thấy — nó không đổi được tiết diện phản xạ radar của cánh quạt đang quay, cũng không làm mất được sóng điều khiển mà drone buộc phải phát. Phép phòng vệ do đó không nằm ở chỗ làm camera khoẻ hơn, mà ở chỗ phát hiện mâu thuẫn giữa các cảm biến rồi hạ quyền cảm biến đang bị tấn công.',
  'Attack assumption: an adversarial patch on the airframe makes the image classifier read the wrong class, and read it confidently. The key point is that a patch only fools visible light — it cannot change the radar cross-section of a spinning rotor, and it cannot suppress the control link the drone must transmit. The defence therefore is not a tougher camera but detecting the disagreement between sensors and down-weighting the one under attack.')));
C.push(img(`adversarial_${L}.png`, 470, 196));
C.push(caption(T(`Hình 6. Cùng một tập mục tiêu, cùng một chuỗi số đo, chấm trên ${num(AD.n_frames_scored)} khung mà camera đang thật sự đóng góp.`,
  `Figure 6. Same targets, same measurement sequences, scored over ${num(AD.n_frames_scored)} frames in which the camera is actually contributing.`)));
C.push(p(T(
  `Con số đáng chú ý nhất không phải ${pct(AD.defended_acc * 100, 1)} mà là ${pct(AD.naive_acc * 100, 1)}: **hợp nhất không thôi thì không cứu được gì**. Nếu cộng đều mọi cảm biến, một camera tự tin và lấy mẫu dày vẫn đủ sức lật kết luận của cả radar lẫn RF. Phải có cơ chế phát hiện mâu thuẫn và trần bằng chứng thì hợp nhất mới thành phòng vệ.`,
  `The number that matters most is not ${pct(AD.defended_acc * 100, 1)} but ${pct(AD.naive_acc * 100, 1)}: **fusion on its own saves nothing**. With equal weighting, one confident, fast-sampling camera still overturns both radar and RF. Only with conflict detection and evidence caps does fusion become a defence.`)));

// ---------------------------------------------------------------- 8
C.push(h1(T('8. Kết quả theo 7 kịch bản mô phỏng điều kiện hiện trường', '8. Results across 7 simulated field scenarios')));
C.push(img(`scenarios_${L}.png`, 600, 170));
C.push(caption(T('Hình 7. Bảy kịch bản, mỗi kịch bản 8 lần chạy độc lập với hạt giống khác nhau.',
  'Figure 7. Seven scenarios, each run 8 independent times with different seeds.')));
C.push(table([T('Kịch bản', 'Scenario'), T('Nhận dạng đúng', 'Identity'), T('Sai số bám', 'Track error'), T('Thời gian đến khi đủ tin', 'Time to confidence'), T('Hỏi người trực', 'Escalated')],
  scen.map(s => [s.scenario, pct(s.cls_acc_after_warmup * 100, 0), num(s.rmse_m, 1) + ' m',
    s.time_to_confirm_s == null ? '–' : num(s.time_to_confirm_s, 2) + ' s', pct(s.operator_ask_rate * 100, 0)]),
  [3.0, 1.1, 1.1, 1.5, 1.1], { rightNum: true }));
C.push(caption(T('Bảng 3. Trung bình 8 lần chạy. "Hỏi người trực" là tỉ lệ khung hệ thống đề nghị chuyên viên xem xét.',
  'Table 3. Means over 8 runs. "Escalated" is the share of frames on which the system asks the operator to look.')));
C.push(p(T(
  `Hai dòng đáng chú ý. **Chim: 0% khung bị đẩy lên cho người trực** — hệ thống nhận ra đó là chim và không làm phiền ai, đây là chỉ số quan trọng nhất của một hệ cảnh báo vì báo động giả nhiều thì người ta sẽ tắt nó đi. **Nhiễu dải RF: thời gian đến khi đủ tin tăng lên ${num(byId('S3').time_to_confirm_s, 1)} giây** so với ${num(byId('S1').time_to_confirm_s, 1)} giây lúc trời quang, vì mất một nguồn bằng chứng nên phải chờ radar góp đủ.`,
  `Two rows stand out. **Birds: 0% of frames escalated** — the system recognises a bird and bothers nobody, which is the single most important property of an alerting system, because an operator drowned in false alarms simply switches it off. **RF jamming: time to confidence rises to ${num(byId('S3').time_to_confirm_s, 1)} s** from ${num(byId('S1').time_to_confirm_s, 1)} s in clear air, because one source of evidence is gone and the radar has to carry the weight alone.`)));
C.push(p(T(
  'Điểm tin cậy ban đầu cũng phải sửa sau khi đo. Bản đầu cộng thẳng bốn thành phần, trong đó có độ chính xác vị trí — mà ở khung đầu tiên con số đó thực chất chỉ là hiệp phương sai khởi tạo do mình tự đặt, chưa phải bằng chứng gì cả. Kết quả là hệ thống đạt mức "đủ tin để báo người" chỉ sau 0,1 giây. Một hệ cảnh báo sớm mà tự tin sau một khung thì điểm tin cậy đó vô nghĩa. Giờ độ chín là một hệ số nhân, nên phải có ít nhất hai loại cảm biến đồng ý và quan sát khoảng 1,5 giây.',
  'The confidence score also had to be fixed after measuring. The first version simply added four terms, one of them positional accuracy — which in the first frame is really just the initial covariance I chose myself, not evidence at all. The system therefore reached "confident enough to alert a human" after 0.1 s. An early-warning system that is confident after one frame has a meaningless confidence score. Maturity is now a multiplier, so at least two sensor types must agree over roughly 1.5 s.')));

// ---------------------------------------------------------------- 9
C.push(h1(T('9. Thời gian xử lý', '9. Latency')));
C.push(img(`latency_${L}.png`, 580, 225));
C.push(caption(T(`Hình 8. Thời gian từng chặng, p99 trên ${num(LAT.total.n)} khung. Đã bỏ 3 khung khởi động đầu mỗi lần chạy.`,
  `Figure 8. Per-stage timing, p99 over ${num(LAT.total.n)} frames. The first 3 warm-up frames of each run are excluded.`)));
C.push(table([T('Chặng', 'Stage'), T('Trung bình (ms)', 'Mean (ms)'), 'p95 (ms)', 'p99 (ms)'],
  ['preproc', 'rf_net', 'md_net', 'assoc', 'ekf', 'fuse', 'traj', 'total'].filter(k => LAT[k]).map(k => [
    { preproc: T('Tiền xử lý', 'Pre-processing'), rf_net: T('Mạng RF', 'RF network'), md_net: T('Mạng micro-Doppler', 'Micro-Doppler network'), assoc: T('Liên kết số đo', 'Association'), ekf: 'EKF', fuse: T('Hợp nhất nhận dạng', 'Identity fusion'), traj: T('Dự đoán quỹ đạo', 'Trajectory prediction'), total: T('TỔNG', 'TOTAL') }[k],
    num(LAT[k].mean_ms, 3), num(LAT[k].p95_ms, 3), num(LAT[k].p99_ms, 3)]),
  [3.0, 1.3, 1.3, 1.3], { rightNum: true }));
C.push(caption(T('Bảng 4. Hai mạng nặng không chạy mỗi khung: micro-Doppler cần 0,35 giây chiếu radar mới có một chữ ký, RF lấy mẫu 0,5 giây một lần. Chạy chúng 10 lần mỗi giây là vô nghĩa về mặt vật lý, và đó cũng là cách giữ được ngân sách.',
  'Table 4. The two heavy networks do not run every frame: micro-Doppler needs 0.35 s of radar dwell per signature and RF samples every 0.5 s. Running them ten times a second would be physically meaningless, and skipping that is also how the budget is kept.')));

// ---------------------------------------------------------------- 10
C.push(h1(T('10. Giao diện cho người trực ca', '10. The operator interface')));
C.push(img('dash_patch.png', 600, 392));
C.push(caption(T('Hình 9. Màn hình lúc camera bị đánh lừa: hệ thống vẫn nhận dạng đúng, nhưng hạ điểm tin cậy và nói rõ vì sao.',
  'Figure 9. The screen while the camera is fooled: the identity stays correct, but confidence drops and the reason is stated.')));
C.push(p(T(
  'Màn hình được thiết kế quanh một câu hỏi: người trực ca cần gì để ra quyết định và chịu trách nhiệm về nó. Vì vậy bằng chứng được tách theo từng cảm biến chứ không gộp thành một con số, thời gian xử lý hiện công khai, và khi các cảm biến mâu thuẫn thì hệ thống nói thẳng ra điều đó thay vì im lặng chọn một bên. Hai nút xác nhận và bỏ qua ghi lại ai quyết định, vào lúc nào, với bằng chứng gì.',
  'The screen is built around one question: what does the duty operator need in order to decide and to be accountable for it. So evidence is broken out per sensor rather than collapsed into one number, processing time is shown openly, and when sensors disagree the system says so instead of quietly picking a side. The confirm and dismiss buttons record who decided, when, and on what evidence.')));

// ---------------------------------------------------------------- 11
C.push(h1(T('11. Hạn chế', '11. Limitations')));
C.push(p(T('Những điểm sau cần nói rõ, vì chúng quyết định cách đọc mọi con số phía trên.',
  'The following must be stated plainly, because they govern how every number above should be read.')));
C.push(bullet(T('**Chưa đo trên phần cứng biên thật.** Mọi con số thời gian đo trên CPU x86 2 nhân, không phải Jetson Orin Nano/NX. Chưa có số liệu về điện năng tiêu thụ.',
  '**Not measured on real edge hardware.** All timings are from a 2-core x86 CPU, not a Jetson Orin Nano/NX. There are no power-consumption figures.')));
C.push(bullet(T('**Toàn bộ dữ liệu là mô phỏng.** Mô phỏng dựng theo mô hình vật lý và có thêm nhiễu, thời tiết, đa đường, nhưng vẫn là mô phỏng. Độ chính xác trên tín hiệu thực địa chắc chắn thấp hơn.',
  '**All data is simulated.** The simulation is physics-based and includes noise, weather and multipath, but it is still simulation. Accuracy on real field signals will certainly be lower.')));
C.push(bullet(T('**Nhánh EO/IR không chạy mô hình thị giác thật.** Camera được mô hình hoá ở mức đầu ra (góc nhìn, tầm, độ tin cậy phân loại, và khả năng bị đánh lừa), chứ chưa có mạng phát hiện vật thể chạy trên video thật.',
  '**The EO/IR branch runs no real vision model.** The camera is modelled at its output level — field of view, range, classification confidence and susceptibility to attack — rather than by running an object detector on real video.')));
C.push(bullet(T('**Mỗi lần chỉ bám một mục tiêu.** Bài toán liên kết số đo khi có nhiều mục tiêu cùng lúc (multi-target data association) chưa làm. Đây là phần việc lớn tiếp theo.',
  '**One target at a time.** Multi-target data association is not implemented. That is the next substantial piece of work.')));
C.push(bullet(T('**Nhiễu dải RF chỉ mô hình ở mức làm giảm xác suất phát hiện và tăng sai số góc**, chưa mô phỏng các dạng tấn công vô tuyến tinh vi hơn.',
  '**RF jamming is modelled only as reduced detection probability and increased bearing error**, not as more sophisticated electronic attack.')));

C.push(h1(T('12. Bước tiếp theo', '12. Next steps')));
C.push(bullet(T('Đo lại toàn bộ trên Jetson Orin Nano, xuất mô hình sang TensorRT, ghi cả điện năng tiêu thụ.', 'Re-measure everything on a Jetson Orin Nano, export the models to TensorRT, and record power draw.')));
C.push(bullet(T('Thêm liên kết số đo đa mục tiêu, bắt đầu từ thuật toán Hungarian theo khung rồi tiến tới JPDA.', 'Add multi-target data association, starting with a per-frame Hungarian assignment and moving toward JPDA.')));
C.push(bullet(T('Thay nhánh EO/IR mô phỏng bằng mô hình phát hiện vật thể thật chạy trên video hồng ngoại.', 'Replace the simulated EO/IR branch with a real object detector running on infrared video.')));
C.push(bullet(T('Đối chiếu mô phỏng với một bộ dữ liệu micro-Doppler công khai để kiểm chứng mô hình vật lý.', 'Validate the physical model against a public micro-Doppler dataset.')));

C.push(h1(T('Phụ lục · Cách chạy lại', 'Appendix · How to reproduce')));
C.push(p(T('Mọi con số trong báo cáo đều sinh lại được bằng các lệnh sau, theo đúng thứ tự:',
  'Every number in this report can be regenerated with the following commands, in order:')));
[['python3 src/train_detect.py md', T('huấn luyện bộ micro-Doppler', 'train the micro-Doppler detector')],
 ['python3 src/train_rf2.py', T('huấn luyện bộ RF (STFT + CNN 2D)', 'train the RF detector (STFT + 2D CNN)')],
 ['python3 src/ablation_rf.py', T('so sánh với CNN 1D trên I/Q thô', 'compare against the raw-I/Q 1D CNN')],
 ['python3 src/train_traj_ekf.py', T('huấn luyện Transformer quỹ đạo trên đầu ra EKF', 'train the trajectory Transformer on EKF output')],
 ['python3 src/evaluate.py', T('chạy 7 kịch bản và đo thời gian xử lý', 'run the 7 scenarios and measure latency')],
 ['python3 src/adversarial.py', T('thử nghiệm chống đánh lừa', 'the adversarial test')],
 ['python3 src/figures.py', T('vẽ lại toàn bộ hình', 'regenerate every figure')],
 ['python3 -m pytest tests/ -q', T('chạy kiểm thử tự động', 'run the automated tests')],
 ['python3 -m uvicorn server:app --port 8099', T('mở dashboard', 'open the dashboard')],
].forEach(([cmd, desc]) => C.push(new Paragraph({
  spacing: { after: 60 }, shading: { fill: GREY, type: ShadingType.CLEAR, color: 'auto' },
  children: [new TextRun({ text: '  ' + cmd + '  ', font: 'Consolas', size: 18 }),
    new TextRun({ text: '   — ' + desc, size: 18, color: '555555' })],
})));

const doc = new Document({
  creator: 'Tran Do Hai Anh',
  title: T('Giám sát đa cảm biến tại biên', 'Multi-Sensor Edge AI Surveillance'),
  numbering: { config: [{ reference: 'b', levels: [{ level: 0, format: LevelFormat.BULLET, text: '•', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 360, hanging: 200 } } } }] }] },
  styles: {
    default: { document: { run: { font: 'Calibri', size: 21, color: '1A1A1A' } } },
    paragraphStyles: [
      { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { size: 30, bold: true, color: INK, font: 'Calibri' } },
      { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { size: 24, bold: true, color: RED, font: 'Calibri' } },
    ],
  },
  sections: [{
    properties: { page: { margin: { top: 1134, bottom: 1134, left: 1134, right: 1134 } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: T('Trần Đỗ Hải Anh · Dự án 2 · ', 'Tran Do Hai Anh · Project 2 · '), size: 16, color: '888888' }), new TextRun({ children: [PageNumber.CURRENT], size: 16, color: '888888' })] })] }) },
    children: C,
  }],
});

Packer.toBuffer(doc).then(b => {
  const out = path.join(__dirname, `../Edge_AI_Surveillance_Report_${L.toUpperCase()}.docx`);
  fs.writeFileSync(out, b);
  console.log('wrote', out, (b.length / 1024).toFixed(0) + ' KB');
});
