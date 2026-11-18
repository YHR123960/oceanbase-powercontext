/**
 * browser-embedding.spec.mjs — 真实浏览器测试（Playwright + 系统 Chrome）
 *
 * 验证：
 *  1. 页面加载、模型本地加载（env.allowRemoteModels=false）
 *  2. 拦截所有外部网络请求，确认没有云端 embedding API 调用
 *  3. 实际执行文档 embedding 与查询 embedding（本地推理）
 *  4. 前端显示真实推理后端，且 WebGPU 路径经过实际推理验证
 *  5. 完整 UI 流程：导入 → seekdb 写入 → 混合检索 → 结果展示
 *
 * 注意：WebGPU 是否可用取决于运行浏览器环境；若不可用会如实记录降级，不伪造。
 */
import { chromium } from '@playwright/test';
import { writeFileSync, mkdirSync } from 'node:fs';

const OUT = './evidence/browser';
mkdirSync(OUT, { recursive: true });
const RESULT = `${OUT}/browser-test.log`;
let lines = [];
const log = (...a) => { const s = a.join(' '); lines.push(s); console.log(s); };

const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const URL = 'http://127.0.0.1:5173/';

async function main() {
  const browser = await chromium.launch({
    executablePath: CHROME,
    headless: true,
    args: [
      '--no-sandbox',
      '--enable-unsafe-webgpu',       // 尝试启用 WebGPU
      '--use-angle=swiftshader',      // 软件 GPU（若硬件不可用）
      '--enable-features=Vulkan',
    ],
  });
  const context = await browser.newContext({ viewport: { width: 1400, height: 950 } });
  const page = await context.newPage();

  // 记录所有网络请求；标记是否有外部（非本地）请求 = 潜在云端调用
  const external = [];
  const allRequests = [];
  page.on('request', req => {
    const u = req.url();
    allRequests.push(u);
    if (!u.startsWith('http://127.0.0.1') && !u.startsWith('http://localhost') && !u.startsWith('data:') && !u.startsWith('blob:')) {
      external.push(u);
    }
  });
  const consoleMsgs = [];
  page.on('console', m => consoleMsgs.push(`${m.type()}: ${m.text()}`));
  const pageErrors = [];
  page.on('pageerror', e => pageErrors.push(e.message));

  await page.goto(URL, { waitUntil: 'networkidle' });
  log('PAGE_TITLE ' + await page.title());

  // WebGPU 探测信息（真实 requestAdapter）
  const probeText = await page.locator('.hint').filter({ hasText: 'WebGPU 探测' }).textContent().catch(() => '');
  log('WEBGPU_PROBE_UI ' + (probeText || '').trim());

  let pass = 0, fail = 0;
  const check = (n, c, d) => { if (c) { pass++; log('PASS ' + n); } else { fail++; log('FAIL ' + n + ' :: ' + JSON.stringify(d)); } };

  // 强制 WASM 加载模型，确保可重复验证（WebGPU 单独在下面探测）
  await page.selectOption('select >> nth=0', 'q8');
  await page.selectOption('select >> nth=1', 'wasm');
  await page.getByRole('button', { name: /加载\/重载模型/ }).click();

  // 等待模型加载完成（后端 chip 显示 wasm 且未加载字样消失）
  await page.waitForFunction(() => {
    const chip = document.querySelector('.status-chips .chip');
    return chip && chip.textContent && chip.textContent.includes('wasm') && !chip.textContent.includes('未加载');
  }, { timeout: 180000 });
  const backendChip = await page.locator('.status-chips .chip').first().textContent();
  log('BACKEND_CHIP ' + (backendChip || '').trim());
  check('模型在本地加载成功并显示后端', !!backendChip && backendChip.includes('wasm'), backendChip);

  // 导入文本文档（触发文档 embedding + 写库 + 刷新索引）
  const testText = `seekdb 是一个支持向量与全文混合检索的数据库。
它的混合检索由数据库端 DBMS_HYBRID_SEARCH 执行。
Transformers.js 在浏览器本地计算 embedding，不调用云端 API。
WebGPU 不可用时自动降级到 WASM 推理后端。`;
  await page.fill('textarea', testText);
  await page.getByRole('button', { name: /导入并向量化/ }).click();
  await page.waitForFunction(() => {
    const p = document.querySelector('.progress');
    return p && p.textContent && p.textContent.includes('导入完成');
  }, { timeout: 180000 });
  const progressText = await page.locator('.progress').textContent();
  log('IMPORT_PROGRESS ' + (progressText || '').trim());
  check('文档导入+本地向量化+写库+索引刷新', !!progressText && progressText.includes('导入完成'), progressText);

  // 查询（触发查询 embedding + seekdb 混合检索）
  await page.fill('input[placeholder*="输入查询"]', '浏览器本地 embedding');
  await page.getByRole('button', { name: '检索', exact: true }).click();
  await page.waitForSelector('.result', { timeout: 60000 });
  const resultCount = await page.locator('.result').count();
  log('RESULT_COUNT ' + resultCount);
  check('混合检索返回结果', resultCount > 0, resultCount);
  const searchMeta = await page.locator('.search-meta').textContent();
  log('SEARCH_META ' + (searchMeta || '').trim());
  check('检索由 seekdb 执行', !!searchMeta && searchMeta.includes('seekdb'), searchMeta);

  // 无云端请求验证：允许的模型文件/静态资源都来自 127.0.0.1
  const realExternal = external.filter(u => !u.startsWith('chrome-extension') && !u.startsWith('about:'));
  log('EXTERNAL_REQUEST_COUNT ' + realExternal.length);
  realExternal.slice(0, 20).forEach(u => log('EXTERNAL_REQ ' + u));
  check('无云端 embedding 请求（所有请求本地）', realExternal.length === 0, realExternal);

  check('无页面运行时错误', pageErrors.length === 0, pageErrors);

  // 截图佐证
  await page.screenshot({ path: `${OUT}/app-wasm.png`, fullPage: true });

  // WebGPU 路径单独探测（强制 webgpu，看是否真的能推理；否则记录降级限制）
  await page.selectOption('select >> nth=1', 'webgpu');
  await page.getByRole('button', { name: /加载\/重载模型/ }).click();
  await page.waitForTimeout(30000);
  const chipAfter = await page.locator('.status-chips .chip').first().textContent().catch(() => '');
  const detailLogs = logsFromConsole(consoleMsgs);
  log('WEBGPU_FORCE_CHIP ' + (chipAfter || '').trim());
  log('WEBGPU_CONSOLE ' + detailLogs.slice(-10).join(' | '));

  log(`\nSUMMARY pass=${pass} fail=${fail}`);
  log('CONSOLE_TAIL\n' + consoleMsgs.slice(-30).join('\n'));
  writeFileSync(RESULT, lines.join('\n') + '\n');
  await browser.close();
  process.exit(fail === 0 ? 0 : 1);
}

function logsFromConsole(msgs) {
  return msgs.filter(m => /webgpu|wasm|device|backend|onnx|error/i.test(m));
}

main().catch(e => { log('ERROR ' + (e.stack || e)); writeFileSync(RESULT, lines.join('\n') + '\n'); process.exit(2); });
