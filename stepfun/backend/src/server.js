/**
 * server.js — 本地 Node.js API 服务（单进程，已验证可工作模式）
 *
 * 实测结论（2026-11-18）：
 *  - seekdb Embedded 原生 addon 若用【静态 import】在模块加载阶段载入，
 *    会导致 Express 的 HTTP 请求无响应（事件循环异常）。
 *  - 改为【动态 import】（Express 就绪后再 import db）+ 一个非 unref 的
 *    低频心跳定时器后，health 与 DB 路由均稳定返回 HTTP 200（见 _diag2 实验）。
 *
 * 浏览器负责：文档/查询 embedding（Transformers.js，本地）
 * 本服务负责：接收向量 → seekdb-js 写入 → 数据库端混合检索 → 返回结果
 * 严禁在 Node 端调用任何 embedding 模型或云端 embedding API。
 */
import express from 'express';
import cors from 'cors';
import { appendFileSync, mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PORT = Number(process.env.PORT || 8787);
const LOG_FILE = path.join(__dirname, '..', 'evidence', 'server.log');
function slog(op, detail) {
  const line = `[${new Date().toISOString()}] ${op} ${JSON.stringify(detail || {})}\n`;
  try { mkdirSync(path.dirname(LOG_FILE), { recursive: true }); appendFileSync(LOG_FILE, line, 'utf8'); } catch {}
  // 仅写文件日志，不写 stdout（避免后台任务输出管道写满阻塞事件循环）。
}

const app = express();
app.use(cors());
app.use(express.json({ limit: '64mb' }));
let ready = false;
let initInfo = null;
let db = null; // 动态 import 的 db 模块

app.get('/api/health', (req, res) => {
  res.json({ ok: true, ready, ...(initInfo || {}), ts: new Date().toISOString() });
});
app.post('/api/kb/:kb/add', async (req, res) => {
  try { res.json({ ok: true, ...(await db.addDocuments(req.params.kb, req.body.docs)) }); }
  catch (e) { slog('API_ERR_ADD', { error: e.message }); res.status(400).json({ ok: false, error: e.message }); }
});
app.post('/api/kb/:kb/refresh', async (req, res) => {
  try { res.json({ ok: true, ...(await db.refreshIndex()) }); }
  catch (e) { slog('API_ERR_REFRESH', { error: e.message }); res.status(500).json({ ok: false, error: e.message }); }
});
app.post('/api/kb/:kb/search', async (req, res) => {
  try {
    const { keyword, embedding, nResults, mode } = req.body;
    const out = mode === 'vector'
      ? await db.vectorSearch({ kb: req.params.kb, embedding, nResults })
      : await db.hybridSearch({ kb: req.params.kb, keyword, embedding, nResults });
    res.json({ ok: true, ...out });
  } catch (e) { slog('API_ERR_SEARCH', { error: e.message }); res.status(400).json({ ok: false, error: e.message }); }
});
app.get('/api/kb/:kb/count', async (req, res) => {
  try { res.json({ ok: true, ...(await db.countByKb(req.params.kb)) }); }
  catch (e) { res.status(500).json({ ok: false, error: e.message }); }
});
app.delete('/api/kb/:kb', async (req, res) => {
  try { res.json({ ok: true, ...(await db.clearKb(req.params.kb)) }); }
  catch (e) { res.status(500).json({ ok: false, error: e.message }); }
});
app.get('/api/debug/all', async (req, res) => {
  try {
    const docs = await db.listAll();
    res.json({ ok: true, count: docs.length, docs: docs.map(d => ({ id: d.id, text: d.text, metadata: d.metadata })) });
  } catch (e) { res.status(500).json({ ok: false, error: e.message }); }
});

async function main() {
  slog('SERVER_BOOT', { port: PORT });
  // 关键：Express 先监听，再动态 import db（避免原生 addon 干扰事件循环初始化）
  await new Promise(resolve => app.listen(PORT, '127.0.0.1', resolve));
  slog('LISTENING', { port: PORT });
  // 非 unref 心跳：保持事件循环稳定（实测必要）
  setInterval(() => {}, 2000);

  try {
    db = await import('./db.js');
    const t0 = performance.now();
    await db.initDb();
    initInfo = { initMs: Math.round(performance.now() - t0), dbDir: db.DB_DIR, dimension: db.DIMENSION };
    ready = true;
    slog('SERVER_READY', initInfo);
  } catch (e) {
    slog('INIT_FAILED', { error: e.message });
  }
}
main().catch(e => { slog('FATAL', { error: e.message }); process.exit(1); });
