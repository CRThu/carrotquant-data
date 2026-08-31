"""
StockDBProvider 单元测试。

验证:
1. 代码前缀规范化与剥离 (normalize_symbol / strip_symbol_prefix)
2. 表支持与类别/排序路由 (get_supported_tables / get_table_category / get_sort_keys)
3. 标的发现 (ashare 合并在市与退市股, aetf 隔离 1/5 号段, 事件表返回 _ALL_)
4. 日线数据清洗 (剔除 pre_close 脏列, 归一化列名, 保留截面因子, 15:00:00 对齐)
5. 1 分钟高频线清洗 (14 位时间戳解析)
6. 复权因子隔离分流 (ashare vs aetf 独立性与 cum -> back_adj_factor 映射)
7. 概念与申万行业平铺表生成
8. 空数据防御 (返回完整标准 Schema)
9. 异常拦截 (未启动服务时的 ConnectionRefusedError)
"""

import pytest
import polars as pl
from unittest.mock import MagicMock, patch

from cq.data.provider.stockdb.provider import (
    StockDBProvider,
    normalize_symbol,
    strip_symbol_prefix,
    check_stockdb_connection,
)


@pytest.fixture(autouse=True)
def _reset_provider_manager():
    """每个测试前后清理 ProviderManager singleton，防止泄漏。"""
    from cq.data.provider.provider_manager import ProviderManager
    ProviderManager._instance = None
    ProviderManager._providers = {}
    yield
    ProviderManager._instance = None
    ProviderManager._providers = {}


class MockStockDBRd:
    """模拟 stockdb.pyd 中的 rd 对象"""
    def __init__(self):
        self.code_dict = {
            "0": ["000001", "000002"],
            "3": ["300001"],
            "6": ["600000", "600519"],
            "9": ["900901"],
            "1": ["159919", "160105"],
            "5": ["510300", "588000"],
        }
        self.retired_list = ["600421", "000003"]
        self.daily_kline = [
            {
                "code": "600000", "date": 20240102, "open": 6.63, "high": 6.65, "low": 6.60, "close": 6.60,
                "volume": 22066700.0, "amount": 146066304.0, "turnover": 0.0752, "pct_chg": -0.302,
                "pre_close": 6.20, "name": "浦发银行", "total_mv": 193724367196.8, "float_mv": 193724367196.8,
                "total_share": 29352176848.0, "float_share": 29352176848.0, "pe_ttm": 5.0064, "pb": 0.321,
                "is_st": False, "vol_ratio": 0.99, "amplitude": 0.76
            }
        ]
        self.minute_kline = [
            {
                "code": "600000", "date": 20250102093000, "open": 10.3, "high": 10.3, "low": 10.3, "close": 10.3,
                "volume": 241900.0, "amount": 2491570.0
            }
        ]
        self.cum_factors = [
            ["复权:000001:19910430", 1.41],
            ["复权:600000:20240102", 10.5],
            ["复权:510300:20240105", 1.25],
            ["复权:159919:20240105", 1.10],
        ]
        self.boards = [
            ["板块:概念_人工智能:300001", {
                "code": "BK0800", "name": "人工智能", "category": "概念", "symbols": ["000001", "600000"]
            }],
            ["板块:行业_银行:801780", {
                "code": "801780.SI", "name": "银行", "category": "申万一级", "symbols": ["600000", "000001"]
            }],
            ["板块:行业_国有大型银行:801192", {
                "code": "801192.SI", "name": "国有大型银行", "category": "申万二级", "symbols": ["600000"]
            }],
        ]

    def get(self, *args):
        if args[0] == "股票代码":
            return self.code_dict
        elif args[0] == "复权*":
            mock_cum = MagicMock()
            mock_cum.get.return_value = self.cum_factors
            return mock_cum
        elif args[0] == "板块*":
            mock_bk = MagicMock()
            mock_bk.do.return_value = self.boards
            return mock_bk
        return None

    def vals(self, *args):
        if args[0] == "退市*":
            return self.retired_list
        elif args[0] == "日k":
            return self.daily_kline
        elif args[0] == "分钟k":
            return self.minute_kline
        return []


@pytest.fixture
def mock_stockdb_env():
    """Mock StockDB 的模块与底层 socket 探针"""
    mock_rd = MockStockDBRd()
    with patch("cq.data.provider.stockdb.provider.stockdb") as mock_mod, \
         patch("cq.data.provider.stockdb.provider.check_stockdb_connection", return_value=True):
        mock_mod.rd = mock_rd
        yield mock_rd


class TestSymbolNormalization:
    """测试证券代码规范化工具函数"""

    def test_normalize_symbol(self):
        assert normalize_symbol("600000") == "sh.600000"
        assert normalize_symbol("688001") == "sh.688001"
        assert normalize_symbol("900901") == "sh.900901"
        assert normalize_symbol("510300") == "sh.510300"
        assert normalize_symbol("588000") == "sh.588000"
        assert normalize_symbol("000001") == "sz.000001"
        assert normalize_symbol("300001") == "sz.300001"
        assert normalize_symbol("200002") == "sz.200002"
        assert normalize_symbol("159919") == "sz.159919"
        assert normalize_symbol("830001") == "bj.830001"
        assert normalize_symbol("430002") == "bj.430002"
        assert normalize_symbol("920156") == "bj.920156"
        # 已经带前缀的不重复添加
        assert normalize_symbol("sh.600000") == "sh.600000"
        assert normalize_symbol("sz.000001") == "sz.000001"

    def test_strip_symbol_prefix(self):
        assert strip_symbol_prefix("sh.600000") == "600000"
        assert strip_symbol_prefix("sz.000001") == "000001"
        assert strip_symbol_prefix("bj.830001") == "830001"
        assert strip_symbol_prefix("600000") == "600000"


class TestStockDBProviderCapabilities:
    """测试表支持与类别/排序路由"""

    def test_supported_tables(self, mock_stockdb_env):
        p = StockDBProvider()
        tables = p.get_supported_tables()
        assert "ashare.kline.1m.raw.stockdb" in tables
        assert "ashare.kline.1d.raw.stockdb" in tables
        assert "ashare.adj_factor.stockdb" in tables
        assert "ashare.concept.stockdb" in tables
        assert "ashare.industry.stockdb" in tables
        assert "aetf.kline.1m.raw.stockdb" in tables
        assert "aetf.kline.1d.raw.stockdb" in tables
        assert "aetf.adj_factor.stockdb" in tables
        assert len(tables) == 8

    def test_table_category_and_sort_keys(self, mock_stockdb_env):
        p = StockDBProvider()
        assert p.get_table_category("ashare.kline.1d.raw.stockdb") == "timeseries"
        assert p.get_sort_keys("ashare.kline.1d.raw.stockdb") == ["timestamp"]

        assert p.get_table_category("ashare.adj_factor.stockdb") == "event"
        assert p.get_sort_keys("ashare.adj_factor.stockdb") == ["timestamp", "symbol"]

        assert p.get_table_category("ashare.concept.stockdb") == "event"
        assert p.get_sort_keys("ashare.concept.stockdb") == ["board_code", "symbol"]


class TestStockDBSymbolDiscovery:
    """测试标的池发现与市场隔离"""

    def test_ashare_symbols_discovery(self, mock_stockdb_env):
        p = StockDBProvider()
        symbols = p.get_all_symbols("ashare.kline.1d.raw.stockdb")
        # 包含了 0/3/6/9 以及退市股 600421, 000003
        assert "sh.600000" in symbols
        assert "sz.000001" in symbols
        assert "sz.300001" in symbols
        assert "sh.600421" in symbols
        # 严格隔离：不包含 1/5 基金号段
        assert "sz.159919" not in symbols
        assert "sh.510300" not in symbols

    def test_aetf_symbols_discovery(self, mock_stockdb_env):
        p = StockDBProvider()
        symbols = p.get_all_symbols("aetf.kline.1d.raw.stockdb")
        assert "sz.159919" in symbols
        assert "sh.510300" in symbols
        assert "sh.588000" in symbols
        # 严格隔离：不包含个股
        assert "sh.600000" not in symbols
        assert "sz.000001" not in symbols

    def test_event_tables_discovery(self, mock_stockdb_env):
        p = StockDBProvider()
        assert p.get_all_symbols("ashare.concept.stockdb") == ["_ALL_"]
        assert p.get_all_symbols("ashare.industry.stockdb") == ["_ALL_"]
        assert p.get_all_symbols("ashare.adj_factor.stockdb") == ["_ALL_"]
        assert p.get_all_symbols("aetf.adj_factor.stockdb") == ["_ALL_"]


class TestStockDBDataFetchAndCleaning:
    """测试数据拉取与清洗规范"""

    def test_fetch_kline_1d_cleaning(self, mock_stockdb_env):
        p = StockDBProvider()
        df = p.fetch("ashare.kline.1d.raw.stockdb", "sh.600000", "2024-01-01", "2024-01-05")
        assert not df.is_empty()
        assert len(df) == 1

        # 1. 核心列排在最前
        assert df.columns[:3] == ["symbol", "datetime", "timestamp"]
        assert df["symbol"][0] == "sh.600000"

        # 2. 脏列 pre_close 与 name 必须被物理剔除
        assert "pre_close" not in df.columns
        assert "name" not in df.columns

        # 3. 字段归一化与类型
        assert "turnover_rate" in df.columns
        assert "change_pct" in df.columns
        assert df.schema["turnover_rate"] == pl.Float64
        assert df.schema["change_pct"] == pl.Float64

        # 4. 全量截面多因子保留
        assert df.schema["total_mv"] == pl.Float64
        assert df.schema["float_mv"] == pl.Float64
        assert df.schema["pe_ttm"] == pl.Float64
        assert df.schema["pb"] == pl.Float64
        assert df.schema["is_st"] == pl.Boolean
        assert df.schema["vol_ratio"] == pl.Float64
        assert df.schema["amplitude"] == pl.Float64

        # 5. 时间轴对齐 15:00:00 (收盘时间)
        assert df["datetime"][0].endswith("15:00:00.000+08:00")

    def test_fetch_kline_1m_cleaning(self, mock_stockdb_env):
        p = StockDBProvider()
        df = p.fetch("ashare.kline.1m.raw.stockdb", "sh.600000", "2025-01-02", "2025-01-02")
        assert not df.is_empty()
        assert df["symbol"][0] == "sh.600000"
        assert df.columns[:3] == ["symbol", "datetime", "timestamp"]
        # 1m 时间轴保持原始时分秒 (09:30:00)
        assert "09:30:00.000+08:00" in df["datetime"][0]

    def test_fetch_adj_factor_isolation(self, mock_stockdb_env):
        p = StockDBProvider()
        # 1. 股票复权因子表：仅包含个股 (0/6 号段)
        df_ashare = p.fetch("ashare.adj_factor.stockdb", "_ALL_", "1990-01-01", "2025-01-01")
        assert not df_ashare.is_empty()
        symbols_ashare = set(df_ashare["symbol"].to_list())
        assert "sz.000001" in symbols_ashare
        assert "sh.600000" in symbols_ashare
        assert "sh.510300" not in symbols_ashare
        assert "sz.159919" not in symbols_ashare
        assert "back_adj_factor" in df_ashare.columns

        # 2. 基金 ETF 复权因子表：仅包含基金 (1/5 号段)
        df_aetf = p.fetch("aetf.adj_factor.stockdb", "_ALL_", "1990-01-01", "2025-01-01")
        assert not df_aetf.is_empty()
        symbols_aetf = set(df_aetf["symbol"].to_list())
        assert "sh.510300" in symbols_aetf
        assert "sz.159919" in symbols_aetf
        assert "sz.000001" not in symbols_aetf
        assert "sh.600000" not in symbols_aetf

    def test_fetch_concept_and_industry(self, mock_stockdb_env):
        p = StockDBProvider()
        # 概念板块
        df_concept = p.fetch("ashare.concept.stockdb", "_ALL_", None, None)
        assert not df_concept.is_empty()
        assert set(df_concept.columns) == {"board_code", "board_name", "category", "symbol"}
        assert all(c == "概念" for c in df_concept["category"].to_list())
        assert "BK0800" in df_concept["board_code"].to_list()
        assert "sz.000001" in df_concept["symbol"].to_list()

        # 申万行业板块
        df_ind = p.fetch("ashare.industry.stockdb", "_ALL_", None, None)
        assert not df_ind.is_empty()
        assert set(df_ind.columns) == {"board_code", "board_name", "category", "symbol"}
        cats = set(df_ind["category"].to_list())
        assert cats.issubset({"申万一级", "申万二级", "申万三级"})
        assert "801780.SI" in df_ind["board_code"].to_list()


class TestStockDBExceptionsAndEmptyData:
    """测试异常拦截与空数据防御"""

    def test_service_disconnected_raises_connection_refused(self):
        """当本地 TCP 探针探测失败时，显式调用应立即 Fail-Fast 抛出 ConnectionRefusedError"""
        with patch("cq.data.provider.stockdb.provider.check_stockdb_connection", return_value=False), \
             patch("cq.data.provider.stockdb.provider.stockdb", MagicMock()):
            p = StockDBProvider()
            with pytest.raises(ConnectionRefusedError, match="无法连接至 StockDB 服务端"):
                p.fetch("ashare.kline.1d.raw.stockdb", "sh.600000", "2024-01-01", "2024-01-05")

    def test_empty_kline_returns_standard_schema(self, mock_stockdb_env):
        """无数据时返回标准的空 DataFrame，且包含完整的 schema"""
        mock_stockdb_env.daily_kline = []
        p = StockDBProvider()
        df = p.fetch("ashare.kline.1d.raw.stockdb", "sh.600000", "2024-01-01", "2024-01-05")
        assert df.is_empty()
        assert df.columns[:3] == ["symbol", "datetime", "timestamp"]
        assert df.schema["open"] == pl.Float64
        assert df.schema["turnover_rate"] == pl.Float64
        assert df.schema["total_mv"] == pl.Float64
