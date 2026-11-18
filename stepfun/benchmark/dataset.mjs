/**
 * 固定评测语料与查询集（固定随机种子，保证可复现）
 * 覆盖 4 个主题，共 24 篇文档，12 条查询，每条查询标注相关文档 id。
 */
export const BENCH_KB = 'benchmark_kb';

export const CORPUS = [
  // 主题：向量数据库
  { id: 'v1', text: 'seekdb 是一个支持向量检索和全文检索的数据库，提供 HNSW 索引和混合排序能力。', topic: 'vector' },
  { id: 'v2', text: '向量数据库通过近似最近邻搜索实现高维向量的高效相似度查询，常用于语义检索。', topic: 'vector' },
  { id: 'v3', text: 'HNSW 分层可导航小世界图是一种高效的近似最近邻索引结构，查询复杂度为对数级。', topic: 'vector' },
  { id: 'v4', text: '余弦相似度是向量检索中常用的距离度量，通过向量夹角衡量语义相关性。', topic: 'vector' },
  { id: 'v5', text: '混合检索结合关键词全文检索与语义向量检索，使用 RRF 倒数排名融合进行重排序。', topic: 'vector' },
  { id: 'v6', text: 'Embedding 模型将文本映射为固定维度的稠密向量，语义相近的文本向量距离更近。', topic: 'vector' },

  // 主题：浏览器AI
  { id: 'b1', text: 'Transformers.js 可以在浏览器中运行 ONNX 模型，实现完全本地的推理和 embedding 计算。', topic: 'browser' },
  { id: 'b2', text: 'WebGPU 是现代浏览器提供的图形与通用计算 API，可为深度学习推理提供硬件加速。', topic: 'browser' },
  { id: 'b3', text: '当 WebGPU 不可用时，ONNX Runtime Web 会自动降级到 WASM 后端执行推理。', topic: 'browser' },
  { id: 'b4', text: 'INT8 量化通过降低模型权重精度，将模型体积减少约四分之三，显著加快下载速度。', topic: 'browser' },
  { id: 'b5', text: '浏览器本地推理保护数据隐私，因为用户文档无需上传到云端服务器即可完成向量化。', topic: 'browser' },
  { id: 'b6', text: '模型预热是指先用少量样本推理一次，让运行时完成初始化，降低后续推理的首次延迟。', topic: 'browser' },

  // 主题：OceanBase
  { id: 'o1', text: 'OceanBase 是分布式关系型数据库，支持 MySQL 兼容协议和多租户架构。', topic: 'oceanbase' },
  { id: 'o2', text: 'seekdb 是 OceanBase 团队推出的轻量嵌入式数据库，可在本地进程中直接运行。', topic: 'oceanbase' },
  { id: 'o3', text: '嵌入式数据库无需单独部署服务进程，安装依赖后即可在本地文件中存储数据。', topic: 'oceanbase' },
  { id: 'o4', text: '数据库索引刷新使新写入的文档能够被近似最近邻检索立即命中。', topic: 'oceanbase' },
  { id: 'o5', text: '增量导入允许分批写入文档而无需重建整个数据库，适合大规模知识库场景。', topic: 'oceanbase' },
  { id: 'o6', text: '元数据过滤可以在检索时按知识库标识限定范围，防止不同知识库之间数据串扰。', topic: 'oceanbase' },

  // 主题：通用知识
  { id: 'g1', text: '知识库系统通过检索增强生成技术为大模型提供外部领域知识，减少幻觉。', topic: 'general' },
  { id: 'g2', text: 'RAG 系统通常包括文档切分、向量化、检索和答案生成四个主要阶段。', topic: 'general' },
  { id: 'g3', text: '文本切分将长文档按段落或固定长度分块，以适配模型的最大输入长度限制。', topic: 'general' },
  { id: 'g4', text: 'Recall@K 指标衡量检索结果前 K 条中命中相关文档的比例，用于评估检索质量。', topic: 'general' },
  { id: 'g5', text: 'nDCG@K 考虑相关文档的位置排序，对排在前面的相关文档给予更高权重。', topic: 'general' },
  { id: 'g6', text: '中位数对异常值不敏感，比平均值更适合报告包含冷启动开销的性能测试结果。', topic: 'general' },
];

/** 查询集：query 文本 + 相关文档 id（ground truth） */
export const QUERIES = [
  { q: '什么是 HNSW 近似最近邻索引', rel: ['v3', 'v1', 'v2'] },
  { q: '向量数据库如何做语义相似度检索', rel: ['v2', 'v1', 'v4', 'v6'] },
  { q: '浏览器里如何保护数据隐私地运行模型', rel: ['b5', 'b1', 'b4'] },
  { q: 'WebGPU 不可用时怎么办', rel: ['b3', 'b2'] },
  { q: 'INT8 量化能减少多少模型体积', rel: ['b4', 'b6'] },
  { q: '混合检索是怎么融合排序的', rel: ['v5', 'g1'] },
  { q: 'seekdb 嵌入式数据库需要部署服务吗', rel: ['o2', 'o3', 'o1'] },
  { q: '增量导入和索引刷新', rel: ['o5', 'o4'] },
  { q: '不同知识库如何防止数据串扰', rel: ['o6', 'o3'] },
  { q: 'RAG 系统有哪些阶段', rel: ['g2', 'g1', 'g3'] },
  { q: '如何评估检索结果质量 Recall nDCG', rel: ['g4', 'g5'] },
  { q: '为什么性能测试要报告中位数', rel: ['g6'] },
];

/** Recall@K 与 nDCG@K 计算 */
export function evaluate(retrievedIds, relevantIds, K) {
  const top = retrievedIds.slice(0, K);
  const hits = top.filter(id => relevantIds.includes(id));
  const recall = relevantIds.length ? hits.length / relevantIds.length : 0;
  let dcg = 0;
  top.forEach((id, i) => {
    if (relevantIds.includes(id)) dcg += 1 / Math.log2(i + 2);
  });
  const ideal = Math.min(relevantIds.length, K);
  let idcg = 0;
  for (let i = 0; i < ideal; i++) idcg += 1 / Math.log2(i + 2);
  const ndcg = idcg ? dcg / idcg : 0;
  return { recall, ndcg, hits };
}

export function median(arr) {
  const s = [...arr].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}
