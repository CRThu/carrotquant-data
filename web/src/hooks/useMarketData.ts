import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { DATA_SOURCE_OPTIONS } from '../types/api';
import type {
  OHLCBar,
  HistogramBar,
  MovingAverageData,
  MACDResult,
  BSMarkerItem,
  QueryMatrixResponse,
} from '../types/api';
import { apiClient } from '../services/apiClient';
import { matrixToOHLC, ohlcToVolume } from '../services/transformers';
import { calculateMAMulti, calculateMACD, calculateRSI, deriveBSMarkers } from '../services/indicators';
import type { ColorMode, LineDataPoint } from '../types/api';

export interface UseMarketDataReturn {
  tableId: string;
  setTableId: (id: string) => void;
  market: string;
  setMarket: (m: string) => void;
  category: string;
  freq: string;
  setFreq: (f: string) => void;
  adj: string;
  setAdj: (a: string) => void;
  source: string;
  setSource: (s: string) => void;
  symbol: string;
  setSymbol: (sym: string) => void;
  barLimit: number;
  setBarLimit: (limit: number) => void;
  selectedIndicator: string;
  setSelectedIndicator: (ind: string) => void;
  loading: boolean;
  error: string | null;
  ohlcBars: OHLCBar[];
  volumeBars: HistogramBar[];
  maData: MovingAverageData;
  macdData: MACDResult;
  rsiData: LineDataPoint[];
  markers: BSMarkerItem[];
  matrixRaw: QueryMatrixResponse | null;
  setExternalMarkers: (markers: BSMarkerItem[]) => void;
  refreshData: () => void;
  hasMoreHistory: boolean;
  isLoadingMore: boolean;
  loadMoreHistory: () => Promise<void>;
  resetView: boolean;
  prependCount: number;
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

export const useMarketData = (
  initialTableId: string = DATA_SOURCE_OPTIONS[0].table_id,
  initialSymbol: string = 'sh.600000',
  colorMode: ColorMode = 'redUpGreenDown'
): UseMarketDataReturn => {
  const initialDims = useMemo(() => parseTableIdDimensions(initialTableId), [initialTableId]);

  const [tableId, setTableIdState] = useState<string>(initialTableId);
  const [market, setMarket] = useState<string>(initialDims.market);
  const [category, setCategory] = useState<string>(initialDims.category);
  const [freq, setFreqState] = useState<string>(initialDims.freq);
  const [adj, setAdjState] = useState<string>(initialDims.adj);
  const [source, setSourceState] = useState<string>(initialDims.source);

  const [symbol, setSymbol] = useState<string>(initialSymbol);
  const [barLimit, setBarLimit] = useState<number>(1000); // 默认加载最新 1000 条 Bars
  const [selectedIndicator, setSelectedIndicator] = useState<string>('MACD');
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const [historyPage, setHistoryPage] = useState<number>(1);
  const [hasMoreHistory, setHasMoreHistory] = useState<boolean>(true);
  const [isLoadingMore, setIsLoadingMore] = useState<boolean>(false);
  const [resetView, setResetView] = useState<boolean>(true);
  const [prependCount, setPrependCount] = useState<number>(0);

  const rawBarsRef = useRef<OHLCBar[]>([]);
  const totalPagesRef = useRef<number>(1);
  const isFetchingMoreRef = useRef<boolean>(false);

  const [ohlcBars, setOhlcBars] = useState<OHLCBar[]>([]);
  const [volumeBars, setVolumeBars] = useState<HistogramBar[]>([]);
  const [maData, setMaData] = useState<MovingAverageData>({ ma5: [], ma10: [], ma20: [], ma60: [] });
  const [macdData, setMacdData] = useState<MACDResult>({ dif: [], dea: [], macdBar: [] });
  const [rsiData, setRsiData] = useState<LineDataPoint[]>([]);
  const [derivedMarkers, setDerivedMarkers] = useState<BSMarkerItem[]>([]);
  const [externalMarkers, setExternalMarkers] = useState<BSMarkerItem[]>([]);
  const [matrixRaw, setMatrixRaw] = useState<QueryMatrixResponse | null>(null);

  // 维度联动更新 table_id
  const setTableId = useCallback((newTableId: string) => {
    setTableIdState(newTableId);
    const d = parseTableIdDimensions(newTableId);
    setMarket(d.market);
    setCategory(d.category);
    setFreqState(d.freq);
    setAdjState(d.adj);
    setSourceState(d.source);
  }, []);

  const setFreq = useCallback((newFreq: string) => {
    setFreqState(newFreq);
    setTableIdState(buildTableId(market, category, newFreq, adj, source));
  }, [market, category, adj, source]);

  const setAdj = useCallback((newAdj: string) => {
    setAdjState(newAdj);
    setTableIdState(buildTableId(market, category, freq, newAdj, source));
  }, [market, category, freq, source]);

  const setSource = useCallback((newSource: string) => {
    setSourceState(newSource);
    setTableIdState(buildTableId(market, category, freq, adj, newSource));
  }, [market, category, freq, adj]);

  // 在 Render 阶段同步 Prop 变动，彻底消除切换/加载标的时产生的二次串行 HTTP 请求 (1.6s -> 0.2s)
  const [prevInitialTableId, setPrevInitialTableId] = useState(initialTableId);
  const [prevInitialSymbol, setPrevInitialSymbol] = useState(initialSymbol);

  if (initialTableId !== prevInitialTableId) {
    setPrevInitialTableId(initialTableId);
    setTableId(initialTableId);
  }

  if (initialSymbol !== prevInitialSymbol) {
    setPrevInitialSymbol(initialSymbol);
    setSymbol(initialSymbol);
  }

  const lastFetchedRef = useRef<string>('');

  const fetchData = useCallback(async (isForce: boolean = false) => {
    if (!symbol) return;

    const isKline = category === 'kline' || tableId.includes('kline');
    const fetchKey = isKline
      ? `${market}:${category}:${freq}:${adj}:${source}:${symbol}`
      : `${tableId}:${symbol}`;

    if (!isForce && lastFetchedRef.current === fetchKey && matrixRaw !== null) {
      return;
    }

    // 当请求新股票/新表时，立即清空上一次旧股票的数据，防止图表残留旧 K 线造成误解
    if (lastFetchedRef.current !== fetchKey) {
      setOhlcBars([]);
      setVolumeBars([]);
      setMaData({ ma5: [], ma10: [], ma20: [], ma60: [] });
      setMatrixRaw(null);
      rawBarsRef.current = [];
    }

    setLoading(true);
    setError(null);
    setResetView(true);
    setPrependCount(0);
    setHistoryPage(1);

    try {
      let res: QueryMatrixResponse;

      if (isKline) {
        // 核心升级：通过新功能端点查询，默认使用 order="desc" 降序切片加载最新数据
        const dynamicRes = await apiClient.fetchMarketData({
          market,
          category: 'kline',
          symbols: symbol,
          freq,
          adj,
          source,
          page: 1,
          page_size: 1000,
          order: 'desc',
        });
        res = {
          table_id: dynamicRes.resolved_table_id || dynamicRes.table_id || tableId,
          total: dynamicRes.total,
          page: dynamicRes.page,
          page_size: dynamicRes.page_size,
          total_pages: dynamicRes.total_pages,
          count: dynamicRes.count,
          columns: dynamicRes.columns,
          data: dynamicRes.data,
        };
      } else {
        // 非行情或物理表回退走底层 queryData (同样支持 order="desc" 降序切片)
        res = await apiClient.queryData({
          table_id: tableId,
          symbols: symbol,
          page: 1,
          page_size: 1000,
          order: 'desc',
        });
      }

      setMatrixRaw(res);
      lastFetchedRef.current = fetchKey;
      totalPagesRef.current = res.total_pages;
      setHasMoreHistory(res.page < res.total_pages);

      // 1. 转换为 OHLC Bars：matrixToOHLC 内部已按时间升序去重排序，供 TradingView 绘制
      const fullBars = matrixToOHLC(res);
      rawBarsRef.current = fullBars;

      const fullVols = ohlcToVolume(fullBars, colorMode);
      const fullMas = calculateMAMulti(fullBars);
      const fullMacd = calculateMACD(fullBars, 12, 26, 9, colorMode);
      const fullRsi = calculateRSI(fullBars, 14);
      const fullMarkers = deriveBSMarkers(fullBars, fullMas.ma5, fullMas.ma20, colorMode);

      setOhlcBars(fullBars);
      setVolumeBars(fullVols);
      setMaData(fullMas);
      setMacdData(fullMacd);
      setRsiData(fullRsi);
      setDerivedMarkers(fullMarkers);
    } catch (err: any) {
      console.error('Failed to fetch market data:', err);
      setError(err?.response?.data?.detail || err?.message || '获取数据失败');
      setOhlcBars([]);
      setVolumeBars([]);
      setMatrixRaw(null);
      rawBarsRef.current = [];
      lastFetchedRef.current = '';
    } finally {
      setLoading(false);
    }
  }, [tableId, market, category, freq, adj, source, symbol, colorMode, matrixRaw]);

  // 向左无限滚动追加历史数据
  const loadMoreHistory = useCallback(async () => {
    if (isFetchingMoreRef.current || !hasMoreHistory || loading || historyPage >= totalPagesRef.current) {
      return;
    }

    isFetchingMoreRef.current = true;
    setIsLoadingMore(true);

    try {
      const nextPage = historyPage + 1;
      const isKline = category === 'kline' || tableId.includes('kline');

      let moreRes: QueryMatrixResponse;
      if (isKline) {
        const dynamicRes = await apiClient.fetchMarketData({
          market,
          category: 'kline',
          symbols: symbol,
          freq,
          adj,
          source,
          page: nextPage,
          page_size: 1000,
          order: 'desc',
        });
        moreRes = {
          table_id: dynamicRes.resolved_table_id || dynamicRes.table_id || tableId,
          total: dynamicRes.total,
          page: dynamicRes.page,
          page_size: dynamicRes.page_size,
          total_pages: dynamicRes.total_pages,
          count: dynamicRes.count,
          columns: dynamicRes.columns,
          data: dynamicRes.data,
        };
      } else {
        moreRes = await apiClient.queryData({
          table_id: tableId,
          symbols: symbol,
          page: nextPage,
          page_size: 1000,
          order: 'desc',
        });
      }

      // matrixToOHLC 已按时间升序去重排序，更早历史直接拼在现有数据头部
      const moreBars = matrixToOHLC(moreRes);
      if (moreBars.length === 0) {
        setHasMoreHistory(false);
        return;
      }

      // 历史数据排在前面 (升序排列)
      const nextFullBars = [...moreBars, ...rawBarsRef.current];
      rawBarsRef.current = nextFullBars;

      const fullVols = ohlcToVolume(nextFullBars, colorMode);
      const fullMas = calculateMAMulti(nextFullBars);
      const fullMacd = calculateMACD(nextFullBars, 12, 26, 9, colorMode);
      const fullRsi = calculateRSI(nextFullBars, 14);
      const fullMarkers = deriveBSMarkers(nextFullBars, fullMas.ma5, fullMas.ma20, colorMode);

      setPrependCount(moreBars.length);
      setResetView(false);

      setOhlcBars(nextFullBars);
      setVolumeBars(fullVols);
      setMaData(fullMas);
      setMacdData(fullMacd);
      setRsiData(fullRsi);
      setDerivedMarkers(fullMarkers);

      setHistoryPage(nextPage);
      setHasMoreHistory(nextPage < moreRes.total_pages);
    } catch (err) {
      console.error('Failed to load more history:', err);
    } finally {
      setIsLoadingMore(false);
      isFetchingMoreRef.current = false;
    }
  }, [hasMoreHistory, loading, historyPage, category, tableId, market, symbol, freq, adj, source, colorMode]);

  useEffect(() => {
    fetchData(false);
  }, [fetchData]);

  // 合并派生的金叉死叉 Marker 与外部扩展注入的 Marker (使用 useMemo 缓存 Array 引用防重绘)
  const combinedMarkers = useMemo(
    () => [...derivedMarkers, ...externalMarkers],
    [derivedMarkers, externalMarkers]
  );

  return {
    tableId,
    setTableId,
    market,
    setMarket,
    category,
    freq,
    setFreq,
    adj,
    setAdj,
    source,
    setSource,
    symbol,
    setSymbol,
    barLimit,
    setBarLimit,
    selectedIndicator,
    setSelectedIndicator,
    loading,
    error,
    ohlcBars,
    volumeBars,
    maData,
    macdData,
    rsiData,
    markers: combinedMarkers,
    matrixRaw,
    setExternalMarkers,
    refreshData: () => fetchData(true),
    hasMoreHistory,
    isLoadingMore,
    loadMoreHistory,
    resetView,
    prependCount,
  };
};
