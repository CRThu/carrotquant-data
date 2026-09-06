import os
import shutil
import threading
import uuid
from pathlib import Path
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

    def finalize(self, table_id: str, mode: str = "append", sort_keys: list[str] = None):
        """
        收敛所有暂存分片 (.staging) 并基于流式管道 (sink_parquet) 执行一次性落盘。
        彻底消除批处理中每批重复重写大文件的 O(N^2) 写放大与全内存 OOM 隐患。
        """
        with self._lock:
            # 1. 检查平铺模式的暂存目录
            flat_staging = self._get_staging_dir(table_id)
            if flat_staging.exists():
                staging_files = sorted(list(flat_staging.glob("*.parquet")))
                if staging_files:
                    lazy_stages = [pl.scan_parquet(f) for f in staging_files]
                    target_path = self._get_flat_event_path(table_id)
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    tmp_path = target_path.with_name(f".tmp_{target_path.stem}_{uuid.uuid4().hex[:8]}.tmp")

                    base_schema = lazy_stages[0].collect_schema()
                    if mode == "append" and target_path.exists():
                        lazy_old = pl.scan_parquet(target_path)
                        valid_schema = {k: v for k, v in base_schema.items() if k in lazy_old.collect_schema().names()}
                        lazy_old = lazy_old.cast(valid_schema)
                        all_lazy = [lazy_old] + [ls.cast(valid_schema) for ls in lazy_stages]
                    else:
                        all_lazy = [ls.cast(base_schema) for ls in lazy_stages]

                    q = pl.concat(all_lazy).unique(subset=None, keep="last")
                    if sort_keys:
                        q = q.sort(sort_keys)
                    q.sink_parquet(tmp_path)
                    os.replace(tmp_path, target_path)
                shutil.rmtree(flat_staging, ignore_errors=True)

            # 2. 检查各 Hive 分区目录下的暂存目录
            table_dir = self.data_dir / table_id
            if not table_dir.exists():
                return

            for year_dir in sorted(table_dir.glob("year=*")):
                if not year_dir.is_dir():
                    continue
                stage_dir = year_dir / ".staging"
                if not stage_dir.exists():
                    continue

                staging_files = sorted(list(stage_dir.glob("*.parquet")))
                if staging_files:
                    lazy_stages = [pl.scan_parquet(f) for f in staging_files]
                    target_path = year_dir / "data.parquet"
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    tmp_path = target_path.with_name(f".tmp_{target_path.stem}_{uuid.uuid4().hex[:8]}.tmp")

                    base_schema = lazy_stages[0].collect_schema()
                    if mode == "append" and target_path.exists():
                        lazy_old = pl.scan_parquet(target_path)
                        valid_schema = {k: v for k, v in base_schema.items() if k in lazy_old.collect_schema().names()}
                        lazy_old = lazy_old.cast(valid_schema)
                        all_lazy = [lazy_old] + [ls.cast(valid_schema) for ls in lazy_stages]
                    else:
                        all_lazy = [ls.cast(base_schema) for ls in lazy_stages]

                    is_ts = self.category == "timeseries"
                    subset = ["symbol", "timestamp"] if is_ts else None
                    q = pl.concat(all_lazy).unique(subset=subset, keep="last")

                    if is_ts:
                        q = q.sort(["symbol", "timestamp"])
                    else:
                        if sort_keys:
                            q = q.sort(sort_keys)
                        elif "timestamp" in q.collect_schema().names():
                            q = q.sort(["timestamp"])

                    q.sink_parquet(tmp_path)
                    os.replace(tmp_path, target_path)

                shutil.rmtree(stage_dir, ignore_errors=True)

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
                # 仅扫描 symbol 列加速提取
                df = pl.read_parquet(parquet_file, columns=["symbol"])
                symbols.update(df["symbol"].unique().to_list())
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
