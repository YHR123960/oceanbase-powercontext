/**
 * init-db.js — 预初始化 seekdb 数据库目录
 * 在干净环境首次部署时先跑一次：npm run init
 * 之后 server 启动时复用目录，open 只需数秒。
 */
import { initDb, log } from './db.js';
import { DB_DIR } from './db.js';

const t0 = performance.now();
await initDb();
log('DB_PREINIT_DONE', { dbDir: DB_DIR, totalMs: Math.round(performance.now() - t0) });
console.log(`[init] database ready at ${DB_DIR}`);
// 原生 addon 后台线程会阻止自然退出，显式退出
setTimeout(() => process.exit(0), 300);
