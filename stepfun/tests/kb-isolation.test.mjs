/**
 * kb-isolation.test.mjs — 知识库切换与会话状态验证
 * 验证：跨知识库数据隔离、增量导入、索引刷新后可检索、会话状态正确。
 */
import { writeFileSync, mkdirSync } from 'node:fs';
const BASE = 'http://127.0.0.1:8787';
const OUT = './evidence/kb-isolation.log';
mkdirSync('./evidence', { recursive: true });
let lines = [];
const log = (...a) => { const s = a.join(' '); lines.push(s); console.log(s); };
let pass = 0, fail = 0;
const check = (n, c, d) => { if (c) { pass++; log('PASS ' + n); } else { fail++; log('FAIL ' + n + ' :: ' + JSON.stringify(d)); } };
const vec = s => { const v = new Array(384).fill(0); v[s % 384] = 1; return v; };
async function req(m, u, b) {
  const r = await fetch(BASE + u, { method: m, headers: { 'Content-Type': 'application/json' }, body: b ? JSON.stringify(b) : undefined });
  return { status: r.status, json: await r.json() };
}

async function main() {
  // 独立测试用 kb，避免与 benchmark 数据混淆
  const A = 'iso_test_a', B = 'iso_test_b';
  await req('DELETE', `/api/kb/${A}`);
  await req('DELETE', `/api/kb/${B}`);

  // 向 A 导入 2 条，向 B 导入 1 条
  let r = await req('POST', `/api/kb/${A}/add`, { docs: [
    { id: 'x1', text: 'alpha only document about database indexes', embedding: vec(1), metadata: { source: 'a.txt' } },
    { id: 'x2', text: 'alpha second document about vector search', embedding: vec(2), metadata: { source: 'a2.txt' } },
  ]});
  check('导入知识库A(2条)', r.json.count === 2, r.json);
  r = await req('POST', `/api/kb/${B}/add`, { docs: [
    { id: 'y1', text: 'beta only document about cooking recipes', embedding: vec(100), metadata: { source: 'b.txt' } },
  ]});
  check('导入知识库B(1条)', r.json.count === 1, r.json);
  await req('POST', `/api/kb/${A}/refresh`, {});
  await req('POST', `/api/kb/${B}/refresh`, {});

  // 计数隔离
  r = await req('GET', `/api/kb/${A}/count`);
  check('切换后A文档数=2', r.json.count === 2, r.json);
  r = await req('GET', `/api/kb/${B}/count`);
  check('切换后B文档数=1', r.json.count === 1, r.json);

  // 混合检索隔离：在 B 中检索不得出现 A 的文档
  r = await req('POST', `/api/kb/${B}/search`, { keyword: 'database', embedding: vec(1), nResults: 20, mode: 'hybrid' });
  const bIds = (r.json.hits || []).map(h => String(h.id));
  check('B检索不串A数据', bIds.every(id => id.startsWith('iso_test_b::')), bIds);
  check('B检索结果kb均为beta', (r.json.hits || []).every(h => h.metadata?.kb === B), r.json.hits);

  // 在 A 中检索不得出现 B 的文档
  r = await req('POST', `/api/kb/${A}/search`, { keyword: 'cooking', embedding: vec(100), nResults: 20, mode: 'hybrid' });
  const aIds = (r.json.hits || []).map(h => String(h.id));
  check('A检索不串B数据', aIds.every(id => id.startsWith('iso_test_a::')), aIds);

  // 增量导入后再检索：新文档可被检索到（索引刷新后）
  r = await req('POST', `/api/kb/${B}/add`, { docs: [
    { id: 'y2', text: 'beta incremental document about gardening plants', embedding: vec(101), metadata: { source: 'b2.txt' } },
  ]});
  check('B增量导入(+1)', r.json.count === 1, r.json);
  await req('POST', `/api/kb/${B}/refresh`, {});
  r = await req('GET', `/api/kb/${B}/count`);
  check('增量后B文档数=2', r.json.count === 2, r.json);
  r = await req('POST', `/api/kb/${B}/search`, { keyword: 'gardening', embedding: vec(101), nResults: 10, mode: 'hybrid' });
  const hasNew = (r.json.hits || []).some(h => String(h.id).includes('y2'));
  check('索引刷新后新文档可检索', hasNew, r.json.hits?.map(h => h.id));

  // 会话状态：切回 A，文档仍为 2（不受 B 增量影响）
  r = await req('GET', `/api/kb/${A}/count`);
  check('切回A状态正确(=2)', r.json.count === 2, r.json);

  log(`\nSUMMARY pass=${pass} fail=${fail}`);
  writeFileSync(OUT, lines.join('\n') + '\n');
  process.exit(fail === 0 ? 0 : 1);
}
main().catch(e => { log('ERROR ' + (e.stack || e)); writeFileSync(OUT, lines.join('\n') + '\n'); process.exit(2); });
