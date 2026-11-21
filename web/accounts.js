/* 平台账号面板：登录、验证、取消和退出；不依赖搜索结果状态。 */
import {$, el, fetchTimeout, postJSON} from './dom.js';
import {requestGate} from './order.mjs';

/** 各账号状态下可执行的操作（纯函数，导出供单测覆盖状态矩阵）。 */
export function actionsFor(a){
  const acts=[];const login=lbl=>acts.push({k:'login',lbl});
  switch(a.state){
    case 'no_profile': login('登录');break;
    case 'pending': acts.push({k:'verify',lbl:'检查状态'});login('登录');break;
    case 'logged_in': acts.push({k:'verify',lbl:'检查状态'},{k:'login',lbl:'重新登录'},{k:'logout',lbl:'退出'});break;
    case 'expired': login('重新登录');acts.push({k:'verify',lbl:'检查状态'},{k:'logout',lbl:'退出'});break;
    case 'login_failed': login('重试登录');break;
    case 'unknown': acts.push({k:'verify',lbl:'检查状态'},{k:'login',lbl:'重新登录'},{k:'logout',lbl:'退出'});break;
  }
  return acts;
}

/** 页面加载时初始化账号交互，返回轮询清理入口。 */
export function initAccounts(){
/* ---- 平台账号（右上角用户入口 → 面板；登录/检查状态/重新登录/退出） ---- */
let loginPlat=null,loginTimer=null,verifyTimer=null;
const verifyTimers={};
const verifyInFlight=new Set();   // 防止“检查状态”双击重复提交，杀掉正在运行的验证
const accountGate=requestGate();   // 面板渲染身份：晚到的账号快照不覆盖新面板
const loginGate=requestGate();     // 登录弹窗会话身份：取消/换平台后旧轮询失效
const badgeCls={no_profile:'no_profile',pending:'pending',verifying:'verifying',logged_in:'logged_in',expired:'expired',login_failed:'login_failed',unknown:'unknown'};

async function loadAccounts(){
  const id=accountGate.next();
  try{
    const r=await fetchTimeout('/api/accounts',{},8000);
    if(!r.ok)return;   // 拉取失败保留旧面板，不误报成功
    const d=await r.json();
    if(!accountGate.latest(id))return;   // 晚到的账号快照不覆盖新面板
    const box=$('acct-list');box.replaceChildren();
    (d.accounts||[]).forEach(a=>box.append(acctCard(a)));
    $('user-name').textContent=(d.accounts||[]).some(a=>a.state==='logged_in')?'已登录':'访客';
  }catch(e){}
}
function acctCard(a){
  const card=el('div',undefined,'acct-card');card.dataset.plat=a.platform;
  const top=el('div',undefined,'acct-top');
  top.append(el('span',a.label,'name'),el('span',a.state_label||a.state,'badge '+(badgeCls[a.state]||'')));
  card.append(top);
  const sub=el('div',undefined,'acct-sub');
  if(a.nickname)sub.append(el('span','昵称：'+a.nickname,'nick'));
  sub.append(el('span','最近验证：'+(a.last_verified_at||'—')));
  card.append(sub);
  if(!a.login_supported){card.append(el('div',a.note||'暂不支持登录','acct-note'));return card;}
  if(a.note)card.append(el('div',a.note,'acct-note'));
  if(a.state==='verifying'){card.append(el('div','正在验证会话有效性…','acct-note'));return card;}
  const acts=el('div',undefined,'acct-actions');
  actionsFor(a).forEach(act=>{
    const b=el('button',act.lbl);
    if(act.k==='login')b.className='primary';
    if(act.k==='logout')b.className='danger';
    if(act.k==='verify'&&verifyInFlight.has(a.platform))b.disabled=true;
    b.onclick=()=>{if(act.k==='login')startLogin(a.platform,a.label);else if(act.k==='verify')doVerify(a.platform);else if(act.k==='logout')doLogout(a.platform,a.label);};
    acts.append(b);
  });
  card.append(acts);
  return card;
}
function openPanel(){$('acct-panel').hidden=false;loadAccounts();}
function closePanel(){$('acct-panel').hidden=true;}
$('user-btn').onclick=()=>{if($('acct-panel').hidden)openPanel();else closePanel();};
$('acct-close').onclick=closePanel;

async function doVerify(platform){
  if(verifyInFlight.has(platform))return;   // 双击/重试防抖：验证进行中不重复提交
  verifyInFlight.add(platform);loadAccounts();  // 立即禁用按钮，给出可感知反馈
  try{
    const r=await postJSON('/api/verify',{platform});
    const d=await r.json();
    if(!r.ok||d.ok===false){alert('检查状态失败：'+(d.error||('HTTP '+r.status)));verifyInFlight.delete(platform);loadAccounts();return;}
  }catch(e){alert('检查状态失败：'+e);verifyInFlight.delete(platform);loadAccounts();return;}
  if(verifyTimers[platform])return;
  verifyTimers[platform]=setInterval(async()=>{
    try{
      const r=await fetchTimeout('/api/verify?platform='+encodeURIComponent(platform),{},8000);
      if(!r.ok)return;   // 轮询失败继续等下一轮，不显示成功
      const d=await r.json();
      if(d.state!=='verifying'){
        clearInterval(verifyTimers[platform]);delete verifyTimers[platform];
        verifyInFlight.delete(platform);loadAccounts();
      }
    }catch(e){}
  },2000);
}
async function doLogout(platform,label){
  if(!confirm('退出登录将清除「'+label+'」在本机的专用登录档案（不影响采集资料与其他平台）。确认退出？'))return;
  try{
    const r=await postJSON('/api/logout',{platform});
    const d=await r.json();
    if(!r.ok||!d.ok){alert('退出失败：'+(d.error||('HTTP '+r.status)));return;}
    loadAccounts();
  }catch(e){alert('退出失败：'+e);}
}

function startLogin(platform,label){
  loginPlat=platform;
  loginGate.next();      // 作废旧登录会话的轮询响应（防止旧平台迟到响应串入新弹窗）
  $('login-title').textContent='扫码登录'+label;
  $('qr-holder').replaceChildren(el('p','正在启动登录…','empty'));
  $('login-status').textContent='';
  $('qr-retry').hidden=true;$('qr-close').hidden=true;$('qr-cancel').hidden=false;
  $('login-modal').hidden=false;
  postJSON('/api/login',{platform})
    .then(async r=>{const d=await r.json();if(!r.ok||d.status==='failed'){$('login-status').textContent='启动失败：'+(d.error||('HTTP '+r.status));$('qr-cancel').hidden=true;$('qr-close').hidden=false;}})
    .catch(e=>{$('login-status').textContent='启动失败：'+e;});
  clearLoginTimers();
  loginTimer=setInterval(pollLogin,2000);
  pollLogin();
}
function imgFromB64(b64){const im=el('img','');im.src='data:image/png;base64,'+b64;im.alt='扫码登录';return im;}
async function pollLogin(){
  if(!loginPlat)return;
  const id=loginGate.peek();   // 捕获当前登录会话身份，不推进
  const plat=loginPlat;
  try{
    const r=await fetchTimeout('/api/login?platform='+encodeURIComponent(plat),{},8000);
    const d=await r.json();
    if(plat!==loginPlat||!loginGate.latest(id))return;   // 已换平台/已关闭：丢弃旧响应
    if(d.status==='window_open')$('qr-holder').replaceChildren(el('p','在新窗口点击平台的登录按钮，可使用平台提供的扫码方式。'));
    if(d.qr)$('qr-holder').replaceChildren(imgFromB64(d.qr));
    const msgs={starting:'正在启动登录…（首次会短暂打开专用浏览器）',window_open:'请在专用浏览器窗口完成登录，再关闭该窗口以验证状态',qr_ready:'请用手机 App 扫码，等待确认',qr_missing:'未读取到二维码',logged_in:'认证完成，正在验证会话…',expired:'二维码已过期，可重新生成',failed:'登录失败',cancelled:'已取消登录',idle:'未开始'};
    const extra=(d.qr_error?' · '+d.qr_error:'');
    $('login-status').textContent=(msgs[d.status]||d.status)+(d.error?' · '+d.error:'')+extra;
    if(d.status==='logged_in'){
      clearInterval(loginTimer);loginTimer=null;
      verifyTimer=setInterval(pollVerify,2000);pollVerify();
    }else if(d.status==='expired'||d.status==='failed'){
      $('qr-retry').hidden=false;
      clearInterval(loginTimer);loginTimer=null;
    }
  }catch(e){$('login-status').textContent='网络异常，自动重试中…';}
}
async function pollVerify(){
  if(!loginPlat)return;
  const id=loginGate.peek();   // 捕获当前登录会话身份，不推进
  const plat=loginPlat;
  try{
    const r=await fetchTimeout('/api/verify?platform='+encodeURIComponent(plat),{},8000);
    const d=await r.json();
    if(plat!==loginPlat||!loginGate.latest(id))return;   // 已换平台/已关闭：丢弃旧响应
    if(d.state==='verifying'){$('login-status').textContent='正在验证会话有效性…';return;}
    clearInterval(verifyTimer);verifyTimer=null;
    if(d.state==='logged_in'){$('login-status').textContent='登录成功（会话已验证）';}
    else{$('login-status').textContent='验证结果：'+(d.state_label||d.state)+(d.error?' · '+d.error:'');}
    $('qr-close').hidden=false;$('qr-cancel').hidden=true;
    loadAccounts();
  }catch(e){$('login-status').textContent='网络异常，自动重试中…';}
}
function clearLoginTimers(){if(loginTimer){clearInterval(loginTimer);loginTimer=null;}if(verifyTimer){clearInterval(verifyTimer);verifyTimer=null;}}
function closeModal(){clearLoginTimers();$('login-modal').hidden=true;loginPlat=null;}
$('qr-close').onclick=closeModal;
$('qr-retry').onclick=()=>{if(loginPlat)startLogin(loginPlat,$('login-title').textContent.replace('扫码登录','')||loginPlat);};
$('qr-cancel').onclick=async()=>{
  try{
    const r=await postJSON('/api/login/cancel',{platform:loginPlat});
    const d=await r.json();
    if(!r.ok||!d.ok){$('login-status').textContent='取消失败：'+(d.error||('HTTP '+r.status));return;}
    if(!d.cancelled){$('login-status').textContent=d.note||'当前没有可取消的登录任务';return;}
    $('login-status').textContent='已取消登录';
  }catch(e){$('login-status').textContent='取消失败：'+e;return;}
  clearLoginTimers();
  setTimeout(closeModal,700);
  loadAccounts();
};
loadAccounts();
  return {destroy(){
    clearLoginTimers();
    Object.keys(verifyTimers).forEach(platform=>{clearInterval(verifyTimers[platform]);delete verifyTimers[platform];});
  }};
}
