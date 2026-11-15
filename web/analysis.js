/* 分析视图：读取搜索状态，通过原接口获取并展示样本统计。 */
import {$, el} from './dom.js';
import {requestGate} from './order.mjs';

/** 注入状态读取函数，避免图表模块依赖搜索模块的全局变量。 */
export function createAnalysis(getState){
const dimTitle={timeline:'时间热度',topics:'高频短语',groups:'平台与作者'};
const gate=requestGate();   // 统计请求身份：换词/切维度后旧统计响应不得覆盖
async function showAnalysis(){
  const S=getState();
  if(!S.keyword){$('chart-title').textContent='请先搜索一个词。';return;}
  const id=gate.next();                  // 每次请求统计都登记身份
  const kw=S.keyword;
  $('chart-title').textContent=dimTitle[S.dim]+' · 「'+kw+'」';
  const chart=$('chart');chart.replaceChildren(el('p','统计中…','empty'));
  try{
    const r=await fetch('/api/analysis?keyword='+encodeURIComponent(kw));
    const d=await r.json();
    const now=getState();
    if(!gate.latest(id)||kw!==now.keyword)return;   // 已换词：丢弃旧统计
    chart.replaceChildren();
    if(now.dim==='timeline')renderTimeline(chart,d.timeline);
    else if(now.dim==='topics')renderTopics(chart,d.topics);
    else renderGroups(chart,d.groups);
  }catch(e){const now=getState();if(gate.latest(id)&&kw===now.keyword)chart.replaceChildren(el('p','分析失败：'+e,'empty'));}
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

  return {showAnalysis};
}
