"""
tests/unit/test_custom_table_read_write.py

自定义数据表读写闭环集成单元测试：
验证 cq.data.write、cq.data.read、list_tables、list_symbols、get_time_range 等在自定义 Table 下的无缝配合。
"""

import pytest
import polars as pl
from cq.data.entrypoints.python_api import (
    write,
    read,
    list_tables,
    list_symbols,
    get_time_range,
    get_schema,
    get_row_count,
    list_formats
)
from cq.data.config import settings


def test_custom_table_full_sdk_lifecycle(tmp_path):
    """测试通过 Python SDK 统一 API 完成自定义数据表的创建、写入、读取与元数据探查"""
    orig_data_dir = settings.data_dir
    settings.data_dir = str(tmp_path)
    
    try:
        # 1. 写入自定义时序表
        df_kline = pl.DataFrame({
            "symbol": ["BTC.USDT", "BTC.USDT", "ETH.USDT"],
            "timestamp": [1704067200000, 1704153600000, 1704067200000],
            "close": [42000.5, 43500.0, 2250.0],
            "volume": [150.0, 210.0, 800.0]
        })
        
        write(
            table_id="crypto.kline.1d.binance",
            df=df_kline,
            formats=["parquet", "csv"]
        )
        
        # 2. 写入自定义事件表
        df_event = pl.DataFrame({
            "symbol": ["BTC.USDT", "ETH.USDT"],
            "timestamp": [1704067200000, 1704067200000],
            "funding_rate": [0.0001, 0.00015]
        })
        write(
            table_id="crypto.funding_rate.binance",
            df=df_event,
            category="event"
        )
        
        # 3. 探查表清单
        tables = list_tables()
        table_ids = [t["table_id"] for t in tables]
        assert "crypto.kline.1d.binance" in table_ids
        assert "crypto.funding_rate.binance" in table_ids
        
        # 4. 探查 symbols
        syms = list_symbols("crypto.kline.1d.binance")
        assert "BTC.USDT" in syms
        assert "ETH.USDT" in syms
        
        # 5. 探查 schema 与 row_count
        schema = get_schema("crypto.kline.1d.binance")
        assert "close" in schema
        assert "volume" in schema
        assert get_row_count("crypto.kline.1d.binance") == 3
        
        # 6. 探查 formats
        fmts = list_formats("crypto.kline.1d.binance")
        assert "parquet" in fmts
        assert "csv" in fmts
        
        # 7. 通过 cq.data.read() 切片读取 (带 symbol 与 columns 过滤)
        df_filtered = read(
            table_id="crypto.kline.1d.binance",
            symbols=["BTC.USDT"],
            columns=["timestamp", "close"]
        )
        assert df_filtered.height == 2
        assert df_filtered.columns == ["timestamp", "close"]
        assert df_filtered["close"].to_list() == [42000.5, 43500.0]
        
        # 8. 通过 cq.data.read() 读取事件表
        df_ev_read = read(table_id="crypto.funding_rate.binance")
        assert df_ev_read.height == 2
        assert "funding_rate" in df_ev_read.columns
        
    finally:
        settings.data_dir = orig_data_dir
