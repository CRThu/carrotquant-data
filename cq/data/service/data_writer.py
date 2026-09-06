"""
cqdata/service/data_writer.py

数据写入与导入服务模块。
负责将外部 DataFrame 标准化并落地至本地存储 (Parquet / CSV)，
并原子化创建或更新 metadata.json 元数据。
"""

import time
from pathlib import Path
from typing import List, Optional, Union, Dict, Any
import polars as pl
from loguru import logger

from cq.data.config import settings
from cq.data.service.metadata_manager import MetadataManager
from cq.data.storage.storage_factory import StorageFactory
from cq.data.utils.time_utils import ts_to_iso, parse_date_to_ts
from cq.data.provider.data_cleaner import DataCleaner


class DataWriter:
    """
    数据写入核心服务类
    负责外部数据集的验证、标准化、持久化落盘与元数据盖章
    """

    def __init__(self, data_dir: Optional[Union[str, Path]] = None):
        """
        初始化 DataWriter
        
        Args:
            data_dir: 自定义数据存储根目录，未指定时使用全局 settings.data_dir
        """
        self.data_dir = Path(data_dir) if data_dir else Path(settings.data_dir)
        self.meta_mgr = MetadataManager(str(self.data_dir))

    def _normalize_dataframe(
        self,
        df: pl.DataFrame,
        category: str = "timeseries",
    ) -> tuple[pl.DataFrame, str]:
        """
        验证并标准化 DataFrame 的时间与主键列。
        
        策略 (TS 默认 & 显式契约):
        - 默认 category 为 'timeseries'，要求提供 symbol 和时间列 (timestamp/date/datetime/trade_date)；
        - 对于无时间列的纯静态平铺表或特殊事件表，需显式声明 category='event'。
        """
        if not isinstance(df, pl.DataFrame):
            raise TypeError(f"Expected polars.DataFrame, got {type(df).__name__}")

        resolved_category = category.lower() if isinstance(category, str) else "timeseries"
        if resolved_category not in ("timeseries", "event"):
            raise ValueError(f"Invalid category: '{category}'. Must be 'timeseries' or 'event'.")

        if df.is_empty():
            return df, resolved_category

        result_df = df

        # 1. 常用主键/时间别名自动规范化 (code/ticker -> symbol, trade_date -> date, time -> datetime)
        cols_lower_map = {c.lower(): c for c in result_df.columns}
        if "symbol" not in result_df.columns:
            if "code" in cols_lower_map:
                result_df = result_df.rename({cols_lower_map["code"]: "symbol"})
            elif "ticker" in cols_lower_map:
                result_df = result_df.rename({cols_lower_map["ticker"]: "symbol"})

        if "timestamp" not in result_df.columns and "date" not in result_df.columns and "datetime" not in result_df.columns:
            if "trade_date" in cols_lower_map:
                result_df = result_df.rename({cols_lower_map["trade_date"]: "date"})
            elif "time" in cols_lower_map:
                result_df = result_df.rename({cols_lower_map["time"]: "datetime"})

        # 2. 如果缺少 timestamp 但有 date 或 datetime，进行标准化
        if "timestamp" not in result_df.columns:
            if "date" in result_df.columns:
                result_df = DataCleaner.standardize(result_df, time_col="date")
            elif "datetime" in result_df.columns:
                result_df = DataCleaner.standardize(result_df, time_col="datetime")

        # 3. 如果已有 timestamp 但缺少 datetime，补齐 datetime
        if "timestamp" in result_df.columns and "datetime" not in result_df.columns:
            if result_df.schema["timestamp"] != pl.Int64:
                result_df = result_df.with_columns(pl.col("timestamp").cast(pl.Int64))

            result_df = result_df.with_columns(
                pl.from_epoch(pl.col("timestamp"), time_unit="ms")
                .dt.replace_time_zone("UTC")
                .dt.convert_time_zone("Asia/Shanghai")
                .dt.strftime("%Y-%m-%dT%H:%M:%S%.3f%:z")
                .alias("datetime")
            )

        # 4. 时序表契约检查 (Fail-Fast)
        if resolved_category == "timeseries":
            if "symbol" not in result_df.columns:
                raise ValueError("TimeSeries table requires a 'symbol' column. For static flat tables, pass category='event'.")
            if "timestamp" not in result_df.columns:
                raise ValueError("TimeSeries table requires a time column ('timestamp', 'date', or 'datetime'). For static flat tables, pass category='event'.")

        # 5. 保证 symbol 为 String 类型
        if "symbol" in result_df.columns and result_df.schema["symbol"] != pl.String:
            result_df = result_df.with_columns(pl.col("symbol").cast(pl.String))

        # 6. 将主键列排在最前
        priority_cols = [c for c in ["symbol", "datetime", "timestamp"] if c in result_df.columns]
        other_cols = [c for c in result_df.columns if c not in priority_cols]
        result_df = result_df.select(priority_cols + other_cols)

        return result_df, resolved_category

    def write(
        self,
        table_id: str,
        df: pl.DataFrame,
        category: str = "timeseries",
        formats: Union[List[str], str] = "parquet",
        mode: str = "append",
        sort_keys: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        写入数据至指定的本地数据表
        
        Args:
            table_id: 表标识符 (如 'my_factor' 或 'crypto.kline.1d.binance')
            df: 要写入的 Polars DataFrame
            category: 数据集类别 ('timeseries' 或 'event')，默认为 'timeseries'
            formats: 存储格式 ('parquet', 'csv', 或 ['parquet', 'csv'])
            mode: 写入模式 ('append' 增量合并，'overwrite' 覆盖)
            sort_keys: 事件表排序键 (可选)
            
        Returns:
            Dict[str, Any]: 写入结果元信息
        """
        if not table_id or not isinstance(table_id, str):
            raise ValueError("table_id must be a non-empty string.")

        target_formats = [formats] if isinstance(formats, str) else list(formats)
        target_formats = [f.lower() for f in target_formats]

        for fmt in target_formats:
            if fmt not in ("parquet", "csv"):
                raise ValueError(f"Unsupported format: {fmt}. Must be 'parquet' or 'csv'.")

        if mode not in ("append", "overwrite"):
            raise ValueError(f"Invalid mode: {mode}. Must be 'append' or 'overwrite'.")

        # 标准化 DataFrame
        normalized_df, resolved_category = self._normalize_dataframe(df, category)



        if normalized_df.is_empty():
            logger.warning(f"DataWriter: Attempting to write empty DataFrame to {table_id}. Skipping.")
            return {
                "table_id": table_id,
                "category": resolved_category,
                "formats": target_formats,
                "rows_written": 0,
                "status": "empty_skipped"
            }

        # 逐个格式落盘
        for fmt in target_formats:
            storage = StorageFactory.get_storage(
                storage_format=fmt,
                data_dir=str(self.data_dir),
                category=resolved_category
            )

            if resolved_category == "event":
                storage.write_event(table_id, normalized_df, mode=mode, sort_keys=sort_keys)
            else:
                storage.write_series(table_id, normalized_df, mode=mode)

            # 单次写入后立即流式收敛落盘，保障外部 SDK/CLI 用户即写即读
            storage.finalize(table_id, mode=mode, sort_keys=sort_keys if resolved_category == "event" else None)

            # 更新 metadata.json
            self._update_metadata(table_id, fmt, storage, normalized_df, resolved_category)

        logger.info(f"[+] Successfully written {len(normalized_df)} rows to table '{table_id}' ({target_formats}).")
        return {
            "table_id": table_id,
            "category": resolved_category,
            "formats": target_formats,
            "rows_written": len(normalized_df),
            "status": "success"
        }

    def _update_metadata(
        self,
        table_id: str,
        format: str,
        storage: Any,
        df: pl.DataFrame,
        category: str
    ):
        """物理巡检并原子化保存 metadata.json"""
        total_bars = storage.get_total_bars(table_id)
        start_ts, end_ts = storage.get_global_time_range(table_id)

        old_metadata = self.meta_mgr.load(table_id, format)
        schema_dict = old_metadata.get("schema", {}) if old_metadata else {}
        if df is not None and not df.is_empty():
            schema_dict = {k: str(v) for k, v in df.schema.items()}

        table_path = Path(self.data_dir) / format / table_id
        flat_csv = table_path / "data.csv"
        flat_pq = table_path / "data.parquet"
        layout = "flat" if flat_csv.exists() or flat_pq.exists() else "hive"

        now_ms = int(time.time() * 1000)
        updated_at_str = ts_to_iso(now_ms)

        metadata = {
            "table_id": table_id,
            "category": category,
            "format": format,
            "partition": storage.partition,
            "layout": layout,
            "schema": schema_dict,
            "statistics": {}
        }

        if category == "timeseries":
            all_symbols = storage.get_all_symbols(table_id)
            unique_tss = storage.get_unique_timestamps(table_id)
            metadata["statistics"] = {
                "updated_at": updated_at_str,
                "start_timestamp": start_ts,
                "end_timestamp": end_ts,
                "start_datetime": ts_to_iso(start_ts) if start_ts else "",
                "end_datetime": ts_to_iso(end_ts) if end_ts else "",
                "total_bars": total_bars,
                "symbol_count": len(all_symbols),
                "time_steps": len(unique_tss)
            }
        elif start_ts == 0 and end_ts == 0:
            metadata["statistics"] = {
                "updated_at": updated_at_str,
                "total_bars": total_bars
            }
        else:
            metadata["statistics"] = {
                "updated_at": updated_at_str,
                "start_timestamp": start_ts,
                "end_timestamp": end_ts,
                "start_datetime": ts_to_iso(start_ts) if start_ts else "",
                "end_datetime": ts_to_iso(end_ts) if end_ts else "",
                "total_bars": total_bars
            }

        self.meta_mgr.save(table_id, format, metadata)


def write(
    table_id: str,
    df: pl.DataFrame,
    category: str = "timeseries",
    formats: Union[List[str], str] = "parquet",
    mode: str = "append",
    sort_keys: Optional[List[str]] = None,
    data_dir: Optional[Union[str, Path]] = None
) -> Dict[str, Any]:
    """
    写入数据至指定数据表的快捷函数
    
    Args:
        table_id: 表标识符
        df: Polars DataFrame
        category: 数据集类别 ('timeseries' 或 'event')，默认为 'timeseries'
        formats: 存储格式 ('parquet', 'csv' 或 ['parquet', 'csv'])
        mode: 写入模式 ('append' 或 'overwrite')
        sort_keys: 事件表排序字段
        data_dir: 自定义数据存储根目录
    """

    writer = DataWriter(data_dir=data_dir)
    return writer.write(
        table_id=table_id,
        df=df,
        category=category,
        formats=formats,
        mode=mode,
        sort_keys=sort_keys
    )
