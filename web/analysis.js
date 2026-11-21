/* 分析视图：读取搜索状态，通过原接口获取并展示样本统计。 */
import {$, el} from './dom.js';
import {requestGate} from './order.mjs';

/** 注入状态读取函数，避免图表模块依赖搜索模块的全局变量。 */
export function createAnalysis(getState){
const dimTitle={timeline:'时间热度',topics:'共现话题',ai:'AI 分析'};
const gate=requestGate();   // 统计请求身份：换词/切维度后旧统计响应不得覆盖
let cleanup=()=>{}, aiKeyword='';
async function showAnalysis(){
  cleanup();
  const S=getState();
  const chart=$('chart'), ai=$('ai-analysis');
  if(aiKeyword!==S.keyword){ai.replaceChildren();aiKeyword='';}
  chart.hidden=S.dim==='ai';
  ai.hidden=S.dim!=='ai';
  if(!S.keyword){$('chart-title').textContent='请先搜索一个词。';return;}
  const id=gate.next();                  // 每次请求统计都登记身份
  const kw=S.keyword;
  $('chart-title').textContent=dimTitle[S.dim]+' · 「'+kw+'」';
  if(S.dim==='ai'){
    if(!ai.firstChild){aiKeyword=kw;renderAi(ai,kw);}
    return;
  }
  chart.replaceChildren(el('p','统计中…','empty'));
  try{
    const r=await fetch('/api/analysis?keyword='+encodeURIComponent(kw)+(S.dim==='topics'?'&text=1':''));
    const d=await r.json();
    const now=getState();
    if(!gate.latest(id)||kw!==now.keyword)return;   // 已换词：丢弃旧统计
    chart.replaceChildren();
    if(d.error){chart.append(el('p',d.error));return;}
    chart.append(el('p',`${document.body.dataset.mode==='public'?'当前搜索':'当前搜索及本地库'}去重后共 ${d.total} 篇帖子，其中 ${d.dated} 篇有日期，${d.tagged} 篇带其他话题标签。`));
    if(now.dim==='timeline')renderTimeline(chart,d.timeline);
    else if(now.dim==='topics')renderTopics(chart,d,kw);

  }catch(e){const now=getState();if(gate.latest(id)&&kw===now.keyword)chart.replaceChildren(el('p','分析失败：'+e,'empty'));}
}
function renderTimeline(chart,data){
  if(!data||!data.length){chart.append(el('p','暂无发布时间的样本。','empty'));return;}
  const counts=new Map(data), first=data[0][0], last=data.at(-1)[0];
  const controls=el('div',undefined,'time-controls');
  function dateBox(name,value){
    const label=el('label',name),input=el('input');input.type='date';
    input.min=first;input.max=last;input.value=value;label.append(input);controls.append(label);return input;
  }
  const from=dateBox('起始日期',first),to=dateBox('结束日期',last),reset=el('button','全部日期');
  controls.append(reset);
  const canvas=el('canvas');canvas.style.cssText='width:100%;height:245px;display:block';
  const note=el('p',undefined,'meta-line');chart.append(controls,canvas,note);
  function draw(){
    const w=canvas.clientWidth||500,h=245,ratio=window.devicePixelRatio||1;
    canvas.width=w*ratio;canvas.height=h*ratio;
    const ctx=canvas.getContext('2d');ctx.scale(ratio,ratio);
    const lo=Date.parse(from.value),hi=Date.parse(to.value),day=86400000;
    if(!Number.isFinite(lo+hi)||hi<lo){note.textContent='请选择有效范围，结束日期应晚于或等于起始日期。';return;}
    const span=Math.round((hi-lo)/day)+1, step=Math.max(1,Math.ceil(span/Math.max(1,Math.floor(w/4))));
    const bins=new Array(Math.ceil(span/step)).fill(0);
    for(const [d,n] of counts){const t=Date.parse(d);if(t>=lo&&t<=hi)bins[Math.floor((t-lo)/day/step)]+=n;}
    const peak=Math.max(1,...bins),left=44,right=w-42,base=202;
    ctx.font='12px sans-serif';
    for(const n of new Set([0,Math.round(peak/2),peak])){
      const y=base-n/peak*175;ctx.strokeStyle='#ddd';ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(right,y);ctx.stroke();
      ctx.fillStyle='#444';ctx.textAlign='right';ctx.fillText(n,left-6,y+4);
    }
    const x=i=>left+(bins.length===1?.5:i/(bins.length-1))*(right-left);
    ctx.strokeStyle='#16736c';ctx.lineWidth=2;ctx.beginPath();
    bins.forEach((n,i)=>{const y=base-175*n/peak;if(i)ctx.lineTo(x(i),y);else ctx.moveTo(x(i),y);});ctx.stroke();
    if(bins.length===1){ctx.fillStyle='#16736c';ctx.beginPath();ctx.arc(x(0),base-175*bins[0]/peak,3,0,7);ctx.fill();}
    const ticks=Math.min(bins.length,Math.max(2,Math.floor((right-left)/105)+1));ctx.textAlign='center';ctx.fillStyle='#444';
    for(let j=0;j<ticks;j++){const i=ticks===1?0:Math.round(j*(bins.length-1)/(ticks-1));ctx.fillText(new Date(lo+i*step*day).toISOString().slice(0,10),x(i),225);}
    note.textContent=`所选时段共 ${bins.reduce((a,b)=>a+b,0)} 篇 · 每点 ${step} 天 · 纵轴为样本发帖数`;canvas.setAttribute('aria-label',note.textContent);
  }
  from.oninput=to.oninput=draw;reset.onclick=()=>{from.value=first;to.value=last;draw();};
  draw();const observer=new ResizeObserver(draw);observer.observe(canvas);cleanup=()=>observer.disconnect();
}
function renderTopics(chart,d,kw){
  const stop=new Set('这个 那个 一个 一种 还有 以及 他们 我们 自己 什么 怎么 可以 已经 就是 觉得 还是 因为 所以 如果 但是 这里 这些 那些 非常 可能 时候 进行 视频 小红书 微博 豆瓣'.split(' '));
  const counts=new Map(), platforms=new Set(), segmenter=new Intl.Segmenter('zh',{granularity:'word'});
  for(const doc of d.documents||[]){
    platforms.add(doc.platform);
    const words=new Set();
    for(const item of segmenter.segment(doc.text.replace(/#[\w\p{L}·-]+#?/gu,' '))){
      const w=item.segment.toLowerCase();
      if(item.isWordLike&&w.length>=2&&w!==kw.toLowerCase()&&!stop.has(w)&&!/^[0-9]+$/.test(w))words.add(w);
    }
    for(const w of words)counts.set(w,(counts.get(w)||0)+1);
  }
  const terms=[...counts].filter(x=>x[1]>=2).sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0])).slice(0,30).map(([word,count])=>({word,count}));
  function list(title,rows){
    chart.append(el('h3',title));const box=el('div',undefined,'term-list');
    rows.forEach(t=>box.append(el('span',t.word+' · '+t.count+' 篇')));chart.append(rows.length?box:el('p','暂无符合条件的词。'));
  }
  list('帖子话题标签',d.topics);list('标题与正文共现词',terms);
  chart.append(el('p',`正文统计覆盖 ${d.documents.length} 条资料（含豆瓣条目简介）。同一词每条只计一次，至少出现在两条资料中。`,'meta-line'));
}
function renderAi(chart,kw){
  const form=el('form',undefined,'ai-settings'),provider=el('select'),model=el('input'),key=el('input'),submit=el('button','搜索并解读这个梗'),answer=el('p'),works=el('section');
  chart.append(form,answer,works);
  for(const name of ['DeepSeek','OpenAI','SiliconFlow'])provider.add(new Option(name,name));
  key.type='password';key.autocomplete='off';key.required=model.required=true;model.placeholder='填写服务商提供的模型名';
  for(const [name,input] of [['服务商',provider],['模型',model],['API Key',key]]){const label=el('label',name);label.append(input);form.append(label);}
  form.append(el('small','点击后检索公开 B 站作品，将搜索词、作品标题、简介片段和互动统计发送给所选模型服务。'),submit);
  form.onsubmit=async e=>{
    e.preventDefault();submit.disabled=true;answer.textContent='正在查找作品、读取互动数据并生成解读…';works.replaceChildren();
    try{
      const res=await fetch('/api/topic-interpretation',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({provider:provider.value,model:model.value,key:key.value,keyword:kw})});
      const result=await res.json();answer.textContent=res.ok?result.text:result.error;
      if(res.ok){
        works.append(el('h3','推荐作品 · '+result.mode));
        const list=el('ol');
        for(const item of result.sources){
          const row=el('li'),a=el('a',item.title);
          a.href=item.url;a.target='_blank';a.rel='noopener noreferrer';
          const metrics=Object.entries(item.metrics).map(([k,v])=>k+' '+v).join(' · ');
          row.append(a,el('p',metrics||'暂无互动数据','meta-line'));list.append(row);
        }
        works.append(list);
      }
    }catch{answer.textContent='请求失败，请检查本地服务。';}finally{submit.disabled=false;}
  };
}
  return {showAnalysis};
}
