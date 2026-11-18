import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from './api';
import { embedBatch, embedOne, loadEmbedder, probeWebGPU } from './embedding';
import type { BackendType, DType, Doc, ModelInfo, SearchHit } from './types';
import './styles.css';

const KBS = ['通用知识库', '技术文档库', '产品手册库'];
const KB_KEYS: Record<string, string> = {
  '通用知识库': 'general',
  '技术文档库': 'tech',
  '产品手册库': 'product',
};

type Phase = 'idle' | 'loading' | 'embedding' | 'writing' | 'refreshing' | 'done' | 'error';

export default function App() {
  const [kb, setKb] = useState(KBS[0]);
  const [dtype, setDType] = useState<DType>('q8');
  const [backendPref, setBackendPref] = useState<'auto' | BackendType>('auto');
  const [modelInfo, setModelInfo] = useState<ModelInfo | null>(null);
  const [webgpuProbe, setWebgpuProbe] = useState<{ available: boolean; detail: string } | null>(null);
  const [phase, setPhase] = useState<Phase>('idle');
  const [progress, setProgress] = useState('');
  const [docs, setDocs] = useState<Doc[]>([]);
  const [query, setQuery] = useState('');
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [searchMeta, setSearchMeta] = useState<{ searchMs: number; engine: string; queryMs: number; e2eMs: number } | null>(null);
  const [kbCount, setKbCount] = useState<number | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [perf, setPerf] = useState<Record<string, number>>({});
  const pipeRef = useRef<Awaited<ReturnType<typeof loadEmbedder>>['pipe'] | null>(null);
  const loadInfoRef = useRef<ModelInfo | null>(null);

  const log = useCallback((s: string) => {
    setLogs(prev => [...prev.slice(-200), `[${new Date().toLocaleTimeString()}] ${s}`]);
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const p = await probeWebGPU();
        setWebgpuProbe(p);
        log(`WebGPU 探测: ${p.detail}`);
      } catch (e) { log(`WebGPU 探测失败: ${(e as Error).message}`); }
      try {
        const h = await api.health();
        log(`API 服务: ${h.ready ? '就绪' : '启动中'}`);
      } catch (e) { log(`API 服务未连接: ${(e as Error).message}`); }
    })();
  }, [log]);

  const ensureModel = useCallback(async () => {
    if (pipeRef.current && loadInfoRef.current?.dtype === dtype) {
      log(`复用已加载模型 (${dtype}, ${loadInfoRef.current.device})`);
      return { pipe: pipeRef.current, info: loadInfoRef.current, downloadMs: 0 };
    }
    setPhase('loading');
    setProgress(`正在本地加载模型 (${dtype})…（首次含下载，稍候）`);
    log(`加载模型 dtype=${dtype} 偏好后端=${backendPref}`);
    const force = backendPref === 'auto' ? undefined : backendPref;
    const res = await loadEmbedder({ dtype, forceBackend: force });
    pipeRef.current = res.pipe;
    loadInfoRef.current = res.info;
    setModelInfo(res.info);
    setPerf(p => ({ ...p, modelLoadMs: res.downloadMs }));
    setPhase('idle');
    setProgress(`模型就绪：${res.info.device}（${res.info.deviceVerified ? '已验证' : '未验证'}）`);
    log(`模型加载完成 ${res.downloadMs}ms device=${res.info.device} verified=${res.info.deviceVerified} :: ${res.info.detail}`);
    return res;
  }, [dtype, backendPref, log]);

  const handleImport = useCallback(async (text: string, sourceName: string) => {
    if (!text.trim()) { setProgress('请先输入或选择文档内容'); return; }
    try {
      const { pipe } = await ensureModel();
      const lines = text.split(/\n{2,}/).map(s => s.trim()).filter(Boolean);
      const chunks = lines.length ? lines : [text.trim()];
      setPhase('embedding');
      setProgress(`本地向量化 ${chunks.length} 个段落…`);
      const t0 = performance.now();
      const vectors = await embedBatch(pipe, chunks);
      const embedMs = Math.round(performance.now() - t0);
      setPerf(p => ({ ...p, lastEmbedMs: embedMs, throughput: +(chunks.length / (embedMs / 1000)).toFixed(2) }));
      log(`本地向量化 ${chunks.length} 段 用时 ${embedMs}ms (${(chunks.length / (embedMs / 1000)).toFixed(1)} 段/秒)`);

      const newDocs: Doc[] = chunks.map((c, i) => ({
        id: `${Date.now()}-${i}`,
        text: c,
        embedding: vectors[i],
        metadata: { source: sourceName, chunk: i },
      }));

      setPhase('writing');
      setProgress(`写入 seekdb ${newDocs.length} 条…（Node 端不生成向量）`);
      const w = await api.addDocs(KB_KEYS[kb], newDocs);
      log(`seekdb 写入 ${w.count} 条 用时 ${w.writeMs}ms`);

      setPhase('refreshing');
      setProgress('刷新索引…');
      const r = await api.refresh(KB_KEYS[kb]);
      log(`索引刷新 ${r.refreshMs}ms`);

      setDocs(prev => [...prev, ...newDocs]);
      setPhase('done');
      setProgress(`导入完成：${newDocs.length} 条（向量化 ${embedMs}ms / 写入 ${w.writeMs}ms / 刷新 ${r.refreshMs}ms）`);
      await refreshCount();
    } catch (e) {
      setPhase('error');
      setProgress(`导入失败: ${(e as Error).message}`);
      log(`导入失败: ${(e as Error).message}`);
    }
  }, [kb, ensureModel, log]);

  const refreshCount = useCallback(async () => {
    try { const c = await api.count(KB_KEYS[kb]); setKbCount(c.count); }
    catch { setKbCount(null); }
  }, [kb]);

  useEffect(() => { refreshCount(); }, [kb, refreshCount]);

  const onFile = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    const text = await f.text();
    await handleImport(text, f.name);
    e.target.value = '';
  }, [handleImport]);

  const [pasted, setPasted] = useState('');

  const handleSearch = useCallback(async () => {
    if (!query.trim()) { setProgress('请输入查询内容'); return; }
    try {
      const { pipe, info } = await ensureModel();
      const t0 = performance.now();
      const vec = await embedOne(pipe, query);
      const queryMs = Math.round(performance.now() - t0);
      const t1 = performance.now();
      const res = await api.search(KB_KEYS[kb], {
        keyword: query, embedding: vec, nResults: 8, mode: 'hybrid',
      });
      const e2eMs = Math.round(performance.now() - t1);
      setHits(res.hits);
      setSearchMeta({ searchMs: res.searchMs, engine: res.engine, queryMs, e2eMs });
      setPerf(p => ({ ...p, queryEmbedMs: queryMs, seekdbSearchMs: res.searchMs, e2eQueryMs: e2eMs }));
      log(`查询 "${query}" 本地向量 ${queryMs}ms / seekdb 检索 ${res.searchMs}ms / 端到端 ${e2eMs}ms device=${info.device}`);
    } catch (e) {
      setProgress(`查询失败: ${(e as Error).message}`);
      log(`查询失败: ${(e as Error).message}`);
    }
  }, [query, kb, ensureModel, log]);

  const switchKb = useCallback((name: string) => {
    setKb(name);
    setHits([]);
    setSearchMeta(null);
    setDocs([]);
    log(`切换知识库 -> ${name} (${KB_KEYS[name]})，清空会话检索状态`);
  }, [log]);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <div className="logo">SF</div>
          <div>
            <h1>StepFun 迷你知识库</h1>
            <p>浏览器本地推理 · seekdb 数据库端混合检索</p>
          </div>
        </div>
        <div className="status-chips">
          <span className={`chip ${modelInfo?.device === 'webgpu' ? 'chip-webgpu' : 'chip-wasm'}`}>
            推理后端: {modelInfo?.device ?? '未加载'}{modelInfo ? (modelInfo.deviceVerified ? ' ✓已验证' : '') : ''}
          </span>
          <span className="chip">模型: {modelInfo?.name ?? '—'} / {dtype === 'q8' ? 'INT8' : 'FP32'}</span>
          <span className="chip">维度: {modelInfo?.dimension ?? 384}</span>
        </div>
      </header>

      <div className="layout">
        <aside className="sidebar">
          <section className="panel">
            <h2>知识库</h2>
            <div className="kb-list">
              {KBS.map(name => (
                <button key={name} className={`kb-item ${kb === name ? 'active' : ''}`} onClick={() => switchKb(name)}>
                  <span>{name}</span>
                  <small>{KB_KEYS[name]}</small>
                </button>
              ))}
            </div>
            <div className="kb-count">当前库文档数：{kbCount ?? '—'}</div>
          </section>

          <section className="panel">
            <h2>推理配置</h2>
            <label className="field">
              <span>模型精度</span>
              <select value={dtype} onChange={e => { setDType(e.target.value as DType); pipeRef.current = null; loadInfoRef.current = null; }}>
                <option value="q8">INT8 量化 (model_quantized)</option>
                <option value="fp32">FP32 非量化基线 (model)</option>
              </select>
            </label>
            <label className="field">
              <span>推理后端</span>
              <select value={backendPref} onChange={e => { setBackendPref(e.target.value as 'auto' | BackendType); pipeRef.current = null; loadInfoRef.current = null; }}>
                <option value="auto">自动（WebGPU 优先，降级 WASM）</option>
                <option value="webgpu">强制 WebGPU</option>
                <option value="wasm">强制 WASM</option>
              </select>
            </label>
            <p className="hint">WebGPU 探测：{webgpuProbe?.detail ?? '检测中…'}</p>
            <button className="btn btn-ghost" onClick={async () => { try { await ensureModel(); } catch (e) { log(`加载失败: ${(e as Error).message}`); } }}>
              加载/重载模型
            </button>
          </section>

          <section className="panel perf-panel">
            <h2>性能与状态</h2>
            <div className="kv"><span>阶段</span><b>{phase}</b></div>
            <div className="kv"><span>模型加载</span><b>{perf.modelLoadMs ?? '—'} ms</b></div>
            <div className="kv"><span>文档向量化</span><b>{perf.lastEmbedMs ?? '—'} ms</b></div>
            <div className="kv"><span>文档吞吐</span><b>{perf.throughput ?? '—'} 段/秒</b></div>
            <div className="kv"><span>查询向量化</span><b>{perf.queryEmbedMs ?? '—'} ms</b></div>
            <div className="kv"><span>seekdb 检索</span><b>{perf.seekdbSearchMs ?? '—'} ms</b></div>
            <div className="kv"><span>端到端查询</span><b>{perf.e2eQueryMs ?? '—'} ms</b></div>
          </section>
        </aside>

        <main className="main">
          <section className="panel import-panel">
            <h2>导入文本文档</h2>
            <p className="hint">文档在浏览器本地向量化后发送给 seekdb；Node 服务端不生成向量。空行分段。</p>
            <div className="import-row">
              <label className="btn btn-primary">
                选择 .txt 文件
                <input type="file" accept=".txt,text/plain" onChange={onFile} hidden />
              </label>
              <span className="or">或粘贴文本</span>
            </div>
            <textarea
              placeholder="在此粘贴文本，用空行分隔段落…"
              value={pasted}
              onChange={e => setPasted(e.target.value)}
              rows={5}
            />
            <button className="btn btn-primary" onClick={() => handleImport(pasted, 'pasted.txt')} disabled={phase === 'embedding' || phase === 'writing'}>
              导入并向量化
            </button>
            <div className={`progress ${phase === 'error' ? 'err' : ''}`}>{progress || '就绪'}</div>
          </section>

          <section className="panel search-panel">
            <h2>混合检索</h2>
            <div className="search-row">
              <input
                placeholder="输入查询（全文关键词 + 语义向量融合，由 seekdb 执行）"
                value={query}
                onChange={e => setQuery(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') handleSearch(); }}
              />
              <button className="btn btn-primary" onClick={handleSearch}>检索</button>
            </div>
            {searchMeta && (
              <div className="search-meta">
                引擎 <b>{searchMeta.engine}</b> · 查询向量 {searchMeta.queryMs}ms · seekdb 检索 {searchMeta.searchMs}ms · 端到端 {searchMeta.e2eMs}ms
              </div>
            )}
            <div className="results">
              {hits.length === 0 && <div className="empty">尚无检索结果。先导入文档，再输入查询。</div>}
              {hits.map((h, i) => (
                <article className="result" key={h.id}>
                  <div className="result-head">
                    <span className="rank">#{i + 1}</span>
                    <span className="source">来源：{String(h.metadata?.source ?? '—')}</span>
                    <span className="dist">相似度得分：{h.distance ?? '—'}</span>
                  </div>
                  <p className="result-text">{h.text}</p>
                  <div className="result-id">ID: {h.id}</div>
                </article>
              ))}
            </div>
          </section>

          <section className="panel log-panel">
            <h2>运行日志</h2>
            <div className="logbox">
              {logs.length === 0 ? <div className="empty">无日志</div> : logs.map((l, i) => <div key={i}>{l}</div>)}
            </div>
          </section>
        </main>
      </div>
    </div>
  );
}
