/**
 * copy-ort-assets.mjs — 将 ONNX Runtime Web 的 WASM 运行时文件复制到前端 public/ort/，
 * 保证浏览器完全本地加载（禁止 CDN）。在 npm install 后运行一次。
 */
import { copyFileSync, mkdirSync, existsSync } from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';

const require = createRequire(import.meta.url);
const frontendDir = path.resolve(import.meta.dirname ?? path.dirname(new URL(import.meta.url).pathname), '..', 'frontend');
// 解析 onnxruntime-web 的 dist 路径
const ortPkg = require.resolve('onnxruntime-web/package.json', { paths: [frontendDir] });
const distDir = path.join(path.dirname(ortPkg), 'dist');
const outDir = path.join(frontendDir, 'public', 'ort');
mkdirSync(outDir, { recursive: true });

const files = [
  'ort-wasm-simd-threaded.asyncify.mjs',
  'ort-wasm-simd-threaded.asyncify.wasm',
  'ort-wasm-simd-threaded.jsep.mjs',
  'ort-wasm-simd-threaded.jsep.wasm',
];
for (const f of files) {
  const src = path.join(distDir, f);
  if (!existsSync(src)) { console.warn('missing source: ' + src); continue; }
  copyFileSync(src, path.join(outDir, f));
  console.log('copied ' + f);
}
console.log('ORT assets ready at ' + outDir);
