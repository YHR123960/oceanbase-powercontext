/**
 * verify-fresh.mjs — 干净环境复现检查
 * 逐项验证交付物完整性与可运行性，输出 evidence/verify-fresh.log。
 * 不修改数据，只做只读检查 + 轻量 HTTP 探测。
 */
import { existsSync, statSync, readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);

mkdirSync('./evidence', { recursive: true });
let lines = [];
const log = (...a) => { const s = a.join(' '); lines.push(s); console.log(s); };
let pass = 0, fail = 0;
const check = (n, c, d) => { if (c) { pass++; log('PASS ' + n); } else { fail++; log('FAIL ' + n + ' :: ' + d); } };
const R = process.cwd(); // stepfun/

log('=== 干净环境复现检查 ===');
log('时间: ' + new Date().toISOString());
log('Node: ' + process.version);
log('工作目录: ' + R);

// 1. 目录结构
for (const d of ['frontend', 'backend', 'scripts', 'tests', 'benchmark', 'evidence', 'frontend/public/models/all-MiniLM-L6-v2', 'frontend/public/ort']) {
  check('目录存在 ' + d, existsSync(path.join(R, d)), d);
}

// 2. 关键文档
for (const f of ['README.md', 'TECHNICAL_OVERVIEW.md', 'PROGRESS.md']) {
  check('文档存在 ' + f, existsSync(path.join(R, f)), f);
}

// 3. 模型文件（真实体积）
const modelDir = path.join(R, 'frontend/public/models/all-MiniLM-L6-v2');
for (const [f, minSize] of [
  ['config.json', 100], ['tokenizer.json', 100000], ['tokenizer_config.json', 100],
  ['special_tokens_map.json', 50], ['onnx/model_quantized.onnx', 20000000], ['onnx/model.onnx', 80000000],
]) {
  const p = path.join(modelDir, f);
  const ok = existsSync(p) && statSync(p).size >= minSize;
  check(`模型文件 ${f}`, ok, existsSync(p) ? `size=${statSync(p).size}` : 'missing');
}

// 4. ORT wasm 文件
for (const f of ['ort-wasm-simd-threaded.asyncify.wasm', 'ort-wasm-simd-threaded.asyncify.mjs']) {
  const p = path.join(R, 'frontend/public/ort', f);
  check('ORT文件 ' + f, existsSync(p) && statSync(p).size > 1000, existsSync(p) ? 'ok' : 'missing');
}

// 5. 源码关键约束（静态检查）
const embedSrc = readFileSync(path.join(R, 'frontend/src/embedding.ts'), 'utf8');
check('禁止远程模型 allowRemoteModels=false', /allowRemoteModels\s*=\s*false/.test(embedSrc), '');
check('本地ORT wasmPaths配置', /wasmPaths/.test(embedSrc), '');
const dbSrc = readFileSync(path.join(R, 'backend/src/db.js'), 'utf8');
check('seekdb embeddingFunction=null', /embeddingFunction:\s*null/.test(dbSrc), '');
check('数据库端hybridSearch', /hybridSearch\(/.test(dbSrc), '');
check('Node端无console.log日志', !/console\.log/.test(dbSrc), '');

// 6. 依赖可解析
for (const [dir, pkg] of [['frontend', '@huggingface/transformers'], ['frontend', 'react'], ['backend', 'seekdb'], ['backend', 'express']]) {
  try {
    const p = require.resolve(pkg, { paths: [path.join(R, dir)] });
    check(`依赖 ${pkg}`, !!p, '');
  } catch (e) { check(`依赖 ${pkg}`, false, e.message); }
}

// 7. 构建产物或可构建
const frontendIndex = path.join(R, 'frontend/dist/index.html');
check('前端已构建(dist/index.html)', existsSync(frontendIndex), '');

// 8. HTTP 服务存活（若运行）
try {
  const r = await fetch('http://127.0.0.1:8787/api/health', { signal: AbortSignal.timeout(5000) });
  const j = await r.json();
  check('API服务健康', r.status === 200 && j.ready, JSON.stringify(j));
} catch (e) { log('INFO API服务未运行（复现时需先 npm start）: ' + e.message); }

log(`\nSUMMARY pass=${pass} fail=${fail}`);
writeFileSync(path.join(R, 'evidence/verify-fresh.log'), lines.join('\n') + '\n');
process.exit(fail === 0 ? 0 : 1);
