import React, { useState, useEffect } from 'react';
import type { TableDetailedMeta, SyncStatusItem } from '../types/api';
import { apiClient } from '../services/apiClient';
import { TableManagementGrid } from '../components/TableManagementGrid';
import { Database, HardDrive, Layers, RefreshCcw, AlertTriangle } from 'lucide-react';

interface DataManagementViewProps {
  onSyncStatusChange?: (activeCount: number) => void;
}

export const DataManagementView: React.FC<DataManagementViewProps> = ({ onSyncStatusChange }) => {
  const [tables, setTables] = useState<TableDetailedMeta[]>([]);
  const [statuses, setStatuses] = useState<Record<string, SyncStatusItem>>({});
  const [activeTasks, setActiveTasks] = useState<string[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [syncing, setSyncing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // 1. 加载所有表及格式的详细物理元数据
  const fetchDetailedTables = async () => {
    try {
      setError(null);
      const res = await apiClient.getDetailedTables();
      setTables(res.tables || []);
    } catch (e: any) {
      console.error('Failed to fetch detailed tables', e);
      setError('无法获取本地数据表元数据，请检查 REST API 连接');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDetailedTables();

    // 基于 SSE 实时事件流监听同步状态 (彻底消除 setInterval 定时轮询)
    const es = apiClient.createSyncEventSource();

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'snapshot') {
          setStatuses(data.statuses || {});
          const activeList = data.active_tasks || [];
          setActiveTasks(activeList);
          if (onSyncStatusChange) {
            onSyncStatusChange(activeList.length);
          }
        } else if (data.type === 'progress') {
          const item: SyncStatusItem = data.item;
          if (item) {
            setStatuses((prev) => ({ ...prev, [item.table_id]: item }));
          }
          const activeList = data.active_tasks || [];
          setActiveTasks(activeList);
          if (onSyncStatusChange) {
            onSyncStatusChange(activeList.length);
          }
          // 任务完成或失败时，自动刷新一次物理存储元数据
          if (item && (item.status === 'success' || item.status === 'failed')) {
            fetchDetailedTables();
          }
        }
      } catch (e) {
        // 静默 ping 心跳
      }
    };

    return () => {
      es.close();
    };
  }, []);

  // 触发同步逻辑
  const handleTriggerSync = async (payload: {
    table_ids: string[];
    formats: string[];
    start_date?: string;
    end_date?: string;
    force_refresh?: boolean;
    provider_kwargs?: Record<string, any>;
  }) => {
    setSyncing(true);
    setError(null);
    try {
      await apiClient.triggerSync(payload);
    } catch (err: any) {
      console.error('Failed to trigger sync', err);
      setError(err?.response?.data?.detail || err?.message || '启动同步失败');
    } finally {
      setSyncing(false);
    }
  };

  // 统计概览数据
  const totalBarsParquet = tables.reduce((acc, t) => acc + (t.formats.parquet?.total_bars || 0), 0);
  const totalBarsCsv = tables.reduce((acc, t) => acc + (t.formats.csv?.total_bars || 0), 0);
  const activeTaskCount = activeTasks.length;

  return (
    <div className="space-y-6 animate-in fade-in duration-300 pb-12">
      {/* 顶部标题与数据量概览 Cards */}
      <div className="bg-slate-900/60 p-3.5 rounded-2xl border border-slate-800 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center space-x-3">
          <div className="p-2 bg-cyan-950/60 rounded-xl border border-cyan-800/50 text-cyan-400">
            <Database className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-sm font-bold text-slate-100">数据中心</h1>
            <p className="text-[10px] text-slate-400 mt-0.5">
              监控本地存储格式、增量水位线与全自动增量数据同步
            </p>
          </div>
        </div>

        <button
          onClick={fetchDetailedTables}
          disabled={loading}
          title="刷新物理状态"
          className="p-2 bg-slate-950 hover:bg-slate-800 border border-slate-800 text-slate-300 rounded-xl transition-colors cursor-pointer disabled:opacity-50"
        >
          <RefreshCcw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {error && (
        <div className="p-3 bg-red-950/40 border border-red-800/60 rounded-xl text-xs text-red-300 flex items-center space-x-2">
          <AlertTriangle className="w-4 h-4 text-red-400 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* 3 大数据概览 Card */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4 flex items-center space-x-4 shadow-lg">
          <div className="w-10 h-10 rounded-xl bg-cyan-950/60 border border-cyan-800/60 flex items-center justify-center text-cyan-400">
            <Layers className="w-5 h-5" />
          </div>
          <div>
            <div className="text-[11px] font-medium text-slate-400">数据源/数据表数</div>
            <div className="text-xl font-bold font-mono text-slate-100">{tables.length} <span className="text-xs text-slate-500 font-sans">个</span></div>
          </div>
        </div>

        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4 flex items-center space-x-4 shadow-lg">
          <div className="w-10 h-10 rounded-xl bg-blue-950/60 border border-blue-800/60 flex items-center justify-center text-blue-400">
            <HardDrive className="w-5 h-5" />
          </div>
          <div>
            <div className="text-[11px] font-medium text-slate-400">Parquet 存储总记录条数</div>
            <div className="text-xl font-bold font-mono text-cyan-400">{totalBarsParquet.toLocaleString()}</div>
          </div>
        </div>

        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4 flex items-center space-x-4 shadow-lg">
          <div className="w-10 h-10 rounded-xl bg-amber-950/60 border border-amber-800/60 flex items-center justify-center text-amber-400">
            <HardDrive className="w-5 h-5" />
          </div>
          <div>
            <div className="text-[11px] font-medium text-slate-400">CSV 存储总记录条数</div>
            <div className="text-xl font-bold font-mono text-amber-400">{totalBarsCsv.toLocaleString()}</div>
          </div>
        </div>
      </div>

      {/* 主数据表层级管理表格 */}
      <TableManagementGrid
        tables={tables}
        statuses={statuses}
        onTriggerSync={handleTriggerSync}
        syncing={syncing || activeTaskCount > 0}
      />
    </div>
  );
};

