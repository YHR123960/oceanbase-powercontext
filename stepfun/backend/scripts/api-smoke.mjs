/**
 * api-smoke.mjs — 通过 HTTP 对运行中的 API 服务做端到端冒烟测试。
 * 验证：写入 / 增量导入 / 索引刷新 / 数据库端混合检索 / 知识库隔离。
 * 向量在【本测试脚本】中构造（模拟浏览器输出），Node 服务端不生成向量。
 */
import { writeFileSync } from 'node:fs';

const BASE = 'http://127.0.0.1:8787';
const OUT = './evidence/api-smoke.log';
let lines = [];
const log = (...a) => { const s = a.join(' '); lines.push(s); console.log(s); };

function makeVec(seed) {
  const v = new Array(384).fill(0);
  for (let i = 0; i < 384; i++) v[i] = Math.sin((i + 1) * seed) * 0.01;
  v[seed % 384] = 1.0;
  return v;
}
async function req(method, url, body) {
  const r = await fetch(BASE + url, {
    method, headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  return { status: r.status, json: await r.json() };
}
let pass = 0, fail = 0;
function check(name, cond, detail) {
  if (cond) { pass++; log('PASS ' + name); }
  else { fail++; log('FAIL ' + name + ' :: ' + JSON.stringify(detail)); }
}

async function main() {
  let r = await req('GET', '/api/health');
  check('health', r.status === 200 && r.json.ready, r);

  await req('DELETE', '/api/kb/alpha');
  await req('DELETE', '/api/kb/beta');

  r = await req('POST', '/api/kb/alpha/add', { docs: [
    { id: 'a1', text: 'seekdb is a fast vector database with hybrid search', embedding: makeVec(1), metadata: { source: 'a1.txt' } },
    { id: 'a2', text: 'OceanBase provides distributed SQL and a storage engine', embedding: makeVec(2), metadata: { source: 'a2.txt' } },
  ]});
  check('initial import alpha (2 docs)', r.status === 200 && r.json.count === 2, r);
  log('WRITE_MS ' + r.json.writeMs);

  r = await req('POST', '/api/kb/alpha/add', { docs: [
    { id: 'a3', text: 'browser local embedding accelerated by WebGPU', embedding: makeVec(3), metadata: { source: 'a3.txt' } },
  ]});
  check('incremental import alpha (+1)', r.status === 200 && r.json.count === 1, r);

  r = await req('POST', '/api/kb/beta/add', { docs: [
    { id: 'b1', text: 'totally different content about baking bread recipes', embedding: makeVec(50), metadata: { source: 'b1.txt' } },
  ]});
  check('import beta (isolation setup)', r.status === 200 && r.json.count === 1, r);

  r = await req('POST', '/api/kb/alpha/refresh', {});
  check('index refresh', r.status === 200 && r.json.ok, r);
  log('REFRESH_MS ' + r.json.refreshMs);

  r = await req('GET', '/api/kb/alpha/count');
  check('alpha count=3', r.status === 200 && r.json.count === 3, r);
  r = await req('GET', '/api/kb/beta/count');
  check('beta count=1', r.status === 200 && r.json.count === 1, r);

  r = await req('POST', '/api/kb/alpha/search', { keyword: 'vector', embedding: makeVec(1), nResults: 5, mode: 'hybrid' });
  check('hybrid search by seekdb', r.status === 200 && r.json.engine === 'seekdb::DBMS_HYBRID_SEARCH' && r.json.hits.length > 0, r);
  log('HYBRID_ALPHA ' + JSON.stringify(r.json.hits.map(h => ({ id: h.id, kb: h.metadata?.kb, d: h.distance }))));
  log('SEARCH_MS ' + r.json.searchMs);

  r = await req('POST', '/api/kb/beta/search', { keyword: 'vector', embedding: makeVec(1), nResults: 5, mode: 'hybrid' });
  const ids = (r.json.hits || []).map(h => String(h.id));
  check('kb isolation (beta has no alpha docs)', ids.every(id => id.startsWith('beta::')), ids);
  log('HYBRID_BETA ' + JSON.stringify(ids));

  r = await req('POST', '/api/kb/alpha/search', { embedding: makeVec(3), nResults: 3, mode: 'vector' });
  check('vector-only search', r.status === 200 && r.json.hits.length > 0, r);

  log(`\nSUMMARY pass=${pass} fail=${fail}`);
  writeFileSync(OUT, lines.join('\n') + '\n');
  process.exit(fail === 0 ? 0 : 1);
}
main().catch(e => { log('ERROR ' + (e.stack || e)); writeFileSync(OUT, lines.join('\n') + '\n'); process.exit(2); });
