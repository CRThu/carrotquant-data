"""TDXProvider 单元测试。

验证:
1. Provider 路由与 table_id 注册
2. get_all_symbols 返回正确结构
3. fetch 路由到正确的私有方法
4. 数据转换: polars + 标准列
5. 空数据防御
6. tdxpy reader 本地解析
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
import polars as pl

from cq.data.provider.tdx_provider import TDXProvider
from cq.data.provider.tdx_utils import (
    tdx_code_to_standard,
    standard_to_tdx_code,
    read_tdx_file_from_local,
    discover_tdx_symbols_from_local,
)
from cq.data.provider.provider_manager import ProviderManager

# 通达信默认安装路径
_VIPDOC_DIR = Path(r"C:\new_tdx\vipdoc")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_provider_manager():
    """每个测试前后清理 ProviderManager singleton，防止泄漏。"""
    ProviderManager._instance = None
    ProviderManager._providers = {}
    yield
    ProviderManager._instance = None
    ProviderManager._providers = {}


@pytest.fixture
def provider():
    """创建 TDXProvider 实例 (使用已下载的测试数据)。"""
    if not _VIPDOC_DIR.exists():
        pytest.skip("vipdoc 目录不存在，跳过测试")
    return TDXProvider(mode="local", vipdoc_dir=str(_VIPDOC_DIR))


def _skip_if_no_vipdoc():
    if not _VIPDOC_DIR.exists():
        pytest.skip("vipdoc 目录不存在，跳过测试")


# ---------------------------------------------------------------------------
# Provider 注册与路由
# ---------------------------------------------------------------------------

class TestProviderRegistration:
    """测试 ProviderManager 能正确路由到 TDXProvider。"""

    def test_provider_manager_routes_to_tdx(self):
        ProviderManager._instance = None
        ProviderManager._providers = {}
        pm = ProviderManager()
        p = pm.get_provider("ashare.kline.1d.raw.tdx")
        assert isinstance(p, TDXProvider)

    def test_supported_tables_complete(self, provider):
        tables = provider.get_supported_tables()
        expected = [
            "ashare.kline.1d.raw.tdx",
            "ashare.kline.5m.raw.tdx",
            "ashare.kline.1m.raw.tdx",
            "aindex.kline.1d.raw.tdx",
            "aindex.kline.5m.raw.tdx",
            "aindex.kline.1m.raw.tdx",
        ]
        assert set(tables) == set(expected)

    def test_unsupported_table_raises(self, provider):
        with pytest.raises(ValueError, match="not supported"):
            provider.get_table_category("ashare.kline.1d.baostock")

    def test_fetch_unsupported_table_raises(self, provider):
        with pytest.raises(ValueError, match="not supported"):
            provider.fetch("ashare.kline.1d.baostock", "sh.600000", "2024-01-01", "2024-12-31")


# ---------------------------------------------------------------------------
# get_table_category
# ---------------------------------------------------------------------------

class TestGetTableCategory:
    @pytest.mark.parametrize("table_id", [
        "ashare.kline.1d.raw.tdx",
        "ashare.kline.5m.raw.tdx",
        "ashare.kline.1m.raw.tdx",
        "aindex.kline.1d.raw.tdx",
        "aindex.kline.5m.raw.tdx",
        "aindex.kline.1m.raw.tdx",
    ])
    def test_all_tables_are_timeseries(self, provider, table_id):
        assert provider.get_table_category(table_id) == "timeseries"


# ---------------------------------------------------------------------------
# get_sort_keys
# ---------------------------------------------------------------------------

class TestGetSortKeys:
    def test_sort_keys_returns_timestamp(self, provider):
        assert provider.get_sort_keys("ashare.kline.1d.raw.tdx") == ["timestamp"]


# ---------------------------------------------------------------------------
# 代码格式转换
# ---------------------------------------------------------------------------

class TestTdxCodeConversion:
    @pytest.mark.parametrize("tdx_code,standard", [
        ("sh600000", "sh.600000"),
        ("sz000001", "sz.000001"),
        ("bj832000", "bj.832000"),
    ])
    def test_tdx_code_to_standard(self, tdx_code, standard):
        assert tdx_code_to_standard(tdx_code) == standard

    @pytest.mark.parametrize("standard,tdx_code", [
        ("sh.600000", "sh600000"),
        ("sz.000001", "sz000001"),
        ("bj.832000", "bj832000"),
    ])
    def test_standard_to_tdx_code(self, standard, tdx_code):
        assert standard_to_tdx_code(standard) == tdx_code


# ---------------------------------------------------------------------------
# tdxpy reader 本地解析
# ---------------------------------------------------------------------------

class TestTdxpyReader:
    """测试 tdxpy reader 解析本地 vipdoc 文件。"""

    def test_read_daily_file(self):
        _skip_if_no_vipdoc()
        records = read_tdx_file_from_local(_VIPDOC_DIR, "sh600000", freq="1d")
        assert len(records) > 0
        r = records[0]
        assert "date" in r
        assert "open" in r
        assert "high" in r
        assert "low" in r
        assert "close" in r
        assert "volume" in r
        assert "amount" in r

    def test_read_daily_file_date_format(self):
        _skip_if_no_vipdoc()
        records = read_tdx_file_from_local(_VIPDOC_DIR, "sh600000", freq="1d")
        assert len(records) > 0
        assert records[0]["date"] == "1999-11-10"

    def test_read_daily_file_values(self):
        _skip_if_no_vipdoc()
        records = read_tdx_file_from_local(_VIPDOC_DIR, "sh600000", freq="1d")
        assert len(records) > 0
        r = records[0]
        assert r["open"] == 29.50
        assert r["high"] == 29.80
        assert r["low"] == 27.00
        assert r["close"] == 27.75

    def test_read_minute_file(self):
        _skip_if_no_vipdoc()
        records = read_tdx_file_from_local(_VIPDOC_DIR, "sh600000", freq="1m")
        assert len(records) > 0
        r = records[0]
        assert "datetime" in r
        assert "date" in r
        assert "time" in r
        assert "open" in r
        assert "close" in r

    def test_read_minute_file_datetime_format(self):
        _skip_if_no_vipdoc()
        records = read_tdx_file_from_local(_VIPDOC_DIR, "sh600000", freq="1m")
        assert len(records) > 0
        assert records[0]["datetime"] == "2025-01-02 09:31:00"
        assert records[0]["date"] == "2025-01-02"
        assert records[0]["time"] == "09:31:00"

    def test_read_minute_file_values(self):
        _skip_if_no_vipdoc()
        records = read_tdx_file_from_local(_VIPDOC_DIR, "sh600000", freq="1m")
        assert len(records) > 0
        r = records[0]
        assert r["open"] == 10.30
        assert r["high"] == 10.42
        assert r["low"] == 10.29
        assert r["close"] == 10.38

    def test_read_nonexistent_file_returns_empty(self):
        _skip_if_no_vipdoc()
        records = read_tdx_file_from_local(_VIPDOC_DIR, "sh999999", freq="5m")
        assert records == []

    def test_read_unsupported_freq_raises(self):
        _skip_if_no_vipdoc()
        with pytest.raises(ValueError, match="不支持的频率"):
            read_tdx_file_from_local(_VIPDOC_DIR, "sh600000", freq="2m")


class TestDiscoverSymbolsLocal:
    """测试从本地 vipdoc 发现证券代码。"""

    def test_discover_all_symbols(self):
        _skip_if_no_vipdoc()
        symbols = discover_tdx_symbols_from_local(_VIPDOC_DIR)
        assert len(symbols) > 0
        assert all(len(s) >= 4 for s in symbols)

    def test_discover_sh_symbols(self):
        _skip_if_no_vipdoc()
        symbols = discover_tdx_symbols_from_local(_VIPDOC_DIR, market="sh")
        assert len(symbols) > 0
        assert all(s.startswith("sh") for s in symbols)


# ---------------------------------------------------------------------------
# fetch 数据验证
# ---------------------------------------------------------------------------

class TestFetchData:
    def test_fetch_daily_returns_polars(self, provider):
        df = provider.fetch("ashare.kline.1d.raw.tdx", "sh.600000", "2024-01-01", "2024-01-10")
        assert isinstance(df, pl.DataFrame)

    def test_fetch_daily_has_standard_columns(self, provider):
        df = provider.fetch("ashare.kline.1d.raw.tdx", "sh.600000", "2024-01-01", "2024-01-10")
        for col in ["symbol", "datetime", "timestamp", "open", "high", "low", "close", "volume", "amount"]:
            assert col in df.columns

    def test_fetch_daily_column_types(self, provider):
        df = provider.fetch("ashare.kline.1d.raw.tdx", "sh.600000", "2024-01-01", "2024-01-10")
        assert df.schema["symbol"] == pl.String
        assert df.schema["datetime"] == pl.String
        assert df.schema["timestamp"] == pl.Int64
        assert df.schema["open"] == pl.Float64
        assert df.schema["close"] == pl.Float64

    def test_fetch_daily_symbol_column(self, provider):
        df = provider.fetch("ashare.kline.1d.raw.tdx", "sh.600000", "2024-01-01", "2024-01-10")
        if not df.is_empty():
            assert (df["symbol"] == "sh.600000").all()

    def test_fetch_index_daily(self, provider):
        df = provider.fetch("aindex.kline.1d.raw.tdx", "sh.000001", "2024-01-01", "2024-01-10")
        assert isinstance(df, pl.DataFrame)
        if not df.is_empty():
            assert (df["symbol"] == "sh.000001").all()

    def test_fetch_empty_date_range(self, provider):
        df = provider.fetch("ashare.kline.1d.raw.tdx", "sh.600000", "2000-01-01", "2000-01-01")
        assert df.is_empty()
        assert list(df.columns) == ["symbol", "datetime", "timestamp", "open", "high", "low", "close", "volume", "amount"]

    def test_fetch_none_dates_use_defaults(self, provider):
        df = provider.fetch("ashare.kline.1d.raw.tdx", "sh.600000", None, None)
        assert isinstance(df, pl.DataFrame)

    def test_fetch_int_timestamp_converted(self, provider):
        df = provider.fetch("ashare.kline.1d.raw.tdx", "sh.600000", 1704038400000, 1704211200000)
        assert isinstance(df, pl.DataFrame)


# ---------------------------------------------------------------------------
# _safe_tcp_call 异常处理与 None 拦截测试
# ---------------------------------------------------------------------------

class TestSafeTcpCall:
    """测试 _safe_tcp_call 的网络故障拦截与异常重试逻辑。"""

    def test_safe_tcp_call_success(self):
        from cq.data.provider.tdx_utils import _safe_tcp_call
        mock_fn = MagicMock(return_value=[{"date": "2024-01-01"}])
        res = _safe_tcp_call(mock_fn)
        assert res == [{"date": "2024-01-01"}]

    def test_safe_tcp_call_empty_list_allowed(self):
        from cq.data.provider.tdx_utils import _safe_tcp_call
        mock_fn = MagicMock(return_value=[])
        res = _safe_tcp_call(mock_fn)
        assert res == []

    def test_safe_tcp_call_none_reconnects_and_raises(self):
        import cq.data.provider.tdx_utils as tdx_utils
        mock_api = MagicMock()
        mock_api.client = None  # 模拟 Socket 断线状态
        tdx_utils._cached_api = mock_api
        mock_fn = MagicMock(return_value=None)

        def _mock_reconnect_side_effect():
            tdx_utils._cached_api = mock_api
            mock_api.client = None
            return mock_api

        with patch("cq.data.provider.tdx_utils._reconnect_tdx_api", side_effect=_mock_reconnect_side_effect) as mock_reconnect, \
             patch("cq.data.provider.tdx_utils._connect_tdx_api", side_effect=_mock_reconnect_side_effect):
            with pytest.raises(Exception):
                tdx_utils._safe_tcp_call(mock_fn)
            assert mock_reconnect.called

    def test_safe_tcp_call_reraises_runtime_error_on_disconnect(self):
        from cq.data.provider.tdx_utils import _safe_tcp_call
        mock_fn = MagicMock(side_effect=RuntimeError("TDX 服务器全部不可用，请检查网络"))
        with pytest.raises(RuntimeError, match="检查网络"):
            _safe_tcp_call(mock_fn)

    def test_safe_tcp_call_cached_api_none_reconnects_properly(self):
        import cq.data.provider.tdx_utils as tdx_utils
        tdx_utils._cached_api = None
        mock_api = MagicMock()
        mock_api.get_security_bars.return_value = [{"date": "2024-01-01"}]

        def _mock_connect():
            tdx_utils._cached_api = mock_api
            return mock_api

        with patch("cq.data.provider.tdx_utils._connect_tdx_api", side_effect=_mock_connect) as mock_connect:
            fn = lambda: tdx_utils._cached_api.get_security_bars(0, 0, "600000", 0, 10)
            res = tdx_utils._safe_tcp_call(fn)
            assert mock_connect.called
            assert res == [{"date": "2024-01-01"}]


# ---------------------------------------------------------------------------
# TDX Provider kwargs 与 Local 模式探针测试
# ---------------------------------------------------------------------------

class TestTDXProviderKwargs:
    """测试 ProviderManager 正确传递 provider_kwargs 并实例化 TDXProvider。"""

    def test_provider_manager_passes_kwargs_to_tdx(self):
        pm = ProviderManager()
        provider = pm.get_provider("ashare.kline.1d.raw.tdx", mode="local", vipdoc_dir="C:/custom_test_path")
        assert isinstance(provider, TDXProvider)
        assert provider._mode == "local"
        assert str(provider._vipdoc_dir).replace("\\", "/") == "C:/custom_test_path"


class TestTDXLocalModeMock:
    """测试 TDX Local 模式下的探针与数据解析。"""

    def test_local_fetch_empty_dir_returns_empty_kline(self, tmp_path):
        provider = TDXProvider(mode="local", vipdoc_dir=str(tmp_path))
        df = provider.fetch("ashare.kline.1d.raw.tdx", "sh.600000", "2024-01-01", "2024-01-10")
        assert isinstance(df, pl.DataFrame)
        assert df.is_empty()
        assert list(df.columns) == ["symbol", "datetime", "timestamp", "open", "high", "low", "close", "volume", "amount"]


# ---------------------------------------------------------------------------
# 个股与指数代码隔离防线测试
# ---------------------------------------------------------------------------

class TestTdxSymbolFilter:
    """测试 ashare 和 aindex 的证券代码隔离与边界防御。"""

    def test_ashare_contains_only_stocks_and_no_indices(self, provider):
        with patch("cq.data.provider.tdx_provider.fetch_stock_list_online") as mock_fetch:
            mock_fetch.side_effect = lambda market: {
                "sh": ["sh600000", "sh688001", "sh000001", "sh000300"],
                "sz": ["sz000001", "sz300750", "sz395001", "sz399001"],
                "bj": ["bj832000", "bj920001", "bj899050"],
            }[market]

            symbols = provider._get_all_symbols_online("ashare")
            # 应该只包含个股
            assert set(symbols) == {"sh.600000", "sh.688001", "sz.000001", "sz.300750", "bj.832000", "bj.920001"}
            # 严格不能包含指数
            assert "sz.395001" not in symbols
            assert "sz.399001" not in symbols
            assert "sh.000001" not in symbols
            assert "bj.899050" not in symbols

    def test_aindex_contains_only_indices_including_bj899050(self, provider):
        with patch("cq.data.provider.tdx_provider.fetch_stock_list_online") as mock_fetch:
            mock_fetch.side_effect = lambda market: {
                "sh": ["sh600000", "sh000001", "sh000300"],
                "sz": ["sz000001", "sz395001", "sz399001"],
                "bj": ["bj832000", "bj899050"],
            }[market]

            symbols = provider._get_all_symbols_online("aindex")
            # 应该包含 SH 00 / SZ 39 / BJ 89
            assert set(symbols) == {"sh.000001", "sh.000300", "sz.395001", "sz.399001", "bj.899050"}
            # 严格不能包含个股
            assert "sh.600000" not in symbols
            assert "sz.000001" not in symbols
            assert "bj.832000" not in symbols

    def test_unsupported_prefix_raises(self, provider):
        with pytest.raises(ValueError, match="Unsupported Universe prefix"):
            provider._get_all_symbols_online("hk")

        with pytest.raises(ValueError, match="Unsupported Universe prefix"):
            provider._get_all_symbols_local("us")

    def test_bj_symbols_baostock_fallback_success(self, provider):
        """当 TDX 不提供 BJ 列表时，自动退避至 BaostockProvider 基础库拉取。"""
        mock_bp = MagicMock()
        mock_bp.get_all_symbols.return_value = ["sh.600000", "sz.000001", "bj.832000", "bj.920001"]
        with patch("cq.data.provider.tdx_provider.fetch_stock_list_online") as mock_tdx_fetch, \
             patch("cq.data.provider.baostock_provider.BaostockProvider", return_value=mock_bp):
            mock_tdx_fetch.side_effect = lambda market: {
                "sh": ["sh600000"],
                "sz": ["sz000001"],
                "bj": [],
            }[market]

            symbols = provider._get_all_symbols_online("ashare")
            assert "bj.832000" in symbols
            assert "bj.920001" in symbols
            assert mock_bp.get_all_symbols.called

    def test_bj_symbols_fallback_warning_on_exception(self, provider):
        """当拉取 BJ 列表抛出异常时，抓取逻辑捕获异常、日志 Warning 告警，并放弃 BJ 保证 SH/SZ 顺畅。"""
        with patch("cq.data.provider.tdx_provider.fetch_stock_list_online") as mock_tdx_fetch, \
             patch("cq.data.provider.baostock_provider.BaostockProvider", side_effect=RuntimeError("Baostock down")):
            mock_tdx_fetch.side_effect = lambda market: {
                "sh": ["sh600000"],
                "sz": ["sz000001"],
                "bj": [],
            }[market]

            symbols = provider._get_all_symbols_online("ashare")
            # 应该包含 SH 和 SZ 代码，优雅跳过 BJ
            assert symbols == ["sh.600000", "sz.000001"]

    def test_b_share_symbols_filtered_out_for_ashare(self, provider):
        """验证 ashare 表严格过滤剔除 B 股代码 (sh.900xxx / sz.200xxx)，纯粹代表 A 股个股。"""
        with patch("cq.data.provider.tdx_provider.fetch_stock_list_online") as mock_tdx_fetch:
            mock_tdx_fetch.side_effect = lambda market: {
                "sh": ["sh600000", "sh900901"],
                "sz": ["sz000001", "sz200012"],
                "bj": ["bj832000"],
            }[market]

            symbols = provider._get_all_symbols_online("ashare")
            assert "sh.900901" not in symbols
            assert "sz.200012" not in symbols
            assert symbols == ["bj.832000", "sh.600000", "sz.000001"]

    def test_patch_tdxpy_market2_support(self):
        """验证 tdxpy 的 market=2 (BJ) 补丁机制正常运行，不破坏 SH/SZ，支持 BJ 代码类型转换。"""
        from cq.data.provider.tdx_utils import _patch_tdxpy_once
        import tdxpy.helper as h
        import tdxpy.constants as c

        _patch_tdxpy_once()
        assert "BJ_A_STOCK" in c.SECURITY_COEFFICIENT
        assert "BJ_INDEX" in c.SECURITY_COEFFICIENT
        # 验证 BJ 分支
        assert h.get_security_type(2, "920002") == "BJ_A_STOCK"
        assert h.get_security_type(2, "899050") == "BJ_INDEX"
        # 验证 SH/SZ 保持透传原封不动
        assert h.get_security_type(1, "600000") == "SH_A_STOCK"
        assert h.get_security_type(0, "000001") == "SZ_A_STOCK"


# ---------------------------------------------------------------------------
# 脏数据过滤与 Float Overflow 溢出防护测试
# ---------------------------------------------------------------------------

class TestTdxDataSanitization:
    """测试通达信接口错位二进制脏记录与溢出防护的 Fail-Fast 阻断机制。"""

    def test_corrupted_datetime_raises_fail_fast(self):
        from cq.data.provider.tdx_utils import fetch_bars_online
        corrupted_data = [
            {"open": 10.0, "high": 10.5, "low": 9.8, "close": 10.2, "vol": 1000, "amount": 10000, "datetime": "2024-01-02 15:00", "year": 2024},
            {"open": -228.95, "high": 82523.5, "low": -228.95, "close": -228.9, "vol": 6.26e85, "amount": 5.87e-39, "datetime": "125102-38-16 15:00", "year": 125102},
        ]
        mock_api = MagicMock()
        mock_api.get_security_bars.return_value = corrupted_data
        with patch("cq.data.provider.tdx_utils._cached_api", mock_api), \
             patch("cq.data.provider.tdx_utils._connect_tdx_api", return_value=mock_api):
            with pytest.raises(ValueError, match="收到损坏的数据记录"):
                fetch_bars_online("sh.600000", freq="1d", table_id="ashare.kline.1d.raw.tdx")

    def test_float_overflow_amount_raises_fail_fast(self):
        from cq.data.provider.tdx_utils import fetch_bars_online
        overflow_data = [
            {"open": 10.0, "high": 10.5, "low": 9.8, "close": 10.2, "vol": 1000, "amount": 2.6678137566601576e+41, "datetime": "2024-01-02 15:00", "year": 2024},
        ]
        mock_api = MagicMock()
        mock_api.get_security_bars.return_value = overflow_data
        with patch("cq.data.provider.tdx_utils._cached_api", mock_api), \
             patch("cq.data.provider.tdx_utils._connect_tdx_api", return_value=mock_api):
            with pytest.raises(ValueError, match="收到超范围异常数值"):
                fetch_bars_online("sh.600000", freq="1d", table_id="ashare.kline.1d.raw.tdx")

    def test_empty_batch_returns_empty_kline(self):
        from cq.data.provider.tdx_utils import fetch_bars_online
        mock_api = MagicMock()
        mock_api.get_security_bars.return_value = []
        with patch("cq.data.provider.tdx_utils._cached_api", mock_api), \
             patch("cq.data.provider.tdx_utils._connect_tdx_api", return_value=mock_api):
            df = fetch_bars_online("sh.600000", freq="1d", table_id="ashare.kline.1d.raw.tdx")
            assert df.is_empty()
            assert df.schema["volume"] == pl.Float64


# ---------------------------------------------------------------------------
# 在线指数拉取路由与北交所指数测试
# ---------------------------------------------------------------------------

class TestTdxFetchIndexBars:
    """测试深交所指数 (sz.395001) 与北交所指数 (bj.899050) 的路由与解析。"""

    def test_fetch_sz_index_395001_routes_to_index_api(self):
        from cq.data.provider.tdx_utils import fetch_bars_online
        mock_data = [
            {"open": 522.0, "high": 522.0, "low": 522.0, "close": 522.0, "vol": 5000, "amount": 30000, "datetime": "2005-02-01 15:00", "year": 2005},
        ]
        mock_api = MagicMock()
        mock_api.get_index_bars.return_value = mock_data
        with patch("cq.data.provider.tdx_utils._cached_api", mock_api), \
             patch("cq.data.provider.tdx_utils._connect_tdx_api", return_value=mock_api):
            df = fetch_bars_online("sz.395001", freq="1d", table_id="aindex.kline.1d.raw.tdx")
            assert mock_api.get_index_bars.called
            assert not mock_api.get_security_bars.called
            assert len(df) == 1
            assert df["symbol"][0] == "sz.395001"

    def test_fetch_bj_index_899050_routes_to_index_api(self):
        from cq.data.provider.tdx_utils import fetch_bars_online
        mock_data = [
            {"open": 1000.0, "high": 1050.0, "low": 990.0, "close": 1020.0, "vol": 8000, "amount": 50000, "datetime": "2024-01-02 15:00", "year": 2024},
        ]
        mock_api = MagicMock()
        mock_api.get_index_bars.return_value = mock_data
        with patch("cq.data.provider.tdx_utils._cached_api", mock_api), \
             patch("cq.data.provider.tdx_utils._connect_tdx_api", return_value=mock_api):
            df = fetch_bars_online("bj.899050", freq="1d", table_id="aindex.kline.1d.raw.tdx")
            assert mock_api.get_index_bars.called
            assert len(df) == 1
            assert df["symbol"][0] == "bj.899050"

    def test_fetch_sz_stock_000001_routes_to_sz_market_0(self):
        from cq.data.provider.tdx_utils import fetch_bars_online
        mock_data = [
            {"open": 12.0, "high": 12.5, "low": 11.8, "close": 12.2, "vol": 50000, "amount": 600000, "datetime": "2024-01-02 15:00", "year": 2024},
        ]
        mock_api = MagicMock()
        mock_api.get_security_bars.return_value = mock_data
        with patch("cq.data.provider.tdx_utils._cached_api", mock_api), \
             patch("cq.data.provider.tdx_utils._connect_tdx_api", return_value=mock_api):
            df = fetch_bars_online("sz.000001", freq="1d", table_id="ashare.kline.1d.raw.tdx")
            # 必须调用 get_security_bars 且传入 market=0 (深交所)
            mock_api.get_security_bars.assert_called_with(4, 0, "000001", 0, 800)
            assert len(df) == 1
            assert df["symbol"][0] == "sz.000001"


# ---------------------------------------------------------------------------
# TestTdxDownloader
# ---------------------------------------------------------------------------

class TestTdxDownloader:
    """测试通达信全量日线包下载器 (tdx_downloader.py)"""

    def test_verify_vipdoc_empty(self, tmp_path):
        from cq.data.provider.tdx_downloader import verify_vipdoc
        assert verify_vipdoc(tmp_path) is False

    def test_verify_vipdoc_with_files(self, tmp_path):
        from cq.data.provider.tdx_downloader import verify_vipdoc
        sh_dir = tmp_path / "sh" / "lday"
        sh_dir.mkdir(parents=True)
        (sh_dir / "sh600000.day").write_bytes(b"dummy")

        sz_dir = tmp_path / "sz" / "lday"
        sz_dir.mkdir(parents=True)
        (sz_dir / "sz000001.day").write_bytes(b"dummy")

        assert verify_vipdoc(tmp_path) is True

    @patch("cq.data.provider.tdx_downloader.urlretrieve")
    def test_download_and_extract(self, mock_urlretrieve, tmp_path):
        import zipfile
        import io
        from cq.data.provider.tdx_downloader import download_and_extract

        # 模拟生成一个真实的测试 zip 内存数据并写入 tempfile
        def fake_urlretrieve(url, zip_target, reporthook=None):
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as zf:
                zf.writestr("sh/lday/sh600000.day", b"test content")
                zf.writestr("sz/lday/sz000001.day", b"test content")
                zf.writestr("other/file.txt", b"skip")
            Path(zip_target).write_bytes(buf.getvalue())
            if reporthook:
                reporthook(1, 1024, 1024)

        mock_urlretrieve.side_effect = fake_urlretrieve

        out_dir = tmp_path / "vipdoc_out"
        download_and_extract(out_dir, task_id="test.download")

        assert (out_dir / "sh" / "lday" / "sh600000.day").exists()
        assert (out_dir / "sz" / "lday" / "sz000001.day").exists()
        assert not (out_dir / "other" / "file.txt").exists()

    def test_verify_vipdoc_with_bj_files(self, tmp_path):
        from cq.data.provider.tdx_downloader import verify_vipdoc
        bj_dir = tmp_path / "bj" / "lday"
        bj_dir.mkdir(parents=True)
        (bj_dir / "bj832000.day").write_bytes(b"dummy")
        assert verify_vipdoc(tmp_path) is True

    @patch("cq.data.provider.tdx_downloader.urlretrieve")
    def test_download_and_extract_failure(self, mock_urlretrieve, tmp_path):
        from cq.data.provider.tdx_downloader import download_and_extract
        mock_urlretrieve.side_effect = ConnectionError("Network download failed")

        with pytest.raises(ConnectionError, match="Network download failed"):
            download_and_extract(tmp_path / "fail_out", task_id="test.download.fail")

    @patch("cq.data.provider.tdx_downloader.urlretrieve")
    def test_download_reporthook_unknown_size(self, mock_urlretrieve, tmp_path):
        import zipfile
        import io
        from cq.data.provider.tdx_downloader import download_and_extract

        def fake_urlretrieve_zero_size(url, zip_target, reporthook=None):
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as zf:
                zf.writestr("sh/lday/sh600000.day", b"dummy")
            Path(zip_target).write_bytes(buf.getvalue())
            if reporthook:
                reporthook(1, 1024, 0)  # total_size = 0 (未知大小)

        mock_urlretrieve.side_effect = fake_urlretrieve_zero_size
        out_dir = tmp_path / "zero_size_out"
        download_and_extract(out_dir, task_id="test.download.zero_size")
        assert (out_dir / "sh" / "lday" / "sh600000.day").exists()





