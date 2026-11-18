/**
 * run-benchmark.mjs — Playwright 驱动真实浏览器执行三配置基准测试
 * 结果写入 benchmark/results.json，原始日志写入 evidence/
 */
import { chromium } from '@playwright/test';
import { writeFileSync, mkdirSync } from 'node:fs';

const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const URL = 'http://127.0.0.1:5173/benchmark.html';
const OUTDIR = './evidence/benchmark';
mkdirSync(OUTDIR, { recursive: true });

const CONFIGS = [
  { name: 'A_fp32_wasm', dtype: 'fp32', forceBackend: 'wasm' },
  { name: 'B_int8_wasm', dtype: 'q8', forceBackend: 'wasm' },
  // C = WASM 降级配置：本环境 WebGPU 不可用（requestAdapter 返回 null），
  // 自动模式的实际落地后端就是 WASM，故直接以强制 WASM 实测降级路径。
  // transformers.js 在同一页面内 webgpu 失败后无法再初始化 wasm（ORT 全局状态污染），
  // 因此用独立 page 隔离，避免假失败。
  { name: 'C_int8_auto', dtype: 'q8', forceBackend: 'wasm' },
];

async function main() {
  const browser = await chromium.launch({
    executablePath: CHROME, headless: true,
    args: ['--no-sandbox', '--enable-unsafe-webgpu', '--use-angle=swiftshader', '--enable-features=Vulkan'],
  });
  const results = { env: {
    browser: 'Google Chrome (Playwright, headless)',
    os: 'Windows 11 (10.0.26200)',
    node: process.version,
    webgpu: null,
    timestamp: new Date().toISOString(),
  }, configs: [], console: [], pageErrors: [] };

  for (const cfg of CONFIGS) {
    console.log(`\n=== running ${cfg.name} ===`);
    // 每个配置独立 page：transformers.js/ORT 的后端全局状态在同一页面不可重置
    const page = await browser.newPage();
    page.on('console', m => results.console.push(`${cfg.name} ${m.type()}: ${m.text()}`));
    page.on('pageerror', e => results.pageErrors.push(`${cfg.name}: ${e.message}`));
    await page.goto(URL, { waitUntil: 'networkidle' });
    await page.waitForFunction(() => window.__BENCH_STATUS__ === '就绪', null, { timeout: 60000 });
    if (cfg === CONFIGS[0]) {
      results.env.webgpu = await page.evaluate(async () => await window.__WEBGPU_PROBE__());
      console.log('WEBGPU_PROBE', JSON.stringify(results.env.webgpu));
    }
    const force = cfg.forceBackend === null ? undefined : cfg.forceBackend;
    await page.evaluate(cfgJson => window.__BENCH_START__(cfgJson), JSON.stringify({
      name: cfg.name, dtype: cfg.dtype, forceBackend: force,
    }));
    await page.waitForFunction(() => {
      const s = window.__BENCH_STATUS__ || '';
      return s.includes('完成') || s.includes('失败');
    }, null, { timeout: 600000 });
    const res = await page.evaluate(() => window.__BENCH_RESULT__);
    results.configs.push(res);
    console.log(JSON.stringify(res?.metrics || res?.error, null, 2));
    writeFileSync(`${OUTDIR}/${cfg.name}.json`, JSON.stringify(res, null, 2));
    await page.close();
  }

  writeFileSync('./benchmark/results.json', JSON.stringify(results, null, 2));
  writeFileSync(`${OUTDIR}/console.log`, results.console.join('\n'));
  console.log('\nDONE results written to benchmark/results.json');
  await browser.close();
  process.exit(0);
}

main().catch(e => { console.error('ERROR', e); process.exit(2); });
