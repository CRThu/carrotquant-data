"""
tests/unit/test_metadata_reader.py

元数据探查服务 (MetadataReader) 单元测试
"""

import pytest
import polars as pl
from cq.data.service.metadata_reader import (
    MetadataReader,
    list_series_tables,
    list_event_tables,
    list_formats,
    list_symbols,
    get_time_range,
    get_schema,
    get_row_count
)
from cq.data.storage.storage_factory import StorageFactory
from cq.data.service.metadata_manager import MetadataManager
from cq.data.utils.time_utils import parse_date_to_ts, ts_to_iso


@pytest.fixture
def mock_storage_env(temp_data_dir):
    """在临时目录初始化模拟元数据与数据文件"""
    ts_table = "ashare.kline.1d.raw.baostock"
    ev_table = "ashare.dragon_tiger.eastmoney"

    ts1 = parse_date_to_ts("2023-01-01")
    ts2 = parse_date_to_ts("2024-06-30")

    # 1. 模拟 TS 时序数据 (Parquet & CSV)
    df_ts = pl.DataFrame({
        "symbol": ["sh.600000", "sz.000001"],
        "timestamp": [ts1, ts2],
        "datetime": [ts_to_iso(ts1), ts_to_iso(ts2)],
        "close": [10.0, 12.5]
    })
    
    pq_ts = StorageFactory.get_storage("parquet", str(temp_data_dir), "timeseries")
    pq_ts.write_series(ts_table, df_ts)
    pq_ts.finalize(ts_table)

    meta_mgr = MetadataManager(str(temp_data_dir))
    meta_mgr.save(ts_table, "parquet", {
        "category": "timeseries",
        "schema": {
            "symbol": "String",
            "timestamp": "Int64",
            "datetime": "String",
            "close": "Float64"
        },
        "statistics": {
            "start_timestamp": ts1,
            "end_timestamp": ts2,
            "start_datetime": ts_to_iso(ts1),
            "end_datetime": ts_to_iso(ts2),
            "total_bars": 2
        }
    })

    # 2. 模拟 EV 事件数据 (Flat Parquet)
    df_ev = pl.DataFrame({
        "symbol": ["sh.600000"],
        "stock_name": ["浦发银行"],
        "buy_amount": [1000000.0]
    })
    pq_ev = StorageFactory.get_storage("parquet", str(temp_data_dir), "event")
    pq_ev.write_event(ev_table, df_ev, mode="overwrite", sort_keys=["symbol"])
    pq_ev.finalize(ev_table, mode="overwrite", sort_keys=["symbol"])

    meta_mgr.save(ev_table, "parquet", {
        "category": "event",
        "schema": {
            "symbol": "String",
            "stock_name": "String",
            "buy_amount": "Float64"
        },
        "statistics": {
            "total_bars": 1
        }
    })

    return ts_table, ev_table


def test_list_series_tables(mock_storage_env, temp_data_dir):
    """测试探查时序表列表"""
    ts_table, _ = mock_storage_env
    tables = list_series_tables(data_dir=temp_data_dir)
    assert ts_table in tables


def test_list_event_tables(mock_storage_env, temp_data_dir):
    """测试探查事件表列表"""
    _, ev_table = mock_storage_env
    tables = list_event_tables(data_dir=temp_data_dir)
    assert ev_table in tables


def test_list_formats(mock_storage_env, temp_data_dir):
    """测试获取表支持的格式"""
    ts_table, _ = mock_storage_env
    formats = list_formats(ts_table, data_dir=temp_data_dir)
    assert "parquet" in formats


def test_list_symbols(mock_storage_env, temp_data_dir):
    """测试获取 symbol 唯一列表"""
    ts_table, _ = mock_storage_env
    symbols = list_symbols(ts_table, data_dir=temp_data_dir)
    assert set(symbols) == {"sh.600000", "sz.000001"}


def test_get_time_range(mock_storage_env, temp_data_dir):
    """测试获取起止 ISO 时间 tuple"""
    ts_table, _ = mock_storage_env
    start_dt, end_dt = get_time_range(ts_table, data_dir=temp_data_dir)
    assert "2023-01-01" in start_dt
    assert "2024-06-30" in end_dt


def test_get_schema(mock_storage_env, temp_data_dir):
    """测试获取 Schema"""
    ts_table, _ = mock_storage_env
    schema = get_schema(ts_table, data_dir=temp_data_dir)
    assert schema.get("close") == "Float64"
    assert schema.get("symbol") == "String"


def test_get_row_count(mock_storage_env, temp_data_dir):
    """测试获取物理行数"""
    ts_table, ev_table = mock_storage_env
    assert get_row_count(ts_table, data_dir=temp_data_dir) == 2
    assert get_row_count(ev_table, data_dir=temp_data_dir) == 1
