/* 共享DOM工具：安全输出文本、创建元素与限制原文链接协议。 */
export const $=id=>document.getElementById(id);
export const labels={bilibili:'B站',weibo:'微博',douban:'豆瓣',xiaohongshu:'小红书',douyin:'抖音',zhihu:'知乎'};
export function el(tag,text,cls){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;}
export function link(row){const a=el('a','查看原文 ↗','');try{const u=new URL(row.url);if(!['http:','https:'].includes(u.protocol))throw Error();a.href=u.href;a.target='_blank';a.rel='noopener noreferrer';}catch{a.removeAttribute('href');a.textContent='来源不可用';}return a;}
/** 带超时的 fetch：超时/网络异常会抛出，由调用方决定提示或静默重试。 */
export function fetchTimeout(url,init={},timeout=10000){
  const signal=init.signal??AbortSignal.timeout(timeout);
  return fetch(url,{...init,signal});
}
