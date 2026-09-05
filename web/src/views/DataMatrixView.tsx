import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { DATA_SOURCE_OPTIONS, type ColorMode, type QueryMatrixResponse } from '../types/api';
import { DataTable } from '../components/DataTable';
import { Table, RefreshCw, AlertCircle, Loader2, ArrowUpDown } from 'lucide-react';
import { SearchInput } from '../components/SearchInput';
import { apiClient } from '../services/apiClient';

interface DataMatrixViewProps {
  currentTableId: string;
  selectedSymbol: string;
  onTableChange?: (tableId: string) => void;
  onSymbolChange?: (symbol: string) => void;
  colorMode?: ColorMode;
}

// 解析 table_id 分解出业务维度
function parseTableIdDimensions(tid: string) {
  const parts = tid.split('.');
  const market = parts[0] || 'ashare';
  const category = parts[1] || (tid.includes('kline') ? 'kline' : 'timeseries');
  const freq = parts.find((p) => ['1d', '5m', '1m'].includes(p)) || '1d';
  const adj = parts.find((p) => ['raw', 'adj'].includes(p)) || 'raw';
  const source = parts[parts.length - 1] || 'baostock';
  return { market, category, freq, adj, source };
}

// 根据业务维度合成规范 table_id
function buildTableId(market: string, category: string, freq: string, adj: string, source: string) {
  if (category === 'kline') {
    return `${market}.kline.${freq}.${adj}.${source}`;
  }
  return `${market}.${category}.${source}`;
}

export const DataMatrixView: React.FC<DataMatrixViewProps> = ({
  currentTableId,
  selectedSymbol,
  onTableChange,
  onSymbolChange,
  colorMode = 'redUpGreenDown',
}) => {
  const [activeTableId, setActiveTableId] = useState<string>(currentTableId);
  const [symbolInput, setSymbolInput] = useState<string>(selectedSymbol);
  const [dynamicTables, setDynamicTables] = useState<string[]>([]);

  // 业务维度状态
  const initialDims = useMemo(() => parseTableIdDimensions(currentTableId), [currentTableId]);
  const [market, setMarket] = useState<string>(initialDims.market);
  const [category, setCategory] = useState<string>(initialDims.category);
  const [freq, setFreqState] = useState<string>(initialDims.freq);
  const [adj, setAdjState] = useState<string>(initialDims.adj);
  const [source, setSource] = useState<string>(initialDims.source);

  // 服务端真物理分页
  const [page, setPage] = useState<number>(1);
  const [pageSize] = useState<number>(50);
  const [sortOrder, setSortOrder] = useState<'desc' | 'asc'>('desc');
  const [matrixData, setMatrixData] = useState<QueryMatrixResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // 外部 Props 变更同步
  useEffect(() => {
    setActiveTableId(currentTableId);
    const d = parseTableIdDimensions(currentTableId);
    setMarket(d.market);
    setCategory(d.category);
    setFreqState(d.freq);
    setAdjState(d.adj);
    setSource(d.source);
    setPage(1);
  }, [currentTableId]);

  useEffect(() => {
    setSymbolInput(selectedSymbol);
    setPage(1);
  }, [selectedSymbol]);

  // 动态数据表列表探测
  useEffect(() => {
    let isMounted = true;
    apiClient
      .listTables()
      .then((res) => {
        if (isMounted && res && res.tables) {
          const tableIds = res.tables.map((t: any) => (typeof t === 'string' ? t : t.table_id));
          setDynamicTables(tableIds);
        }
      })
      .catch(() => {});
    return () => {
      isMounted = false;
    };
  }, []);

  // 维度切换
  const setFreq = useCallback(
    (newFreq: string) => {
      setFreqState(newFreq);
      const newTid = buildTableId(market, category, newFreq, adj, source);
      setActiveTableId(newTid);
      setPage(1);
      if (onTableChange) onTableChange(newTid);
    },
    [market, category, adj, source, onTableChange]
  );

  const setAdj = useCallback(
    (newAdj: string) => {
      setAdjState(newAdj);
      const newTid = buildTableId(market, category, freq, newAdj, source);
      setActiveTableId(newTid);
      setPage(1);
      if (onTableChange) onTableChange(newTid);
    },
    [market, category, freq, source, onTableChange]
  );

  const handleTableSelect = (tid: string) => {
    setActiveTableId(tid);
    const d = parseTableIdDimensions(tid);
    setMarket(d.market);
    setCategory(d.category);
    setFreqState(d.freq);
    setAdjState(d.adj);
    setSource(d.source);
    setPage(1);
    if (onTableChange) onTableChange(tid);
  };

  const handleSymbolSelect = (sym: string) => {
    const clean = sym.trim().toLowerCase();
    setSymbolInput(clean);
    setPage(1);
    if (onSymbolChange) onSymbolChange(clean);
  };

  // 核心：服务端权威物理分页查询（解除前端内存假切片20页的限制，直达全量数据）
  const fetchMatrix = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const isKline = category === 'kline' || activeTableId.includes('kline');
      let res: QueryMatrixResponse;

      if (isKline) {
        const dynamicRes = await apiClient.fetchMarketData({
          market,
          category: 'kline',
          symbols: symbolInput,
          freq,
          adj,
          source,
          page,
          page_size: pageSize,
          order: sortOrder,
        });
        res = {
          table_id: dynamicRes.resolved_table_id || dynamicRes.table_id || activeTableId,
          total: dynamicRes.total,
          page: dynamicRes.page,
          page_size: dynamicRes.page_size,
          total_pages: dynamicRes.total_pages,
          count: dynamicRes.count,
          columns: dynamicRes.columns,
          data: dynamicRes.data,
        };
      } else {
        res = await apiClient.queryData({
          table_id: activeTableId,
          symbols: symbolInput,
          page,
          page_size: pageSize,
          order: sortOrder,
        });
      }

      setMatrixData(res);
    } catch (err: any) {
      console.error('Failed to fetch matrix data:', err);
      setError(err?.response?.data?.detail || err?.message || '获取矩阵数据失败');
      setMatrixData(null);
    } finally {
      setLoading(false);
    }
  }, [market, category, symbolInput, freq, adj, source, page, pageSize, activeTableId, sortOrder]);

  useEffect(() => {
    fetchMatrix();
  }, [fetchMatrix]);

  // 快捷可搜索的数据源列表
  const tableSearchItems = useMemo(() => {
    const knownSet = new Set(DATA_SOURCE_OPTIONS.map((opt) => opt.table_id));
    const items = DATA_SOURCE_OPTIONS.map((opt) => ({
      code: opt.table_id,
      name: opt.name,
      subText: opt.source.toUpperCase(),
    }));

    dynamicTables.forEach((tid) => {
      if (!knownSet.has(tid)) {
        items.push({
          code: tid,
          name: `自定义表 (${tid})`,
          subText: 'CUSTOM',
        });
      }
    });

    return items;
  }, [dynamicTables]);

  return (
    <div className="h-full flex flex-col space-y-2 overflow-hidden animate-in fade-in duration-300">
      {/* 视图 Header: 统一格式的工作区表头 (带 shrink-0 min-w-max 防挤压折行) */}
      <div className="bg-slate-900/60 p-3 rounded-2xl border border-slate-800 flex flex-col lg:flex-row lg:items-center justify-between gap-3 shrink-0">
        <div className="flex items-center space-x-3 shrink-0 min-w-max">
          <div className="p-2 bg-cyan-950/60 rounded-xl border border-cyan-800/50 text-cyan-400 shrink-0">
            <Table className="w-5 h-5" />
          </div>
          <div className="shrink-0">
            <div className="flex items-center space-x-2 flex-nowrap">
              <h1 className="text-sm font-bold text-slate-100 tracking-wide whitespace-nowrap">数据矩阵</h1>
              <span className="text-[10px] font-mono bg-cyan-950 text-cyan-400 border border-cyan-800/60 px-2 py-0.5 rounded-full whitespace-nowrap shrink-0">
                {symbolInput}
              </span>
              <span className="text-[10px] font-mono text-slate-400 hidden xl:inline whitespace-nowrap">
                ({activeTableId})
              </span>
              {loading && (
                <span className="flex items-center space-x-1 text-[10px] font-mono bg-amber-950/80 text-amber-400 border border-amber-800/60 px-2 py-0.5 rounded-full shrink-0 whitespace-nowrap animate-pulse">
                  <Loader2 className="w-3 h-3 animate-spin" />
                  <span>加载中...</span>
                </span>
              )}
            </div>
            <p className="text-[10px] text-slate-400 mt-0.5 whitespace-nowrap">
              物理存储字段投影与数据切片明细 · 共 <span className="text-cyan-400 font-mono font-bold">{matrixData?.total ?? 0}</span> 条记录 (共 <span className="text-amber-400 font-mono font-bold">{matrixData?.total_pages ?? 0}</span> 页)
            </p>
          </div>
        </div>

        {/* 搜表与搜代码控制组 */}
        <div className="flex flex-wrap items-center gap-2">
          {/* 行情类数据周期与复权切换胶囊 */}
          {(category === 'kline' || activeTableId.includes('kline')) && (
            <>
              <div className="flex items-center bg-slate-950 p-0.5 rounded-xl border border-slate-800 text-[11px] font-mono">
                {[
                  { key: '1d', label: '日线' },
                  { key: '5m', label: '5分' },
                  { key: '1m', label: '1分' },
                ].map((f) => (
                  <button
                    key={f.key}
                    onClick={() => setFreq(f.key)}
                    className={`px-2 py-1 rounded-lg transition-colors cursor-pointer ${
                      freq === f.key
                        ? 'bg-cyan-950 text-cyan-300 font-bold border border-cyan-800/80'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    {f.label}
                  </button>
                ))}
              </div>

              <div className="flex items-center bg-slate-950 p-0.5 rounded-xl border border-slate-800 text-[11px] font-mono">
                {[
                  { key: 'raw', label: '不复权' },
                  { key: 'adj', label: '后复权' },
                ].map((a) => (
                  <button
                    key={a.key}
                    onClick={() => setAdj(a.key)}
                    className={`px-2 py-1 rounded-lg transition-colors cursor-pointer ${
                      adj === a.key
                        ? 'bg-amber-950 text-amber-300 font-bold border border-amber-800/80'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    {a.label}
                  </button>
                ))}
              </div>
            </>
          )}

          {/* 排序规则切换胶囊 */}
          <button
            onClick={() => {
              const next = sortOrder === 'desc' ? 'asc' : 'desc';
              setSortOrder(next);
              setPage(1);
            }}
            className="px-2.5 py-1 bg-slate-950 hover:bg-slate-800 border border-slate-800 text-[11px] font-mono text-slate-300 rounded-xl transition-colors cursor-pointer flex items-center space-x-1.5 shrink-0"
            title="切换时间排序规则 (最新降序 / 最早升序)"
          >
            <ArrowUpDown className="w-3.5 h-3.5 text-cyan-400" />
            <span>{sortOrder === 'desc' ? '最新降序' : '最早升序'}</span>
          </button>

          {/* 数据表选择与搜索 */}
          <div className="w-36 sm:w-44">
            <SearchInput
              items={tableSearchItems}
              placeholder="切换数据表..."
              value={activeTableId}
              onSelect={(item) => handleTableSelect(item.code)}
            />
          </div>

          {/* 标的代码/名称/拼音选择 */}
          <div className="w-36 sm:w-44">
            <SearchInput
              value={symbolInput}
              onChange={setSymbolInput}
              placeholder="搜索代码/拼音..."
              onSelect={(item) => handleSymbolSelect(item.code)}
            />
          </div>

          <button
            onClick={fetchMatrix}
            disabled={loading}
            className="p-2 bg-slate-950 hover:bg-slate-800 text-slate-300 rounded-xl border border-slate-800 transition-colors cursor-pointer disabled:opacity-50 shrink-0"
            title="刷新矩阵数据"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {error && (
        <div className="p-2.5 bg-red-950/40 border border-red-800/60 rounded-xl text-xs text-red-300 flex items-center space-x-2 shrink-0">
          <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* 主矩阵表格: 服务端全量真实物理分页 */}
      <div className="flex-1 min-h-0 w-full overflow-hidden">
        <DataTable
          matrix={matrixData}
          loading={loading}
          colorMode={colorMode}
          onPageChange={(newPage) => setPage(newPage)}
        />
      </div>
    </div>
  );
};

export default DataMatrixView;
