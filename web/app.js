/* 页面入口：组织搜索、分页、总结轮询与视图切换，不处理账号和图表细节。 */
import {$, labels, el, link, fetchTimeout, postJSON, errorText} from './dom.js';
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
  if(progressTimer){clearTimeout(progressTimer);progressTimer=null;}
}

let searchGeneration=0, requestedPage=1;
function search(){
  const kw=$('q').value.trim();if(!kw)return;
  requestedPage=1;gate.next();clearInterval(pollTimer);pollTimer=null;
  S={...S,keyword:kw,rows:[],total:0,page:1,pages:1,errors:[],expanded:[kw]};
  $('analyze-nav').hidden=true;$('more-search').hidden=true;$('more-word').value='';
  $('ai-analysis').replaceChildren();
  renderList();renderPager();switchView('data');$('meta').textContent='';
  runSearch(kw);
}

async function runSearch(kw,more=false){
  const generation=++searchGeneration;
  const start=Date.now(), button=$('more-button'), note=$('more-note');
  hideProgress();button.disabled=true;note.textContent='';
  showProgress(more?'正在寻找更多内容…':'第 1 轮 · 各平台正在搜索…');
  try{
    const path=more?'/api/search/continue':'/api/search/start';
    const body=more?{keyword:kw,related_word:$('more-word').value.trim()}:{keyword:kw,progressive:true};
    const r=await postJSON(path,body);
    if(!r.ok)throw Error(await errorText(r,'启动失败'));
    const started=await r.json();
    if(generation!==searchGeneration)return;
    if(started.status==='failed')throw Error('搜索服务暂不可用');
    if(more)$('more-word').value='';
    let last=-1;
    const finish=message=>{
      hideProgress();$('more-search').hidden=false;button.disabled=false;
      note.textContent=message||'';
    };
    async function poll(){
      if(generation!==searchGeneration)return;
      try{
        const pr=await fetchTimeout('/api/search/progress?task='+encodeURIComponent(kw),{},10000);
        if(!pr.ok)throw Error('进度暂不可用');
        const d=await pr.json();
        if(generation!==searchGeneration)return;
        if(d.status==='failed'||d.status==='idle'){
          finish(d.error||'搜索任务暂不可用，请重试。');return;
        }
        const count=d.total??d.collected??0;
        const done=d.status==='done';
        showProgress((done?'搜索完成':d.step||'搜索中')+' · 已找到 '+count+' 条 · '+Math.floor((Date.now()-start)/1000)+' 秒');
        if(done){
          try{
            if(!more||d.added)await loadPage(requestedPage,!more);
          }catch(e){
            if(generation===searchGeneration)finish('结果读取失败：'+e.message);
            return;
          }
          if(generation!==searchGeneration)return;
          finish(more?d.message:'');
          if(more&&d.added&&S.view==='analysis'&&S.dim!=='ai')showAnalysis();
          return;
        }
        if(!more&&count>0&&count!==last){await loadPage(requestedPage,true);last=count;}
      }catch(e){if(generation===searchGeneration)showProgress('进度读取失败，正在重试…');}
      if(generation===searchGeneration)progressTimer=setTimeout(poll,600);
    }
    await poll();
  }catch(e){
    if(generation===searchGeneration){
      hideProgress();button.disabled=false;
      (more?note:$('meta')).textContent='搜索失败：'+e.message;
    }
  }
}
$('more-search').onsubmit=e=>{
  e.preventDefault();
  if(S.keyword&&!$('more-button').disabled)runSearch(S.keyword,true);
};

async function loadPage(page,background=false){
  const id=gate.next(),kw=S.keyword;
  const platforms=Array.from(document.querySelectorAll('#filters input:checked'),n=>n.value);
  const r=await postJSON('/api/search',{keyword:kw,page,size:PAGE_SIZE,platforms,snapshot:true});
  if(!r.ok)throw Error(await errorText(r,'读取结果失败'));
  const d=await r.json();
  if(!gate.latest(id))return;
  // 浏览时保留已显示的卡片，只补满当前页；翻页或切筛选时按最新排序取页。
  const old=background && page===S.page ? S.rows : [];
  const seen=new Set(old.map(x=>x.platform+' '+x.url));
  S.rows=[...old,...d.rows.filter(x=>!seen.has(x.platform+' '+x.url))].slice(0,PAGE_SIZE);
  S.page=page;S.pages=d.pages;S.total=d.total;S.expanded=d.expanded;S.errors=d.errors;
  renderMeta();if(!background||old.length<PAGE_SIZE)renderList();renderPager();
  $('analyze-nav').hidden=false;
  if(!publicMode&&!pollTimer)pollTimer=setInterval(pollSummaries,2000);
}

async function pollSummaries(){
  if(!S.keyword)return;
  const id=gate.peek();                  // 轮询不产生新身份，只捕获当前身份
  const kw=S.keyword;
  try{
    const r=await fetchTimeout('/api/summaries?keyword='+encodeURIComponent(kw),{},10000);
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
  if(r.text && r.text !== r.title)a.append(el('p',r.text.slice(0,240)));
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
  requestedPage=page;
  try{await loadPage(page);}catch(e){$('meta').textContent=String(e);}
}
$('filters').onchange=()=>{if(S.keyword && (S.total || $('search-progress').hidden || $('analyze-nav').hidden===false))go(1);};

function switchView(v){S.view=v;$('tab-data').classList.toggle('active',v==='data');$('tab-analysis').classList.toggle('active',v==='analysis');$('data-view').hidden=v!=='data';$('analysis-view').hidden=v!=='analysis';if(v==='analysis')showAnalysis();}

// 显式传递状态读取方式；账号模块独立初始化。
const {showAnalysis}=createAnalysis(()=>S);
const publicMode=document.body.dataset.mode==='public';
const accounts=publicMode?null:initAccounts();
$('go').onclick=search;
$('q').addEventListener('keydown',e=>{if(e.key==='Enter')search();});
$('tab-data').onclick=()=>switchView('data');
$('tab-analysis').onclick=()=>switchView('analysis');
document.querySelectorAll('input[name=dim]').forEach(r=>r.onchange=()=>{S.dim=r.value;if(S.view==='analysis')showAnalysis();});

// 离开页面清理轮询；不将关闭页面误解为退出平台账号。
window.addEventListener('pagehide',(event)=>{
  // 页面进入后退缓存时由浏览器暂停/恢复定时器，不清理可恢复的状态。
  if(event.persisted)return;
  if(pollTimer)clearInterval(pollTimer);
  hideProgress();
  accounts?.destroy();
});
