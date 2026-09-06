"""平铺模式存储单元测试。

验证无 timestamp 列的 EV 数据（如板块成分股）在平铺路径下的:
1. 写入路径正确 (data.csv / data.parquet，无 year= 分区)
2. 读取正常
3. 增量合并 (全行去重)
4. 统计接口 (get_total_bars, get_global_time_range, get_unique_timestamps)
"""

import pytest
import polars as pl
from cq.data.storage.csv_storage import CSVStorage
from cq.data.storage.parquet_storage import ParquetStorage
from cq.data.service.metadata_manager import MetadataManager


def _stamp_metadata(storage, table_id, df, fmt="csv", category="event", mode="append", sort_keys=None):
    """辅助函数：为测试收敛分片并生成元数据"""
    storage.finalize(table_id, mode=mode, sort_keys=sort_keys)
    meta_mgr = MetadataManager(storage.data_dir.parent)
    meta_mgr.save(table_id, fmt, {
        "table_id": table_id, "category": category, "format": fmt,
        "schema": {k: str(v) for k, v in df.schema.items()}
    })


# ---------------------------------------------------------------------------
# CSV 平铺模式
# ---------------------------------------------------------------------------

class TestCSVFlat:
    """测试 CSV 平铺模式（无 timestamp 列的板块数据等）。"""

    def test_flat_write_creates_data_csv(self, temp_data_dir):
        """平铺写入应创建 {table_id}/data.csv，无 year= 分区。"""
        storage = CSVStorage(str(temp_data_dir / "csv"), category="event")
        table_id = "test.flat.write"
        
        df = pl.DataFrame({
            "board_code": ["BK0001", "BK0001", "BK0002"],
            "board_name": ["板块A", "板块A", "板块B"],
            "symbol": ["sh.600000", "sz.000001", "sh.600000"],
            "stock_name": ["股票A", "股票B", "股票A"],
        })
        storage.write_event(table_id, df, mode="overwrite", sort_keys=["board_code", "board_name", "symbol"])
        
        # 验证文件路径
        flat_path = temp_data_dir / "csv" / table_id / "data.csv"
        assert flat_path.exists(), "应创建平铺文件 data.csv"
        
        # 验证无 year= 目录
        year_dirs = list((temp_data_dir / "csv" / table_id).glob("year=*"))
        assert len(year_dirs) == 0, "不应创建 year= 分区目录"

    def test_flat_read(self, temp_data_dir):
        """平铺读取应返回完整数据。"""
        storage = CSVStorage(str(temp_data_dir / "csv"), category="event")
        table_id = "test.flat.read"
        
        df = pl.DataFrame({
            "board_code": ["BK0001", "BK0002"],
            "board_name": ["板块A", "板块B"],
            "symbol": ["sh.600000", "sz.000001"],
            "stock_name": ["股票A", "股票B"],
        })
        storage.write_event(table_id, df, mode="overwrite", sort_keys=["board_code", "board_name", "symbol"])
        _stamp_metadata(storage, table_id, df, fmt="csv")
        
        # 读取（不传 year 参数）
        read_df = storage.read_event(table_id)
        assert len(read_df) == 2
        assert read_df["board_code"].to_list() == ["BK0001", "BK0002"]

    def test_flat_incremental_merge_dedup(self, temp_data_dir):
        """平铺增量写入应全行去重。"""
        storage = CSVStorage(str(temp_data_dir / "csv"), category="event")
        table_id = "test.flat.dedup"
        
        df1 = pl.DataFrame({
            "board_code": ["BK0001", "BK0001", "BK0002"],
            "board_name": ["板块A", "板块A", "板块B"],
            "symbol": ["sh.600000", "sz.000001", "sh.600000"],
            "stock_name": ["股票A", "股票B", "股票A"],
        })
        storage.write_event(table_id, df1, mode="overwrite", sort_keys=["board_code", "board_name", "symbol"])
        _stamp_metadata(storage, table_id, df1, fmt="csv")
        
        # 第二次写入：完全重复 + 新增
        df2 = pl.DataFrame({
            "board_code": ["BK0001", "BK0001", "BK0003"],
            "board_name": ["板块A", "板块A", "板块C"],
            "symbol": ["sh.600000", "sz.000001", "sz.300001"],
            "stock_name": ["股票A", "股票B", "股票C"],
        })
        storage.write_event(table_id, df2, mode="append", sort_keys=["board_code", "board_name", "symbol"])
        
        read_df = storage.read_event(table_id)
        # BK0001+sh.600000 重复1行去重，BK0001+sz.000001 重复1行去重，BK0002 保留，BK0003 新增 = 4行
        assert len(read_df) == 4, f"期望 4 行，实际 {len(read_df)}"

    def test_flat_sort_by_first_two_cols(self, temp_data_dir):
        """平铺数据应按指定 sort_keys 排序。"""
        storage = CSVStorage(str(temp_data_dir / "csv"), category="event")
        table_id = "test.flat.sort"
        
        df = pl.DataFrame({
            "board_code": ["BK0002", "BK0001", "BK0001"],
            "board_name": ["板块B", "板块A", "板块A"],
            "symbol": ["sh.600000", "sz.000001", "sh.600000"],
            "stock_name": ["股票A", "股票B", "股票A"],
        })
        storage.write_event(table_id, df, mode="overwrite", sort_keys=["board_code", "board_name", "symbol"])
        _stamp_metadata(storage, table_id, df, fmt="csv")
        
        read_df = storage.read_event(table_id)
        # 默认排序：board_code, board_name, symbol
        assert read_df["board_code"].to_list() == ["BK0001", "BK0001", "BK0002"]

    def test_flat_custom_sort_keys(self, temp_data_dir):
        """传入 sort_keys 时应按指定列排序。"""
        storage = CSVStorage(str(temp_data_dir / "csv"), category="event")
        table_id = "test.flat.custom_sort"
        
        df = pl.DataFrame({
            "board_code": ["BK0002", "BK0001", "BK0001"],
            "board_name": ["板块B", "板块A", "板块A"],
            "symbol": ["sh.600000", "sz.000001", "sh.600000"],
            "stock_name": ["股票A", "股票B", "股票A"],
        })
        # 按 stock_name 排序
        storage.write_event(table_id, df, mode="overwrite", sort_keys=["stock_name", "symbol"])
        _stamp_metadata(storage, table_id, df, fmt="csv")
        
        read_df = storage.read_event(table_id)
        # 应按 stock_name 排序: 股票A, 股票A, 股票B
        assert read_df["stock_name"].to_list() == ["股票A", "股票A", "股票B"]

    def test_flat_total_bars(self, temp_data_dir):
        """get_total_bars 应返回正确的行数。"""
        storage = CSVStorage(str(temp_data_dir / "csv"), category="event")
        table_id = "test.flat.bars"
        
        df = pl.DataFrame({
            "board_code": ["BK0001", "BK0001", "BK0002"],
            "board_name": ["板块A", "板块A", "板块B"],
            "symbol": ["sh.600000", "sz.000001", "sh.600000"],
            "stock_name": ["股票A", "股票B", "股票A"],
        })
        storage.write_event(table_id, df, mode="overwrite", sort_keys=["board_code", "board_name", "symbol"])
        
        assert storage.get_total_bars(table_id) == 3

    def test_flat_global_time_range_returns_zero(self, temp_data_dir):
        """无 timestamp 的平铺数据 get_global_time_range 应返回 (0, 0)。"""
        storage = CSVStorage(str(temp_data_dir / "csv"), category="event")
        table_id = "test.flat.timerange"
        
        df = pl.DataFrame({
            "board_code": ["BK0001"],
            "board_name": ["板块A"],
            "symbol": ["sh.600000"],
            "stock_name": ["股票A"],
        })
        storage.write_event(table_id, df, mode="overwrite", sort_keys=["board_code", "board_name", "symbol"])
        
        assert storage.get_global_time_range(table_id) == (0, 0)

    def test_flat_unique_timestamps_returns_empty(self, temp_data_dir):
        """无 timestamp 的平铺数据 get_unique_timestamps 应返回空列表。"""
        storage = CSVStorage(str(temp_data_dir / "csv"), category="event")
        table_id = "test.flat.timesteps"
        
        df = pl.DataFrame({
            "board_code": ["BK0001"],
            "board_name": ["板块A"],
            "symbol": ["sh.600000"],
            "stock_name": ["股票A"],
        })
        storage.write_event(table_id, df, mode="overwrite", sort_keys=["board_code", "board_name", "symbol"])
        
        assert storage.get_unique_timestamps(table_id) == []


# ---------------------------------------------------------------------------
# Parquet 平铺模式
# ---------------------------------------------------------------------------

class TestParquetFlat:
    """测试 Parquet 平铺模式（无 timestamp 列的板块数据等）。"""

    def test_flat_write_creates_data_parquet(self, temp_data_dir):
        """平铺写入应创建 {table_id}/data.parquet，无 year= 分区。"""
        storage = ParquetStorage(str(temp_data_dir / "parquet"), category="event")
        table_id = "test.parquet.flat.write"
        
        df = pl.DataFrame({
            "board_code": ["BK0001", "BK0001", "BK0002"],
            "board_name": ["板块A", "板块A", "板块B"],
            "symbol": ["sh.600000", "sz.000001", "sh.600000"],
            "stock_name": ["股票A", "股票B", "股票A"],
        })
        storage.write_event(table_id, df, mode="overwrite", sort_keys=["board_code", "board_name", "symbol"])
        storage.finalize(table_id, mode="overwrite", sort_keys=["board_code", "board_name", "symbol"])
        
        flat_path = temp_data_dir / "parquet" / table_id / "data.parquet"
        assert flat_path.exists(), "应创建平铺文件 data.parquet"
        
        year_dirs = list((temp_data_dir / "parquet" / table_id).glob("year=*"))
        assert len(year_dirs) == 0, "不应创建 year= 分区目录"

    def test_flat_read(self, temp_data_dir):
        """平铺读取应返回完整数据。"""
        storage = ParquetStorage(str(temp_data_dir / "parquet"), category="event")
        table_id = "test.parquet.flat.read"
        
        df = pl.DataFrame({
            "board_code": ["BK0001", "BK0002"],
            "board_name": ["板块A", "板块B"],
            "symbol": ["sh.600000", "sz.000001"],
            "stock_name": ["股票A", "股票B"],
        })
        storage.write_event(table_id, df, mode="overwrite", sort_keys=["board_code", "board_name", "symbol"])
        _stamp_metadata(storage, table_id, df, fmt="parquet", mode="overwrite", sort_keys=["board_code", "board_name", "symbol"])
        
        read_df = storage.read_event(table_id)
        assert len(read_df) == 2
        assert read_df["board_code"].to_list() == ["BK0001", "BK0002"]

    def test_flat_incremental_merge_dedup(self, temp_data_dir):
        """平铺增量写入应全行去重。"""
        storage = ParquetStorage(str(temp_data_dir / "parquet"), category="event")
        table_id = "test.parquet.flat.dedup"
        
        df1 = pl.DataFrame({
            "board_code": ["BK0001", "BK0001", "BK0002"],
            "board_name": ["板块A", "板块A", "板块B"],
            "symbol": ["sh.600000", "sz.000001", "sh.600000"],
            "stock_name": ["股票A", "股票B", "股票A"],
        })
        storage.write_event(table_id, df1, mode="overwrite", sort_keys=["board_code", "board_name", "symbol"])
        _stamp_metadata(storage, table_id, df1, fmt="parquet", mode="overwrite", sort_keys=["board_code", "board_name", "symbol"])
        
        df2 = pl.DataFrame({
            "board_code": ["BK0001", "BK0001", "BK0003"],
            "board_name": ["板块A", "板块A", "板块C"],
            "symbol": ["sh.600000", "sz.000001", "sz.300001"],
            "stock_name": ["股票A", "股票B", "股票C"],
        })
        storage.write_event(table_id, df2, mode="append", sort_keys=["board_code", "board_name", "symbol"])
        storage.finalize(table_id, mode="append", sort_keys=["board_code", "board_name", "symbol"])
        
        read_df = storage.read_event(table_id)
        assert len(read_df) == 4, f"期望 4 行，实际 {len(read_df)}"

    def test_flat_total_bars(self, temp_data_dir):
        """get_total_bars 应返回正确的行数。"""
        storage = ParquetStorage(str(temp_data_dir / "parquet"), category="event")
        table_id = "test.parquet.flat.bars"
        
        df = pl.DataFrame({
            "board_code": ["BK0001", "BK0001", "BK0002"],
            "board_name": ["板块A", "板块A", "板块B"],
            "symbol": ["sh.600000", "sz.000001", "sh.600000"],
            "stock_name": ["股票A", "股票B", "股票A"],
        })
        storage.write_event(table_id, df, mode="overwrite", sort_keys=["board_code", "board_name", "symbol"])
        storage.finalize(table_id, mode="overwrite", sort_keys=["board_code", "board_name", "symbol"])
        
        assert storage.get_total_bars(table_id) == 3

    def test_flat_global_time_range_returns_zero(self, temp_data_dir):
        """无 timestamp 的平铺数据 get_global_time_range 应返回 (0, 0)。"""
        storage = ParquetStorage(str(temp_data_dir / "parquet"), category="event")
        table_id = "test.parquet.flat.timerange"
        
        df = pl.DataFrame({
            "board_code": ["BK0001"],
            "board_name": ["板块A"],
            "symbol": ["sh.600000"],
            "stock_name": ["股票A"],
        })
        storage.write_event(table_id, df, mode="overwrite", sort_keys=["board_code", "board_name", "symbol"])
        
        assert storage.get_global_time_range(table_id) == (0, 0)

    def test_flat_unique_timestamps_returns_empty(self, temp_data_dir):
        """无 timestamp 的平铺数据 get_unique_timestamps 应返回空列表。"""
        storage = ParquetStorage(str(temp_data_dir / "parquet"), category="event")
        table_id = "test.parquet.flat.timesteps"
        
        df = pl.DataFrame({
            "board_code": ["BK0001"],
            "board_name": ["板块A"],
            "symbol": ["sh.600000"],
            "stock_name": ["股票A"],
        })
        storage.write_event(table_id, df, mode="overwrite", sort_keys=["board_code", "board_name", "symbol"])
        
        assert storage.get_unique_timestamps(table_id) == []
