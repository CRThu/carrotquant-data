import { describe, it, expect, vi, beforeEach } from 'vitest';
import { KLineCanvasEngine } from '../services/chartEngine';

// Mock lightweight-charts
vi.mock('lightweight-charts', () => {
  const mockCandlestickSeries = {
    setData: vi.fn(),
    setMarkers: vi.fn(),
    applyOptions: vi.fn(),
  };
  const mockLineSeries = {
    setData: vi.fn(),
  };
  const mockHistogramSeries = {
    setData: vi.fn(),
  };
  const mockChart = {
    addCandlestickSeries: vi.fn().mockReturnValue(mockCandlestickSeries),
    addLineSeries: vi.fn().mockReturnValue(mockLineSeries),
    addHistogramSeries: vi.fn().mockReturnValue(mockHistogramSeries),
    subscribeCrosshairMove: vi.fn(),
    timeScale: vi.fn().mockReturnValue({
      subscribeVisibleLogicalRangeChange: vi.fn(),
      fitContent: vi.fn(),
      setVisibleLogicalRange: vi.fn(),
      getVisibleLogicalRange: vi.fn().mockReturnValue({ from: 0, to: 100 }),
    }),
    priceScale: vi.fn().mockReturnValue({
      applyOptions: vi.fn(),
    }),
    applyOptions: vi.fn(),
    remove: vi.fn(),
  };

  return {
    createChart: vi.fn().mockReturnValue(mockChart),
    ColorType: { Solid: 'solid' },
    CrosshairMode: { Normal: 0 },
  };
});

describe('KLineCanvasEngine Unit Tests', () => {
  let engine: KLineCanvasEngine;
  const dummyMainDiv = {} as HTMLDivElement;
  const dummyVolDiv = {} as HTMLDivElement;

  beforeEach(() => {
    engine = new KLineCanvasEngine();
  });

  it('mounts chart engine successfully without throwing', () => {
    expect(() => {
      engine.mount(dummyMainDiv, dummyVolDiv, { colorMode: 'redUpGreenDown' });
    }).not.toThrow();
  });

  it('updates data and markers incrementally', () => {
    engine.mount(dummyMainDiv, dummyVolDiv);

    const mockBars = [
      { time: '2024-01-01', open: 10, high: 12, low: 9, close: 11, volume: 1000 },
    ];
    const mockVols = [
      { time: '2024-01-01', value: 1000, color: '#ef4444' },
    ];
    const mockMa = {
      ma5: [{ time: '2024-01-01', value: 10.5 }],
      ma10: [],
      ma20: [],
      ma60: [],
    };
    const mockMarkers = [
      { time: '2024-01-01', position: 'aboveBar' as const, color: '#ef4444', shape: 'arrowDown' as const, text: 'Sell' },
    ];

    expect(() => {
      engine.updateData(mockBars, mockVols, mockMa, mockMarkers);
    }).not.toThrow();
  });

  it('updates colors on updateColors()', () => {
    engine.mount(dummyMainDiv, dummyVolDiv);
    expect(() => {
      engine.updateColors('greenUpRedDown');
    }).not.toThrow();
  });

  it('clears chart data on clear()', () => {
    engine.mount(dummyMainDiv, dummyVolDiv);
    expect(() => {
      engine.clear();
    }).not.toThrow();
  });

  it('destroys engine safely', () => {
    engine.mount(dummyMainDiv, dummyVolDiv);
    expect(() => {
      engine.destroy();
    }).not.toThrow();
  });
});
