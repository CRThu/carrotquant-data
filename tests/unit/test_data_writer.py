"""
tests/unit/test_data_writer.py

DataWriter 单元测试：
覆盖时序表写入、事件表写入、平铺表写入、自动类型推断、多格式落盘、增量合并与元数据生成。
"""

import pytest
import polars as pl
from pathlib import Path
from cq.data.service.data_writer import DataWriter, write
from cq.data.service.metadata_manager import MetadataManager
from cq.data.service.data_reader import DataReader


def test_writer_timeseries_parquet_and_csv(tmp_path):
    """测试时序数据同时落盘 Parquet 和 CSV 格式，并验证元数据与物理结构"""
    writer = DataWriter(data_dir=tmp_path)
    
    df = pl.DataFrame({
        "symbol": ["sh.600000", "sh.600000", "sz.000001"],
        "timestamp": [1704067200000, 1704153600000, 1704067200000],
        "close": [10.5, 10.8, 15.2],
        "volume": [1000, 1200, 800]
    })
    
    res = writer.write(
        table_id="custom.kline.test",
        df=df,
        formats=["parquet", "csv"],
        mode="append"
    )
    
    assert res["status"] == "success"
    assert res["rows_written"] == 3
    assert res["category"] == "timeseries"
    
    # 验证元数据
    meta_mgr = MetadataManager(str(tmp_path))
    meta_pq = meta_mgr.load("custom.kline.test", "parquet")
    assert meta_pq["category"] == "timeseries"
    assert meta_pq["statistics"]["total_bars"] == 3
    assert meta_pq["statistics"]["symbol_count"] == 2
    assert "datetime" in meta_pq["schema"]
    
    meta_csv = meta_mgr.load("custom.kline.test", "csv")
    assert meta_csv["category"] == "timeseries"
    assert meta_csv["statistics"]["total_bars"] == 3


def test_writer_date_column_auto_standardization(tmp_path):
    """测试仅传入 date 字符串列时自动标准化为 timestamp (Int64) 和 ISO datetime"""
    df = pl.DataFrame({
        "symbol": ["sh.600000", "sz.000001"],
        "date": ["2024-01-02", "2024-01-02"],
        "score": [95.5, 88.0]
    })
    
    res = write(
        table_id="custom.factor.alpha",
        df=df,
        data_dir=tmp_path
    )
    
    assert res["category"] == "timeseries"
    assert res["rows_written"] == 2
    
    # 读取验证
    reader = DataReader(data_dir=tmp_path)
    df_read = reader.read_series("custom.factor.alpha")
    assert not df_read.is_empty()
    assert "timestamp" in df_read.columns
    assert "datetime" in df_read.columns
    assert "score" in df_read.columns
    assert df_read.schema["timestamp"] == pl.Int64


def test_writer_flat_event_table(tmp_path):
    """测试无 timestamp 的平铺事件表 (如自定义静态板块或字典表)"""
    df = pl.DataFrame({
        "board_code": ["BK9999", "BK9999", "BK8888"],
        "board_name": ["量子计算", "量子计算", "低空经济"],
        "symbol": ["sh.600001", "sh.600002", "sz.000002"]
    })
    
    writer = DataWriter(data_dir=tmp_path)
    res = writer.write(
        table_id="custom.board.static",
        df=df,
        category="event",
        formats=["parquet", "csv"]
    )
    
    assert res["category"] == "event"
    assert res["rows_written"] == 3
    
    # 验证物理文件为平铺 layout
    assert (tmp_path / "parquet" / "custom.board.static" / "data.parquet").exists()
    assert (tmp_path / "csv" / "custom.board.static" / "data.csv").exists()
    
    # 验证元数据
    meta_mgr = MetadataManager(str(tmp_path))
    meta = meta_mgr.load("custom.board.static", "parquet")
    assert meta["layout"] == "flat"
    assert meta["statistics"]["total_bars"] == 3


def test_writer_append_and_overwrite(tmp_path):
    """测试 append 增量去重与 overwrite 全量覆盖行为"""
    writer = DataWriter(data_dir=tmp_path)
    
    df1 = pl.DataFrame({
        "symbol": ["sh.600000"],
        "timestamp": [1704067200000],
        "val": [100]
    })
    writer.write("custom.test_mode", df1, mode="append")
    
    # 增量追加新数据及重复数据
    df2 = pl.DataFrame({
        "symbol": ["sh.600000", "sh.600000"],
        "timestamp": [1704067200000, 1704153600000],
        "val": [105, 200] # 第1条覆盖更新
    })
    writer.write("custom.test_mode", df2, mode="append")
    
    reader = DataReader(data_dir=tmp_path)
    df_merged = reader.read_series("custom.test_mode")
    assert df_merged.height == 2
    assert df_merged.filter(pl.col("timestamp") == 1704067200000)["val"][0] == 105
    
    # Overwrite 全量覆盖
    df3 = pl.DataFrame({
        "symbol": ["sz.000001"],
        "timestamp": [1704240000000],
        "val": [300]
    })
    writer.write("custom.test_mode", df3, mode="overwrite")
    df_overwritten = reader.read_series("custom.test_mode")
    assert df_overwritten.height == 1
    assert df_overwritten["symbol"][0] == "sz.000001"


def test_writer_input_validation(tmp_path):
    """测试输入参数边界防错与异常处理"""
    writer = DataWriter(data_dir=tmp_path)
    
    # 非 DataFrame 抛出 TypeError
    with pytest.raises(TypeError):
        writer.write("test_invalid", "not_a_df")
        
    # 非法 category 抛出 ValueError
    with pytest.raises(ValueError):
        writer.write("test_invalid", pl.DataFrame({"a": [1]}), category="invalid_cat")
        
    # 缺少 symbol 的 timeseries 抛出 ValueError
    with pytest.raises(ValueError):
        writer.write("test_invalid", pl.DataFrame({"timestamp": [1000]}), category="timeseries")
        
    # 空 DataFrame 静默跳过
    res = writer.write("test_empty", pl.DataFrame())
    assert res["status"] == "empty_skipped"


def test_writer_alias_normalization_and_metadata_inheritance(tmp_path):
    """测试 code/trade_date 别名自动规范化及已有 metadata.json 继承策略"""
    writer = DataWriter(data_dir=tmp_path)

    # 1. 传入含 code 和 trade_date 的 DataFrame，验证自动转为 symbol 和 timestamp/datetime，并推断为 timeseries
    df_alias = pl.DataFrame({
        "code": ["sh.600000", "sz.000001"],
        "trade_date": ["2024-01-02", "2024-01-02"],
        "factor_val": [1.2, 3.4]
    })
    res = writer.write("custom.alias.table", df_alias)
    assert res["category"] == "timeseries"
    assert res["rows_written"] == 2

    reader = DataReader(data_dir=tmp_path)
    df_read = reader.read_series("custom.alias.table")
    assert "symbol" in df_read.columns
    assert "timestamp" in df_read.columns
    assert "datetime" in df_read.columns
    assert df_read["symbol"].to_list() == ["sh.600000", "sz.000001"]

    # 2. 追加写入时不传 category，验证继承已有 metadata.json 中的 category
    df_append = pl.DataFrame({
        "symbol": ["sh.600000"],
        "date": ["2024-01-03"],
        "factor_val": [1.5]
    })
    res_app = writer.write("custom.alias.table", df_append)
    assert res_app["category"] == "timeseries"
    assert res_app["rows_written"] == 1


def test_writer_validation_and_defense_paths(tmp_path):
    """测试 DataWriter 入参防御校验与 ticker/time 别名转换"""
    writer = DataWriter(data_dir=tmp_path)

    # 1. table_id 为空
    with pytest.raises(ValueError, match="table_id must be a non-empty string"):
        writer.write("", pl.DataFrame({"symbol": ["000001"], "timestamp": [1000]}))

    # 2. 不支持的 format
    with pytest.raises(ValueError, match="Unsupported format"):
        writer.write("test.table", pl.DataFrame({"symbol": ["000001"], "timestamp": [1000]}), formats="json")

    # 3. 不支持的 mode
    with pytest.raises(ValueError, match="Invalid mode"):
        writer.write("test.table", pl.DataFrame({"symbol": ["000001"], "timestamp": [1000]}), mode="upsert")

    # 4. 时序表缺少时间列
    with pytest.raises(ValueError, match="TimeSeries table requires a time column"):
        writer.write("test.table", pl.DataFrame({"symbol": ["000001"], "val": [10]}), category="timeseries")

    # 5. ticker 别名与 time 别名转换
    df_ticker = pl.DataFrame({
        "ticker": ["000001"],
        "time": ["2024-01-01 15:00:00"],
        "val": [100.0]
    })
    res = writer.write("test.ticker_alias", df_ticker)
    assert res["rows_written"] == 1
    reader = DataReader(data_dir=tmp_path)
    df_read = reader.read_series("test.ticker_alias")
    assert "symbol" in df_read.columns
    assert "timestamp" in df_read.columns
    assert df_read["symbol"][0] == "000001"

