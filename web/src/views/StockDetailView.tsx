import React, { useState } from 'react';
import { useMarketData } from '../hooks/useMarketData';
import { TradingViewKLineChart } from '../components/TradingViewKLineChart';
import { ErrorBoundary } from '../components/ErrorBoundary';
import { BarChart2, Table, RefreshCw, AlertCircle, Loader2 } from 'lucide-react';
import type { ColorMode } from '../types/api';
import { SearchInput } from '../components/SearchInput';

interface StockDetailViewProps {
  currentTableId: string;
  selectedSymbol: string;
  onSymbolChange?: (symbol: string) => void;
  onTableChange?: (tableId: string) => void;
  onOpenMatrix?: () => void;
  colorMode?: ColorMode;
}

export const StockDetailView: React.FC<StockDetailViewProps> = ({
  currentTableId,
  selectedSymbol,
  onSymbolChange,
  onTableChange,
  onOpenMatrix,
  colorMode = 'redUpGreenDown',
}) => {
  const {
    tableId,
    freq,
    setFreq,
    adj,
    setAdj,
    source,
    setSource,
    symbol,
    loading,
    error,
    ohlcBars,
    volumeBars,
    maData,
    refreshData,
    hasMoreHistory,
    isLoadingMore,
    loadMoreHistory,
    resetView,
    prependCount,
  } = useMarketData(currentTableId, selectedSymbol, colorMode);

  const [symbolInput, setSymbolInput] = useState<string>(selectedSymbol);

  // 当内部 tableId 发生变化时通知上层（如跳转数据矩阵需要）
  React.useEffect(() => {
    if (onTableChange && tableId) {
      onTableChange(tableId);
    }
  }, [tableId, onTableChange]);

  const handleSymbolSelect = (sym: string) => {
    setSymbolInput(sym);
    if (onSymbolChange) {
      onSymbolChange(sym.trim().toLowerCase());
    }
  };

  return (
    <div className="h-full flex flex-col space-y-2 overflow-hidden animate-in fade-in duration-300">
      {/* 视图页头: 统一风格的工作区表头 */}
      <div className="bg-slate-900/60 p-3 rounded-2xl border border-slate-800 flex flex-col lg:flex-row lg:items-center justify-between gap-3 shrink-0">
        <div className="flex items-center space-x-3 shrink-0 min-w-max">
          <div className="p-2 bg-cyan-950/60 rounded-xl border border-cyan-800/50 text-cyan-400 shrink-0">
            <BarChart2 className="w-5 h-5" />
          </div>
          <div className="shrink-0">
            <div className="flex items-center space-x-2 flex-nowrap">
              <h1 className="text-sm font-bold text-slate-100 tracking-wide whitespace-nowrap">K 线行情</h1>
              <span className="text-[10px] font-mono bg-cyan-950 text-cyan-400 border border-cyan-800/60 px-2 py-0.5 rounded-full whitespace-nowrap shrink-0">
                {symbol}
              </span>
              <span className="text-[10px] font-mono text-slate-400 hidden xl:inline whitespace-nowrap">
                ({tableId})
              </span>
              {loading && (
                <span className="flex items-center space-x-1 text-[10px] font-mono bg-amber-950/80 text-amber-400 border border-amber-800/60 px-2 py-0.5 rounded-full shrink-0 whitespace-nowrap animate-pulse">
                  <Loader2 className="w-3 h-3 animate-spin" />
                  <span>加载中...</span>
                </span>
              )}
              {isLoadingMore && (
                <span className="flex items-center space-x-1 text-[10px] font-mono bg-cyan-950/80 text-cyan-400 border border-cyan-800/60 px-2 py-0.5 rounded-full shrink-0 whitespace-nowrap">
                  <Loader2 className="w-3 h-3 animate-spin" />
                  <span>加载更早历史...</span>
                </span>
              )}
            </div>
            <p className="text-[10px] text-slate-400 mt-0.5 whitespace-nowrap">
              按时间序列展现 OHLC 与成交量明细 · 已加载 <span className="text-amber-400 font-mono font-bold">{ohlcBars.length}</span> 条{hasMoreHistory ? ' (向左滑动加载历史)' : ' (已是全部历史)'}
            </p>
          </div>
        </div>

        {/* 金融级三组核心控制组: 数据源 | 周期 | 复权 + 标的搜索 */}
        <div className="flex flex-wrap items-center gap-2">
          {/* 1. 数据源选择器 */}
          <div className="flex items-center bg-slate-950 p-0.5 rounded-xl border border-slate-800 text-[11px] font-mono">
            {[
              { key: 'baostock', label: 'Baostock' },
              { key: 'tdx', label: '通达信' },
              { key: 'stockdb', label: 'StockDB' },
            ].map((s) => (
              <button
                key={s.key}
                onClick={() => setSource(s.key)}
                className={`px-2 py-1 rounded-lg transition-colors cursor-pointer ${
                  source === s.key
                    ? 'bg-cyan-950 text-cyan-300 font-bold border border-cyan-800/80 shadow-xs'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {s.label}
              </button>
            ))}
          </div>

          {/* 2. K线周期选择器 */}
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
                    ? 'bg-cyan-950 text-cyan-300 font-bold border border-cyan-800/80 shadow-xs'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>

          {/* 3. 复权模式选择器 */}
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
                    ? 'bg-amber-950 text-amber-300 font-bold border border-amber-800/80 shadow-xs'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {a.label}
              </button>
            ))}
          </div>

          {/* 代码搜索与选择 */}
          <div className="w-36 sm:w-48">
            <SearchInput
              value={symbolInput}
              onChange={setSymbolInput}
              placeholder="搜索代码/拼音..."
              onSelect={(item) => handleSymbolSelect(item.code)}
            />
          </div>

          {onOpenMatrix && (
            <button
              onClick={onOpenMatrix}
              className="flex items-center space-x-1.5 px-3 py-1.5 bg-slate-950 hover:bg-slate-800 border border-slate-800 text-slate-300 rounded-xl text-xs font-medium transition-colors cursor-pointer shrink-0"
              title="打开独立数据矩阵切片视图"
            >
              <Table className="w-3.5 h-3.5 text-cyan-400" />
              <span className="hidden sm:inline">数据矩阵</span>
            </button>
          )}

          <button
            onClick={refreshData}
            disabled={loading}
            className="p-2 bg-slate-950 hover:bg-slate-800 text-slate-300 rounded-xl border border-slate-800 transition-colors cursor-pointer disabled:opacity-50 shrink-0"
            title="刷新数据"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* 错误警告 Banner */}
      {error && (
        <div className="p-2.5 bg-red-950/40 border border-red-800/60 rounded-xl text-xs text-red-300 flex items-center space-x-2 shrink-0">
          <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* 极速 K 线 + 成交量 2-Pane 联动图表 */}
      <div className="flex-1 min-h-0 w-full">
        <ErrorBoundary fallbackTitle="K 线图表组件渲染异常拦截">
          <TradingViewKLineChart
            ohlcBars={ohlcBars}
            volumeBars={volumeBars}
            maData={maData}
            colorMode={colorMode}
            onLoadMoreHistory={loadMoreHistory}
            resetView={resetView}
            prependCount={prependCount}
          />
        </ErrorBoundary>
      </div>
    </div>
  );
};

export default StockDetailView;
