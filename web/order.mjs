/* 请求身份门卫：防止晚到的旧响应覆盖用户最新的操作结果。

用法（搜索/翻页等“启动新操作”的请求）：
    const id = gate.next();              // 本次操作唯一身份
    const r = await fetch(...);
    if (!gate.latest(id)) return;        // 已有更新的操作，丢弃旧响应

用法（轮询类请求，它们不应产生新身份）：
    const id = gate.peek();              // 捕获当前身份，不推进
    const kw = S.keyword;
    const r = await fetch(...);
    if (!gate.latest(id) || kw !== S.keyword) return;   // 已换词/换页则丢弃
*/
export function requestGate() {
  let current = 0;
  return {
    /** 开始一次新操作：使所有在途旧请求失效，返回新身份。 */
    next() { current += 1; return current; },
    /** 读取当前身份而不推进（轮询使用）。 */
    peek() { return current; },
    /** 响应返回后校验：只有身份仍等于最新时才算有效。 */
    latest(id) { return id === current; },
  };
}
