/* 页面入口：组织搜索、分页、总结轮询与视图切换，不处理账号和图表细节。 */
import {$, labels, el, link} from './dom.js';
import {createAnalysis} from './analysis.js';
import {initAccounts} from './accounts.js';
import {requestGate} from './order.mjs';

let S={keyword:'',rows:[],total:0,page:1,pages:1,expanded:[],errors:[],view:'data',dim:'timeline'};
let pollTimer=null,progressTimer=null;
const gate=requestGate();   // 请求身份：搜索/翻页/轮询共享，防止旧响应串结果
const PAGE_SIZE=20;         // 与后端 settings.DEFAULT_PAGE_SIZE 保持一致

function showProgress(text){
  $('search-progress').hidden=false;
  $('search-progress-text').textContent=text;
}
function hideProgress(){
  $('search-progress').hidden=true;
  if(progressTimer){clearInterval(progressTimer);progressTimer=null;}
}

async function search(page=1){
  const id=gate.next();                  // 本次搜索身份：晚到的旧搜索响应将被丢弃
  const kw=$('q').value.trim();if(!kw)return;
  $('meta').textContent='';$('list').replaceChildren();$('pager').replaceChildren();
  hideProgress();
  let page1Shown=false;                  // 主词完成时先渲染一次第 1 页
  try{
    // 先启动/复用搜索任务：done 直接取结果，running 轮询真实进度。
    const r=await fetch('/api/search/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({keyword:kw,page,size:PAGE_SIZE})});
    if(!r.ok)throw Error('接口 '+r.status);
    const d=await r.json();
    if(!gate.latest(id))return;          // 旧请求晚到：不覆盖更新的结果
    if(!d.ok)throw Error(d.error||'搜索任务启动失败');
    if(d.status==='done'){await fetchPage(id,kw,page);return;}
    const t0=Date.now();
    showProgress('正在搜索「'+kw+'」，准备任务…');
    progressTimer=setInterval(async()=>{
      try{
        const pr=await fetch('/api/search/progress?task='+encodeURIComponent(kw));
        const pd=await pr.json();
        if(!gate.latest(id)){hideProgress();return;}
        if(pd.status==='done'){hideProgress();await fetchPage(id,kw,page);return;}
        if(pd.status==='failed'){hideProgress();if(gate.latest(id))$('meta').textContent='搜索失败：'+(pd.error||'未知错误');return;}
        // 主词完成：已找到够一页的量就先渲染第 1 页，扩展词在后台继续补。
        if(!page1Shown&&typeof pd.collected==='number'&&pd.collected>=PAGE_SIZE){
          page1Shown=true;
          await fetchPage(id,kw,page);
        }
        if(Date.now()-t0>180000){hideProgress();if(gate.latest(id))$('meta').textContent='搜索超时，请重试';return;}
        let text=(pd.step||'正在搜索…');
        if(typeof pd.collected==='number'&&pd.collected>0)text+=' · 已找到 '+pd.collected+' 条';
        text+=' · '+Math.round((Date.now()-t0)/1000)+'s';
        showProgress(text);
      }catch(e){}
    },700);
  }catch(e){if(gate.latest(id))$('meta').textContent='搜索失败：'+e;}
}

async function fetchPage(id,kw,page){
  try{
    const r=await fetch('/api/search',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({keyword:kw,page,size:PAGE_SIZE})});
    if(!r.ok)throw Error('接口 '+r.status);
    const d=await r.json();
    if(!gate.latest(id))return;          // 旧请求晚到：不覆盖更新的结果
    S={keyword:d.keyword||kw,rows:d.rows||[],total:d.total||0,page:d.page||1,pages:d.pages||1,expanded:d.expanded||[kw],errors:d.errors||[],view:S.view,dim:S.dim};
  }catch(e){if(gate.latest(id))$('meta').textContent='搜索失败：'+e;return;}
  renderMeta();renderList();renderPager();
  $('analyze-nav').hidden=false;
  switchView('data');
  if(pollTimer)clearInterval(pollTimer);
  pollTimer=setInterval(pollSummaries,2000);
}

async function pollSummaries(){
  if(!S.keyword)return;
  const id=gate.peek();                  // 轮询不产生新身份，只捕获当前身份
  const kw=S.keyword;
  try{
    const r=await fetch('/api/summaries?keyword='+encodeURIComponent(kw));
    const d=await r.json();
    if(!gate.latest(id)||kw!==S.keyword)return;   // 已换词/换页：丢弃旧轮询响应
    const states={};
    (d.states||[]).forEach(s=>states[s.url]=s);
    let changed=false;
    S.rows.forEach(row=>{
      const st=states[row.url];
      if(st&&(row.summary_status!==st.status||(st.done&&!row._done))){row._done=!!st.done;row.summary=st.summary;row.comments=st.comments;row.summary_status=st.status;row.summary_error=st.error;changed=true;}
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
  else{const messages={idle:'等待总结任务',queued:'总结排队中…',running:'总结生成中…',skipped:'未配置 AI 总结',failed:'总结失败，可查看原文',cancelled:'总结任务已取消',completed:'暂无总结内容'};const note=el('div',messages[r.summary_status]||(r._done?'暂无总结内容':'总结生成中…'),'summary placeholder');if(r.summary_error)note.title=r.summary_error;a.append(note);}
  if(r.comments&&r.comments.length){const c=el('div',undefined,'comments');r.comments.forEach(cm=>c.append(el('span','▸ '+cm)));a.append(c);}
  const foot=el('div',undefined,'row-foot');foot.append(link(r));
  const e=r.extra||{},bits=[];
  if(e.play)bits.push('播放 '+e.play);
  if(e.liked||e.voteup)bits.push('赞 '+(e.liked||e.voteup));
  if(e.attitudes_count)bits.push('赞 '+e.attitudes_count);
  if(e.comment||e.reply||e.comments_count)bits.push('评论 '+(e.comment||e.reply||e.comments_count));
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
  const id=gate.next();                  // 翻页也是新操作：作废在途搜索/轮询
  hideProgress();
  $('list').replaceChildren();$('meta').textContent='加载第 '+page+' 页…';
  try{
    const r=await fetch('/api/search',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({keyword:S.keyword,page})});
    const d=await r.json();
    if(!gate.latest(id))return;          // 旧翻页晚到：丢弃
    S.rows=d.rows||[];S.page=d.page||1;S.pages=d.pages||1;S.expanded=d.expanded||S.expanded;
  }catch(e){if(gate.latest(id))$('meta').textContent='翻页失败：'+e;return;}
  renderMeta();renderList();renderPager();
}

function switchView(v){S.view=v;$('tab-data').classList.toggle('active',v==='data');$('tab-analysis').classList.toggle('active',v==='analysis');$('data-view').hidden=v!=='data';$('analysis-view').hidden=v!=='analysis';if(v==='analysis')showAnalysis();}

// 显式传递状态读取方式；账号模块独立初始化。
const {showAnalysis}=createAnalysis(()=>S);
const accounts=initAccounts();
$('go').onclick=()=>search(1);
$('q').addEventListener('keydown',e=>{if(e.key==='Enter')search(1);});
$('tab-data').onclick=()=>switchView('data');
$('tab-analysis').onclick=()=>switchView('analysis');
document.querySelectorAll('input[name=dim]').forEach(r=>r.onchange=()=>{S.dim=r.value;if(S.view==='analysis')showAnalysis();});

// 离开页面清理轮询；不将关闭页面误解为退出平台账号。
window.addEventListener('pagehide',(event)=>{
  // 页面进入后退缓存时由浏览器暂停/恢复定时器，不清理可恢复的状态。
  if(event.persisted)return;
  if(pollTimer)clearInterval(pollTimer);
  hideProgress();
  accounts.destroy();
});
