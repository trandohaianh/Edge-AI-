// Dashboard Edge AI. Tách khỏi index.html để Content-Security-Policy bỏ được
// 'unsafe-inline' cho script (docs/SECURITY.md, R-3): trang chỉ chạy mã từ
// chính máy chủ, mã chèn vào HTML sẽ không chạy.
const SC=[["clear","Trời quang"],["fog_night","Đêm + sương mù"],["jamming","Nhiễu RF"],
          ["bird","Chim (không báo động)"],["patch","Nhãn ngụy trang"],["dropout","Mất dấu 4 s"],
          ["swarm","Nhiều mục tiêu"]];
let SEL=null;   // ID vết bám người trực đang chọn (giữ ở trình duyệt)
const KIND={multirotor:"Drone đa cánh quạt",fixed_wing:"Drone cánh bằng",bird:"Chim"};
const SNAME={radar:"RADAR",rf:"RF",eo:"EO/IR",lidar:"LiDAR"};
const scen=document.getElementById('scen');
const $=id=>document.getElementById(id);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
// Mã truy cập (khi máy chủ đặt EDGE_API_TOKEN): hỏi một lần, giữ trong
// sessionStorage của tab này, không bao giờ đưa lên URL.
function token(){try{return sessionStorage.getItem('edge_token')||'';}catch(e){return '';}}
async function post(url,body){
  const h={'Content-Type':'application/json'};const t=token();if(t)h['X-API-Token']=t;
  // fetch chỉ ném lỗi khi không tới được máy chủ: báo bằng tiếng Việt, rõ là CHƯA ghi.
  const send=()=>fetch(url,{method:'POST',headers:h,body:body?JSON.stringify(body):undefined})
    .catch(()=>{throw new Error('mất kết nối máy chủ — chưa có gì được ghi');});
  let r=await send();
  if(r.status===401){const t2=prompt('Máy chủ yêu cầu mã truy cập ca trực:');
    if(t2){try{sessionStorage.setItem('edge_token',t2);}catch(e){} h['X-API-Token']=t2;
      r=await send();}}
  let d={};try{d=await r.json();}catch(e){}
  if(!r.ok)throw new Error(d.detail&&typeof d.detail==='string'?d.detail:(d.error||('lỗi '+r.status)));
  return d;}
function say(t,err){const m=$('actmsg');m.textContent=t;m.className='msg'+(err?' err':'');}
SC.forEach(([k,t])=>{const b=document.createElement('button');b.className='btn';b.textContent=t;
  b.onclick=()=>post('/api/scenario/'+k).then(()=>say('Đã chuyển kịch bản: '+t))
    .catch(e=>say('Không chuyển được kịch bản: '+e.message,true));
  b.dataset.k=k;scen.appendChild(b);});
$('bok').onclick=()=>act('xac_nhan');
$('bno').onclick=()=>act('bo_qua');
async function act(a){
  $('bok').disabled=$('bno').disabled=true;
  try{const d=await post('/api/act',{action:a,operator:'truc-ca-1',tid:SEL});
    say(d.persisted?'Đã ghi quyết định vào nhật ký.':'Đã ghi trên màn hình nhưng KHÔNG ghi được xuống đĩa — báo kỹ thuật.',!d.persisted);}
  catch(e){say('Không ghi được quyết định: '+e.message,true);}}

const cv=document.getElementById('map'),cx=cv.getContext('2d');
let SCALE=1;
function toXY(p,w,h){return [w/2+p[0]*SCALE, h/2-p[1]*SCALE];}
const PAL=['#D7153A','#4EA8FF','#C77DFF','#FF8A3D','#2EC4B6','#F15BB5','#9BE564','#FFD23F'];
const col=t=>PAL[Math.abs(t)%PAL.length];
function draw(s,sel){
  const w=cv.width,h=cv.height;cx.clearRect(0,0,w,h);
  const trails=s.trails||{};const truths=s.truth_trails||[];
  let pts=[];truths.forEach(t=>pts=pts.concat(t));Object.values(trails).forEach(t=>pts=pts.concat(t));
  let m=250;pts.forEach(p=>{m=Math.max(m,Math.abs(p[0]),Math.abs(p[1]))});
  SCALE=(Math.min(w,h)/2-46)/(m*1.04);
  cx.strokeStyle='#1A1D24';cx.lineWidth=1;
  for(const r of [200,400,600,800,1000,1500,2000,2500,3000]){
    if(r*SCALE>Math.min(w,h)/2)break;
    cx.beginPath();cx.arc(w/2,h/2,r*SCALE,0,7);cx.stroke();
    cx.fillStyle='#363C49';cx.font='10px ui-monospace';cx.fillText(r+' m',w/2+r*SCALE+4,h/2-3);}
  cx.beginPath();cx.moveTo(w/2,0);cx.lineTo(w/2,h);cx.moveTo(0,h/2);cx.lineTo(w,h/2);cx.stroke();
  const line=(tr,col,dash)=>{if(!tr||tr.length<2)return;cx.setLineDash(dash||[]);cx.strokeStyle=col;
    cx.lineWidth=2;cx.beginPath();tr.forEach((p,i)=>{const[a,b]=toXY(p,w,h);i?cx.lineTo(a,b):cx.moveTo(a,b)});
    cx.stroke();cx.setLineDash([]);};
  // góc nhìn camera trên bệ quay (60°)
  if(typeof s.eo_az==='number'){const R=Math.min(w,h);cx.fillStyle='rgba(78,168,255,.07)';
    cx.beginPath();cx.moveTo(w/2,h/2);cx.arc(w/2,h/2,R,-s.eo_az-Math.PI/6,-s.eo_az+Math.PI/6);cx.closePath();cx.fill();}
  truths.forEach(t=>line(t,'#2BD576'));
  (s.tracks||[]).forEach(t=>{
    const c=col(t.tid),isSel=t.tid===sel;
    line(trails[String(t.tid)],c);
    if(t.predicted&&t.predicted.length)line([t.pos].concat(t.predicted),'#FFB020',[6,5]);
    const[a,b]=toXY(t.pos,w,h);
    cx.strokeStyle=c;cx.globalAlpha=.55;cx.lineWidth=1.5;cx.beginPath();
    cx.arc(a,b,Math.max(5,(t.sigma||5)*SCALE),0,7);cx.stroke();cx.globalAlpha=1;
    if(t.needs_operator){cx.strokeStyle='#FFB020';cx.lineWidth=2;cx.beginPath();cx.arc(a,b,11,0,7);cx.stroke();}
    cx.fillStyle=c;cx.beginPath();cx.arc(a,b,isSel?6:4,0,7);cx.fill();
    cx.fillStyle='#F3F4F7';cx.font=(isSel?'700 ':'500 ')+'12px system-ui';
    cx.fillText('#'+t.tid+' '+(KIND[t.kind]||t.kind)+(isSel?'  '+Math.round(Math.hypot(t.pos[0],t.pos[1]))+' m  '
      +Math.round(t.pos[2])+' m cao':''),a+11,b-9);});
  cx.fillStyle='#8A93A6';cx.font='11px ui-monospace';
  cx.fillText('TRẠM GIÁM SÁT',w/2+7,h/2+15);
  cx.fillStyle='#F3F4F7';cx.fillRect(w/2-3,h/2-3,6,6);
  if(s.blind){cx.fillStyle='rgba(255,176,32,.13)';cx.fillRect(0,0,w,h);
    cx.fillStyle='#FFB020';cx.font='700 15px system-ui';
    cx.fillText('MẤT DẤU — đang chạy dự đoán quỹ đạo',18,28);}
}

function renderTracks(s,T){
  // Sắp theo ID cho hàng đứng yên: máy chủ xếp theo mức ưu tiên, đổi liên
  // tục mỗi khung, người trực sẽ bấm nhầm hàng.
  $('trk').innerHTML=T.length?[...T].sort((a,b)=>a.tid-b.tid).map(t=>`<tr data-tid="${t.tid}" class="${t.tid===SEL?'sel':''}">
    <td><b style="color:${col(t.tid)}">#${t.tid}</b></td><td>${esc(KIND[t.kind]||t.kind)}</td>
    <td>${Math.round(Math.hypot(t.pos[0],t.pos[1]))} m</td><td>${(t.confidence*100).toFixed(0)}%</td>
    <td>${t.operator?`<span class="tag ${t.operator==='xac_nhan'?'ok':'no'}">${t.operator==='xac_nhan'?'ĐÃ XÁC NHẬN':'ĐÃ BỎ QUA'}</span>`
      :(t.needs_operator?'<span class="tag warn">CHỜ QUYẾT ĐỊNH</span>':esc(t.status))}</td></tr>`).join('')
    :'<tr><td colspan="5" style="color:var(--muted)">chưa có vết bám xác nhận</td></tr>';
  $('trknote').textContent=s.multi?`Mục tiêu thật trong mô phỏng: ${s.n_targets_truth}. `
    +`Vết tạm đang chờ xác nhận (phần lớn là báo động giả): ${s.tentative??0}.`:'';
}
$('trk').addEventListener('click',e=>{const r=e.target.closest('tr[data-tid]');if(r){SEL=+r.dataset.tid;say('');}});
function bar(v,cls){return `<div class="bar ${cls||''}"><i style="width:${Math.round(v*100)}%"></i></div>`;}
function live(ok,text){const l=$('live');l.textContent=text;l.className='pill '+(ok?'live':'down');}
async function tick(){
  let s;
  try{const r=await fetch('/api/state',{cache:'no-store'});
    if(!r.ok)throw new Error('HTTP '+r.status);s=await r.json();}
  catch(e){
    // Mất kết nối: số liệu trên màn hình đã cũ. Làm mờ và khoá nút quyết
    // định để người trực không quyết dựa trên dữ liệu cũ (kiểm thử bước 8).
    live(false,'● mất kết nối máy chủ');document.body.classList.add('stale');
    $('bok').disabled=$('bno').disabled=true;
    const b=$('banner');b.style.display='block';
    b.textContent='⚠ Mất kết nối máy chủ — số liệu bên dưới là của lần cập nhật cuối, KHÔNG dùng để ra quyết định. Đang thử kết nối lại…';
    return;}
  document.body.classList.remove('stale');
  const ban=$('banner');
  if(s.models_trained===false){ban.style.display='block';
    ban.textContent='⚠ Máy chủ đang chạy với trọng số CHƯA HUẤN LUYỆN — mọi nhận dạng trên màn hình là vô nghĩa.';}
  else ban.style.display='none';
  const T=s.tracks||[];
  if(!T.length||!T.some(t=>t.tid===SEL))SEL=T.length?T[0].tid:null;
  renderTracks(s,T);
  if(!T.length){live(true,'● đang chạy — chưa có vết bám xác nhận');$('bok').disabled=$('bno').disabled=true;draw(s,SEL);return;}
  live(true,'● đang chạy');
  draw(s,SEL);
  s=Object.assign({},s,T.find(t=>t.tid===SEL));
  document.getElementById('scn').textContent=s.scenario_label||'';
  document.getElementById('wx').textContent='Thời tiết: '+(s.weather||'');
  document.getElementById('kind').textContent=KIND[s.kind]||s.kind;
  const st=document.getElementById('status');st.textContent=s.status;
  st.style.color=s.status==='đang bám'?'var(--ok)':(s.status==='mất dấu'?'var(--red)':'var(--warn)');
  const names=['multirotor','fixed_wing','bird'];
  document.getElementById('probs').innerHTML=names.map((n,i)=>
    `<div class="sens"><span>${KIND[n]}</span>${bar(s.probs[i])}<span>${(s.probs[i]*100).toFixed(0)}%</span></div>`).join('');
  const r=Math.hypot(s.pos[0],s.pos[1]);
  document.getElementById('kin').innerHTML=
    `<span>cự ly</span><span>${r.toFixed(0)} m</span>`+
    `<span>độ cao</span><span>${s.pos[2].toFixed(0)} m</span>`+
    `<span>tốc độ</span><span>${Math.hypot(s.vel[0],s.vel[1],s.vel[2]).toFixed(1)} m/s</span>`+
    `<span>sai số vị trí (1σ)</span><span>${s.sigma.toFixed(1)} m</span>`+
    (s.truth_kind?`<span>sự thật mô phỏng</span><span>${KIND[s.truth_kind]||s.truth_kind}</span>`:'');
  document.getElementById('confv').textContent=(s.confidence*100).toFixed(0)+'%';
  const cb=document.getElementById('confb');cb.style.width=(s.confidence*100)+'%';
  cb.parentElement.className='bar '+(s.confidence>.75?'g':(s.confidence>.45?'w':''));
  document.getElementById('sens').innerHTML=['radar','rf','eo','lidar'].map(k=>{
    const on=(s.sensors||[]).includes(k);const e=(s.evidence||{})[k]||0;
    return `<div class="sens ${on?'':'off'}"><span>${SNAME[k]}</span>${bar(Math.min(1,e/2.5),on?'g':'')}
      <span>${on?'đang thấy':'—'}</span></div>`;}).join('');
  document.getElementById('conflict').innerHTML = s.conflict>0.15
    ? `⚠ <b>Phát hiện mâu thuẫn giữa các cảm biến (${(s.conflict*100).toFixed(0)}%).</b>
       Camera chỉ một đằng, radar và RF chỉ một nẻo — trọng số của camera đã bị hạ xuống.
       Đây là dấu hiệu điển hình của nhãn ngụy trang dán lên thân mục tiêu.`
      +(s.deception_suspected?` <b>Nghi bị đánh lừa: hệ thống đưa vết bám này lên để người trực xem xét.</b>`:'') : '';
  const L=s.stage_latency||{};const order=['preproc','rf_net','md_net','assoc','ekf','fuse','traj','total'];
  const NM={preproc:'tiền xử lý',rf_net:'mạng RF',md_net:'mạng radar',assoc:'liên kết',
            ekf:'EKF',fuse:'hợp nhất',traj:'dự đoán',total:'TỔNG'};
  document.getElementById('lat').innerHTML=order.filter(k=>L[k]).map(k=>{
    const v=L[k].p99_ms,f=Math.min(1,v/50);
    return `<div class="lat"><span>${NM[k]}</span>${bar(f,k==='total'?(v<50?'g':''):'')}
      <span>${v.toFixed(2)} ms</span></div>`;}).join('')+
    `<div class="note">Cột số là p99 — 99% số khung xử lý xong nhanh hơn giá trị này.</div>`;
  const a=s.audit||[];
  document.getElementById('audit').innerHTML=a.length?a.map(x=>
    `<tr><td>${esc(x.frame)} · #${esc(x.tid)}</td><td><span class="tag ${x.action==='xac_nhan'?'ok':'no'}">
      ${x.action==='xac_nhan'?'XÁC NHẬN':'BỎ QUA'}</span></td>
      <td>${esc(x.operator)}</td><td>${esc(KIND[x.kind]||x.kind)}</td><td>${(x.confidence*100).toFixed(0)}%</td></tr>`).join('')
    :'<tr><td colspan="5" style="color:var(--muted)">chưa có thao tác nào</td></tr>';
  $('bok').disabled=!!s.operator;
  $('bno').disabled=!!s.operator;
  $('ask').style.display=s.needs_operator?'block':'none';
  [...scen.children].forEach(b=>b.classList.toggle('on',b.dataset.k===s.scenario));
}
// Hẹn giờ nối tiếp thay cho setInterval: máy chủ chậm thì không dồn hàng
// chục yêu cầu chồng lên nhau.
async function loop(){try{await tick();}finally{setTimeout(loop,180);}}
loop();
