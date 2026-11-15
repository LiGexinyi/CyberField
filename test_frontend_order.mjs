/* 前端请求身份门卫回归测试（Node，无第三方依赖）。

模拟 app.js / analysis.js / accounts.js 使用 requestGate 的乱序场景：
先搜 A、马上搜 B，B 先返回、A 后到，页面必须始终接受“最新一次有效操作”
的响应。用 Node 直接跑：node test_frontend_order.mjs
*/
import assert from 'node:assert/strict';
import { requestGate } from './web/order.mjs';

// 1) 搜索 A → 搜索 B，B 先返回，A 后到：只有 B 的响应被接受。
{
  const gate = requestGate();
  const idA = gate.next();          // 用户先搜 A
  const idB = gate.next();          // 马上搜 B
  assert.equal(gate.latest(idA), false, '旧搜索 A 的响应应被丢弃');
  assert.equal(gate.latest(idB), true, '最新搜索 B 的响应应被接受');
}

// 2) 轮询用 peek()：不产生新身份；换词后旧轮询失效。
{
  const gate = requestGate();
  const idA = gate.next();          // 搜索 A
  const pollA = gate.peek();        // A 期间的总结轮询捕获
  assert.equal(gate.latest(pollA), true, '无新操作时轮询身份仍有效');
  gate.next();                      // 用户换了词 B
  assert.equal(gate.latest(pollA), false, '换词后旧轮询响应应被丢弃');
  assert.equal(gate.latest(idA), false, '换词后旧搜索响应应被丢弃');
}

// 3) 翻页是新操作：作废在途搜索与旧轮询。
{
  const gate = requestGate();
  const idSearch = gate.next();
  const poll = gate.peek();
  const idPage = gate.next();       // 点击翻页
  assert.equal(gate.latest(idSearch), false, '翻页应作废在途搜索');
  assert.equal(gate.latest(poll), false, '翻页应作废旧轮询');
  assert.equal(gate.latest(idPage), true, '翻页本身是最新操作');
}

// 4) 账号登录弹窗：取消/换平台后旧平台的轮询响应不得生效。
{
  const gate = requestGate();
  gate.next();                      // 打开小红书登录
  const pollXhs = gate.peek();
  gate.next();                      // 取消并打开知乎登录
  const pollZhihu = gate.peek();
  assert.equal(gate.latest(pollXhs), false, '旧平台轮询应被作废');
  assert.equal(gate.latest(pollZhihu), true, '当前平台轮询有效');
}

console.log('PASS: requestGate 乱序守卫（4 组场景）');
