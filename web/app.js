/* CyberField 搜索引擎前端：黑白极简、模糊搜索、30 条/页、LLM 总结轮询。 */
const $=id=>document.getElementById(id);
const labels={bilibili:'B站',weibo:'微博',douban:'豆瓣',xiaohongshu:'小红书',douyin:'抖音',zhihu:'知乎'};
function el(tag,text,cls){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;}
function link(row){const a=el('a','查看原文 ↗','');try{const u=new URL(row.url);if(!['http:','https:'].includes(u.protocol))throw Error();a.href=u.href;a.target='_blank';a.rel='noopener noreferrer';}catch{a.removeAttribute('href');a.textContent='来源不可用';}return a;}
let S={keyword:'',rows:[],total:0,page:1,pages:1,expanded:[],errors:[],view:'data',dim:'timeline'};
let pollTimer=null;

async function search(page=1){
  const kw=$('q').value.trim();if(!kw)return;
  $('meta').textContent='正在搜索「'+kw+'」，自动扩展相关词…（约 10~25 秒）';
  $('list').replaceChildren();$('pager').replaceChildren();
  try{
    const r=await fetch('/api/search',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({keyword:kw,page})});
    if(!r.ok)throw Error('接口 '+r.status);
    const d=await r.json();
    S={keyword:d.keyword||kw,rows:d.rows||[],total:d.total||0,page:d.page||1,pages:d.pages||1,expanded:d.expanded||[kw],errors:d.errors||[],view:S.view,dim:S.dim};
  }catch(e){$('meta').textContent='搜索失败：'+e;return;}
  renderMeta();renderList();renderPager();
  $('analyze-nav').hidden=false;
  switchView('data');
  if(pollTimer)clearInterval(pollTimer);
  pollTimer=setInterval(pollSummaries,2000);
}

async function pollSummaries(){
  if(!S.keyword)return;
  try{
    const r=await fetch('/api/summaries?keyword='+encodeURIComponent(S.keyword));
    const d=await r.json();const states={};
    (d.states||[]).forEach(s=>states[s.url]=s);
    let changed=false;
    S.rows.forEach(row=>{
      const st=states[row.url];
      if(st&&st.done&&!row._done){row._done=true;row.summary=st.summary;row.comments=st.comments;changed=true;}
    });
    if(changed)renderList();
    const all=(d.states||[]).filter(s=>s.done).length>0;
    if((d.states||[]).length&&(d.states||[]).every(s=>s.done)){clearInterval(pollTimer);pollTimer=null;}
  }catch(e){}
}

function renderMeta(){
  const bits=[`${S.total} 条结果`];
  if(S.expanded.length>1)bits.push('已扩展为 '+S.expanded.join(' / '));
  $('meta').textContent=bits.join(' · ');
  if(S.errors&&S.errors.length)$('meta').textContent+=' · '+S.errors.length+' 个源不可用';
}

function renderList(){
  const list=$('list');list.replaceChildren();
  if(!S.rows.length){const e=el('div',undefined,'empty');e.append(el('h3','没有匹配结果'),el('p','换个搜索词试试。'));list.append(e);return;}
  S.rows.forEach(r=>list.append(card(r)));
}

function card(r){
  const a=el('article',undefined,'record');
  const head=el('div',undefined,'record-head');
  head.append(el('span',labels[r.platform]||r.platform,'plat'),el('h3',r.title||r.text?.slice(0,40)||'无标题'));
  a.append(head);
  a.append(el('p',`${r.author||'未知作者'} · ${r.published_at?r.published_at.slice(0,16):'时间未知'}`,'byline'));
  if(r.summary)a.append(el('div',r.summary,'summary'));
  else a.append(el('div',r._done?'（未配置 AI 总结）':'总结生成中…','summary placeholder'));
  if(r.comments&&r.comments.length){const c=el('div',undefined,'comments');r.comments.forEach(cm=>c.append(el('span','▸ '+cm)));a.append(c);}
  const foot=el('div',undefined,'row-foot');foot.append(link(r));
  const e=r.extra||{},bits=[];
  if(e.play)bits.push('播放 '+e.play);
  if(e.liked)bits.push('赞 '+e.liked);
  if(e.comment||e.reply)bits.push('评论 '+(e.comment||e.reply));
  if(e.duration)bits.push((e.duration/60).toFixed(0)+' 分钟');
  if(bits.length)foot.append(el('span',bits.join(' · ')));
  a.append(foot);
  return a;
}

function renderPager(){
  const p=$('pager');p.replaceChildren();
  if(S.pages<=1)return;
  const prev=el('button','← 上一页');prev.disabled=S.page<=1;prev.onclick=()=>go(S.page-1);
  const next=el('button','下一页 →');next.disabled=S.page>=S.pages;next.onclick=()=>go(S.page+1);
  p.append(prev,el('span',`第 ${S.page} / ${S.pages} 页`,'page-num'),next);
}
async function go(page){
  $('list').replaceChildren();$('meta').textContent='加载第 '+page+' 页…';
  try{
    const r=await fetch('/api/search',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({keyword:S.keyword,page})});
    const d=await r.json();
    S.rows=d.rows||[];S.page=d.page||1;S.pages=d.pages||1;S.expanded=d.expanded||S.expanded;
  }catch(e){$('meta').textContent='翻页失败：'+e;return;}
  renderMeta();renderList();renderPager();
}

const dimTitle={timeline:'时间热度',topics:'相关话题',groups:'相关群体'};
async function showAnalysis(){
  if(!S.keyword){$('chart-title').textContent='请先搜索一个词。';return;}
  $('chart-title').textContent=dimTitle[S.dim]+' · 「'+S.keyword+'」';
  const chart=$('chart');chart.replaceChildren(el('p','统计中…','empty'));
  try{
    const r=await fetch('/api/analysis?keyword='+encodeURIComponent(S.keyword));
    const d=await r.json();
    chart.replaceChildren();
    if(S.dim==='timeline')renderTimeline(chart,d.timeline);
    else if(S.dim==='topics')renderTopics(chart,d.topics);
    else renderGroups(chart,d.groups);
  }catch(e){chart.replaceChildren(el('p','分析失败：'+e,'empty'));}
}
function renderTimeline(chart,data){
  if(!data||!data.length){chart.append(el('p','暂无发布时间的样本。','empty'));return;}
  const values=[...data].sort((a,b)=>a[0].localeCompare(b[0]));
  const max=Math.max(...values.map(x=>x[1]));
  const bars=el('div',undefined,'bars');
  for(const[d,n]of values){const c=el('div',undefined,'bar-col');const b=el('div',undefined,'bar');b.style.height=`${n/max*170}px`;b.title=`${d}：${n} 条`;c.append(el('span',n),b,el('small',d.slice(5)));bars.append(c);}
  chart.append(bars,el('p',`${data.reduce((a,x)=>a+x[1],0)} 条样本的时间分布。`,'meta-line'));
}
function renderTopics(chart,data){
  if(!data||!data.length){chart.append(el('p','重复表达不足。','empty'));return;}
  const cloud=el('div',undefined,'wordcloud');
  data.forEach((t,i)=>{const s=el('span',t.word);s.style.fontSize=`${15+Math.min(t.count,12)*1.3}px`;s.title=`出现 ${t.count} 次`;cloud.append(s);});
  chart.append(cloud);
}
function renderGroups(chart,data){
  if(!data||!data.length){chart.append(el('p','暂无群体样本。','empty'));return;}
  const max=Math.max(...data.map(x=>x.count));
  data.forEach(g=>{const row=el('div',undefined,'dist'),track=el('div',undefined,'track'),fill=el('div',undefined,'fill');fill.style.width=`${g.count/max*100}%`;track.append(fill);row.append(el('span',g.label),track,el('span',g.count,'num'));chart.append(row);});
}

function switchView(v){S.view=v;$('tab-data').classList.toggle('active',v==='data');$('tab-analysis').classList.toggle('active',v==='analysis');$('data-view').hidden=v!=='data';$('analysis-view').hidden=v!=='analysis';if(v==='analysis')showAnalysis();}

/* ---- 平台账号（右上角用户入口 → 面板；登录/检查状态/重新登录/退出） ---- */
let loginPlat=null,loginTimer=null,verifyTimer=null;
const verifyTimers={};
const badgeCls={no_profile:'no_profile',pending:'pending',verifying:'verifying',logged_in:'logged_in',expired:'expired',login_failed:'login_failed',unknown:'unknown'};

async function loadAccounts(){
  try{
    const r=await fetch('/api/accounts');
    const d=await r.json();
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
    b.onclick=()=>{if(act.k==='login')startLogin(a.platform,a.label);else if(act.k==='verify')doVerify(a.platform);else if(act.k==='logout')doLogout(a.platform,a.label);};
    acts.append(b);
  });
  card.append(acts);
  return card;
}
function actionsFor(a){
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
function openPanel(){$('acct-panel').hidden=false;loadAccounts();}
function closePanel(){$('acct-panel').hidden=true;}
$('user-btn').onclick=()=>{if($('acct-panel').hidden)openPanel();else closePanel();};
$('acct-close').onclick=closePanel;

async function doVerify(platform){
  try{await fetch('/api/verify',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({platform})});}catch(e){}
  if(verifyTimers[platform])return;
  verifyTimers[platform]=setInterval(async()=>{
    try{
      const r=await fetch('/api/verify?platform='+encodeURIComponent(platform));
      const d=await r.json();
      if(d.state!=='verifying'){clearInterval(verifyTimers[platform]);delete verifyTimers[platform];loadAccounts();}
    }catch(e){}
  },2000);
}
async function doLogout(platform,label){
  if(!confirm('退出登录将清除「'+label+'」在本机的专用登录档案（不影响采集资料与其他平台）。确认退出？'))return;
  try{await fetch('/api/logout',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({platform})});}catch(e){}
  loadAccounts();
}

function startLogin(platform,label){
  loginPlat=platform;
  $('login-title').textContent='扫码登录'+label;
  $('qr-holder').replaceChildren(el('p','正在启动登录…','empty'));
  $('login-status').textContent='';
  $('qr-retry').hidden=true;$('qr-close').hidden=true;$('qr-cancel').hidden=false;
  $('login-modal').hidden=false;
  fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({platform})})
    .then(r=>r.json()).then(d=>{if(d.status==='failed'){$('login-status').textContent='启动失败：'+(d.error||'');$('qr-cancel').hidden=true;$('qr-close').hidden=false;}})
    .catch(e=>{$('login-status').textContent='启动失败：'+e;});
  clearLoginTimers();
  loginTimer=setInterval(pollLogin,2000);
  pollLogin();
}
function imgFromB64(b64){const im=el('img','');im.src='data:image/png;base64,'+b64;im.alt='扫码登录';return im;}
async function pollLogin(){
  if(!loginPlat)return;
  try{
    const r=await fetch('/api/login?platform='+encodeURIComponent(loginPlat));
    const d=await r.json();
    if(d.qr)$('qr-holder').replaceChildren(imgFromB64(d.qr));
    const msgs={starting:'正在启动登录…（首次会短暂打开专用浏览器）',qr_ready:'请用手机 App 扫码，等待确认',logged_in:'认证完成，正在验证会话…',expired:'二维码已过期，可重新生成',failed:'登录失败',cancelled:'已取消登录',idle:'未开始'};
    $('login-status').textContent=(msgs[d.status]||d.status)+(d.error?' · '+d.error:'');
    if(d.status==='logged_in'){
      clearInterval(loginTimer);loginTimer=null;
      verifyTimer=setInterval(pollVerify,2000);pollVerify();
    }else if(d.status==='expired'||d.status==='failed'){
      $('qr-retry').hidden=false;
      clearInterval(loginTimer);loginTimer=null;
    }
  }catch(e){}
}
async function pollVerify(){
  if(!loginPlat)return;
  try{
    const r=await fetch('/api/verify?platform='+encodeURIComponent(loginPlat));
    const d=await r.json();
    if(d.state==='verifying'){$('login-status').textContent='正在验证会话有效性…';return;}
    clearInterval(verifyTimer);verifyTimer=null;
    if(d.state==='logged_in'){$('login-status').textContent='登录成功（会话已验证）';}
    else{$('login-status').textContent='验证结果：'+(d.state_label||d.state)+(d.error?' · '+d.error:'');}
    $('qr-close').hidden=false;$('qr-cancel').hidden=true;
    loadAccounts();
  }catch(e){}
}
function clearLoginTimers(){if(loginTimer){clearInterval(loginTimer);loginTimer=null;}if(verifyTimer){clearInterval(verifyTimer);verifyTimer=null;}}
function closeModal(){clearLoginTimers();$('login-modal').hidden=true;loginPlat=null;}
$('qr-close').onclick=closeModal;
$('qr-retry').onclick=()=>{if(loginPlat)startLogin(loginPlat,$('login-title').textContent.replace('扫码登录','')||loginPlat);};
$('qr-cancel').onclick=async()=>{
  try{await fetch('/api/login/cancel',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({platform:loginPlat})});}catch(e){}
  $('login-status').textContent='已取消登录';
  clearLoginTimers();
  setTimeout(closeModal,700);
  loadAccounts();
};
loadAccounts();
$('go').onclick=()=>search(1);
$('q').addEventListener('keydown',e=>{if(e.key==='Enter')search(1);});
$('tab-data').onclick=()=>switchView('data');
$('tab-analysis').onclick=()=>switchView('analysis');
document.querySelectorAll('input[name=dim]').forEach(r=>r.onchange=()=>{S.dim=r.value;if(S.view==='analysis')showAnalysis();});
