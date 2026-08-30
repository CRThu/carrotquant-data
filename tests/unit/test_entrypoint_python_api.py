"""
tests/unit/test_entrypoint_python_api.py

Python SDK 接入面 (python_api.py) 单元测试。
包含 read_series, read_events, list_*, get_*, sync, configure 等接口的断言与 Mock 覆盖。
"""

import pytest
import polars as pl
from unittest.mock import patch, MagicMock

import cq.data
from cq.data.entrypoints import python_api


def test_read_unified_polars():
    """测试统一 read 接口按 table_id 智能路由返回 Polars DataFrame"""
    mock_pl_df = pl.DataFrame({
        "timestamp": [1704067200000],
        "symbol": ["sh.600000"],
        "close": [10.5]
    })
    with patch("cq.data.service.data_reader.read_series", return_value=mock_pl_df):
        res_pl = python_api.read("ashare.kline.1d.raw.baostock", symbols="sh.600000")
        assert isinstance(res_pl, pl.DataFrame)
        assert res_pl.height == 1

    mock_event_df = pl.DataFrame({
        "symbol": ["sh.600000"],
        "board_name": ["银行"]
    })
    with patch("cq.data.service.data_reader.read_events", return_value=mock_event_df):
        res_event = python_api.read("ashare.concept.eastmoney")
        assert isinstance(res_event, pl.DataFrame)
        assert res_event.height == 1


def test_read_invalid_table_id_raises_error():
    """测试当 table_id 为空或非法类型时直接抛出 ValueError 报错"""
    with pytest.raises(ValueError, match="non-empty string"):
        python_api.read("")

    with pytest.raises(ValueError, match="non-empty string"):
        python_api.read(None)


def test_write_and_register_provider_delegation():
    """测试 write 和 register_provider 快捷函数正确委托"""
    mock_df = pl.DataFrame({"symbol": ["test"], "timestamp": [1000], "val": [1]})
    with patch("cq.data.service.data_writer.DataWriter.write", return_value={"status": "success"}) as mock_write:
        res = python_api.write("custom_table", mock_df)
        assert res["status"] == "success"
        assert mock_write.called

    with patch("cq.data.provider.provider_manager.ProviderManager.register_provider") as mock_reg:
        python_api.register_provider("custom_src", MagicMock())
        assert mock_reg.called



def test_list_and_get_metadata_functions():
    """测试 list_* 与 get_* 元数据读取助手函数正确委托给 metadata_reader"""
    with patch("cq.data.service.metadata_reader.list_series_tables", return_value=["table1"]), \
         patch("cq.data.service.metadata_reader.list_event_tables", return_value=["table2"]):
        tables = python_api.list_tables()
        assert len(tables) == 2
        assert tables[0] == {"table_id": "table1", "category": "timeseries"}
        assert tables[1] == {"table_id": "table2", "category": "event"}

    with patch("cq.data.service.metadata_reader.list_formats", return_value=["parquet"]):
        assert python_api.list_formats("table1") == ["parquet"]

    with patch("cq.data.service.metadata_reader.list_symbols", return_value=["sh.600000"]):
        assert python_api.list_symbols("table1") == ["sh.600000"]

    with patch("cq.data.service.metadata_reader.get_time_range", return_value=("2024-01-01", "2024-01-31")):
        assert python_api.get_time_range("table1") == ("2024-01-01", "2024-01-31")

    with patch("cq.data.service.metadata_reader.get_schema", return_value={"close": "Float64"}):
        assert python_api.get_schema("table1") == {"close": "Float64"}

    with patch("cq.data.service.metadata_reader.get_row_count", return_value=500):
        assert python_api.get_row_count("table1") == 500


def test_sync_function_delegation():
    """测试 sync 快捷函数正确转发至 SyncManager"""
    with patch("cq.data.service.sync_manager.sync") as mock_sync:
        python_api.sync("ashare.kline.1d.raw.baostock", formats="parquet", start_date="2024-01-01")
        assert mock_sync.called
        kwargs = mock_sync.call_args.kwargs
        assert kwargs["table_ids"] == "ashare.kline.1d.raw.baostock"
        assert kwargs["formats"] == "parquet"
        assert kwargs["start_date"] == "2024-01-01"


def test_configure():
    """测试 configure 全局参数配置"""
    assert cq.data.settings is not None

    with patch("cq.data.config.settings.Settings.configure") as mock_conf:
        python_api.configure("/tmp/test_config.yaml")
        assert mock_conf.called
