import time
from loguru import logger
import polars as pl
from pathlib import Path
from .task_planner import TaskPlanner
from ..provider.provider_manager import ProviderManager
from .metadata_manager import MetadataManager
from ..utils.time_utils import ts_to_iso, ts_to_str
from ..storage.storage_factory import StorageFactory
from ..config.settings import settings
from .sync_tracker import sync_tracker
from typing import Any

class SyncManager:
    """
    同步总管：串联规划、采集、落地、巡检、盖章整个流程。
    支持单次抓取、多格式并行落地。
    """

    def __init__(self, data_dir: str = None):
        # 内部自治实例化：基于配置中心
        self.data_dir = data_dir or settings.data_dir
        self.metadata_mgr = MetadataManager(self.data_dir)
        self.planner = TaskPlanner(self.metadata_mgr)
        self.provider_mgr = ProviderManager()

    def sync(self, table_ids: list[str] | str, formats: list[str] | str, start_date: str = None, end_date: str = None, force_refresh: bool = False, batch_size: int = 100, symbol_limit: int = None, provider_kwargs: dict = None):
        """
        执行全自动化同步闭环。
        支持多表、多格式列表传入。

        Args:
            table_ids: 需要同步的表ID或列表
            formats: 需要存储的格式或列表
            start_date: 起始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            force_refresh: 是否强制刷新水位线
            batch_size: 批处理大小
            symbol_limit: 限制同步的证券数量 (常用于生成测试数据)
            provider_kwargs: 传递给 Provider 构造函数的额外参数 (如 TDXProvider 的 mode, vipdoc_dir)
        """
        if isinstance(table_ids, str):
            table_ids = [table_ids]
        if isinstance(formats, str):
            formats = [formats]

        time_info = f"range=[{start_date or 'epoch_start'} -> {end_date or 'latest_now'}]"
        logger.info(f"[*] Starting orchestrated sync for {table_ids} into {formats} ({time_info}, batch_size={batch_size}, force_refresh={force_refresh}, symbol_limit={symbol_limit})...")

        for table_id in table_ids:
            self._sync_single_table(table_id, formats, start_date, end_date, force_refresh, batch_size, symbol_limit, provider_kwargs)

    def _sync_single_table(self, table_id: str, formats: list[str], start_date: str, end_date: str, force_refresh: bool, batch_size: int, symbol_limit: int = None, provider_kwargs: dict = None):
        """
        单表同步逻辑：一次拉取，多处落地。

        Args:
            table_id: 表标识符
            formats: 存储格式列表
            start_date: 起始日期
            end_date: 结束日期
            force_refresh: 是否强制刷新
            batch_size: 批处理大小
            symbol_limit: 限制同步的证券数量 (常用于生成测试数据)
        """
        sync_tracker.start_task(table_id, message=f"正在准备同步 {table_id}...")
        storages = {}

        try:
            # 1. 获取驱动
            provider = self.provider_mgr.get_provider(table_id, **(provider_kwargs or {}))
            # 获取类别
            category = provider.get_table_category(table_id)
            
            # 2. 获取所有目标存储引擎并重置未提交暂存
            storages = {fmt: StorageFactory.get_storage(fmt, self.data_dir, category=category) for fmt in formats}
            for storage in storages.values():
                storage.category = category
                storage.cleanup(table_id)
            
            # 3. 自动发现全量代码
            symbols = provider.get_all_symbols(table_id)
            
            # 限制代码数量
            if symbol_limit:
                symbols = symbols[:symbol_limit]
                logger.info(f"[*] Symbol limit applied: {symbol_limit}")
            
            # 4. 规划补丁
            sync_tracker.update_progress(table_id, current=0, total=len(symbols), message=f"正在规划 {len(symbols)} 个代码的数据水位线...")
            tasks = self.planner.plan(table_id, formats, symbols, start_date, end_date, force_refresh=force_refresh)
            total_tasks = len(tasks)
            if tasks:
                start_ts_min = min(t['start'] for t in tasks)
                end_ts_max = max(t['end'] for t in tasks)
                time_range_desc = f"[{ts_to_str(start_ts_min)} -> {ts_to_str(end_ts_max)}]"
            else:
                time_range_desc = "None (本地已是最新)"
            sync_tracker.update_progress(table_id, current=0, total=total_tasks, message=f"规划完成: 需补全 {total_tasks} 个代码 {time_range_desc}")
            logger.info(f"[*] Task planning finished for {table_id}. {total_tasks}/{len(symbols)} symbols need to be patched. Time range: {time_range_desc}")
            
            # 5. 执行采集与落地循环
            last_success_df = None
            success_count = 0
            data_written = False
            
            # 将任务切分为批次
            for batch_idx in range(0, total_tasks, batch_size):
                batch_tasks = tasks[batch_idx : batch_idx + batch_size]
                batch_dfs = []
                
                logger.info(f"[BATCH] Processing batch {batch_idx//batch_size + 1} ({len(batch_tasks)} symbols)")
                
                for j, task in enumerate(batch_tasks):
                    symbol = task['symbol']
                    start_ts = task['start']
                    end_ts = task['end']
                    
                    # 实时进度 Log 与 命令行动态提示信息更新
                    current_idx = batch_idx + j + 1
                    s_str = ts_to_str(start_ts)
                    e_str = ts_to_str(end_ts)
                    msg_text = f"正在抓取 {symbol} ({current_idx}/{total_tasks}) [{s_str} -> {e_str}]"
                    sync_tracker.update_progress(table_id, current=current_idx, total=total_tasks, current_symbol=symbol, message=msg_text)
                    logger.info(f"[PROGRESS] {table_id} | {current_idx}/{total_tasks} | {symbol} | [{s_str} -> {e_str}]")
                    
                    try:
                        # Step 1: Provider 采集标准化数据
                        df = provider.fetch(table_id, symbol, start_ts, end_ts)
                        
                        if last_success_df is None or not df.is_empty():
                            last_success_df = df
                        
                        if not df.is_empty():
                            batch_dfs.append(df)
                            logger.debug(f"[Sync] {symbol} 下载成功 ({len(df)} rows)")
                        else:
                            logger.debug(f"[Sync] {symbol} (No new data)")
                        
                        success_count += 1
                    except Exception as e:
                        # 失败策略：标记失败与错误信息并抛出异常，停止任务
                        logger.error(f"[Sync] {symbol} 失败，执行 Fail-Fast 策略: {e}")
                        sync_tracker.finish_task(table_id, success=False, message=f"抓取 {symbol} 失败: {e}", error_msg=str(e))
                        raise e
                
                # Step 2: 批次内存聚合与多路分片暂存下沉 (写入独立分片，消除 OOM 与写放大)
                if batch_dfs:
                    big_df = pl.concat(batch_dfs)
                    
                    # 获取表类别 (TS 或 EV) 和排序键
                    category = provider.get_table_category(table_id)
                    sort_keys = provider.get_sort_keys(table_id)
                    
                    sync_tracker.update_progress(table_id, current=current_idx, total=total_tasks, current_symbol=symbol, message=f"正在暂存 {len(batch_dfs)} 个代码数据至 {formats}...")

                    for fmt, storage in storages.items():
                        logger.debug(f"[BATCH] Writing partition batch to storage: {fmt} (category={category})")
                        # 批处理循环中：直接写入分片，避免中间过程重复大文件合并与 OOM
                        if category == "event":
                            storage.write_event(table_id, big_df, sort_keys=sort_keys)
                        else:
                            # 默认为 TS
                            storage.write_series(table_id, big_df)
                    
                    data_written = True
                    logger.info(f"[BATCH] Aggregated {len(batch_dfs)} symbols, total {len(big_df)} rows written to {formats}.")
                    batch_dfs.clear()
                    del big_df

            # 全表所有批次成功采集并暂存后，统一触发流式合并与排序刷盘 (Finalize)
            if data_written:
                mode_to_use = "overwrite" if force_refresh else "append"
                sort_keys = provider.get_sort_keys(table_id) if category == "event" else None
                for fmt, storage in storages.items():
                    logger.info(f"[*] Finalizing staged partitions for {table_id} ({fmt}, mode={mode_to_use})...")
                    def _on_finalize_progress(stage_name: str, cur: int, total: int):
                        msg = f"[收敛落盘] 正在合并 {stage_name} ({cur}/{total})..."
                        sync_tracker.update_progress(table_id, current=total_tasks, total=total_tasks, message=msg)

                    storage.finalize(
                        table_id,
                        mode=mode_to_use,
                        sort_keys=sort_keys,
                        progress_callback=_on_finalize_progress,
                    )

            # 统一更新元数据水位线，防止中途中断导致水位线虚高
            for fmt, storage in storages.items():
                self._update_metadata(table_id, fmt, storage, last_success_df, data_written, force_refresh)
            
            if total_tasks == 0:
                finish_msg = "本地数据已是最新 (无需补全)"
            else:
                finish_msg = f"已成功同步完成 ({success_count}/{total_tasks} 代码)"

            sync_tracker.finish_task(table_id, success=True, message=finish_msg)
            logger.info(f"[+] Sync finished for {table_id}. {finish_msg}")
        except Exception as err:
            # 发生异常时，清理各存储引擎未提交的暂存分片，杜绝脏文件残留
            for fmt, storage in storages.items():
                try:
                    storage.cleanup(table_id)
                except Exception:
                    pass
            sync_tracker.finish_task(table_id, success=False, message=f"同步中断: {err}", error_msg=str(err))
            raise err

    def _update_metadata(self, table_id: str, format: str, storage: Any, last_success_df: pl.DataFrame, data_written: bool, force_refresh: bool):
        """
        执行物理巡检并更新元数据
        """
        logger.info(f"[*] Updating metadata for {table_id} ({format})...")
        
        # 1. 基础物理统计 (低 IO)
        total_bars = storage.get_total_bars(table_id)
        start_ts, end_ts = storage.get_global_time_range(table_id)
        
        # 2. 元数据加载
        old_metadata = self.metadata_mgr.load(table_id, format)
        
        # 3. 如果物理巡检结果为 0，且无元数据或已存在元数据时，执行静默拦截逻辑
        if total_bars == 0:
            if not old_metadata:
                # 场景 A（初次同步）：若本地无 metadata.json，直接记录 logger.warning 并 return
                logger.warning(f"[!] No data found for {table_id} | {format} on disk. Skipping metadata creation.")
                return
            else:
                # 场景 B（增量同步）：若本地已有元数据，直接 return，不更新现有 JSON 文件
                logger.debug(f"[*] Total bars is 0, but metadata already exists for {table_id} | {format}. Keeping existing metadata.")
                return

        # 4. 物理库存变更判定：仅在数据有新增、强制刷新或元数据不存在时才落盘
        if not data_written and old_metadata and not force_refresh:
            logger.debug(f"[*] No new data written and metadata exists for {table_id} | {format}. Skipping metadata update.")
            return

        # 5. Schema 提取
        schema_dict = old_metadata.get("schema", {}) if old_metadata else {}
        if last_success_df is not None:
            schema_dict = {k: str(v) for k, v in last_success_df.schema.items()}
        elif not schema_dict:
            try:
                table_path = Path(self.data_dir) / format / table_id
                sample_pqs = list(table_path.glob("year=*/data.parquet")) + list(table_path.glob("data.parquet"))
                if sample_pqs:
                    s_schema = pl.scan_parquet(str(sample_pqs[0])).collect_schema()
                    schema_dict = {k: str(v) for k, v in s_schema.items()}
            except Exception:
                pass
        
        # 6. 根据 category 分类构建统计结构
        category = storage.category
        
        # 动态判断 layout：平铺文件存在时为 "flat"，否则为 "hive"
        table_path = Path(self.data_dir) / format / table_id
        flat_csv = table_path / "data.csv"
        flat_pq = table_path / "data.parquet"
        layout = "flat" if flat_csv.exists() or flat_pq.exists() else "hive"
        
        now_ms = int(time.time() * 1000)
        updated_at_str = ts_to_iso(now_ms)

        # 补充存储元信息（平铺在第一级）
        metadata = {
            "table_id": table_id,
            "category": category,
            "format": format,
            "partition": storage.partition,
            "layout": layout,
            "schema": schema_dict,
            "statistics": {} # 稍后填充
        }

        if category == "timeseries":
            # TS 类别：补齐所有元数据字段（高 IO 扫描）
            all_symbols = storage.get_all_symbols(table_id)
            unique_tss = storage.get_unique_timestamps(table_id)
            metadata["statistics"] = {
                "updated_at": updated_at_str,
                "start_timestamp": start_ts,
                "end_timestamp": end_ts,
                "start_datetime": ts_to_iso(start_ts),
                "end_datetime": ts_to_iso(end_ts),
                "total_bars": total_bars,
                "symbol_count": len(all_symbols),
                "time_steps": len(unique_tss)
            }
        elif start_ts == 0 and end_ts == 0:
            # 平铺模式（无 timestamp）：仅保留基础统计
            metadata["statistics"] = {
                "updated_at": updated_at_str,
                "total_bars": total_bars
            }
        else:
            # EV 类别：跳过全量扫描，仅保留基础统计 (0 IO 扫描)
            metadata["statistics"] = {
                "updated_at": updated_at_str,
                "start_timestamp": start_ts,
                "end_timestamp": end_ts,
                "start_datetime": ts_to_iso(start_ts),
                "end_datetime": ts_to_iso(end_ts),
                "total_bars": total_bars
            }

        # 6. 原子化保存元数据
        self.metadata_mgr.save(table_id, format, metadata)
        logger.info(f"[+] Metadata updated for {table_id} | {format}")


def sync(
    table_ids: list[str] | str,
    formats: list[str] | str = "parquet",
    start_date: str = None,
    end_date: str = None,
    force_refresh: bool = False,
    batch_size: int = 100,
    symbol_limit: int = None,
    data_dir: str = None,
    provider_kwargs: dict = None
):
    """
    触发全自动化同步闭环的快捷函数
    
    Args:
        table_ids: 表 ID 或表 ID 列表
        formats: 落地格式 ('parquet', 'csv', 或 ['parquet', 'csv'])
        start_date: 起始日期 ('YYYY-MM-DD')
        end_date: 结束日期 ('YYYY-MM-DD')
        force_refresh: 是否强制全量覆盖刷新
        batch_size: 批处理数量
        symbol_limit: 限制处理的证券数
        data_dir: 自定义数据存储根目录
        provider_kwargs: 传递给 Provider 的选项字典
    """
    sm = SyncManager(data_dir=data_dir)
    return sm.sync(
        table_ids=table_ids,
        formats=formats,
        start_date=start_date,
        end_date=end_date,
        force_refresh=force_refresh,
        batch_size=batch_size,
        symbol_limit=symbol_limit,
        provider_kwargs=provider_kwargs
    )
