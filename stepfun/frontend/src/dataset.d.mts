export interface CorpusDoc { id: string; text: string; topic: string; }
export interface QueryItem { q: string; rel: string[]; }
export const BENCH_KB: string;
export const CORPUS: CorpusDoc[];
export const QUERIES: QueryItem[];
export function evaluate(retrievedIds: string[], relevantIds: string[], K: number): { recall: number; ndcg: number; hits: string[] };
export function median(arr: number[]): number;
