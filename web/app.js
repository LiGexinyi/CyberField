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

/* ---- 平台账号登录 ---- */
const platLabels={xhs:'小红书',zhihu:'知乎',bili:'B站',wb:'微博'};
let loginTimer=null,loginPlat=null;
async function loadAccounts(){
  try{
    const r=await fetch('/api/accounts');
    const d=await r.json();
    const box=$('accounts');box.replaceChildren();
    (d.accounts||[]).forEach(a=>box.append(acctRow(a)));
  }catch(e){}
}
function acctRow(a){
  const row=el('div',undefined,'acct'+(a.logged_in?' on':''));
  row.append(el('span',undefined,'dot'),el('span',a.label,'aname'));
  if(a.logged_in){row.append(el('span','已登录','tag'));}
  else{const b=el('button','登录');b.onclick=()=>startLogin(a.platform,a.label);row.append(b);}
  return row;
}
async function startLogin(platform,label){
  loginPlat=platform;
  $('login-title').textContent='扫码登录'+label;
  $('qr-holder').replaceChildren(el('p','正在启动登录…','empty'));
  $('login-status').textContent='';
  $('qr-retry').hidden=true;
  $('login-modal').hidden=false;
  try{await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({platform})});}
  catch(e){$('login-status').textContent='启动失败：'+e;return;}
  if(loginTimer)clearInterval(loginTimer);
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
    const msgs={starting:'正在启动登录…',qr_ready:'请用手机 App 扫码，等待确认',logged_in:'登录成功，可关闭此窗口',expired:'二维码已过期',failed:'登录失败',idle:'未开始'};
    $('login-status').textContent=(msgs[d.status]||d.status)+(d.error?' · '+d.error:'');
    if(d.status==='logged_in'){clearInterval(loginTimer);loginTimer=null;loadAccounts();setTimeout(closeModal,1200);}
    else if(d.status==='expired'||d.status==='failed'){$('qr-retry').hidden=false;clearInterval(loginTimer);loginTimer=null;}
  }catch(e){}
}
function closeModal(){if(loginTimer){clearInterval(loginTimer);loginTimer=null;}$('login-modal').hidden=true;}
$('qr-close').onclick=closeModal;
$('qr-retry').onclick=()=>{if(loginPlat)startLogin(loginPlat,platLabels[loginPlat]||loginPlat);};
loadAccounts();
$('go').onclick=()=>search(1);
$('q').addEventListener('keydown',e=>{if(e.key==='Enter')search(1);});
$('tab-data').onclick=()=>switchView('data');
$('tab-analysis').onclick=()=>switchView('analysis');
document.querySelectorAll('input[name=dim]').forEach(r=>r.onchange=()=>{S.dim=r.value;if(S.view==='analysis')showAnalysis();});
