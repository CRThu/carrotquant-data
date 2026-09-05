import React, { useEffect, useRef, useState } from 'react';
import type { OHLCBar, HistogramBar, MovingAverageData, ColorMode } from '../types/api';
import { getUpDownColors } from '../types/api';
import { Activity, Target } from 'lucide-react';
import { KLineCanvasEngine } from '../services/chartEngine';
import type { HoverBarInfo } from '../services/chartEngine';

interface TradingViewKLineChartProps {
  ohlcBars: OHLCBar[];
  volumeBars: HistogramBar[];
  maData: MovingAverageData;
  colorMode?: ColorMode;
  onLoadMoreHistory?: () => void;
  resetView?: boolean;
  prependCount?: number;
}

export const TradingViewKLineChart: React.FC<TradingViewKLineChartProps> = React.memo(({
  ohlcBars,
  volumeBars,
  maData,
  colorMode = 'redUpGreenDown',
  onLoadMoreHistory,
  resetView = false,
  prependCount = 0,
}) => {
  const outerWrapperRef = useRef<HTMLDivElement>(null);
  const containerMainRef = useRef<HTMLDivElement>(null);
  const containerVolRef = useRef<HTMLDivElement>(null);
  const engineRef = useRef<KLineCanvasEngine | null>(null);
  const onLoadMoreHistoryRef = useRef(onLoadMoreHistory);

  useEffect(() => {
    onLoadMoreHistoryRef.current = onLoadMoreHistory;
  }, [onLoadMoreHistory]);

  // 悬浮数据探针与十字光标 (包含当前柱的 OHLC 与对应 MA 均线值)
  const [hoverInfo, setHoverInfo] = useState<HoverBarInfo | null>(null);
  const { upColor, downColor } = getUpDownColors(colorMode);

  // 1. 初始化并绑定 KLineCanvasEngine 引擎生命周期
  useEffect(() => {
    if (!containerMainRef.current || !containerVolRef.current) return;

    const engine = new KLineCanvasEngine();
    engineRef.current = engine;

    engine.mount(containerMainRef.current, containerVolRef.current, {
      colorMode,
      onCrosshairMove: (bar) => setHoverInfo(bar),
      onLoadMoreHistory: () => {
        if (onLoadMoreHistoryRef.current) {
          onLoadMoreHistoryRef.current();
        }
      },
    });

    // 监听外层 Resize
    let animFrameId: number | null = null;
    let lastW = 0;
    let lastH = 0;

    const handleResize = () => {
      if (!outerWrapperRef.current) return;
      const w = outerWrapperRef.current.clientWidth;
      const totalH = outerWrapperRef.current.clientHeight;

      if (w <= 0 || totalH <= 0) return;
      if (Math.abs(w - lastW) < 2 && Math.abs(totalH - lastH) < 2) return;

      lastW = w;
      lastH = totalH;

      if (animFrameId) cancelAnimationFrame(animFrameId);
      animFrameId = requestAnimationFrame(() => {
        if (engineRef.current) {
          engineRef.current.resize(w, totalH);
        }
      });
    };

    const resizeObserver = new ResizeObserver(handleResize);
    if (outerWrapperRef.current) {
      resizeObserver.observe(outerWrapperRef.current);
    }

    handleResize();

    return () => {
      if (animFrameId) cancelAnimationFrame(animFrameId);
      resizeObserver.disconnect();
      engine.destroy();
      engineRef.current = null;
    };
  }, []);

  // 2. 颜色模式联动更新
  useEffect(() => {
    if (engineRef.current) {
      engineRef.current.updateColors(colorMode);
    }
  }, [colorMode]);

  // 3. 增量填入/重置数据
  useEffect(() => {
    if (engineRef.current) {
      engineRef.current.updateData(ohlcBars, volumeBars, maData, undefined, {
        resetView,
        prependCount,
      });
    }
  }, [ohlcBars, volumeBars, maData, resetView, prependCount]);

  const activeBar = hoverInfo;
  const changePct = activeBar ? (((activeBar.close - activeBar.open) / activeBar.open) * 100).toFixed(2) : '0.00';
  const isUp = activeBar ? activeBar.close >= activeBar.open : true;
  const activeColor = isUp ? upColor : downColor;

  // 均线随动逻辑：十字光标悬浮时显示光标所在 Bar 的对应均线值，未悬浮时显示最新 Bar 的均线值
  const latestMA5 = maData.ma5 && maData.ma5.length > 0 ? maData.ma5[maData.ma5.length - 1].value : undefined;
  const latestMA10 = maData.ma10 && maData.ma10.length > 0 ? maData.ma10[maData.ma10.length - 1].value : undefined;
  const latestMA20 = maData.ma20 && maData.ma20.length > 0 ? maData.ma20[maData.ma20.length - 1].value : undefined;

  const displayMA5 = activeBar?.ma5 !== undefined ? activeBar.ma5 : latestMA5;
  const displayMA10 = activeBar?.ma10 !== undefined ? activeBar.ma10 : latestMA10;
  const displayMA20 = activeBar?.ma20 !== undefined ? activeBar.ma20 : latestMA20;

  return (
    <div
      ref={outerWrapperRef}
      className="h-full w-full flex flex-col space-y-1.5 bg-slate-950 p-2.5 rounded-2xl border border-slate-800 overflow-hidden relative"
    >
      {/* 顶栏: 包含精简标题、随动 MA 均线数值与交互指引 */}
      <div className="flex items-center justify-between px-3 py-1 bg-slate-900/90 rounded-xl border border-slate-800 text-xs shrink-0 h-9">
        <div className="flex items-center space-x-4">
          <span className="flex items-center font-bold text-slate-100 whitespace-nowrap">
            <Activity className="w-3.5 h-3.5 text-cyan-400 mr-1.5" />
            行情走势
          </span>

          <div className="flex items-center space-x-3 text-[11px] font-mono">
            <span className="flex items-center space-x-1 text-amber-400">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
              <span>MA5:</span>
              <span className="font-semibold">{displayMA5 !== undefined ? displayMA5.toFixed(2) : '--'}</span>
            </span>
            <span className="flex items-center space-x-1 text-purple-400">
              <span className="w-1.5 h-1.5 rounded-full bg-purple-400" />
              <span>MA10:</span>
              <span className="font-semibold">{displayMA10 !== undefined ? displayMA10.toFixed(2) : '--'}</span>
            </span>
            <span className="flex items-center space-x-1 text-cyan-400">
              <span className="w-1.5 h-1.5 rounded-full bg-cyan-400" />
              <span>MA20:</span>
              <span className="font-semibold">{displayMA20 !== undefined ? displayMA20.toFixed(2) : '--'}</span>
            </span>
          </div>
        </div>

        <div className="text-[11px] font-mono text-slate-400 hidden sm:block">
          滚轮缩放 / 拖拽平移
        </div>
      </div>

      {/* 1. 主图 Pane (K线 + 均线) */}
      <div className="relative rounded-xl overflow-hidden border border-slate-800/60 flex-1 min-h-0">
        {ohlcBars.length === 0 && (
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-slate-950/90 z-20 text-xs text-slate-400 font-mono">
            <Activity className="w-6 h-6 text-cyan-400 mb-2 animate-spin" />
            <span>正在加载 K 线行情数据...</span>
          </div>
        )}

        {activeBar && (
          <div className="absolute top-2 left-3 z-10 text-[11px] font-mono bg-slate-950/95 px-2.5 py-1 rounded-lg border border-slate-800/80 pointer-events-none flex items-center space-x-3 text-slate-300">
            <span className="flex items-center text-slate-400">
              <Target className="w-3 h-3 text-cyan-400 mr-1" />
              {activeBar.time}
            </span>
            <span>开: <span style={{ color: activeColor }}>{activeBar.open}</span></span>
            <span>高: <span style={{ color: activeColor }}>{activeBar.high}</span></span>
            <span>低: <span style={{ color: activeColor }}>{activeBar.low}</span></span>
            <span>收: <span style={{ color: activeColor }}>{activeBar.close}</span></span>
            <span>幅: <span style={{ color: activeColor }}>{Number(changePct) >= 0 ? `+${changePct}%` : `${changePct}%`}</span></span>
            <span className="text-slate-400">VOL: <span className="text-cyan-300">{activeBar.volume.toLocaleString()}</span></span>
          </div>
        )}
        <div ref={containerMainRef} className="w-full h-full" />
      </div>

      {/* 2. 附图 Pane (成交量 VOL) */}
      <div className="relative rounded-xl overflow-hidden border border-slate-800/60 h-36 shrink-0">
        <div className="absolute top-1.5 left-2.5 z-10 text-[10px] font-mono text-slate-400 pointer-events-none">
          成交量 VOL
        </div>
        <div ref={containerVolRef} className="w-full h-full" />
      </div>
    </div>
  );
});
