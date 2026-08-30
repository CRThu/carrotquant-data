import React, { useState, useEffect, useMemo } from 'react';
import { DATA_SOURCE_OPTIONS, type ColorMode } from '../types/api';
import { useMarketData } from '../hooks/useMarketData';
import { DataTable } from '../components/DataTable';
import { Table, RefreshCw, AlertCircle, Loader2 } from 'lucide-react';
import { SearchInput } from '../components/SearchInput';
import { apiClient } from '../services/apiClient';

interface DataMatrixViewProps {
  currentTableId: string;
  selectedSymbol: string;
  onTableChange?: (tableId: string) => void;
  onSymbolChange?: (symbol: string) => void;
  colorMode?: ColorMode;
}

export const DataMatrixView: React.FC<DataMatrixViewProps> = ({
  currentTableId,
  selectedSymbol,
  onTableChange,
  onSymbolChange,
  colorMode = 'redUpGreenDown',
}) => {
  const { loading, error, matrixRaw, refreshData } = useMarketData(currentTableId, selectedSymbol, colorMode);

  const [activeTableId, setActiveTableId] = useState<string>(currentTableId);
  const [symbolInput, setSymbolInput] = useState<string>(selectedSymbol);
  const [dynamicTables, setDynamicTables] = useState<string[]>([]);
  const [page, setPage] = useState<number>(1);
  const pageSize = 50; // 矩阵切片单页 50 行，纯前端 0ms 无缝切页

  useEffect(() => {
    setActiveTableId(currentTableId);
    setPage(1);
  }, [currentTableId]);

  useEffect(() => {
    setSymbolInput(selectedSymbol);
    setPage(1);
  }, [selectedSymbol]);

  useEffect(() => {
    let isMounted = true;
    apiClient.listTables().then((res) => {
      if (isMounted && res && res.tables) {
        const tableIds = res.tables.map((t: any) => (typeof t === 'string' ? t : t.table_id));
        setDynamicTables(tableIds);
      }
    }).catch(() => {});
    return () => { isMounted = false; };
  }, []);

  const handleTableSelect = (tid: string) => {
    setActiveTableId(tid);
    setPage(1);
    if (onTableChange) onTableChange(tid);
  };

  const handleSymbolSelect = (sym: string) => {
    const clean = sym.trim().toLowerCase();
    setSymbolInput(clean);
    setPage(1);
    if (onSymbolChange) onSymbolChange(clean);
  };

  // 核心优化：直接共享 K 线页已拉取到的原始 2D List 矩阵，进行纯内存极速切片，0 次 HTTP 发包
  const slicedMatrix = useMemo(() => {
    if (!matrixRaw || !matrixRaw.data) return null;

    const total = matrixRaw.data.length;
    const totalPages = Math.ceil(total / pageSize) || 1;
    const safePage = Math.min(page, totalPages);
    const offset = (safePage - 1) * pageSize;
    const pageData = matrixRaw.data.slice(offset, offset + pageSize);

    return {
      table_id: matrixRaw.table_id || activeTableId,
      total: total,
      page: safePage,
      page_size: pageSize,
      total_pages: totalPages,
      count: pageData.length,
      columns: matrixRaw.columns || [],
      data: pageData,
    };
  }, [matrixRaw, page, activeTableId, pageSize]);

  // 快捷可搜索的数据源列表 (预定义表 + 动态磁盘发现的自定义表)
  const tableSearchItems = useMemo(() => {
    const knownSet = new Set(DATA_SOURCE_OPTIONS.map((opt) => opt.table_id));
    const items = DATA_SOURCE_OPTIONS.map((opt) => ({
      code: opt.table_id,
      name: opt.name,
      subText: opt.source.toUpperCase(),
    }));

    // 追加未在预定义中的外部自定义表
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
    <div className="h-full flex flex-col space-y-3 overflow-hidden animate-in fade-in duration-300">
      {/* 视图 Header: 统一格式的工作区表头 */}
      <div className="bg-slate-900/60 p-3 rounded-2xl border border-slate-800 flex flex-col lg:flex-row lg:items-center justify-between gap-3 shrink-0">
        <div className="flex items-center space-x-3">
          <div className="p-2 bg-cyan-950/60 rounded-xl border border-cyan-800/50 text-cyan-400">
            <Table className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h1 className="text-sm font-bold text-slate-100">数据矩阵</h1>
              <span className="text-[10px] font-mono bg-cyan-950 text-cyan-400 border border-cyan-800/60 px-2 py-0.5 rounded-full">
                {symbolInput}
              </span>
              {loading && (
                <span className="flex items-center space-x-1 text-[10px] font-mono bg-amber-950/80 text-amber-400 border border-amber-800/60 px-2 py-0.5 rounded-full animate-pulse">
                  <Loader2 className="w-3 h-3 animate-spin" />
                  <span>矩阵加载中...</span>
                </span>
              )}
            </div>
            <p className="text-[10px] text-slate-400 mt-0.5">
              物理存储字段投影与数据切片明细
            </p>
          </div>
        </div>

        {/* 搜表与搜代码控制 */}
        <div className="flex flex-wrap items-center gap-2">
          {/* 数据表选择与搜索 */}
          <div className="w-44 sm:w-52">
            <SearchInput
              items={tableSearchItems}
              placeholder="切换数据表..."
              value={activeTableId}
              onSelect={(item) => handleTableSelect(item.code)}
            />
          </div>

          {/* 标的代码/名称/拼音选择 */}
          <div className="w-48 sm:w-56">
            <SearchInput
              value={symbolInput}
              onChange={setSymbolInput}
              placeholder="搜索代码/拼音 (如 00 / 600000)..."
              onSelect={(item) => handleSymbolSelect(item.code)}
            />
          </div>

          <button
            onClick={refreshData}
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

      {/* 主矩阵表格 (全量数据共享 + 0ms 纯前端极速切片) */}
      <div className="flex-1 min-h-0 w-full overflow-hidden">
        <DataTable
          matrix={slicedMatrix}
          loading={loading}
          colorMode={colorMode}
          onPageChange={(newPage) => setPage(newPage)}
        />
      </div>
    </div>
  );
};

export default DataMatrixView;
