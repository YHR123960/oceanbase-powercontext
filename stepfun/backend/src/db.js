/**
 * db.js — seekdb Embedded 模式数据库连接与操作封装
 *
 * 架构约束（赛题硬性要求）：
 *  - 向量由浏览器端 Transformers.js 计算，通过 HTTP 传入本模块。
 *  - 本模块及整个 Node 服务端【不生成任何 embedding】，embeddingFunction 恒为 null。
 *  - 混合检索由 seekdb 数据库端 DBMS_HYBRID_SEARCH 执行，绝不在此拼接两路结果。
 *  - 知识库隔离使用 metadata.kb 过滤，在数据库端查询时生效。
 */
import { SeekdbClient, Schema, VectorIndexConfig, FulltextIndexConfig } from 'seekdb';
import { mkdirSync, existsSync, appendFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = path.resolve(__dirname, '..');
export const DB_DIR = process.env.SEEKDB_DATA_DIR || path.join(PROJECT_ROOT, 'data', 'seekdb');
export const LOG_FILE = path.join(PROJECT_ROOT, 'evidence', 'db-operation.log');
const COLLECTION = 'mini_kb_docs';
export const DIMENSION = 384;

let client = null;
let collection = null;
let initMs = 0;

function log(op, detail) {
  const line = `[${new Date().toISOString()}] ${op} ${JSON.stringify(detail)}\n`;
  try { mkdirSync(path.dirname(LOG_FILE), { recursive: true }); appendFileSync(LOG_FILE, line, 'utf8'); } catch {}
  // 不写 stdout：后台任务的输出管道无消费者时会被写满并阻塞事件循环。
}

/** 初始化数据库（幂等）。复用已初始化目录可显著加快 open 速度。 */
export async function initDb() {
  if (collection) return { collection, initMs };
  const t0 = performance.now();
  mkdirSync(DB_DIR, { recursive: true });
  log('DB_OPEN_START', { dbDir: DB_DIR });
  client = new SeekdbClient({ path: DB_DIR, database: 'test' });
  const schema = new Schema({
    vectorIndex: new VectorIndexConfig({
      hnsw: { dimension: DIMENSION, distance: 'cosine' },
      embeddingFunction: null, // 关键：禁止服务端向量化
    }),
    fulltextIndex: new FulltextIndexConfig('ik', { ik_mode: 'smart' }),
  });
  // getOrCreateCollection：重启服务不丢数据
  collection = await client.getOrCreateCollection({ name: COLLECTION, schema });
  initMs = Math.round(performance.now() - t0);
  log('DB_READY', { collection: COLLECTION, dimension: DIMENSION, initMs });
  return { collection, initMs };
}

export function getCollection() {
  if (!collection) throw new Error('DB not initialized; call initDb() first');
  return collection;
}

export { log };

/**
 * 写入文档（向量来自浏览器）。
 * docs: [{ id, text, embedding:number[384], metadata:{ kb, source, ... } }]
 */
export async function addDocuments(kb, docs) {
  const col = getCollection();
  if (!Array.isArray(docs) || docs.length === 0) throw new Error('docs must be a non-empty array');
  for (const d of docs) {
    if (!Array.isArray(d.embedding) || d.embedding.length !== DIMENSION) {
      throw new Error(`embedding of doc ${d.id} must be length ${DIMENSION}, got ${d.embedding?.length}`);
    }
  }
  const ids = docs.map(d => `${kb}::${d.id}`);
  const documents = docs.map(d => d.text);
  const embeddings = docs.map(d => d.embedding);
  const metadatas = docs.map(d => ({ ...(d.metadata || {}), kb }));
  const t0 = performance.now();
  await col.add({ ids, documents, embeddings, metadatas });
  const writeMs = Math.round(performance.now() - t0);
  log('DOC_ADD', { kb, count: docs.length, writeMs, ids: ids.slice(0, 5) });
  return { count: docs.length, writeMs };
}

/** 刷新索引，使增量写入的文档可被近似检索命中 */
export async function refreshIndex() {
  const col = getCollection();
  const t0 = performance.now();
  await col.refresh_index();
  const refreshMs = Math.round(performance.now() - t0);
  log('INDEX_REFRESH', { refreshMs });
  return { refreshMs };
}

/**
 * 数据库端混合检索：全文(query) + 向量(knn) 由 seekdb 融合排序。
 * kb 作为元数据过滤条件在数据库端生效，防止跨知识库串数据。
 */
export async function hybridSearch({ kb, keyword, embedding, nResults = 5 }) {
  const col = getCollection();
  if (!Array.isArray(embedding) || embedding.length !== DIMENSION) {
    throw new Error(`query embedding must be length ${DIMENSION}`);
  }
  const searchParm = {
    query: {
      whereDocument: { $contains: keyword || '' },
      where: { kb },
    },
    knn: { queryEmbeddings: [embedding] },
    nResults,
  };
  const t0 = performance.now();
  const result = await col.hybridSearch(searchParm);
  const searchMs = Math.round(performance.now() - t0);
  const ids = result.ids?.[0] || [];
  const documents = result.documents?.[0] || [];
  const metadatas = result.metadatas?.[0] || [];
  const distances = result.distances?.[0] || [];
  const hits = ids.map((id, i) => ({
    id,
    text: documents[i] ?? '',
    metadata: metadatas[i] || {},
    distance: distances[i] ?? null,
  })).filter(h => h.metadata?.kb === kb); // 双保险：客户端再校验 kb
  log('HYBRID_SEARCH', { kb, keyword, nResults, searchMs, returned: hits.length, topIds: hits.slice(0, 5).map(h => h.id) });
  return { hits, searchMs, engine: 'seekdb::DBMS_HYBRID_SEARCH' };
}

/** 纯向量检索（用于对照实验/质量评估） */
export async function vectorSearch({ kb, embedding, nResults = 5 }) {
  const col = getCollection();
  const t0 = performance.now();
  const result = await col.query({ queryEmbeddings: [embedding], where: { kb }, nResults });
  const searchMs = Math.round(performance.now() - t0);
  const ids = result.ids?.[0] || [];
  const documents = result.documents?.[0] || [];
  const metadatas = result.metadatas?.[0] || [];
  const distances = result.distances?.[0] || [];
  const hits = ids.map((id, i) => ({ id, text: documents[i] ?? '', metadata: metadatas[i] || {}, distance: distances[i] ?? null }));
  log('VECTOR_SEARCH', { kb, nResults, searchMs, returned: hits.length });
  return { hits, searchMs, engine: 'seekdb::vector' };
}

/** 兼容 seekdb get() 的 ids 返回结构（可能是扁平数组或嵌套数组） */
function flattenIds(ids) {
  if (!ids) return [];
  if (!Array.isArray(ids)) return [];
  // 若首元素是数组 → 嵌套结构，取第一组；否则视为扁平结构
  if (Array.isArray(ids[0])) return (ids[0] || []).map(x => String(x));
  return ids.map(x => String(x));
}

/** 获取知识库文档数（用于验证导入/隔离） */
export async function countByKb(kb) {
  const col = getCollection();
  const res = await col.get({ where: { kb }, include: ['documents', 'metadatas'] });
  const ids = flattenIds(res.ids);
  return { kb, count: ids.length, ids: ids.slice(0, 10) };
}

/** 清空某知识库（通过删除该 kb 下全部文档 id） */
export async function clearKb(kb) {
  const col = getCollection();
  const res = await col.get({ where: { kb }, include: [] });
  const ids = flattenIds(res.ids);
  if (ids.length) await col.delete({ ids });
  await col.refresh_index().catch(() => {});
  log('KB_CLEAR', { kb, deleted: ids.length });
  return { deleted: ids.length };
}

/** 列出全部文档（含 metadata），供评测/调试 */
export async function listAll() {
  const col = getCollection();
  const res = await col.get({ include: ['documents', 'metadatas', 'embeddings'] });
  const ids = flattenIds(res.ids);
  const documents = Array.isArray(res.documents?.[0]) ? res.documents[0] : (res.documents || []);
  const metadatas = Array.isArray(res.metadatas?.[0]) ? res.metadatas[0] : (res.metadatas || []);
  return ids.map((id, i) => ({ id, text: documents[i], metadata: metadatas[i] }));
}
