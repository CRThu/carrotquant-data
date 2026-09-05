import axios from 'axios';
import type {
  QueryMatrixResponse,
  TablesResponse,
  SyncRequestPayload,
  SyncTaskResponse,
  TableDetailedMeta,
  SyncStatusResponse,
  TdxCheckResponse,
  FileSystemListResponse,
} from '../types/api';

/**
 * Axios API 客户端，封装与 CarrotQuant.Data FastAPI 后端的交互
 */
const api = axios.create({
  baseURL: typeof window !== 'undefined' ? '/api/v1' : 'http://localhost:8888/api/v1',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// 在途 HTTP GET 请求去重与 Promise 共享 map (解决并发重复发包造成的后端 CPU 竞争与卡顿)
const inFlightPromises = new Map<string, Promise<any>>();

function deduplicateGet<T>(key: string, fetcher: () => Promise<T>): Promise<T> {
  if (inFlightPromises.has(key)) {
    return inFlightPromises.get(key) as Promise<T>;
  }
  const promise = fetcher().finally(() => {
    inFlightPromises.delete(key);
  });
  inFlightPromises.set(key, promise);
  return promise;
}

export const apiClient = {
  /**
   * 健康检查
   */
  async getHealth() {
    const res = await api.get('/health');
    return res.data;
  },

  /**
   * 获取所有本地已建立的数据表总览
   */
  async listTables(format: string = 'auto'): Promise<TablesResponse> {
    return deduplicateGet(`listTables:${format}`, async () => {
      const res = await api.get('/tables', { params: { format } });
      return res.data;
    });
  },

  /**
   * 获取某数据表包含的 Symbol 代码清单
   */
  async listSymbols(tableId: string, format: string = 'auto') {
    return deduplicateGet(`listSymbols:${tableId}:${format}`, async () => {
      const res = await api.get(`/tables/${tableId}/symbols`, { params: { format } });
      return res.data;
    });
  },

  /**
   * 获取某数据表的时间跨度
   */
  async getTimeRange(tableId: string, format: string = 'auto') {
    return deduplicateGet(`getTimeRange:${tableId}:${format}`, async () => {
      const res = await api.get(`/tables/${tableId}/time_range`, { params: { format } });
      return res.data;
    });
  },

  /**
   * 统一切片查询接口 (GET /api/v1/query)，集成在途请求合并 deduplication
   */
  async queryData(params: {
    table_id: string;
    symbols?: string;
    board_code?: string;
    start_date?: string;
    end_date?: string;
    columns?: string;
    format?: string;
    page?: number;
    page_size?: number;
  }): Promise<QueryMatrixResponse> {
    const key = `queryData:${JSON.stringify(params)}`;
    return deduplicateGet(key, async () => {
      const res = await api.get('/query', { params });
      return res.data;
    });
  },

  /**
   * 极速获取概念/行业板块列表及成分股计数 (轻量 20KB 数据包)
   */
  async getConceptBoards(params: {
    table_id: string;
    query?: string;
    page?: number;
    page_size?: number;
    format?: string;
  }): Promise<{
    table_id: string;
    total: number;
    page: number;
    page_size: number;
    total_pages: number;
    boards: { board_code: string; board_name: string; stock_count: number }[];
  }> {
    const key = `getConceptBoards:${JSON.stringify(params)}`;
    return deduplicateGet(key, async () => {
      const res = await api.get(`/tables/${params.table_id}/boards`, { params });
      return res.data;
    });
  },

  /**
   * 获取所有数据表及其各存储格式的详细物理元数据
   */
  async getDetailedTables(): Promise<{ tables: TableDetailedMeta[]; total: number }> {
    return deduplicateGet('getDetailedTables', async () => {
      const res = await api.get('/tables/detailed');
      return res.data;
    });
  },

  /**
   * 异步触发后台同步任务
   */
  async triggerSync(payload: SyncRequestPayload): Promise<SyncTaskResponse> {
    const res = await api.post('/sync', payload);
    return res.data;
  },

  /**
   * 获取正在运行的后台同步任务列表
   */
  async getActiveTasks() {
    const res = await api.get('/tasks');
    return res.data;
  },

  /**
   * 获取所有同步任务的详细精准状态与进度 (含 current, total, percentage, symbol)
   */
  async getSyncStatus(): Promise<SyncStatusResponse> {
    const res = await api.get('/sync/status');
    return res.data;
  },

  /**
   * 检查通达信 vipdoc 本地路径状态
   */
  async checkTdxPath(vipdoc_dir: string = 'C:\\new_tdx\\vipdoc'): Promise<TdxCheckResponse> {
    const res = await api.get('/tdx/check', { params: { vipdoc_dir } });
    return res.data;
  },

  /**
   * 触发后台下载并部署通达信官方全量日线包 hsjday.zip
   */
  async downloadTdxZip(vipdoc_dir: string = 'C:\\new_tdx\\vipdoc') {
    const res = await api.post('/tdx/download', { vipdoc_dir });
    return res.data;
  },

  /**
   * 通用本地文件系统探查，获取指定路径下的文件与子目录列表
   */
  async getDirectoryContents(path?: string): Promise<FileSystemListResponse> {
    const res = await api.get('/filesystem/list', { params: path ? { path } : {} });
    return res.data;
  },

  /**
   * 写入/导入自定义数据表
   */
  async writeTable(payload: {
    table_id: string;
    data: Record<string, any>[];
    category?: string;
    formats?: string[];
    mode?: string;
    sort_keys?: string[];
  }) {
    const res = await api.post('/write', payload);
    return res.data;
  },


  /**
   * 创建 SSE (Server-Sent Events) 日志流 EventSource 连接
   */
  createLogEventSource(): EventSource {
    const sseUrl = typeof window !== 'undefined' ? '/api/v1/logs/stream' : 'http://localhost:8888/api/v1/logs/stream';
    return new EventSource(sseUrl);
  },

  /**
   * 创建 SSE (Server-Sent Events) 同步任务实时进度推流 EventSource 连接
   */
  createSyncEventSource(): EventSource {
    const sseUrl = typeof window !== 'undefined' ? '/api/v1/sync/stream' : 'http://localhost:8888/api/v1/sync/stream';
    return new EventSource(sseUrl);
  },
};


