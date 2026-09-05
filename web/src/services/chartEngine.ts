import { createChart, ColorType, CrosshairMode } from 'lightweight-charts';
import type { IChartApi, ISeriesApi, Time } from 'lightweight-charts';
import type { OHLCBar, HistogramBar, MovingAverageData, ColorMode, BSMarkerItem } from '../types/api';
import { getUpDownColors } from '../types/api';

export interface HoverBarInfo extends OHLCBar {
  ma5?: number;
  ma10?: number;
  ma20?: number;
}

export interface ChartEngineMountOptions {
  colorMode?: ColorMode;
  onCrosshairMove?: (bar: HoverBarInfo | null) => void;
  onLoadMoreHistory?: () => void;
}

/**
 * 封装 TradingView Lightweight Charts 的轻量 2D/WebGL 画布引擎
 * 职责：负责图表实例挂载、手势交互强同步、数据增量 setData、配色切换与平滑 resize。
 * 优势：与 React 解耦，绝不上网重新销毁/创建 Canvas，性能维持 60 FPS 满帧。
 */
export class KLineCanvasEngine {
  private chartMain: IChartApi | null = null;
  private chartVol: IChartApi | null = null;
  private mainContainer: HTMLDivElement | null = null;
  private volContainer: HTMLDivElement | null = null;

  private candlestickSeries: ISeriesApi<'Candlestick'> | null = null;
  private ma5Series: ISeriesApi<'Line'> | null = null;
  private ma10Series: ISeriesApi<'Line'> | null = null;
  private ma20Series: ISeriesApi<'Line'> | null = null;
  private volumeSeries: ISeriesApi<'Histogram'> | null = null;

  private colorMode: ColorMode = 'redUpGreenDown';
  private onCrosshairMoveCb?: (bar: HoverBarInfo | null) => void;
  private onLoadMoreHistoryCb?: () => void;
  private lastDataKey: string = '';

  /**
   * 挂载画布并建立主副图强同步
   */
  public mount(
    mainContainer: HTMLDivElement,
    volContainer: HTMLDivElement,
    options: ChartEngineMountOptions = {}
  ): void {
    this.mainContainer = mainContainer;
    this.volContainer = volContainer;
    this.colorMode = options.colorMode || 'redUpGreenDown';
    this.onCrosshairMoveCb = options.onCrosshairMove;
    this.onLoadMoreHistoryCb = options.onLoadMoreHistory;

    const { upColor, downColor } = getUpDownColors(this.colorMode);

    const commonOptions = {
      layout: {
        background: { type: ColorType.Solid, color: '#090d16' },
        textColor: '#94a3b8',
        fontSize: 11,
        fontFamily: 'sans-serif',
      },
      watermark: { visible: false },
      grid: {
        vertLines: { color: '#162032' },
        horzLines: { color: '#162032' },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: '#1e293b' },
      timeScale: { borderColor: '#1e293b', timeVisible: true, secondsVisible: false },
    };

    // 1. 主图 K 线 (开启全套缩放与滚轮手势)
    this.chartMain = createChart(mainContainer, {
      ...commonOptions,
      height: mainContainer.clientHeight || 320,
      handleScale: { mouseWheel: true, pinch: true, axisPressedMouseMove: true },
      handleScroll: { mouseWheel: true, pressedMouseMove: true },
    });

    this.candlestickSeries = this.chartMain.addCandlestickSeries({
      upColor,
      downColor,
      borderVisible: false,
      wickUpColor: upColor,
      wickDownColor: downColor,
    });

    // 均线 Series 隐藏右侧纵坐标标签与价格线，数值移至顶部 Legend 随动展示，不遮挡股价轴
    this.ma5Series = this.chartMain.addLineSeries({
      color: '#eab308',
      lineWidth: 1,
      lastValueVisible: false,
      priceLineVisible: false,
    });
    this.ma10Series = this.chartMain.addLineSeries({
      color: '#a855f7',
      lineWidth: 1,
      lastValueVisible: false,
      priceLineVisible: false,
    });
    this.ma20Series = this.chartMain.addLineSeries({
      color: '#06b6d4',
      lineWidth: 1,
      lastValueVisible: false,
      priceLineVisible: false,
    });

    // 十字光标悬浮监听 (实时提取光标所在蜡烛的 OHLC 与对应均线值，驱动 Legend 随动)
    this.chartMain.subscribeCrosshairMove((param) => {
      if (!this.onCrosshairMoveCb) return;

      if (!param || !param.time || param.point === undefined || param.point.x < 0 || param.point.y < 0) {
        this.onCrosshairMoveCb(null);
        return;
      }

      if (this.candlestickSeries) {
        const data = param.seriesData.get(this.candlestickSeries) as any;
        if (data && typeof data.close === 'number') {
          const ma5Val = this.ma5Series ? (param.seriesData.get(this.ma5Series) as any)?.value : undefined;
          const ma10Val = this.ma10Series ? (param.seriesData.get(this.ma10Series) as any)?.value : undefined;
          const ma20Val = this.ma20Series ? (param.seriesData.get(this.ma20Series) as any)?.value : undefined;

          this.onCrosshairMoveCb({
            time: String(param.time),
            open: data.open,
            high: data.high,
            low: data.low,
            close: data.close,
            volume: data.volume ?? 0,
            ma5: typeof ma5Val === 'number' ? ma5Val : undefined,
            ma10: typeof ma10Val === 'number' ? ma10Val : undefined,
            ma20: typeof ma20Val === 'number' ? ma20Val : undefined,
          });
        }
      }
    });

    // 2. 附图 成交量 VOL (由主图单向指挥)
    this.chartVol = createChart(volContainer, {
      ...commonOptions,
      height: volContainer.clientHeight || 128,
      handleScale: false,
      handleScroll: false,
      timeScale: {
        visible: false, // 隐藏副图时间轴，时间与主图强同步，全部垂直空间完整留给成交量柱与纵坐标
      },
    });

    this.volumeSeries = this.chartVol.addHistogramSeries({
      priceFormat: { type: 'volume' },
      priceScaleId: 'right',
    });

    // 为成交量纵坐标设置安全内边距，确保 0 刻度与最大成交量文字完全不被裁剪
    this.chartVol.priceScale('right').applyOptions({
      scaleMargins: {
        top: 0.18,
        bottom: 0.06,
      },
      borderColor: '#1e293b',
    });

    // 单向 Master -> Follower 零冲突强同步与无限向左滚动探针
    this.chartMain.timeScale().subscribeVisibleLogicalRangeChange((range) => {
      if (range && this.chartVol) {
        try {
          this.chartVol.timeScale().setVisibleLogicalRange(range);
        } catch {
          // 静默
        }
      }
      // 当向左滑动探测到左侧边界剩余不足 20 根 Bar 时，触发加载更早历史
      if (range && range.from < 20 && this.onLoadMoreHistoryCb) {
        this.onLoadMoreHistoryCb();
      }
    });
  }

  /**
   * 增量更新 K 线、均线与成交量数据 (绝不上网重新销毁/新建 Canvas)
   */
  public updateData(
    ohlcBars: OHLCBar[],
    volumeBars: HistogramBar[],
    maData: MovingAverageData,
    markers?: BSMarkerItem[],
    options?: { resetView?: boolean; prependCount?: number }
  ): void {
    if (!this.candlestickSeries) return;

    if (!ohlcBars || ohlcBars.length === 0) {
      this.clear();
      return;
    }

    const prevRange = this.chartMain?.timeScale()?.getVisibleLogicalRange?.();

    // 1. 设置 K 线
    this.candlestickSeries.setData(
      ohlcBars.map((b) => ({
        time: b.time as Time,
        open: b.open,
        high: b.high,
        low: b.low,
        close: b.close,
      }))
    );

    // 如果有买卖点 Markers 标注，自动上图
    if (markers && markers.length > 0) {
      this.candlestickSeries.setMarkers(
        markers.map((m) => ({
          time: m.time as Time,
          position: m.position,
          color: m.color,
          shape: m.shape,
          text: m.text,
        }))
      );
    }

    // 2. 设置 MA 均线
    if (this.ma5Series && maData.ma5) {
      this.ma5Series.setData(maData.ma5.map((d) => ({ time: d.time as Time, value: d.value })));
    }
    if (this.ma10Series && maData.ma10) {
      this.ma10Series.setData(maData.ma10.map((d) => ({ time: d.time as Time, value: d.value })));
    }
    if (this.ma20Series && maData.ma20) {
      this.ma20Series.setData(maData.ma20.map((d) => ({ time: d.time as Time, value: d.value })));
    }

    // 3. 设置成交量 VOL
    if (this.volumeSeries && volumeBars) {
      this.volumeSeries.setData(
        volumeBars.map((v) => ({
          time: v.time as Time,
          value: v.value,
          color: v.color,
        }))
      );
    }

    const isInitial = !this.lastDataKey;
    const currentDataKey = `${ohlcBars[0]?.time}-${ohlcBars[ohlcBars.length - 1]?.time}-${ohlcBars.length}`;
    this.lastDataKey = currentDataKey;

    if (this.chartMain) {
      if (options?.prependCount && options.prependCount > 0 && prevRange) {
        // 向左无缝追加历史数据时，平移视口保持当前焦点位置不变
        try {
          this.chartMain.timeScale().setVisibleLogicalRange({
            from: prevRange.from + options.prependCount,
            to: prevRange.to + options.prependCount,
          });
        } catch {
          // 静默
        }
      } else if (options?.resetView || isInitial) {
        // 默认首屏适度放大展示最近 ~130 根 K 线，形态清晰可辨，杜绝 1000 根全部挤压在首屏
        const DEFAULT_VISIBLE_BARS = 130;
        const totalBars = ohlcBars.length;
        if (totalBars > DEFAULT_VISIBLE_BARS) {
          const to = totalBars + 4; // 右侧预留 4 根 Bar 的呼吸边距
          const from = to - DEFAULT_VISIBLE_BARS;
          try {
            this.chartMain.timeScale().setVisibleLogicalRange({ from, to });
            this.chartVol?.timeScale().setVisibleLogicalRange({ from, to });
          } catch {
            this.chartMain.timeScale().fitContent();
            this.chartVol?.timeScale().fitContent();
          }
        } else {
          this.chartMain.timeScale().fitContent();
          this.chartVol?.timeScale().fitContent();
        }
      }
    }
  }

  /**
   * 动态切换红涨绿跌 / 绿涨红跌双色
   */
  public updateColors(colorMode: ColorMode): void {
    this.colorMode = colorMode;
    const { upColor, downColor } = getUpDownColors(colorMode);

    if (this.candlestickSeries) {
      this.candlestickSeries.applyOptions({
        upColor,
        downColor,
        wickUpColor: upColor,
        wickDownColor: downColor,
      });
    }
  }

  /**
   * 清空 Series 数据 (切换股票时极速置空，保留 Canvas)
   */
  public clear(): void {
    if (this.candlestickSeries) this.candlestickSeries.setData([]);
    if (this.ma5Series) this.ma5Series.setData([]);
    if (this.ma10Series) this.ma10Series.setData([]);
    if (this.ma20Series) this.ma20Series.setData([]);
    if (this.volumeSeries) this.volumeSeries.setData([]);
    this.lastDataKey = '';
  }

  /**
   * 平滑 resize 画布宽度与高度，严格与 DOM 容器实际渲染高度对齐
   */
  public resize(width: number, height: number): void {
    if (width <= 0 || height <= 0) return;

    if (this.chartMain && this.mainContainer) {
      const w = this.mainContainer.clientWidth || width;
      const h = this.mainContainer.clientHeight;
      if (w > 0 && h > 0) {
        this.chartMain.applyOptions({ width: w, height: h });
      }
    }
    if (this.chartVol && this.volContainer) {
      const w = this.volContainer.clientWidth || width;
      const h = this.volContainer.clientHeight;
      if (w > 0 && h > 0) {
        this.chartVol.applyOptions({ width: w, height: h });
      }
    }
  }

  /**
   * 销毁并释放实例
   */
  public destroy(): void {
    this.clear();
    if (this.chartMain) {
      this.chartMain.remove();
      this.chartMain = null;
    }
    if (this.chartVol) {
      this.chartVol.remove();
      this.chartVol = null;
    }
    this.candlestickSeries = null;
    this.ma5Series = null;
    this.ma10Series = null;
    this.ma20Series = null;
    this.volumeSeries = null;
    this.mainContainer = null;
    this.volContainer = null;
  }
}
