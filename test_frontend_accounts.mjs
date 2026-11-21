/* accounts.js 纯逻辑测试：账号状态 → 可用操作矩阵。
   运行方式：node --test test_frontend_accounts.mjs */
import test from 'node:test';
import assert from 'node:assert/strict';

import {actionsFor} from './web/accounts.js';

/* 状态机 7 态全覆盖：每种状态必须给出符合预期的按钮组合。 */
const CASES=[
  ['no_profile',   ['login']],
  ['pending',      ['verify','login']],
  ['verifying',    []],                       // 验证中面板只显示提示，无按钮
  ['logged_in',    ['verify','login','logout']],
  ['expired',      ['login','verify','logout']],
  ['login_failed', ['login']],
  ['unknown',      ['verify','login','logout']],
];

for(const [state,expected] of CASES){
  test(`actionsFor 状态矩阵：${state} → ${expected.join('/')||'（无操作）'}`,()=>{
    const acts=actionsFor({state});
    assert.deepEqual(acts.map(a=>a.k),expected);
    for(const a of acts){
      assert.equal(typeof a.lbl,'string');
      assert.ok(a.lbl.length>0,'每个操作必须有可见文案');
    }
  });
}

test('actionsFor 未知状态返回空，不抛错',()=>{
  assert.deepEqual(actionsFor({state:'future_state'}),[]);
  assert.deepEqual(actionsFor({}),[]);
});
