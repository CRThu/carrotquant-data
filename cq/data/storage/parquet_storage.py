import os
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable
from loguru import logger
import polars as pl
from .base import StorageManager
from ..service.metadata_manager import MetadataManager

class ParquetStorage(StorageManager):
    """
    Parquet 存储实现类，按年度大表存储。
    TS 路径规则：data_dir/parquet/{table_id}/year=YYYY/data.parquet
    EV 路径规则：data_dir/parquet/{table_id}/year=YYYY/data.parquet
    """

    def __init__(self, data_dir: str = "data/parquet", category: str = "timeseries", partition: str = None, layout: str = "hive"):
        # 逻辑纠偏：如果是 EV，partition 默认为 "none"；如果是 TS，默认为 "none" (因为 Parquet 按年聚合，物理文件级别分区为 none)
        if partition is None:
            partition = "none"
            
        super().__init__(category=category)
        self.data_dir = Path(data_dir)
        self._partition = partition
        self._layout = layout
        self._lock = threading.Lock()

    @property
    def partition(self) -> str:
        return self._partition

    @property
    def layout(self) -> str:
        return self._layout

    def _get_series_path(self, table_id: str, year: int) -> Path:
        """获取 TS 年度 Parquet 文件的完整路径。"""
        return self.data_dir / table_id / f"year={year}" / "data.parquet"

    def _get_event_path(self, table_id: str, year: int) -> Path:
        """获取 EV 数据文件的完整路径。文件名固定为 data。"""
        return self.data_dir / table_id / f"year={year}" / "data.parquet"

    def _read_with_schema(self, table_id: str, path: Path, schema_override: dict = None) -> pl.DataFrame:
        """辅助方法：使用元数据中的 Schema 强锁类型读取 Parquet"""
        # 1. 物理读取
        df = pl.read_parquet(path)
        
        # 2. 优先使用传入的 override schema (用于同步过程中的增量合并)
        if schema_override:
            # 过滤掉不存在于 df 中的列，防止 cast 报错
            valid_schema = {k: v for k, v in schema_override.items() if k in df.columns}
            return df.cast(valid_schema)

        # 3. 加载元数据
        meta_mgr = MetadataManager(self.data_dir.parent)
        metadata = meta_mgr.load(table_id, "parquet")
        
        schema_dict = metadata.get("schema")
        if schema_dict:
            # 映射表：String -> Polars DataType
            type_map = {
                "Int64": pl.Int64,
                "Float64": pl.Float64,
                "String": pl.String,
                "Boolean": pl.Boolean,
                "Date": pl.Date,
                "Datetime": pl.Datetime
            }
            
            polars_schema = {}
            for col, dtype_str in schema_dict.items():
                if col not in df.columns:
                    continue
                # 处理可能带参数的 Datetime 字符串
                if dtype_str.startswith("Datetime"):
                    polars_schema[col] = pl.Datetime
                else:
                    polars_schema[col] = type_map.get(dtype_str, pl.String)
            
            # 显式执行 cast 强制对齐类型
            return df.cast(polars_schema)
            
        # 强制要求元数据：保持架构统一性
        raise RuntimeError(f"Metadata not found for table '{table_id}' (format: parquet). "
                          f"Parquet reading requires explicit schema from metadata.json to ensure type safety.")

    def read_series(self, table_id: str, symbol: str = None, year: int = None) -> pl.DataFrame:
        """读取 TS 数据。按 symbol 过滤。"""
        if year is None:
            raise ValueError("Year must be specified for reading series data")

        path = self._get_series_path(table_id, year)
        if not path.exists():
            return pl.DataFrame()
        
        df = self._read_with_schema(table_id, path)
        if df.is_empty():
            return df
        
        if symbol:
            df = df.filter(pl.col("symbol") == symbol)
        return df.sort("timestamp")

    def _get_flat_event_path(self, table_id: str) -> Path:
        """获取平铺 EV 数据文件路径（无 Hive 分区）。"""
        return self.data_dir / table_id / "data.parquet"

    def _is_flat_event(self, table_id: str) -> bool:
        """判断该表是否使用平铺布局（无 timestamp 列的板块数据等）。"""
        return self._get_flat_event_path(table_id).exists()

    def read_event(self, table_id: str, year: int = None) -> pl.DataFrame:
        """读取 EV 数据。优先检查平铺文件，其次按年份读取。"""
        # 平铺模式
        if self._is_flat_event(table_id):
            path = self._get_flat_event_path(table_id)
            if not path.exists():
                return pl.DataFrame()
            return self._read_with_schema(table_id, path)
        # Hive 分区模式
        if year is None:
            raise ValueError("Year must be specified for partitioned event data")
        path = self._get_event_path(table_id, year)
        if not path.exists():
            return pl.DataFrame()
        return self._read_with_schema(table_id, path)

    def _get_staging_dir(self, table_id: str, year: int = None) -> Path:
        """获取分片暂存目录 (.staging)"""
        if year is not None:
            return self.data_dir / table_id / f"year={year}" / ".staging"
        return self.data_dir / table_id / ".staging"

    def write_series(self, table_id: str, df: pl.DataFrame, mode: str = "append"):
        """
        写入时间序列 (TS) 数据分片至 .staging 暂存目录。
        按年切分毫秒级写入独立的轻量分片，0 读盘开销，0 内存膨胀。
        后续需调用 finalize 统一流式收敛落盘。
        """
        if df.is_empty():
            return

        with self._lock:
            df = df.with_columns(
                pl.from_epoch(pl.col("timestamp"), time_unit="ms").dt.year().alias("_year")
            )
            for (year,), group_df in df.partition_by(["_year"], as_dict=True).items():
                patch_df = group_df.drop("_year")
                stage_dir = self._get_staging_dir(table_id, year)
                stage_dir.mkdir(parents=True, exist_ok=True)
                part_path = stage_dir / f"part_{uuid.uuid4().hex}.parquet"
                patch_df.write_parquet(part_path, compression="zstd")

    def write_event(self, table_id: str, df: pl.DataFrame, mode: str = "append", sort_keys: list[str] = None):
        """
        写入事件数据 (EV) 分片至 .staging 暂存目录。
        支持平铺模式与 Hive 分区模式独立分片写入。
        后续需调用 finalize 统一流式收敛落盘。
        """
        if df.is_empty():
            return

        with self._lock:
            if "timestamp" not in df.columns:
                # 平铺模式
                stage_dir = self._get_staging_dir(table_id)
                stage_dir.mkdir(parents=True, exist_ok=True)
                part_path = stage_dir / f"part_{uuid.uuid4().hex}.parquet"
                df.write_parquet(part_path, compression="zstd")
                return

            # Hive 分区模式
            df = df.with_columns(
                pl.from_epoch(pl.col("timestamp"), time_unit="ms").dt.year().alias("_year")
            )
            for (year,), group_df in df.partition_by(["_year"], as_dict=True).items():
                patch_df = group_df.drop("_year")
                stage_dir = self._get_staging_dir(table_id, year)
                stage_dir.mkdir(parents=True, exist_ok=True)
                part_path = stage_dir / f"part_{uuid.uuid4().hex}.parquet"
                patch_df.write_parquet(part_path, compression="zstd")

    def finalize(
        self,
        table_id: str,
        mode: str = "append",
        sort_keys: list[str] = None,
        progress_callback: Any = None,
    ):
        """
        收敛所有暂存分片 (.staging) 并基于流式管道 (sink_parquet) 与分治 Anti-Join 执行一次性落盘。
        彻底消除批处理中每批重复重写大文件的 O(N^2) 写放大，且通过 Anti-Join 规避巨型哈希表 OOM。
        同时严格遵循 keep="last" 契约，确保新数据精准覆盖旧数据。
        """
        with self._lock:
            # 1. 检查平铺模式的暂存目录
            flat_staging = self._get_staging_dir(table_id)
            if flat_staging.exists():
                staging_files = sorted(list(flat_staging.glob("*.parquet")))
                if staging_files:
                    if progress_callback:
                        progress_callback("平铺数据", 1, 1)

                    target_path = self._get_flat_event_path(table_id)
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    tmp_path = target_path.with_name(f".tmp_{target_path.stem}_{uuid.uuid4().hex[:8]}.tmp")

                    lazy_stages = [pl.scan_parquet(f) for f in staging_files]
                    base_schema = lazy_stages[0].collect_schema()
                    all_new = [ls.cast(base_schema) for ls in lazy_stages]
                    new_lazy = pl.concat(all_new).unique(subset=None, keep="last")

                    if mode == "append" and target_path.exists():
                        lazy_old = pl.scan_parquet(target_path)
                        valid_schema = {k: v for k, v in base_schema.items() if k in lazy_old.collect_schema().names()}
                        lazy_old = lazy_old.cast(valid_schema)
                        col_order = [c for c in base_schema.names() if c in valid_schema]
                        anti_keys = sort_keys if sort_keys else [k for k in base_schema.names() if k in valid_schema]
                        if anti_keys:
                            new_key_set = new_lazy.select(anti_keys).unique()
                            clean_old = lazy_old.join(new_key_set, on=anti_keys, how="anti").select(col_order)
                            q = pl.concat([clean_old, new_lazy.select(col_order)])
                        else:
                            q = pl.concat([lazy_old.select(col_order), new_lazy.select(col_order)]).unique(subset=None, keep="last")
                    else:
                        q = new_lazy

                    if sort_keys:
                        q = q.sort(sort_keys)
                    q.sink_parquet(tmp_path)
                    os.replace(tmp_path, target_path)
                shutil.rmtree(flat_staging, ignore_errors=True)

            # 2. 检查各 Hive 分区目录下的暂存目录
            table_dir = self.data_dir / table_id
            if not table_dir.exists():
                return

            year_dirs = [
                yd for yd in sorted(table_dir.glob("year=*"))
                if yd.is_dir() and (yd / ".staging").exists() and list((yd / ".staging").glob("*.parquet"))
            ]
            total_years = len(year_dirs)

            for idx, year_dir in enumerate(year_dirs, start=1):
                year_name = year_dir.name
                stage_dir = year_dir / ".staging"
                staging_files = sorted(list(stage_dir.glob("*.parquet")))
                if not staging_files:
                    shutil.rmtree(stage_dir, ignore_errors=True)
                    continue

                if progress_callback:
                    progress_callback(year_name, idx, total_years)

                logger.info(f"[*] [收敛落盘] 正在合并 {table_id} {year_name} (分片数: {len(staging_files)}, 进度: {idx}/{total_years})...")
                t_start = time.time()

                lazy_stages = [pl.scan_parquet(f) for f in staging_files]
                target_path = year_dir / "data.parquet"
                target_path.parent.mkdir(parents=True, exist_ok=True)
                tmp_path = target_path.with_name(f".tmp_{target_path.stem}_{uuid.uuid4().hex[:8]}.tmp")

                base_schema = lazy_stages[0].collect_schema()
                all_new = [ls.cast(base_schema) for ls in lazy_stages]
                new_lazy = pl.concat(all_new)

                is_ts = self.category == "timeseries"

                if is_ts:
                    # TS 模式：采用“sym_ranges 微型字典流式覆盖 + 流式排序落盘” (O(1) 内存，零巨型 Hash 表)
                    col_order = list(base_schema.names())
                    # 新分片自身去重 (杜绝并发/重试写入分片主键重复)
                    new_unique = new_lazy.unique(subset=["symbol", "timestamp"], keep="last")

                    if mode == "append" and target_path.exists():
                        lazy_old = pl.scan_parquet(target_path)
                        valid_schema = {k: v for k, v in base_schema.items() if k in lazy_old.collect_schema().names()}
                        col_order = [c for c in base_schema.names() if c in valid_schema]
                        lazy_old = lazy_old.cast(valid_schema).select(col_order)

                        # 计算新数据中各个标的的覆盖时间范围 (微型元数据表，仅几 KB，零内存开销)
                        sym_ranges = (
                            new_unique.select(["symbol", "timestamp"])
                            .group_by("symbol")
                            .agg([
                                pl.col("timestamp").min().alias("_min_ts"),
                                pl.col("timestamp").max().alias("_max_ts")
                            ])
                        )
                        # 旧大表流式剔除覆盖区间，严格保证新数据 100% 覆盖旧数据 (keep="last" 语义)
                        clean_old = (
                            lazy_old
                            .join(sym_ranges, on="symbol", how="left")
                            .filter(
                                pl.col("_min_ts").is_null() |
                                (pl.col("timestamp") < pl.col("_min_ts")) |
                                (pl.col("timestamp") > pl.col("_max_ts"))
                            )
                            .select(col_order)
                        )
                        all_sources = [clean_old, new_unique.select(col_order)]
                    else:
                        all_sources = [new_unique.select(col_order)]

                    q = pl.concat(all_sources).sort(["symbol", "timestamp"])
                else:
                    # EV 模式：遵循协议契约执行全行去重 (subset=None)
                    if mode == "append" and target_path.exists():
                        lazy_old = pl.scan_parquet(target_path)
                        valid_schema = {k: v for k, v in base_schema.items() if k in lazy_old.collect_schema().names()}
                        lazy_old = lazy_old.cast(valid_schema)
                        col_order = [c for c in base_schema.names() if c in valid_schema]
                        q = pl.concat([lazy_old.select(col_order), new_lazy.select(col_order)]).unique(subset=None, keep="last")
                    else:
                        q = new_lazy.unique(subset=None, keep="last")

                    if sort_keys:
                        q = q.sort(sort_keys)
                    elif "timestamp" in q.collect_schema().names():
                        q = q.sort(["timestamp"])

                q.sink_parquet(tmp_path)
                os.replace(tmp_path, target_path)
                shutil.rmtree(stage_dir, ignore_errors=True)

                # 显式清理 LazyFrame 引用并强制垃圾回收，防止跨年份连续流式处理内存叠加
                del q, new_lazy, lazy_stages
                if is_ts:
                    del all_sources, new_unique
                import gc
                gc.collect()

                logger.info(f"[+] [收敛落盘] 完成 {table_id} {year_name} 合并落盘, 耗时: {time.time() - t_start:.2f}s")

    def cleanup(self, table_id: str):
        """
        清理该表下所有未提交的临时分片目录，实现任务异常中断时的无损自愈。
        """
        with self._lock:
            flat_staging = self._get_staging_dir(table_id)
            if flat_staging.exists():
                shutil.rmtree(flat_staging, ignore_errors=True)

            table_dir = self.data_dir / table_id
            if table_dir.exists():
                for year_dir in table_dir.glob("year=*"):
                    stage_dir = year_dir / ".staging"
                    if stage_dir.exists():
                        shutil.rmtree(stage_dir, ignore_errors=True)

    def get_all_symbols(self, table_id: str) -> list[str]:
        """扫描所有 parquet 文件，提取唯一证券代码"""
        if self.category == "event":
            return []
            
        table_dir = self.data_dir / table_id
        if not table_dir.exists():
            return []
        
        symbols = set()
        for parquet_file in table_dir.glob("year=*/data.parquet"):
            try:
                # 流式去重提取 symbol，避免千万级行全量载入内存
                df = pl.scan_parquet(str(parquet_file)).select("symbol").unique().collect()
                symbols.update(df["symbol"].to_list())
            except Exception:
                pass
        
        return sorted(list(symbols))

    def get_total_bars(self, table_id: str) -> int:
        """极速统计总行数 (基于 Parquet Metadata)"""
        # 平铺模式
        if self._is_flat_event(table_id):
            path = self._get_flat_event_path(table_id)
            if not path.exists():
                return 0
            return pl.scan_parquet(str(path)).select(pl.len()).collect().item()
        # Hive 分区模式
        pattern = self.data_dir / table_id / "year=*" / "data.parquet"
        if not any(self.data_dir.glob(f"{table_id}/year=*/data.parquet")):
            return 0
        
        return pl.scan_parquet(str(pattern)).select(pl.len()).collect().item()

    def get_global_time_range(self, table_id: str) -> tuple[int, int]:
        """计算数据集全局最小/最大时间戳"""
        # 平铺模式（无 timestamp）返回 (0, 0)
        if self._is_flat_event(table_id):
            return (0, 0)
        # Hive 分区模式
        pattern = self.data_dir / table_id / "year=*" / "data.parquet"
        if not any(self.data_dir.glob(f"{table_id}/year=*/data.parquet")):
            return (0, 0)
            
        res = pl.scan_parquet(str(pattern)).select([
            pl.col("timestamp").min().alias("min_ts"),
            pl.col("timestamp").max().alias("max_ts")
        ]).collect()
        
        min_ts = res["min_ts"][0] if not res.is_empty() and res["min_ts"][0] is not None else 0
        max_ts = res["max_ts"][0] if not res.is_empty() and res["max_ts"][0] is not None else 0
        return (min_ts, max_ts)

    def get_unique_timestamps(self, table_id: str) -> list[int]:
        """获取全局去重后的时间点"""
        # 平铺模式（无 timestamp）返回空列表
        if self._is_flat_event(table_id):
            return []
        # Hive 分区模式
        table_dir = self.data_dir / table_id
        pattern = table_dir / "year=*" / "*.parquet"
        if not any(table_dir.glob("year=*/*.parquet")):
            return []
            
        df = pl.scan_parquet(str(pattern)).select("timestamp").unique().sort("timestamp").collect()
        return df["timestamp"].to_list() if not df.is_empty() else []
