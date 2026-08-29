"""
tests/unit/test_accessors.py

单元测试：OOP 便捷访问层、DefaultConfig 链式继承与校验
"""

import pytest
from unittest.mock import patch, MagicMock
import polars as pl

import cq.data
from cq.data.entrypoints.accessors import DefaultConfig, AShareKline, AIndexKline, AShareConcept, AShare


def test_default_config_chain():
    """测试 DefaultConfig 三层继承链 (全局 -> 市场 -> 表) 对 source, format 的支持"""
    global_def = DefaultConfig(fallback_source="baostock", fallback_format="parquet")
    market_def = DefaultConfig(parent=global_def)
    table_def = DefaultConfig(parent=market_def)

    # 1. 默认探查：回退到 fallback
    assert table_def.resolve_source() == "baostock"
    assert table_def.resolve_format() == "parquet"

    # 2. 全局设置
    global_def.source = "eastmoney"
    global_def.format = "csv"
    assert table_def.resolve_source() == "eastmoney"
    assert table_def.resolve_format() == "csv"

    # 3. 市场级覆盖全局 (小覆盖大)
    market_def.source = "tdx"
    market_def.format = "parquet"
    assert table_def.resolve_source() == "tdx"
    assert table_def.resolve_format() == "parquet"

    # 4. 表级覆盖市场级
    table_def.source = "baostock"
    table_def.format = "csv"
    assert table_def.resolve_source() == "baostock"
    assert table_def.resolve_format() == "csv"

    # 5. 重置表级，恢复继承
    table_def.source = None
    table_def.format = None
    assert table_def.resolve_source() == "tdx"
    assert table_def.resolve_format() == "parquet"


def test_accessor_default_args(mock_baostock, temp_data_dir):
    """测试 OOP 表的具体 get() 方法默认参数与路径拼接 (默认 100% 为 raw 极速零开销路径)"""
    with patch("cq.data.entrypoints.accessors.base.read") as mock_read:
        mock_read.return_value = pl.DataFrame({"timestamp": [1704067200000], "close": [10.0]})

        # 1. 测试 AShareKline 默认 freq="1d", adj="raw" (只读取 raw 表，零因子 IO)
        df = cq.data.ashare.kline.get(symbols="sh.600000")
        assert not df.is_empty()
        mock_read.assert_called_once_with(
            table_id="ashare.kline.1d.raw.baostock",
            symbols="sh.600000",
            start_date=None,
            end_date=None,
            columns=None,
            format="parquet"
        )

        mock_read.reset_mock()

        # 2. 测试 AIndexKline 默认 freq="1d" (固定 raw)
        cq.data.aindex.kline.get(symbols="sh.000001")
        mock_read.assert_called_once_with(
            table_id="aindex.kline.1d.raw.baostock",
            symbols="sh.000001",
            start_date=None,
            end_date=None,
            columns=None,
            format="parquet"
        )

        mock_read.reset_mock()

        # 3. 测试 AShare 相关事件与静态表 (adj_factor, concept, industry, dragon_tiger, inst_trade)
        cq.data.ashare.adj_factor.get(symbols="sh.600000")
        mock_read.assert_called_with(table_id="ashare.adj_factor.baostock", symbols="sh.600000", start_date=None, end_date=None, columns=None, format="parquet")

        cq.data.ashare.concept.get(source="eastmoney")
        mock_read.assert_called_with(table_id="ashare.concept.eastmoney", symbols=None, start_date=None, end_date=None, columns=None, format="parquet")

        cq.data.ashare.industry.get(source="eastmoney")
        mock_read.assert_called_with(table_id="ashare.industry.eastmoney", symbols=None, start_date=None, end_date=None, columns=None, format="parquet")

        cq.data.ashare.dragon_tiger.get(source="eastmoney")
        mock_read.assert_called_with(table_id="ashare.dragon_tiger.eastmoney", symbols=None, start_date=None, end_date=None, columns=None, format="parquet")

        cq.data.ashare.inst_trade.get(source="eastmoney")
        mock_read.assert_called_with(table_id="ashare.inst_trade.eastmoney", symbols=None, start_date=None, end_date=None, columns=None, format="parquet")


def test_accessor_dynamic_adj_dual_chain(mock_baostock, temp_data_dir):
    """测试 AShareKline 在显式 adj='adj' 时的双链对称解析与动态后复权计算。"""
    raw_df = pl.DataFrame({
        "symbol": ["sh.600000"],
        "datetime": ["2024-06-01T15:00:00.000+08:00"],
        "timestamp": [1717225200000],
        "open": [10.0],
        "high": [11.0],
        "low": [9.5],
        "close": [10.5],
        "volume": [1000.0],
    })
    factor_df = pl.DataFrame({
        "symbol": ["sh.600000"],
        "datetime": ["2024-06-01T15:00:00.000+08:00"],
        "timestamp": [1717225200000],
        "back_adj_factor": [1.5],
    })

    def mock_read_side_effect(table_id, symbols=None, start_date=None, end_date=None, columns=None, format="auto"):
        if "kline" in table_id:
            return raw_df
        elif "adj_factor" in table_id:
            return factor_df
        return pl.DataFrame()

    with patch("cq.data.entrypoints.accessors.base.read", side_effect=mock_read_side_effect) as mock_read:
        # 1. 默认 Baostock 行情 + Baostock 因子
        df_adj = cq.data.ashare.kline.get(symbols="sh.600000", adj="adj", start_date="2024-06-01", end_date="2024-06-01")
        assert df_adj["close"].to_list() == [15.75]
        assert df_adj["open"].to_list() == [15.0]
        assert df_adj["volume"].to_list() == [1000.0]

        # 验证读取了 raw K 线表与 adj_factor 因子表 (因子表 start_date 为 None)
        calls = mock_read.call_args_list
        assert any(c.kwargs.get("table_id") == "ashare.kline.1d.raw.baostock" for c in calls)
        assert any(c.kwargs.get("table_id") == "ashare.adj_factor.baostock" and c.kwargs.get("start_date") is None for c in calls)

        mock_read.reset_mock()

        # 2. 跨源组合：TDX 行情 + Baostock 因子
        df_tdx_adj = cq.data.ashare.kline.get(
            symbols="sh.600000",
            adj="adj",
            source="tdx"
        )
        assert df_tdx_adj["close"].to_list() == [15.75]
        calls_tdx = mock_read.call_args_list
        assert any(c.kwargs.get("table_id") == "ashare.kline.1d.raw.tdx" for c in calls_tdx)
        assert any(c.kwargs.get("table_id") == "ashare.adj_factor.baostock" for c in calls_tdx)


def test_unsupported_adj_mode_error():
    """测试非法复权模式 (如前复权 qfq) 立即抛出 ValueError 拦截。"""
    with pytest.raises(ValueError, match="Unsupported adjustment mode 'qfq'"):
        cq.data.ashare.kline.get(symbols="sh.600000", adj="qfq")


def test_unsupported_table_id_error():
    """测试拼装非法或不受驱动支持的 table_id 时抛出 ValueError"""
    with pytest.raises(ValueError, match="Unsupported table_id"):
        cq.data.ashare.kline.get(freq="100m", adj="raw", source="baostock")


def test_configure_from_yaml(tmp_path):
    """测试 cq.data.configure 指定配置文件路径加载"""
    custom_yaml = tmp_path / "custom_config.yaml"
    custom_yaml.write_text("data_dir: '/custom/storage'\ndefaults:\n  source: 'tdx'\n", encoding="utf-8")

    settings = cq.data.configure(custom_yaml)
    assert settings.data_dir == "/custom/storage"
    assert cq.data.default.resolve_source() == "tdx"

    # 恢复默认设置
    cq.data.settings.data_dir = "data"
    cq.data.default.source = None
    cq.data.default.adj = None
