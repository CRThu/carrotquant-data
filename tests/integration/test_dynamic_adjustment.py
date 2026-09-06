"""
tests/integration/test_dynamic_adjustment.py

集成测试：动态后复权全链路端到端验证 (跨年份存储、历史截断继承、高频分钟线与跨源组装)。
"""

import polars as pl
import pytest
from pathlib import Path

import cq.data
from cq.data.storage.storage_factory import StorageFactory
from cq.data.service.metadata_manager import MetadataManager


@pytest.fixture
def populated_kline_and_factor_storage(temp_data_dir):
    """
    在临时存储目录中写入真实跨年份的 K 线与复权因子数据：
    - 2023 年: 2023-05-10 除权送股，back_adj_factor = 1.2
    - 2024 年: 2024-06-03 除权送股，back_adj_factor = 1.5
    - K 线数据涵盖 2023 与 2024 年的多只股票
    """
    data_dir = str(temp_data_dir)
    meta_mgr = MetadataManager(data_dir)

    # 1. 准备复权因子数据 (ashare.adj_factor.baostock)
    factor_df_2023 = pl.DataFrame({
        "symbol": ["sh.600000"],
        "datetime": ["2023-05-10T15:00:00.000+08:00"],
        "timestamp": [1683702000000],
        "back_adj_factor": [1.2],
    }, schema={
        "symbol": pl.String,
        "datetime": pl.String,
        "timestamp": pl.Int64,
        "back_adj_factor": pl.Float64,
    })

    factor_df_2024 = pl.DataFrame({
        "symbol": ["sh.600000", "sz.000001"],
        "datetime": ["2024-06-03T15:00:00.000+08:00", "2024-06-04T15:00:00.000+08:00"],
        "timestamp": [1717398000000, 1717484400000],
        "back_adj_factor": [1.5, 2.0],
    }, schema={
        "symbol": pl.String,
        "datetime": pl.String,
        "timestamp": pl.Int64,
        "back_adj_factor": pl.Float64,
    })

    storage_pq_ev = StorageFactory.get_storage("parquet", data_dir=data_dir, category="event")
    storage_pq_ev.write_event("ashare.adj_factor.baostock", factor_df_2023)
    storage_pq_ev.write_event("ashare.adj_factor.baostock", factor_df_2024)
    storage_pq_ev.finalize("ashare.adj_factor.baostock")

    meta_mgr.save("ashare.adj_factor.baostock", "parquet", {
        "version": 1,
        "table_id": "ashare.adj_factor.baostock",
        "category": "event",
        "format": "parquet",
        "schema": {"symbol": "String", "datetime": "String", "timestamp": "Int64", "back_adj_factor": "Float64"},
        "statistics": {"start_datetime": "2023-05-10T15:00:00.000+08:00", "end_datetime": "2024-06-04T15:00:00.000+08:00", "total_bars": 3}
    })

    # 2. 准备 Baostock 原始日线 K 线数据 (ashare.kline.1d.raw.baostock)
    kline_df_2024 = pl.DataFrame({
        "symbol": ["sh.600000", "sh.600000", "sz.000001", "sh.688001"],
        "datetime": [
            "2024-06-01T15:00:00.000+08:00",
            "2024-06-05T15:00:00.000+08:00",
            "2024-06-05T15:00:00.000+08:00",
            "2024-06-05T15:00:00.000+08:00",
        ],
        "timestamp": [1717225200000, 1717570800000, 1717570800000, 1717570800000],
        "open": [10.0, 10.5, 20.0, 50.0],
        "high": [10.2, 10.8, 20.5, 51.0],
        "low": [9.8, 10.2, 19.5, 49.0],
        "close": [10.0, 10.4, 20.0, 50.0],
        "volume": [1000.0, 1200.0, 2000.0, 500.0],
        "amount": [10000.0, 12480.0, 40000.0, 25000.0],
        "trade_status": ["1", "1", "1", "1"],
    }, schema={
        "symbol": pl.String,
        "datetime": pl.String,
        "timestamp": pl.Int64,
        "open": pl.Float64,
        "high": pl.Float64,
        "low": pl.Float64,
        "close": pl.Float64,
        "volume": pl.Float64,
        "amount": pl.Float64,
        "trade_status": pl.String,
    })

    storage_pq_ts = StorageFactory.get_storage("parquet", data_dir=data_dir, category="timeseries")
    storage_pq_ts.write_series("ashare.kline.1d.raw.baostock", kline_df_2024)
    storage_pq_ts.finalize("ashare.kline.1d.raw.baostock")

    meta_mgr.save("ashare.kline.1d.raw.baostock", "parquet", {
        "version": 1,
        "table_id": "ashare.kline.1d.raw.baostock",
        "category": "timeseries",
        "format": "parquet",
        "schema": {
            "symbol": "String", "datetime": "String", "timestamp": "Int64",
            "open": "Float64", "high": "Float64", "low": "Float64", "close": "Float64",
            "volume": "Float64", "amount": "Float64", "trade_status": "String"
        },
        "statistics": {
            "start_datetime": "2024-06-01T15:00:00.000+08:00",
            "end_datetime": "2024-06-05T15:00:00.000+08:00",
            "total_bars": 4,
            "symbol_count": 3
        }
    })

    # 3. 准备 TDX 原始 1 分钟高频 K 线数据 (ashare.kline.1m.raw.tdx)
    tdx_min_df_2024 = pl.DataFrame({
        "symbol": ["sh.600000", "sh.600000"],
        "datetime": [
            "2024-06-05T09:30:00.000+08:00",
            "2024-06-05T09:31:00.000+08:00",
        ],
        "timestamp": [1717551000000, 1717551060000],
        "open": [10.5, 10.6],
        "high": [10.6, 10.7],
        "low": [10.4, 10.5],
        "close": [10.5, 10.6],
        "volume": [100.0, 120.0],
        "amount": [1050.0, 1272.0],
    }, schema={
        "symbol": pl.String,
        "datetime": pl.String,
        "timestamp": pl.Int64,
        "open": pl.Float64,
        "high": pl.Float64,
        "low": pl.Float64,
        "close": pl.Float64,
        "volume": pl.Float64,
        "amount": pl.Float64,
    })

    storage_pq_ts.write_series("ashare.kline.1m.raw.tdx", tdx_min_df_2024)
    storage_pq_ts.finalize("ashare.kline.1m.raw.tdx")

    meta_mgr.save("ashare.kline.1m.raw.tdx", "parquet", {
        "version": 1,
        "table_id": "ashare.kline.1m.raw.tdx",
        "category": "timeseries",
        "format": "parquet",
        "schema": {
            "symbol": "String", "datetime": "String", "timestamp": "Int64",
            "open": "Float64", "high": "Float64", "low": "Float64", "close": "Float64",
            "volume": "Float64", "amount": "Float64"
        },
        "statistics": {
            "start_datetime": "2024-06-05T09:30:00.000+08:00",
            "end_datetime": "2024-06-05T09:31:00.000+08:00",
            "total_bars": 2,
            "symbol_count": 1
        }
    })

    return temp_data_dir


def test_end_to_end_default_raw_zero_io(populated_kline_and_factor_storage):
    """端到端验证：默认 get() 参数为 raw，直读原始物理价格，不触发因子表计算。"""
    df_raw = cq.data.ashare.kline.get(
        symbols="sh.600000",
        start_date="2024-06-01",
        end_date="2024-06-05"
    )
    assert not df_raw.is_empty()
    assert df_raw["close"].to_list() == [10.0, 10.4]
    assert df_raw["volume"].to_list() == [1000.0, 1200.0]


def test_end_to_end_dynamic_adj_with_history_truncation(populated_kline_and_factor_storage):
    """端到端验证：显式指定 adj='adj'，仅查 2024-06 月切片，正确跨年份继承 2023 年历史累计因子并折算。"""
    df_adj = cq.data.ashare.kline.get(
        symbols="sh.600000",
        adj="adj",
        start_date="2024-06-01",
        end_date="2024-06-05"
    )
    assert not df_adj.is_empty()
    # 2024-06-01 继承 2023-05-10 的 1.2 因子 -> 10.0 * 1.2 = 12.0
    # 2024-06-05 匹配 2024-06-03 的 1.5 因子 -> 10.4 * 1.5 = 15.6
    assert df_adj["close"].to_list() == pytest.approx([12.0, 15.6])
    assert df_adj["open"].to_list() == pytest.approx([12.0, 15.75])
    # 非价格列严格保持不变
    assert df_adj["volume"].to_list() == [1000.0, 1200.0]
    assert df_adj["trade_status"].to_list() == ["1", "1"]


def test_end_to_end_tdx_1m_high_freq_dynamic_adjustment(populated_kline_and_factor_storage):
    """端到端验证：TDX 1m 超高频分笔行情 + Baostock 因子表动态复权。"""
    df_tdx_adj = cq.data.ashare.kline.get(
        freq="1m",
        adj="adj",
        source="tdx",
        symbols="sh.600000",
        start_date="2024-06-05",
        end_date="2024-06-05"
    )
    assert not df_tdx_adj.is_empty()
    # 2024-06-05 当日 1m bar 共享 1.5 因子 -> 10.5 * 1.5 = 15.75, 10.6 * 1.5 = 15.90
    assert df_tdx_adj["close"].to_list() == pytest.approx([15.75, 15.90])
    assert df_tdx_adj["open"].to_list() == pytest.approx([15.75, 15.90])
    assert df_tdx_adj["volume"].to_list() == [100.0, 120.0]


def test_end_to_end_subnew_stock_fallback(populated_kline_and_factor_storage):
    """端到端验证：次新股 (sh.688001) 无因子记录时，复权调用自动保底 1.0，价格不变。"""
    df_subnew = cq.data.ashare.kline.get(
        symbols="sh.688001",
        adj="adj",
        start_date="2024-06-01",
        end_date="2024-06-05"
    )
    assert not df_subnew.is_empty()
    assert df_subnew["close"].to_list() == [50.0]
    assert df_subnew["open"].to_list() == [50.0]


def test_end_to_end_static_adj_precedence(populated_kline_and_factor_storage, temp_data_dir):
    """端到端验证：当本地已同步静态 adj 表时，优先 0 Join 直读静态表"""
    data_dir = str(temp_data_dir)
    meta_mgr = MetadataManager(data_dir)
    storage_pq_ts = StorageFactory.get_storage("parquet", data_dir=data_dir, category="timeseries")

    # 写入静态 adj 数据 (假设 close 值为 99.0 以明确区分动态计算)
    static_adj_df = pl.DataFrame({
        "symbol": ["sh.600000"],
        "datetime": ["2024-06-05T15:00:00.000+08:00"],
        "timestamp": [1717570800000],
        "open": [99.0],
        "high": [100.0],
        "low": [98.0],
        "close": [99.0],
        "volume": [1200.0],
        "amount": [12480.0],
        "trade_status": ["1"],
    }, schema={
        "symbol": pl.String,
        "datetime": pl.String,
        "timestamp": pl.Int64,
        "open": pl.Float64,
        "high": pl.Float64,
        "low": pl.Float64,
        "close": pl.Float64,
        "volume": pl.Float64,
        "amount": pl.Float64,
        "trade_status": pl.String,
    })

    storage_pq_ts.write_series("ashare.kline.1d.adj.baostock", static_adj_df)
    storage_pq_ts.finalize("ashare.kline.1d.adj.baostock")
    meta_mgr.save("ashare.kline.1d.adj.baostock", "parquet", {
        "version": 1,
        "table_id": "ashare.kline.1d.adj.baostock",
        "category": "timeseries",
        "format": "parquet",
        "schema": {
            "symbol": "String", "datetime": "String", "timestamp": "Int64",
            "open": "Float64", "high": "Float64", "low": "Float64", "close": "Float64",
            "volume": "Float64", "amount": "Float64", "trade_status": "String"
        },
        "statistics": {"start_datetime": "2024-06-05T15:00:00.000+08:00", "end_datetime": "2024-06-05T15:00:00.000+08:00", "total_bars": 1}
    })

    # 调用 get(adj="adj") -> 优先直读静态 adj 表
    df_res = cq.data.ashare.kline.get(
        symbols="sh.600000",
        adj="adj",
        start_date="2024-06-05",
        end_date="2024-06-05"
    )
    assert not df_res.is_empty()
    assert df_res["close"].to_list() == [99.0]

