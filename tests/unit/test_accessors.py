"""
tests/unit/test_accessors.py

单元测试：OOP 便捷访问层、DefaultConfig 链式继承与校验
"""

import pytest
from unittest.mock import patch, MagicMock
import polars as pl

import cq.data
from cq.data.entrypoints.accessors.base import DefaultConfig


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
        if ".raw." in table_id:
            return raw_df
        elif "adj_factor" in table_id:
            return factor_df
        elif ".adj." in table_id:
            raise FileNotFoundError(f"Static table {table_id} not found")
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


def test_accessor_adj_prefers_static_table_when_available(mock_baostock):
    """测试当本地存在物理静态 adj 表时，优先 0 Join 直接读取该表"""
    static_df = pl.DataFrame({
        "symbol": ["sh.600000"],
        "datetime": ["2024-06-01T15:00:00.000+08:00"],
        "timestamp": [1717225200000],
        "open": [15.0],
        "close": [15.75],
    })

    with patch("cq.data.entrypoints.accessors.base.read", return_value=static_df) as mock_read:
        df = cq.data.ashare.kline.get(symbols="sh.600000", adj="adj", source="baostock")
        assert df["close"].to_list() == [15.75]
        # 验证仅直读了一次静态 adj 表，未去读 factor 表
        mock_read.assert_called_once_with(
            table_id="ashare.kline.1d.adj.baostock",
            symbols="sh.600000",
            start_date=None,
            end_date=None,
            columns=None,
            format="parquet"
        )


def test_aetf_accessor(mock_baostock, temp_data_dir):
    """测试 AETF 命名空间访问器 (kline, adj_factor) 及其动态后复权"""
    raw_df = pl.DataFrame({
        "symbol": ["sz.159919"],
        "datetime": ["2024-06-01T15:00:00.000+08:00"],
        "timestamp": [1717225200000],
        "open": [3.0],
        "high": [3.1],
        "low": [2.9],
        "close": [3.05],
        "volume": [50000.0],
    })
    factor_df = pl.DataFrame({
        "symbol": ["sz.159919"],
        "datetime": ["2024-06-01T15:00:00.000+08:00"],
        "timestamp": [1717225200000],
        "back_adj_factor": [2.0],
    })

    def mock_read_aetf(table_id, symbols=None, start_date=None, end_date=None, columns=None, format="auto"):
        if "kline" in table_id:
            return raw_df
        elif "adj_factor" in table_id:
            return factor_df
        return pl.DataFrame()

    with patch("cq.data.entrypoints.accessors.base.read", side_effect=mock_read_aetf) as mock_read:
        # 1. raw 直读
        df_raw = cq.data.aetf.kline.get(symbols="sz.159919")
        assert not df_raw.is_empty()
        mock_read.assert_called_with(
            table_id="aetf.kline.1d.raw.stockdb",
            symbols="sz.159919",
            start_date=None,
            end_date=None,
            columns=None,
            format="parquet"
        )

        mock_read.reset_mock()

        # 2. 动态后复权
        df_adj = cq.data.aetf.kline.get(symbols="sz.159919", adj="adj")
        assert df_adj["close"].to_list() == [6.1]
        assert df_adj["open"].to_list() == [6.0]

        mock_read.reset_mock()

        # 3. 独立复权因子直读
        cq.data.aetf.adj_factor.get(symbols="sz.159919")
        mock_read.assert_called_with(
            table_id="aetf.adj_factor.stockdb",
            symbols="sz.159919",
            start_date=None,
            end_date=None,
            columns=None,
            format="parquet"
        )


def test_accessor_adj_missing_factor_raises_error(mock_baostock):
    """测试当请求 adj='adj' 时，若本地无静态 adj 表且无因子表，直接显式抛出异常，绝不隐式假复权"""
    raw_df = pl.DataFrame({
        "symbol": ["sh.600000"],
        "datetime": ["2024-06-01T15:00:00.000+08:00"],
        "timestamp": [1717225200000],
        "open": [10.0],
        "close": [10.5],
    })

    def mock_read_missing_factor(table_id, **kwargs):
        if "adj" in table_id and "kline" in table_id:
            raise FileNotFoundError(f"Static adj table '{table_id}' not found.")
        elif "raw" in table_id:
            return raw_df
        elif "adj_factor" in table_id:
            raise FileNotFoundError(f"Factor table '{table_id}' not found.")
        return pl.DataFrame()

    with patch("cq.data.entrypoints.accessors.base.read", side_effect=mock_read_missing_factor):
        with pytest.raises(FileNotFoundError, match="Factor table"):
            cq.data.ashare.kline.get(symbols="sh.600000", adj="adj", source="baostock")


def test_accessor_source_and_format_properties():
    """测试表级与市场级 active_source, source, active_format, format 及 supported_sources 自省能力"""
    # 1. 全局数据源列表查询
    sources = cq.data.list_sources()
    assert "baostock" in sources
    assert "eastmoney" in sources
    assert "tdx" in sources
    assert "stockdb" in sources

    # 2. 表级 active_source 与 source 读取
    assert cq.data.ashare.kline.active_source == "baostock"
    assert cq.data.ashare.kline.source == "baostock"
    assert cq.data.aetf.kline.active_source == "stockdb"
    assert cq.data.aetf.kline.source == "stockdb"

    # 3. 表级 supported_sources 自省
    ashare_kline_sources = cq.data.ashare.kline.supported_sources
    assert "baostock" in ashare_kline_sources
    assert "tdx" in ashare_kline_sources
    assert "stockdb" in ashare_kline_sources

    concept_sources = cq.data.ashare.concept.supported_sources
    assert "eastmoney" in concept_sources
    assert "stockdb" in concept_sources

    dragon_tiger_sources = cq.data.ashare.dragon_tiger.supported_sources
    assert dragon_tiger_sources == ["eastmoney"]

    # 4. 表级 supported_formats
    assert cq.data.ashare.kline.supported_formats == ["parquet", "csv"]

    # 5. 动态修改表级 source 并在 get 中生效
    try:
        cq.data.ashare.kline.source = "tdx"
        assert cq.data.ashare.kline.active_source == "tdx"
        assert cq.data.ashare.kline.source == "tdx"

        # 验证 repr
        rep = repr(cq.data.ashare.kline)
        assert "ashare.kline" in rep
        assert "active_source='tdx'" in rep
    finally:
        # 恢复默认
        cq.data.ashare.kline.source = None

    # 6. 市场级 source 读写验证
    try:
        cq.data.ashare.source = "stockdb"
        assert cq.data.ashare.active_source == "stockdb"
        assert cq.data.ashare.source == "stockdb"
        # 表级继承市场级
        assert cq.data.ashare.kline.active_source == "stockdb"
    finally:
        cq.data.ashare.source = None

    # 7. DefaultConfig 级 active_source 与 active_format
    assert cq.data.default.active_source == "baostock"
    assert cq.data.default.active_format == "parquet"

    # 8. 市场级 supported_sources 与 supported_formats
    ashare_all_sources = cq.data.ashare.supported_sources
    assert "baostock" in ashare_all_sources
    assert "eastmoney" in ashare_all_sources
    assert "tdx" in ashare_all_sources
    assert "stockdb" in ashare_all_sources
    assert cq.data.ashare.supported_formats == ["parquet", "csv"]

    assert cq.data.aetf.supported_sources == ["stockdb"]
    assert cq.data.aindex.supported_sources == ["baostock", "tdx"]

    # 9. 市场级 repr 验证
    assert "<AShare" in repr(cq.data.ashare)
    assert "<AETF" in repr(cq.data.aetf)
    assert "<AIndex" in repr(cq.data.aindex)



