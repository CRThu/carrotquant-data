/**
 * CarrotQuant.Data Web 前端 TypeScript 类型契约
 */

// 权威数据源元数据字典 (SSOT)
export interface DataSourceMeta {
  key: string;
  name: string;
  shortName: string;
  badgeClass: string;
  description: string;
}

export const DATA_SOURCE_METAS: Record<string, DataSourceMeta> = {
  baostock: {
    key: 'baostock',
    name: 'Baostock',
    shortName: '证券宝',
    badgeClass: 'bg-emerald-950/80 text-emerald-400 border-emerald-800/60',
    description: '历史日线、5分钟线与复权因子',
  },
  tdx: {
    key: 'tdx',
    name: '通达信 (TDX)',
    shortName: '通达信',
    badgeClass: 'bg-rose-950/80 text-rose-400 border-rose-800/60',
    description: '本地 vipdoc 直读与在线日线/分时',
  },
  stockdb: {
    key: 'stockdb',
    name: 'StockDB',
    shortName: 'StockDB',
    badgeClass: 'bg-purple-950/80 text-purple-400 border-purple-800/60',
    description: 'LevelDB 引擎 1分钟高频、全生命周期与截面因子',
  },
  eastmoney: {
    key: 'eastmoney',
    name: '东方财富',
    shortName: '东财',
    badgeClass: 'bg-amber-950/80 text-amber-400 border-amber-800/60',
    description: '概念/行业板块映射与龙虎榜/机构席位',
  },
  custom: {
    key: 'custom',
    name: '外部导入',
    shortName: '自定义',
    badgeClass: 'bg-slate-800/80 text-slate-300 border-slate-700/60',
    description: '本地自定义导入的 CSV/Parquet 表',
  },
};

// 物理存储表支持的数据源分类与模板表 ID
export interface DataSourceOption {
  id: string;
  name: string;
  table_id: string;
  category: 'ashare' | 'aetf' | 'aindex' | 'concept' | 'dragon_tiger' | 'inst_trade' | 'adj_factor';
  source: 'baostock' | 'eastmoney' | 'tdx' | 'stockdb';
  description: string;
}

// 预定义常用的金融终端数据源选项 (全量 24 个内置数据表)
export const DATA_SOURCE_OPTIONS: DataSourceOption[] = [
  // Baostock 6 表
  {
    id: 'ashare_kline_1d_raw_baostock',
    name: 'Baostock · A股日线 (不复权)',
    table_id: 'ashare.kline.1d.raw.baostock',
    category: 'ashare',
    source: 'baostock',
    description: '个股日线 OHLCV 数据，按 [symbol, year] CSV/Parquet 分片'
  },
  {
    id: 'ashare_kline_1d_adj_baostock',
    name: 'Baostock · A股日线 (后复权)',
    table_id: 'ashare.kline.1d.adj.baostock',
    category: 'ashare',
    source: 'baostock',
    description: '个股后复权 K 线数据'
  },
  {
    id: 'ashare_kline_5m_raw_baostock',
    name: 'Baostock · A股5分钟 (不复权)',
    table_id: 'ashare.kline.5m.raw.baostock',
    category: 'ashare',
    source: 'baostock',
    description: '个股高频 5 分钟 K 线数据'
  },
  {
    id: 'ashare_kline_5m_adj_baostock',
    name: 'Baostock · A股5分钟 (后复权)',
    table_id: 'ashare.kline.5m.adj.baostock',
    category: 'ashare',
    source: 'baostock',
    description: '个股高频 5 分钟后复权 K 线数据'
  },
  {
    id: 'aindex_kline_1d_raw_baostock',
    name: 'Baostock · 指数日线 (不复权)',
    table_id: 'aindex.kline.1d.raw.baostock',
    category: 'aindex',
    source: 'baostock',
    description: '大盘与主要指数日线 OHLCV 数据'
  },
  {
    id: 'ashare_adj_factor_baostock',
    name: 'Baostock · A股后复权因子',
    table_id: 'ashare.adj_factor.baostock',
    category: 'adj_factor',
    source: 'baostock',
    description: '个股历史除权除息与后复权因子 (Event 表)'
  },
  // TDX (通达信) 6 表
  {
    id: 'ashare_kline_1d_raw_tdx',
    name: '通达信 · A股日线 (不复权)',
    table_id: 'ashare.kline.1d.raw.tdx',
    category: 'ashare',
    source: 'tdx',
    description: '通达信本地 vipdoc 或在线日线数据'
  },
  {
    id: 'ashare_kline_5m_raw_tdx',
    name: '通达信 · A股5分钟 (不复权)',
    table_id: 'ashare.kline.5m.raw.tdx',
    category: 'ashare',
    source: 'tdx',
    description: '通达信本地 vipdoc 或在线 5 分钟线数据'
  },
  {
    id: 'ashare_kline_1m_raw_tdx',
    name: '通达信 · A股1分钟 (不复权)',
    table_id: 'ashare.kline.1m.raw.tdx',
    category: 'ashare',
    source: 'tdx',
    description: '通达信本地 vipdoc 或在线 1 分钟超高频数据'
  },
  {
    id: 'aindex_kline_1d_raw_tdx',
    name: '通达信 · 指数日线 (不复权)',
    table_id: 'aindex.kline.1d.raw.tdx',
    category: 'aindex',
    source: 'tdx',
    description: '通达信大盘与主要指数日线数据'
  },
  {
    id: 'aindex_kline_5m_raw_tdx',
    name: '通达信 · 指数5分钟 (不复权)',
    table_id: 'aindex.kline.5m.raw.tdx',
    category: 'aindex',
    source: 'tdx',
    description: '通达信大盘与主要指数 5 分钟线数据'
  },
  {
    id: 'aindex_kline_1m_raw_tdx',
    name: '通达信 · 指数1分钟 (不复权)',
    table_id: 'aindex.kline.1m.raw.tdx',
    category: 'aindex',
    source: 'tdx',
    description: '通达信大盘与主要指数 1 分钟线数据'
  },
  // StockDB 8 表
  {
    id: 'ashare_kline_1d_raw_stockdb',
    name: 'StockDB · A股日线 (不复权/全截面因子)',
    table_id: 'ashare.kline.1d.raw.stockdb',
    category: 'ashare',
    source: 'stockdb',
    description: 'StockDB 本地个股日线 OHLCV 及全量截面多因子 (市值/估值/量比/ST)'
  },
  {
    id: 'ashare_kline_1m_raw_stockdb',
    name: 'StockDB · A股1分钟 (不复权)',
    table_id: 'ashare.kline.1m.raw.stockdb',
    category: 'ashare',
    source: 'stockdb',
    description: 'StockDB 本地 1 分钟高频 K 线数据 (含 900+ 退市股全生命周期)'
  },
  {
    id: 'ashare_adj_factor_stockdb',
    name: 'StockDB · A股后复权因子',
    table_id: 'ashare.adj_factor.stockdb',
    category: 'adj_factor',
    source: 'stockdb',
    description: 'StockDB 全量个股除权除息与后复权因子 (Event 表)'
  },
  {
    id: 'aetf_kline_1d_raw_stockdb',
    name: 'StockDB · 场内ETF日线 (不复权)',
    table_id: 'aetf.kline.1d.raw.stockdb',
    category: 'aetf',
    source: 'stockdb',
    description: 'StockDB 1/5 号段场内基金与 ETF 日线 OHLCV 行情'
  },
  {
    id: 'aetf_kline_1m_raw_stockdb',
    name: 'StockDB · 场内ETF 1分钟 (不复权)',
    table_id: 'aetf.kline.1m.raw.stockdb',
    category: 'aetf',
    source: 'stockdb',
    description: 'StockDB 1/5 号段场内基金与 ETF 1 分钟超高频行情'
  },
  {
    id: 'aetf_adj_factor_stockdb',
    name: 'StockDB · 场内ETF独立复权因子',
    table_id: 'aetf.adj_factor.stockdb',
    category: 'adj_factor',
    source: 'stockdb',
    description: 'StockDB 场内基金与 ETF 独立历史分红拆分复权因子 (Event 表)'
  },
  {
    id: 'ashare_concept_stockdb',
    name: 'StockDB · 同花顺概念板块',
    table_id: 'ashare.concept.stockdb',
    category: 'concept',
    source: 'stockdb',
    description: 'StockDB 1200+ 同花顺概念板块与成分股映射 (Event 表)'
  },
  {
    id: 'ashare_industry_stockdb',
    name: 'StockDB · 申万行业板块',
    table_id: 'ashare.industry.stockdb',
    category: 'concept',
    source: 'stockdb',
    description: 'StockDB 申万一/二/三级行业分类与成分股映射 (Event 表)'
  },
  // EastMoney 4 表
  {
    id: 'ashare_concept_eastmoney',
    name: '东方财富 · 概念板块成分',
    table_id: 'ashare.concept.eastmoney',
    category: 'concept',
    source: 'eastmoney',
    description: '东财概念板块代码与成分股映射 (Event 表)'
  },
  {
    id: 'ashare_industry_eastmoney',
    name: '东方财富 · 行业板块成分',
    table_id: 'ashare.industry.eastmoney',
    category: 'concept',
    source: 'eastmoney',
    description: '东财行业板块成分股映射 (Event 表)'
  },
  {
    id: 'ashare_dragon_tiger_eastmoney',
    name: '东方财富 · 龙虎榜每日明细',
    table_id: 'ashare.dragon_tiger.eastmoney',
    category: 'dragon_tiger',
    source: 'eastmoney',
    description: '机构与营业部每日上榜明细 (Event 表)'
  },
  {
    id: 'ashare_inst_trade_eastmoney',
    name: '东方财富 · 机构交易明细',
    table_id: 'ashare.inst_trade.eastmoney',
    category: 'inst_trade',
    source: 'eastmoney',
    description: '机构席位买卖交易明细 (Event 表)'
  }
];

// /api/v1/tables 接口返回的数据结构
export interface TableMeta {
  table_id: string;
  category: string;
}

export interface TablesResponse {
  tables: string[];
  total: number;
}

// /api/v1/query 端点返回的 2D 切片矩阵响应结构
export interface QueryMatrixResponse {
  table_id: string;
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  count: number;
  columns: string[];
  data: (string | number | boolean | null)[][];
}

// /api/v1/data/{market}/{category} 动态业务语义切片查询请求参数
export interface FetchMarketDataParams {
  market: string;
  category: string;
  symbols?: string;
  board_code?: string;
  freq?: string;
  adj?: string;
  start_date?: string;
  end_date?: string;
  columns?: string;
  source?: string;
  format?: string;
  page?: number;
  page_size?: number;
  order?: 'asc' | 'desc';
}

// /api/v1/data/{market}/{category} 动态业务语义切片响应结构 (兼容 QueryMatrixResponse 契约)
export interface DynamicMarketDataResponse {
  market: string;
  category: string;
  resolved_table_id?: string;
  table_id?: string;
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  count: number;
  columns: string[];
  data: (string | number | boolean | null)[][];
}

// TradingView Lightweight Charts 蜡烛图数据点契约
export interface OHLCBar {
  time: string; // YYYY-MM-DD 或 timestamp 秒/毫秒字符串
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  amount?: number;
}

// TradingView 柱状图 (成交量/MACD) 数据点
export interface HistogramBar {
  time: string;
  value: number;
  color?: string;
}

// TradingView 曲线 (MA/DIF/DEA) 数据点
export interface LineDataPoint {
  time: string;
  value: number;
}

// 买卖点/交易信号 Marker 标注定义
export interface BSMarkerItem {
  time: string;
  position: 'aboveBar' | 'belowBar' | 'inBar';
  color: string;
  shape: 'circle' | 'square' | 'arrowUp' | 'arrowDown';
  text: string;
  size?: number;
}

// MACD 计算结果集中契约
export interface MACDResult {
  dif: LineDataPoint[];
  dea: LineDataPoint[];
  macdBar: HistogramBar[];
}

// 均线数据集契约
export interface MovingAverageData {
  ma5: LineDataPoint[];
  ma10: LineDataPoint[];
  ma20: LineDataPoint[];
  ma60: LineDataPoint[];
}

// 方案 A 概念/行业板块在前端聚合的树形与成分股数据结构
export interface ConceptBoardItem {
  board_code: string;
  board_name: string;
  stock_count: number;
  stocks: {
    symbol: string;
    stock_name: string;
  }[];
}

// 同步任务请求体与状态结构
export interface SyncRequestPayload {
  table_ids: string[];
  formats?: string[];
  start_date?: string;
  end_date?: string;
  force_refresh?: boolean;
  batch_size?: number;
  symbol_limit?: number;
  provider_kwargs?: Record<string, any>;
}

export interface TdxCheckResponse {
  path: string;
  exists: boolean;
  symbol_count: number;
  valid: boolean;
}

export interface SyncTaskResponse {
  status: string;
  started_tasks: string[];
  ignored_tasks: string[];
  message: string;
}

// 终端配色偏好: 'redUpGreenDown' (A股红涨绿跌) | 'greenUpRedDown' (美股/国际绿涨红跌)
export type ColorMode = 'redUpGreenDown' | 'greenUpRedDown';

export interface UpDownColors {
  upColor: string;
  downColor: string;
}

export const getUpDownColors = (mode: ColorMode = 'redUpGreenDown'): UpDownColors => {
  if (mode === 'greenUpRedDown') {
    return { upColor: '#22c55e', downColor: '#ef4444' };
  }
  return { upColor: '#ef4444', downColor: '#22c55e' };
};

// 单格式 (Parquet / CSV) 的独立物理数据信息
export interface FormatDetailInfo {
  exists: boolean;
  updated_at: string | null;
  start_datetime: string | null;
  end_datetime: string | null;
  total_bars: number;
  symbol_count: number;
}

// 详细数据表元数据定义 (/api/v1/tables/detailed)
export interface TableDetailedMeta {
  table_id: string;
  name: string;
  category: 'timeseries' | 'event';
  source: string;
  description: string;
  formats: {
    parquet: FormatDetailInfo;
    csv: FormatDetailInfo;
  };
}

// 详细同步任务精准状态
export interface SyncStatusItem {
  table_id: string;
  status: 'idle' | 'running' | 'success' | 'failed';
  current: number;
  total: number;
  percentage: number;
  current_symbol: string;
  message?: string;
  start_time: number | null;
  end_time: number | null;
  error_msg: string | null;
}

export interface SyncStatusResponse {
  active_tasks: string[];
  statuses: Record<string, SyncStatusItem>;
}

// SSE / Log 视窗日志项
export interface LogMessage {
  timestamp: string;
  level: 'INFO' | 'DEBUG' | 'WARNING' | 'WARN' | 'ERROR' | 'SUCCESS' | string;
  message: string;
  name?: string;
  line?: number;
  time_raw?: number;
}

// 文件系统探查节点对象
export interface FileSystemItem {
  name: string;
  path: string;
  is_dir: boolean;
  size: number;
  updated_at: string;
}

export interface FileSystemListResponse {
  path: string;
  exists: boolean;
  is_dir: boolean;
  total: number;
  items: FileSystemItem[];
}

