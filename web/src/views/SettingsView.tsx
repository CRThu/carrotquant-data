import React from 'react';
import { DATA_SOURCE_OPTIONS, type ColorMode } from '../types/api';
import { Database, Palette, Server, CheckCircle2, Activity } from 'lucide-react';

interface SettingsViewProps {
  currentTableId: string;
  onTableChange: (tableId: string) => void;
  colorMode: ColorMode;
  onColorModeChange: (mode: ColorMode) => void;
  serverOnline?: boolean;
  latency?: number | null;
  healthInfo?: {
    status: string;
    version: string;
    data_dir: string;
    log_dir?: string;
    log_level?: string;
    active_tasks: number;
  } | null;
}

export const SettingsView: React.FC<SettingsViewProps> = ({
  currentTableId,
  onTableChange,
  colorMode,
  onColorModeChange,
  serverOnline = true,
  latency = null,
  healthInfo = null,
}) => {
  const loading = healthInfo === null && serverOnline;

  const selectedOpt = DATA_SOURCE_OPTIONS.find((opt) => opt.table_id === currentTableId) || DATA_SOURCE_OPTIONS[0];

  return (
    <div className="space-y-6 max-w-5xl mx-auto pb-10 animate-in fade-in duration-300">
      {/* 视图 Header: 统一格式的工作区表头 */}
      <div className="bg-slate-900/60 p-3.5 rounded-2xl border border-slate-800 flex items-center justify-between gap-4">
        <div className="flex items-center space-x-3">
          <div className="p-2 bg-cyan-950/60 rounded-xl border border-cyan-800/50 text-cyan-400 font-bold text-sm">
            ⚙️
          </div>
          <div>
            <h1 className="text-sm font-bold text-slate-100">系统设置</h1>
            <p className="text-[10px] text-slate-400 mt-0.5">
              默认数据源、配色偏好与 API 状态
            </p>
          </div>
        </div>
      </div>

      {/* 模块 1: 🗄️ 全局默认数据源设置 */}
      <section className="bg-slate-900/60 border border-slate-800 rounded-xl p-5 space-y-4 shadow-sm">
        <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
          <div className="flex items-center space-x-2">
            <Database className="w-5 h-5 text-cyan-400" />
            <h2 className="text-sm font-semibold text-slate-200">默认数据源与驱动配置</h2>
          </div>
          <span className="text-[11px] font-mono bg-cyan-950 text-cyan-400 px-2 py-0.5 rounded border border-cyan-800/50">
            {selectedOpt.source.toUpperCase()}
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label htmlFor="settingsDataSourceSelect" className="block text-xs text-slate-400 mb-1.5 font-medium">
              选择默认数据表 (Table ID)
            </label>
            <select
              id="settingsDataSourceSelect"
              value={currentTableId}
              onChange={(e) => onTableChange(e.target.value)}
              className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-cyan-500 cursor-pointer font-mono"
            >
              {DATA_SOURCE_OPTIONS.map((opt) => (
                <option key={opt.id} value={opt.table_id} className="bg-slate-900 text-slate-200">
                  [{opt.source.toUpperCase()}] {opt.name} ({opt.table_id})
                </option>
              ))}
            </select>
          </div>

          <div className="bg-slate-950/80 border border-slate-800/80 rounded-lg p-3 text-xs space-y-1.5">
            <div className="text-slate-400 font-medium">当前选中数据表详情：</div>
            <div className="text-slate-200 font-bold">{selectedOpt.name}</div>
            <div className="text-slate-400 font-mono text-[11px]">ID: {selectedOpt.table_id}</div>
            <div className="text-slate-500 text-[11px]">{selectedOpt.description}</div>
          </div>
        </div>
      </section>

      {/* 模块 2: 🎨 终端涨跌配色主题 */}
      <section className="bg-slate-900/60 border border-slate-800 rounded-xl p-5 space-y-4 shadow-sm">
        <div className="flex items-center space-x-2 border-b border-slate-800/80 pb-3">
          <Palette className="w-5 h-5 text-amber-400" />
          <h2 className="text-sm font-semibold text-slate-200">终端涨跌配色主题</h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* A 股模式: 红涨绿跌 */}
          <button
            type="button"
            onClick={() => onColorModeChange('redUpGreenDown')}
            className={`p-4 rounded-xl border text-left transition-all relative cursor-pointer ${
              colorMode === 'redUpGreenDown'
                ? 'bg-rose-950/20 border-rose-500/50 text-slate-100 shadow-md shadow-rose-950/30'
                : 'bg-slate-950/50 border-slate-800 text-slate-400 hover:border-slate-700'
            }`}
          >
            {colorMode === 'redUpGreenDown' && (
              <CheckCircle2 className="w-4 h-4 text-rose-500 absolute top-3 right-3" />
            )}
            <div className="font-semibold text-xs text-slate-200 mb-1 flex items-center gap-1.5">
              <span>🇨🇳 A股模式</span>
              <span className="text-[10px] text-rose-400 font-mono">(红涨绿跌)</span>
            </div>
            <p className="text-[11px] text-slate-400 mb-3">符合中国 A 股/港股市场的经典交易配色习惯。</p>

            {/* 视觉对比卡片 */}
            <div className="flex items-center space-x-2 text-[11px] font-mono">
              <span className="px-2 py-0.5 bg-rose-500/20 text-rose-400 border border-rose-500/30 rounded">
                ▲ +2.35%
              </span>
              <span className="px-2 py-0.5 bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 rounded">
                ▼ -1.18%
              </span>
            </div>
          </button>

          {/* 美股模式: 绿涨红跌 */}
          <button
            type="button"
            onClick={() => onColorModeChange('greenUpRedDown')}
            className={`p-4 rounded-xl border text-left transition-all relative cursor-pointer ${
              colorMode === 'greenUpRedDown'
                ? 'bg-emerald-950/20 border-emerald-500/50 text-slate-100 shadow-md shadow-emerald-950/30'
                : 'bg-slate-950/50 border-slate-800 text-slate-400 hover:border-slate-700'
            }`}
          >
            {colorMode === 'greenUpRedDown' && (
              <CheckCircle2 className="w-4 h-4 text-emerald-500 absolute top-3 right-3" />
            )}
            <div className="font-semibold text-xs text-slate-200 mb-1 flex items-center gap-1.5">
              <span>🇺🇸 美股/国际模式</span>
              <span className="text-[10px] text-emerald-400 font-mono">(绿涨红跌)</span>
            </div>
            <p className="text-[11px] text-slate-400 mb-3">符合美股、加密货币与国际金融市场的通用习惯。</p>

            {/* 视觉对比卡片 */}
            <div className="flex items-center space-x-2 text-[11px] font-mono">
              <span className="px-2 py-0.5 bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 rounded">
                ▲ +2.35%
              </span>
              <span className="px-2 py-0.5 bg-rose-500/20 text-rose-400 border border-rose-500/30 rounded">
                ▼ -1.18%
              </span>
            </div>
          </button>
        </div>
      </section>

      {/* 模块 3: 🌐 后端配置与 REST API 服务诊断 */}
      <section className="bg-slate-900/60 border border-slate-800 rounded-xl p-5 space-y-4 shadow-sm">
        <div className="flex items-center space-x-2 border-b border-slate-800/80 pb-3">
          <Server className="w-5 h-5 text-emerald-400" />
          <h2 className="text-sm font-semibold text-slate-200">后端配置与服务诊断</h2>
        </div>

        {loading ? (
          <div className="text-xs text-slate-500 py-4 flex items-center space-x-2">
            <Activity className="w-4 h-4 animate-spin text-cyan-400" />
            <span>正在探查后端 REST API 服务诊断信息...</span>
          </div>
        ) : healthInfo ? (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
            <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
              <div className="text-slate-500 text-[11px] mb-1">REST API 状态 & 延迟</div>
              <div className="flex items-center space-x-2">
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse" />
                <span className="font-mono text-slate-200 font-bold">在线</span>
                {latency !== null && (
                  <span className="font-mono text-cyan-400 text-[11px]">({latency}ms)</span>
                )}
              </div>
            </div>

            <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
              <div className="text-slate-500 text-[11px] mb-1">系统版本号</div>
              <div className="font-mono text-slate-200 font-bold">{healthInfo.version || 'v1.2'}</div>
            </div>

            <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
              <div className="text-slate-500 text-[11px] mb-1">后台活动同步任务</div>
              <div className="font-mono text-slate-200 font-bold">{healthInfo.active_tasks} 个</div>
            </div>

            <div className="bg-slate-950 p-3 rounded-lg border border-slate-800 md:col-span-3">
              <div className="text-slate-500 text-[11px] mb-1">物理数据落盘存储目录 (data_dir)</div>
              <div className="font-mono text-cyan-300 select-all truncate">{healthInfo.data_dir}</div>
            </div>

            <div className="bg-slate-950 p-3 rounded-lg border border-slate-800 md:col-span-2">
              <div className="text-slate-500 text-[11px] mb-1">日志落盘存储目录 (log_dir)</div>
              <div className="font-mono text-cyan-300 select-all truncate">{healthInfo.log_dir || 'logs'}</div>
            </div>

            <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
              <div className="text-slate-500 text-[11px] mb-1">系统日志级别 (log_level)</div>
              <div className="font-mono text-cyan-400 font-bold">{healthInfo.log_level || 'INFO'}</div>
            </div>
          </div>
        ) : (
          <div className="p-3 bg-red-950/20 border border-red-800/40 rounded-lg text-xs text-red-400">
            ⚠ REST API 未正常连接，请检查后端 `cqdata server` 是否已正常启动。
          </div>
        )}
      </section>
    </div>
  );
};
