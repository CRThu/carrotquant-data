import React, { useState } from 'react';
import { DATA_SOURCE_OPTIONS, type TableDetailedMeta, type SyncStatusItem } from '../types/api';
import { RefreshCw, ShieldAlert, CheckCircle2, Clock, Play, FolderOpen } from 'lucide-react';
import { FileExplorerModal } from './FileExplorerModal';

interface TableManagementGridProps {
  tables: TableDetailedMeta[];
  statuses: Record<string, SyncStatusItem>;
  onTriggerSync: (payload: {
    table_ids: string[];
    formats: string[];
    start_date?: string;
    end_date?: string;
    force_refresh?: boolean;
    provider_kwargs?: Record<string, any>;
  }) => void;
  syncing: boolean;
}

export const TableManagementGrid: React.FC<TableManagementGridProps> = ({
  tables,
  statuses,
  onTriggerSync,
  syncing,
}) => {
  // 选中的数据表以及各表选中的格式集合
  const [selectedTables, setSelectedTables] = useState<string[]>(tables.map((t) => t.table_id));
  const [selectedFormats, setSelectedFormats] = useState<Record<string, { parquet: boolean; csv: boolean }>>(() => {
    const init: Record<string, { parquet: boolean; csv: boolean }> = {};
    tables.forEach((t) => {
      init[t.table_id] = { parquet: true, csv: false };
    });
    return init;
  });

  // 展开折叠的行控制
  const [expandedRows, setExpandedRows] = useState<Record<string, boolean>>({});
  
  // 固化平铺的起止日期与强制刷新配置
  const [startDate, setStartDate] = useState<string>('');
  const [endDate, setEndDate] = useState<string>('');
  const [forceRefresh, setForceRefresh] = useState<boolean>(false);

  // 各表独立的 TDX 驱动模式与路径 state
  const [tableTdxModes, setTableTdxModes] = useState<Record<string, 'online' | 'local'>>({});
  const [tableVipdocDirs, setTableVipdocDirs] = useState<Record<string, string>>({});
  const [downloadingZip, setDownloadingZip] = useState<Record<string, boolean>>({});

  // 文件探查器 Modal 状态
  const [explorerModalOpen, setExplorerModalOpen] = useState<boolean>(false);
  const [explorerTargetTableId, setExplorerTargetTableId] = useState<string>('');
  const [explorerInitialPath, setExplorerInitialPath] = useState<string>('');

  const getTdxMode = (tableId: string) => tableTdxModes[tableId] || 'online';
  const getVipdocDir = (tableId: string) => tableVipdocDirs[tableId] || 'C:\\new_tdx\\vipdoc';

  const setTdxMode = (tableId: string, mode: 'online' | 'local') => {
    setTableTdxModes((prev) => ({ ...prev, [tableId]: mode }));
  };

  const setVipdocDir = (tableId: string, dir: string) => {
    setTableVipdocDirs((prev) => ({ ...prev, [tableId]: dir }));
  };

  const openExplorerModal = (tableId: string, currentPath: string) => {
    setExplorerTargetTableId(tableId);
    setExplorerInitialPath(currentPath || 'C:\\new_tdx\\vipdoc');
    setExplorerModalOpen(true);
  };

  const handleSelectPathFromExplorer = (selectedPath: string) => {
    if (explorerTargetTableId) {
      setVipdocDir(explorerTargetTableId, selectedPath);
    }
  };

  const toggleRowExpand = (tableId: string) => {
    setExpandedRows((prev) => ({ ...prev, [tableId]: !prev[tableId] }));
  };

  const toggleTableSelect = (tableId: string) => {
    if (selectedTables.includes(tableId)) {
      setSelectedTables(selectedTables.filter((t) => t !== tableId));
    } else {
      setSelectedTables([...selectedTables, tableId]);
    }
  };

  const toggleFormatSelect = (tableId: string, format: 'parquet' | 'csv') => {
    setSelectedFormats((prev) => {
      const current = prev[tableId] || { parquet: true, csv: false };
      return {
        ...prev,
        [tableId]: {
          ...current,
          [format]: !current[format],
        },
      };
    });
  };

  const knownTableIds = new Set(DATA_SOURCE_OPTIONS.map((opt) => opt.table_id));

  const handleSelectAll = (checked: boolean) => {
    if (checked) {
      setSelectedTables(tables.filter((t) => knownTableIds.has(t.table_id)).map((t) => t.table_id));
    } else {
      setSelectedTables([]);
    }
  };

  const handleDownloadZip = async (tableId: string) => {
    const dir = getVipdocDir(tableId);
    setTdxMode(tableId, 'local');
    setDownloadingZip((prev) => ({ ...prev, [tableId]: true }));
    try {
      const { apiClient } = await import('../services/apiClient');
      await apiClient.downloadTdxZip(dir);
    } catch (e) {
      console.error('Failed to trigger download', e);
    } finally {
      setDownloadingZip((prev) => ({ ...prev, [tableId]: false }));
    }
  };

  const handleStartSync = (targetTableIds?: string[]) => {
    const targets = targetTableIds || selectedTables;
    if (targets.length === 0) return;

    // 收集所有选中的格式 (并集)
    const formatsSet = new Set<string>();
    targets.forEach((tid) => {
      const fmts = selectedFormats[tid] || { parquet: true, csv: false };
      if (fmts.parquet) formatsSet.add('parquet');
      if (fmts.csv) formatsSet.add('csv');
    });

    const activeFormats = Array.from(formatsSet);
    if (activeFormats.length === 0) activeFormats.push('parquet');

    const firstTdxId = targets.find((t) => t.includes('.tdx'));
    const isTdxLocal = !!(firstTdxId && getTdxMode(firstTdxId) === 'local');
    const provider_kwargs = firstTdxId
      ? {
          mode: getTdxMode(firstTdxId),
          vipdoc_dir: getVipdocDir(firstTdxId),
        }
      : undefined;

    onTriggerSync({
      table_ids: targets,
      formats: activeFormats,
      start_date: startDate || (isTdxLocal ? '1990-01-01' : undefined),
      end_date: endDate || undefined,
      force_refresh: forceRefresh || isTdxLocal,
      provider_kwargs,
    });
  };

  const formatUpdatedAt = (isoStr?: string | null) => {
    if (!isoStr) return null;
    const datePart = isoStr.split('T')[0];
    const timePart = isoStr.split('T')[1]?.substring(0, 5);
    return timePart ? `${datePart} ${timePart}` : datePart;
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden shadow-xl flex flex-col">
      {/* 顶部固化平铺控制栏 */}
      <div className="p-4 bg-slate-950/80 border-b border-slate-800 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <button
            onClick={() => handleSelectAll(selectedTables.length !== tables.length)}
            className="text-xs text-slate-400 hover:text-slate-200 flex items-center space-x-1.5 cursor-pointer font-medium"
          >
            <input
              type="checkbox"
              checked={selectedTables.length === tables.length && tables.length > 0}
              onChange={(e) => handleSelectAll(e.target.checked)}
              className="rounded bg-slate-950 border-slate-700 text-cyan-500 cursor-pointer"
            />
            <span>全选所有数据表 ({selectedTables.length}/{tables.length})</span>
          </button>

          <button
            onClick={() => handleStartSync()}
            disabled={syncing || selectedTables.length === 0}
            className="flex items-center space-x-1.5 px-4 py-1.5 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white rounded-xl text-xs font-medium shadow-md shadow-cyan-900/30 transition-all disabled:opacity-50 cursor-pointer"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${syncing ? 'animate-spin' : ''}`} />
            <span>批量同步所选数据 ({selectedTables.length})</span>
          </button>
        </div>

        {/* 固定平铺展示的时间与刷新参数 */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2 border-t border-slate-800/60 text-xs">
          <div>
            <label htmlFor="gridStartDate" className="block text-slate-400 mb-1 font-medium">
              起始日期 <span className="text-[10px] text-slate-500 font-normal">(留空自动增量 / 首次全量)</span>
            </label>
            <input
              id="gridStartDate"
              type="date"
              min="1990-01-01"
              max="2099-12-31"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="w-full bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-slate-200 focus:outline-none focus:border-cyan-500 font-mono [color-scheme:dark]"
            />
          </div>
          <div>
            <label htmlFor="gridEndDate" className="block text-slate-400 mb-1 font-medium">
              结束日期 <span className="text-[10px] text-slate-500 font-normal">(留空包含今日)</span>
            </label>
            <input
              id="gridEndDate"
              type="date"
              min="1990-01-01"
              max="2099-12-31"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="w-full bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-slate-200 focus:outline-none focus:border-cyan-500 font-mono [color-scheme:dark]"
            />
          </div>
          <div className="flex items-center space-x-2 pt-5">
            <input
              type="checkbox"
              id="gridForceRefresh"
              checked={forceRefresh}
              onChange={(e) => setForceRefresh(e.target.checked)}
              className="rounded bg-slate-900 border-slate-700 text-cyan-500 cursor-pointer"
            />
            <label htmlFor="gridForceRefresh" className="text-slate-300 cursor-pointer select-none">
              强制全量刷新 (忽略本地历史起止记录)
            </label>
          </div>
        </div>
      </div>

      {/* 数据表表格主区域 */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs text-slate-300">
          <thead className="bg-slate-950/80 text-slate-400 font-semibold border-b border-slate-800">
            <tr>
              <th className="py-3 px-3 w-10 text-center">选择</th>
              <th className="py-3 px-3 w-56">数据源 / 表 ID</th>
              <th className="py-3 px-3 min-w-[240px]">物理存储格式与数据范围</th>
              <th className="py-3 px-3 w-60">当前状态</th>
              <th className="py-3 px-3 w-36 text-right">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60 font-mono">
            {tables.map((item) => {
              const isKnownTable = knownTableIds.has(item.table_id);
              const isSelected = selectedTables.includes(item.table_id);
              const isExpanded = expandedRows[item.table_id] ?? false;
              const statusObj = statuses[item.table_id];
              const fmtSelected = selectedFormats[item.table_id] || { parquet: true, csv: false };
              const isTdx = item.table_id.includes('.tdx');
              const curMode = getTdxMode(item.table_id);
              const curDir = getVipdocDir(item.table_id);

              const pqMeta = item.formats.parquet;
              const csvMeta = item.formats.csv;

              return (
                <React.Fragment key={item.table_id}>
                  {/* 主层级 (Table 行) */}
                  <tr className={`hover:bg-slate-800/40 transition-colors ${isSelected ? 'bg-cyan-950/10' : ''}`}>
                    <td className="py-2.5 px-3 text-center">
                      <input
                        type="checkbox"
                        checked={isSelected}
                        disabled={!isKnownTable}
                        onChange={() => isKnownTable && toggleTableSelect(item.table_id)}
                        className={`rounded bg-slate-950 border-slate-700 text-cyan-500 ${
                          isKnownTable ? 'cursor-pointer' : 'cursor-not-allowed opacity-40'
                        }`}
                        title={!isKnownTable ? '非预定义数据表无外部同步驱动' : ''}
                      />
                    </td>

                    {/* 数据源与名称：零额外偏移，100% 绝对统一左对齐 */}
                    <td className="py-2.5 px-3">
                      <div>
                        <div className="font-bold text-slate-100 font-sans text-xs">{item.name}</div>
                        <div className="text-[10px] text-slate-500 font-mono mt-0.5">{item.table_id}</div>
                      </div>
                    </td>

                    {/* 主从分明：默认展示核心格式与条数 Badge，悬浮 (Hover) 高颜值 Glassmorphism 气泡查看详细起止范围与刷盘记录 */}
                    <td className="py-2.5 px-3">
                      <div className="flex flex-col space-y-1.5 text-[10px]">
                        {/* Parquet 格式列 */}
                        <div className="flex items-center space-x-2">
                          <label className="flex items-center space-x-1 cursor-pointer select-none shrink-0">
                            <input
                              type="checkbox"
                              checked={fmtSelected.parquet}
                              onChange={() => toggleFormatSelect(item.table_id, 'parquet')}
                              className="rounded bg-slate-950 border-slate-700 text-cyan-500 shrink-0 cursor-pointer"
                            />
                            <span className="font-bold text-cyan-400">Parquet:</span>
                          </label>
                          {pqMeta.exists ? (
                            <div className="relative group inline-block">
                              <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-md bg-cyan-950/70 border border-cyan-800/50 text-cyan-300 font-mono text-[10px] cursor-pointer hover:bg-cyan-900/60 transition-all shadow-sm">
                                <span>{pqMeta.total_bars.toLocaleString()} 条</span>
                                <span className="text-cyan-400/80 text-[9px] font-sans">ℹ️</span>
                              </span>

                              {/* 高颜值悬浮 Glassmorphic 气泡 */}
                              <div className="absolute bottom-full left-0 mb-2 hidden group-hover:block z-50 min-w-[220px] p-3 bg-slate-900/98 border border-slate-700/80 rounded-xl shadow-2xl shadow-black/90 text-xs font-sans text-slate-200 pointer-events-none transition-all">
                                <div className="font-bold text-cyan-400 pb-1.5 mb-2 border-b border-slate-800/80 flex items-center justify-between">
                                  <span>Parquet 存储明细</span>
                                  <span className="text-[9px] px-1.5 py-0.5 rounded bg-cyan-950 text-cyan-300 font-mono border border-cyan-800/60">zstd 压缩</span>
                                </div>
                                <div className="space-y-1.5 font-mono text-[11px]">
                                  <div className="flex justify-between items-center text-slate-400">
                                    <span className="font-sans text-slate-400">数据总行数:</span>
                                    <span className="text-cyan-300 font-bold">{pqMeta.total_bars.toLocaleString()} 条</span>
                                  </div>
                                  <div className="flex justify-between items-center text-slate-400">
                                    <span className="font-sans text-slate-400">起止时间段:</span>
                                    <span className="text-slate-200 text-[10px]">
                                      {(pqMeta.start_datetime || pqMeta.end_datetime)
                                        ? `${pqMeta.start_datetime?.split('T')[0] || '-'} ~ ${pqMeta.end_datetime?.split('T')[0] || '-'}`
                                        : '无时间戳'}
                                    </span>
                                  </div>
                                  <div className="flex justify-between items-center text-slate-400">
                                    <span className="font-sans text-slate-400">最后刷盘:</span>
                                    <span className="text-slate-300 text-[10px]">{pqMeta.updated_at ? formatUpdatedAt(pqMeta.updated_at) : '未知'}</span>
                                  </div>
                                </div>
                                {/* 气泡小箭头 */}
                                <div className="absolute top-full left-4 -mt-1 border-4 border-transparent border-t-slate-900/95" />
                              </div>
                            </div>
                          ) : (
                            <span className="text-slate-600 font-sans whitespace-nowrap">(未落盘)</span>
                          )}
                        </div>

                        {/* CSV 格式列 */}
                        <div className="flex items-center space-x-2">
                          <label className="flex items-center space-x-1 cursor-pointer select-none shrink-0">
                            <input
                              type="checkbox"
                              checked={fmtSelected.csv}
                              onChange={() => toggleFormatSelect(item.table_id, 'csv')}
                              className="rounded bg-slate-950 border-slate-700 text-cyan-500 shrink-0 cursor-pointer"
                            />
                            <span className="font-bold text-amber-400">CSV:</span>
                          </label>
                          {csvMeta.exists ? (
                            <div className="relative group inline-block">
                              <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-md bg-amber-950/70 border border-amber-800/50 text-amber-300 font-mono text-[10px] cursor-pointer hover:bg-amber-900/60 transition-all shadow-sm">
                                <span>{csvMeta.total_bars.toLocaleString()} 条</span>
                                <span className="text-amber-400/80 text-[9px] font-sans">ℹ️</span>
                              </span>

                              {/* 高颜值悬浮 Glassmorphic 气泡 */}
                              <div className="absolute bottom-full left-0 mb-2 hidden group-hover:block z-50 min-w-[220px] p-3 bg-slate-900/98 border border-slate-700/80 rounded-xl shadow-2xl shadow-black/90 text-xs font-sans text-slate-200 pointer-events-none transition-all">
                                <div className="font-bold text-amber-400 pb-1.5 mb-2 border-b border-slate-800/80 flex items-center justify-between">
                                  <span>CSV 存储明细</span>
                                  <span className="text-[9px] px-1.5 py-0.5 rounded bg-amber-950 text-amber-300 font-mono border border-amber-800/60">明文存储</span>
                                </div>
                                <div className="space-y-1.5 font-mono text-[11px]">
                                  <div className="flex justify-between items-center text-slate-400">
                                    <span className="font-sans text-slate-400">数据总行数:</span>
                                    <span className="text-amber-300 font-bold">{csvMeta.total_bars.toLocaleString()} 条</span>
                                  </div>
                                  <div className="flex justify-between items-center text-slate-400">
                                    <span className="font-sans text-slate-400">起止时间段:</span>
                                    <span className="text-slate-200 text-[10px]">
                                      {(csvMeta.start_datetime || csvMeta.end_datetime)
                                        ? `${csvMeta.start_datetime?.split('T')[0] || '-'} ~ ${csvMeta.end_datetime?.split('T')[0] || '-'}`
                                        : '无时间戳'}
                                    </span>
                                  </div>
                                  <div className="flex justify-between items-center text-slate-400">
                                    <span className="font-sans text-slate-400">最后刷盘:</span>
                                    <span className="text-slate-300 text-[10px]">{csvMeta.updated_at ? formatUpdatedAt(csvMeta.updated_at) : '未知'}</span>
                                  </div>
                                </div>
                                {/* 气泡小箭头 */}
                                <div className="absolute top-full left-4 -mt-1 border-4 border-transparent border-t-slate-900/95" />
                              </div>
                            </div>
                          ) : (
                            <span className="text-slate-600 font-sans whitespace-nowrap">(未落盘)</span>
                          )}
                        </div>
                      </div>
                    </td>

                    {/* 当前状态列 */}
                    <td className="py-2.5 px-3">
                      {statusObj?.status === 'running' ? (
                        <div
                          className="inline-flex items-center space-x-1.5 px-2 py-0.5 rounded-full bg-cyan-950 border border-cyan-800 text-cyan-300 text-[10px] font-mono"
                          title={statusObj.message || ''}
                        >
                          <Clock className="w-3 h-3 animate-spin text-cyan-400 shrink-0" />
                          <span className="truncate max-w-[210px]">
                            {statusObj.percentage.toFixed(0)}% - {statusObj.message || statusObj.current_symbol}
                          </span>
                        </div>
                      ) : statusObj?.status === 'success' ? (
                        <div
                          className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-full bg-emerald-950 border border-emerald-800 text-emerald-300 text-[10px]"
                          title={statusObj.message || '已成功同步完成'}
                        >
                          <CheckCircle2 className="w-3 h-3 text-emerald-400 shrink-0" />
                          <span className="font-sans truncate max-w-[210px]">{statusObj.message || '已完成'}</span>
                        </div>
                      ) : statusObj?.status === 'failed' ? (
                        <div
                          className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-full bg-red-950 border border-red-800 text-red-300 text-[10px] cursor-help"
                          title={statusObj.message || statusObj.error_msg || '未知同步失败'}
                        >
                          <ShieldAlert className="w-3 h-3 text-red-400 shrink-0" />
                          <span className="font-sans truncate max-w-[200px]">{statusObj.message || statusObj.error_msg || '同步失败'}</span>
                        </div>
                      ) : (
                        <span className="text-slate-500 text-[11px] font-sans">就绪</span>
                      )}
                    </td>

                    {/* 操作列：包含高级设置（针对 TDX）与立即同步按钮，右侧绝对对齐 */}
                    <td className="py-2.5 px-3 text-right whitespace-nowrap">
                      <div className="flex items-center justify-end space-x-1.5">
                        {isTdx && (
                          <button
                            onClick={() => toggleRowExpand(item.table_id)}
                            className={`p-1 rounded-lg text-xs font-medium transition-colors cursor-pointer ${
                              isExpanded ? 'bg-cyan-950 text-cyan-400 border border-cyan-800' : 'bg-slate-800 hover:bg-slate-700 text-slate-400'
                            }`}
                            title="配置 TDX 驱动参数 (Online / Local 模式)"
                          >
                            <span className="text-[10px] px-1">⚙️ 高级</span>
                          </button>
                        )}
                        {isKnownTable ? (
                          <button
                            onClick={() => handleStartSync([item.table_id])}
                            disabled={syncing}
                            className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg text-xs font-medium transition-colors inline-flex items-center space-x-1 cursor-pointer disabled:opacity-50 font-sans"
                          >
                            <Play className="w-3 h-3 text-cyan-400 shrink-0" />
                            <span>立即同步</span>
                          </button>
                        ) : (
                          <span
                            className="px-2 py-1 bg-slate-800/60 border border-slate-700/50 text-slate-500 rounded-lg text-[11px] font-sans select-none"
                            title="自定义/非预定义数据表，无外部在线数据源驱动，仅支持物理磁盘读取解析"
                          >
                            离线表 (仅解析)
                          </span>
                        )}
                      </div>
                    </td>
                  </tr>

                  {/* 通达信表展开的超紧凑模式配置 */}
                  {isTdx && isExpanded && (
                    <tr className="bg-slate-950/60">
                      <td colSpan={5} className="py-2 px-4 pl-12 border-t border-b border-slate-800/40">
                        <div className="flex flex-wrap items-center justify-between gap-3 text-xs">
                          <div className="flex items-center space-x-4">
                            <span className="text-cyan-400 font-semibold text-[11px]">TDX 模式:</span>
                            <label className="flex items-center space-x-1.5 cursor-pointer text-slate-300">
                              <input
                                type="radio"
                                name={`mode_${item.table_id}`}
                                value="online"
                                checked={curMode === 'online'}
                                onChange={() => setTdxMode(item.table_id, 'online')}
                                className="text-cyan-500 focus:ring-cyan-500 cursor-pointer"
                              />
                              <span>🌐 TCP 在线 (online)</span>
                            </label>

                            <label className="flex items-center space-x-1.5 cursor-pointer text-slate-300">
                              <input
                                type="radio"
                                name={`mode_${item.table_id}`}
                                value="local"
                                checked={curMode === 'local'}
                                onChange={() => setTdxMode(item.table_id, 'local')}
                                className="text-cyan-500 focus:ring-cyan-500 cursor-pointer"
                              />
                              <span>📁 本地 vipdoc (local)</span>
                            </label>
                          </div>

                          {curMode === 'local' && (
                            <div className="flex items-center space-x-2 flex-1 max-w-lg justify-end font-mono">
                              <span className="text-slate-400 text-[11px] shrink-0 font-sans">vipdoc 路径:</span>
                              <input
                                type="text"
                                value={curDir}
                                onChange={(e) => setVipdocDir(item.table_id, e.target.value)}
                                placeholder="C:\new_tdx\vipdoc"
                                className="bg-slate-900 border border-slate-800 rounded px-2 py-0.5 text-xs text-slate-200 focus:outline-none focus:border-cyan-500 w-48"
                              />
                              <button
                                type="button"
                                onClick={() => openExplorerModal(item.table_id, curDir)}
                                className="px-2 py-0.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 rounded text-[10px] font-sans transition-colors shrink-0 cursor-pointer flex items-center space-x-1"
                                title="在线探查与查看本地目录文件"
                              >
                                <FolderOpen className="w-3 h-3 text-cyan-400" />
                                <span>查看目录</span>
                              </button>
                              <button
                                type="button"
                                onClick={() => handleDownloadZip(item.table_id)}
                                disabled={downloadingZip[item.table_id]}
                                className="px-2 py-0.5 bg-cyan-950 hover:bg-cyan-900 border border-cyan-800/80 text-cyan-300 rounded text-[10px] font-sans transition-colors shrink-0 cursor-pointer disabled:opacity-50"
                              >
                                {downloadingZip[item.table_id] ? '下载中...' : '一键下载官方包'}
                              </button>
                            </div>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* 本地目录文件探查器 Modal */}
      <FileExplorerModal
        isOpen={explorerModalOpen}
        initialPath={explorerInitialPath}
        onClose={() => setExplorerModalOpen(false)}
        onSelectDirectory={handleSelectPathFromExplorer}
      />
    </div>
  );
};
