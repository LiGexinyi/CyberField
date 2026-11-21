/* dom.js 工具函数测试：最小 DOM stub，无第三方依赖。
   运行方式：node --test test_frontend_dom.mjs */
import test from 'node:test';
import assert from 'node:assert/strict';

/* ---- 最小 DOM stub：只实现 dom.js 实际用到的成员 ---- */
function makeEl(tag){
  return {
    tag, textContent:'', className:'', children:[],
    append(...kids){this.children.push(...kids);},
    replaceChildren(...kids){this.children=[...kids];},
    removeAttribute(name){delete this[name];},
  };
}
globalThis.document={createElement:tag=>makeEl(tag)};

const {el,link,fetchTimeout,postJSON,errorText}=await import('./web/dom.js');

test('el 设置文本与类名；空值不覆盖',()=>{
  const a=el('div','你好','box');
  assert.equal(a.tag,'div');
  assert.equal(a.textContent,'你好');
  assert.equal(a.className,'box');
  const b=el('span');
  assert.equal(b.textContent,'');
  assert.equal(b.className,'');
});

test('link 放行 http/https 并加安全属性',()=>{
  const a=link({url:'https://example.com/x?y=1'});
  assert.equal(a.href,'https://example.com/x?y=1');
  assert.equal(a.target,'_blank');
  assert.equal(a.rel,'noopener noreferrer');
  const b=link({url:'http://example.com'});
  assert.equal(b.href,'http://example.com/');
});

test('link 拦截 javascript:/data:/非法链接，防止注入',()=>{
  for(const bad of ['javascript:alert(1)','data:text/html,<b>x</b>','not a url','ftp://h/x']){
    const a=link({url:bad});
    assert.equal(a.href,undefined,`不应设置 href：${bad}`);
    assert.equal(a.textContent,'来源不可用');
  }
});

test('fetchTimeout 透传 init 并附加超时信号',async()=>{
  const seen={};
  const oldFetch=globalThis.fetch;
  globalThis.fetch=async(url,init)=>{seen.url=url;seen.init=init;return {ok:true,status:200,json:async()=>({})};};
  try{
    await fetchTimeout('/api/x',{method:'GET'},1234);
    assert.equal(seen.url,'/api/x');
    assert.equal(seen.init.method,'GET');
    assert.ok(seen.init.signal instanceof AbortSignal);
    assert.equal(seen.init.signal.aborted,false);
  }finally{globalThis.fetch=oldFetch;}
});

test('postJSON 统一 POST/JSON 请求头/序列化/超时',async()=>{
  const seen={};
  const oldFetch=globalThis.fetch;
  globalThis.fetch=async(url,init)=>{seen.url=url;seen.init=init;return {ok:true,status:200,json:async()=>({ok:true})};};
  try{
    const r=await postJSON('/api/x',{a:1});
    assert.equal(r.ok,true);
    assert.equal(seen.init.method,'POST');
    assert.equal(seen.init.headers['Content-Type'],'application/json');
    assert.equal(seen.init.body,JSON.stringify({a:1}));
    assert.ok(seen.init.signal instanceof AbortSignal);
  }finally{globalThis.fetch=oldFetch;}
});

test('errorText 优先读服务端 error，解析失败回退 HTTP 状态',async()=>{
  const withError=await errorText({status:500,json:async()=>({error:'服务器内部错误'})});
  assert.equal(withError,'服务器内部错误');
  const fallback=await errorText({status:404,json:async()=>{throw new Error('not json');}});
  assert.equal(fallback,'请求失败（HTTP 404）');
});
