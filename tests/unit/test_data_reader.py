"""
tests/unit/test_data_reader.py

数据读取服务 (DataReader) 单元测试
覆盖 read_series 与 read_events 的列投影 (columns)、多代码/时间范围切片及格式转换
"""

import pytest
import polars as pl

from cq.data.service.data_reader import DataReader, read_series, read_events
from cq.data.storage.storage_factory import StorageFactory
from cq.data.service.metadata_manager import MetadataManager
from cq.data.utils.time_utils import parse_date_to_ts, ts_to_iso


@pytest.fixture
def mock_stored_data(temp_data_dir):
    """构建模拟数据场景"""
    ts_table = "ashare.kline.1d.raw.baostock"
    ev_table = "ashare.dragon_tiger.eastmoney"

    ts1 = parse_date_to_ts("2023-05-01")
    ts2 = parse_date_to_ts("2024-01-15")

    df_ts1 = pl.DataFrame({
        "symbol": ["sh.600000", "sz.000001"],
        "timestamp": [ts1, ts1],
        "datetime": [ts_to_iso(ts1), ts_to_iso(ts1)],
        "open": [9.8, 14.8],
        "close": [10.0, 15.0]
    })

    df_ts2 = pl.DataFrame({
        "symbol": ["sh.600000", "sz.000001"],
        "timestamp": [ts2, ts2],
        "datetime": [ts_to_iso(ts2), ts_to_iso(ts2)],
        "open": [10.8, 15.8],
        "close": [11.0, 16.0]
    })

    pq_storage = StorageFactory.get_storage("parquet", str(temp_data_dir), "timeseries")
    pq_storage.write_series(ts_table, df_ts1)
    pq_storage.write_series(ts_table, df_ts2)
    pq_storage.finalize(ts_table)

    meta_mgr = MetadataManager(str(temp_data_dir))
    meta_mgr.save(ts_table, "parquet", {
        "category": "timeseries",
        "schema": {
            "symbol": "String",
            "timestamp": "Int64",
            "datetime": "String",
            "open": "Float64",
            "close": "Float64"
        }
    })

    # 模拟 EV 数据
    df_ev = pl.DataFrame({
        "symbol": ["sh.600000", "sz.000001"],
        "stock_name": ["浦发银行", "平安银行"],
        "buy_amount": [100.0, 200.0]
    })
    ev_storage = StorageFactory.get_storage("parquet", str(temp_data_dir), "event")
    ev_storage.write_event(ev_table, df_ev, mode="overwrite", sort_keys=["symbol"])
    ev_storage.finalize(ev_table, mode="overwrite", sort_keys=["symbol"])
    meta_mgr.save(ev_table, "parquet", {
        "category": "event",
        "schema": {
            "symbol": "String",
            "stock_name": "String",
            "buy_amount": "Float64"
        }
    })

    return ts_table, ev_table


def test_read_series_basic(mock_stored_data, temp_data_dir):
    """测试常规全量时序数据读取"""
    ts_table, _ = mock_stored_data
    df = read_series(ts_table, data_dir=temp_data_dir)
    assert len(df) == 4
    assert set(df["symbol"].to_list()) == {"sh.600000", "sz.000001"}


def test_read_series_columns_selection(mock_stored_data, temp_data_dir):
    """测试 columns 按需列挑选 (列投影)"""
    ts_table, _ = mock_stored_data

    # 只挑选 timestamp 和 close 字段
    df = read_series(ts_table, columns=["timestamp", "close"], data_dir=temp_data_dir)
    assert df.columns == ["timestamp", "close"]
    assert len(df) == 4


def test_read_series_symbol_and_date_filter(mock_stored_data, temp_data_dir):
    """测试 symbol 和 start_date/end_date 切片过滤"""
    ts_table, _ = mock_stored_data

    df = read_series(
        ts_table,
        symbols="sh.600000",
        start_date="2024-01-01",
        end_date="2024-12-31",
        data_dir=temp_data_dir
    )
    assert len(df) == 1
    assert df["symbol"][0] == "sh.600000"
    assert "2024-01-15" in df["datetime"][0]


def test_read_events_basic(mock_stored_data, temp_data_dir):
    """测试读取事件数据及列筛选"""
    _, ev_table = mock_stored_data

    df = read_events(ev_table, columns=["symbol", "buy_amount"], data_dir=temp_data_dir)
    assert df.columns == ["symbol", "buy_amount"]
    assert len(df) == 2



