"""BaostockProvider 单元测试。

验证:
1. None 日期默认值处理（与 EastMoneyProvider 统一）
2. 支持的 table_id 路由
3. 空数据防御
"""

import pytest
import polars as pl
from unittest.mock import MagicMock
from cq.data.provider.baostock_provider import BaostockProvider


@pytest.fixture(autouse=True)
def _reset_provider_manager():
    """每个测试前后清理 ProviderManager singleton，防止泄漏。"""
    from cq.data.provider.provider_manager import ProviderManager
    ProviderManager._instance = None
    ProviderManager._providers = {}
    yield
    ProviderManager._instance = None
    ProviderManager._providers = {}


@pytest.fixture
def provider(mock_baostock):
    """创建 BaostockProvider 实例，使用 mock_baostock 避免网络调用。"""
    return BaostockProvider()


class TestNoneDateDefaults:
    """测试 None 日期默认值处理。"""

    def test_fetch_none_start_date_defaults_to_1970(self, provider, mock_baostock):
        """start_date=None 时应默认为 1970-01-01。"""
        provider.fetch("ashare.kline.1d.raw.baostock", "sh.600000", None, "2024-01-05")
        call_args = mock_baostock.query_history_k_data_plus.call_args
        assert call_args[1]["start_date"] == "1970-01-01"

    def test_fetch_none_end_date_defaults_to_today(self, provider, mock_baostock):
        """end_date=None 时应默认为今天日期。"""
        from datetime import datetime
        provider.fetch("ashare.kline.1d.raw.baostock", "sh.600000", "2024-01-01", None)
        call_args = mock_baostock.query_history_k_data_plus.call_args
        today = datetime.now().strftime("%Y-%m-%d")
        assert call_args[1]["end_date"] == today

    def test_fetch_both_none_dates(self, provider, mock_baostock):
        """start_date 和 end_date 均为 None 时，应使用默认值。"""
        from datetime import datetime
        provider.fetch("ashare.kline.1d.raw.baostock", "sh.600000", None, None)
        call_args = mock_baostock.query_history_k_data_plus.call_args
        assert call_args[1]["start_date"] == "1970-01-01"
        today = datetime.now().strftime("%Y-%m-%d")
        assert call_args[1]["end_date"] == today

    def test_fetch_int_timestamp_converted(self, provider, mock_baostock):
        """整数时间戳应被转换为日期字符串。"""
        # 2024-01-01 00:00:00 UTC+8 = 1704038400000 ms
        provider.fetch("ashare.kline.1d.raw.baostock", "sh.600000", 1704038400000, 1704124800000)
        call_args = mock_baostock.query_history_k_data_plus.call_args
        assert isinstance(call_args[1]["start_date"], str)
        assert isinstance(call_args[1]["end_date"], str)


class TestTableRouting:
    """测试 table_id 路由。"""

    def test_unsupported_table_raises(self, provider):
        """不支持的 table_id 应抛出 ValueError。"""
        with pytest.raises(ValueError, match="not supported"):
            provider.fetch("unsupported.table", "sh.600000", "2024-01-01", "2024-01-05")


class TestEmptyDataDefense:
    """测试空数据防御。"""

    def test_empty_kline_returns_standardized_empty(self, provider):
        """空 K 线数据应返回含标准列类型的空 DataFrame，时区已归一化。"""
        df = provider.fetch("ashare.kline.1d.raw.baostock", "sh.600000", "2024-01-01", "2024-01-05")
        assert df.is_empty()
        # 验证核心列类型
        assert df.schema["symbol"] == pl.String
        assert df.schema["datetime"] == pl.String
        assert df.schema["timestamp"] == pl.Int64
        # 验证列顺序：symbol, datetime, timestamp 在最前
        front_cols = df.columns[:3]
        assert front_cols == ["symbol", "datetime", "timestamp"]
        # 验证数值列类型（经过 cast 转换）
        assert df.schema["open"] == pl.Float64
        assert df.schema["close"] == pl.Float64
        assert df.schema["volume"] == pl.Float64
        assert df.schema["is_st"] == pl.Boolean

    def test_fetch_kline_is_st_boolean_conversion(self, provider, mock_baostock):
        """测试 is_st 字段从 Baostock 字符串 '1'/'0' 转换为布尔值 True/False。"""
        mock_rs = MagicMock()
        mock_rs.error_code = "0"
        mock_rs.next.side_effect = [True, True, False]
        mock_rs.get_row_data.side_effect = [
            ["2024-01-02", "sh.600000", "6.63", "6.65", "6.60", "6.60", "6.20", "22066700", "146066304", "3", "0.0752", "1", "-0.302", "5.0", "0.32", "2.3", "8.9", "1"],
            ["2024-01-03", "sh.600000", "6.60", "6.62", "6.58", "6.61", "6.60", "20000000", "130000000", "3", "0.0650", "1", "0.151", "5.0", "0.32", "2.3", "8.9", "0"],
        ]
        mock_baostock.query_history_k_data_plus.return_value = mock_rs

        df = provider.fetch("ashare.kline.1d.raw.baostock", "sh.600000", "2024-01-01", "2024-01-05")
        assert len(df) == 2
        assert df.schema["is_st"] == pl.Boolean
        assert df["is_st"].to_list() == [True, False]

    def test_empty_adj_factor_returns_standardized_empty(self, provider):
        """空复权因子数据应返回含标准列类型的空 DataFrame，时区已归一化。"""
        df = provider.fetch("ashare.adj_factor.baostock", "sh.600000", "2024-01-01", "2024-01-05")
        assert df.is_empty()
        # 验证核心列类型
        assert df.schema["symbol"] == pl.String
        assert df.schema["datetime"] == pl.String
        assert df.schema["timestamp"] == pl.Int64
        # 验证列顺序：symbol, datetime, timestamp 在最前
        front_cols = df.columns[:3]
        assert front_cols == ["symbol", "datetime", "timestamp"]
        # 验证数值列类型（经过 cast 转换）
        assert df.schema["back_adj_factor"] == pl.Float64


class TestErrorCodeRetryAndRelogin:
    """测试 error_code != '0' 时的自动 _relogin 重试与异常断言。"""

    def test_safe_bs_call_retries_on_error_code_and_relogins(self, provider, mock_baostock):
        """当 API 返回 error_code != '0' (如网络接收错误) 时，应自动调用 _relogin 重试并成功。"""
        from cq.data.provider.baostock_provider import BaostockCallError

        # 模拟第一个 rs 返回网络接收错误，第二个 rs 返回正常 error_code='0'
        mock_fail_rs = MagicMock()
        mock_fail_rs.error_code = "-1"
        mock_fail_rs.error_msg = "网络接收错误。"

        mock_ok_rs = MagicMock()
        mock_ok_rs.error_code = "0"
        mock_ok_rs.next.side_effect = [True, False]
        mock_ok_rs.get_row_data.return_value = ["sh.600000", "浦发银行", "1999-11-10", "", "1", "1"]

        mock_baostock.query_stock_basic.side_effect = [mock_fail_rs, mock_ok_rs]

        symbols = provider.get_all_symbols("ashare.kline.1d.raw.baostock")
        assert "sh.600000" in symbols

        # 验证重新登录被触发 (初始 1 次 + re-login 1 次 = 2 次)
        assert mock_baostock.login.call_count >= 2

    def test_safe_bs_call_raises_after_max_retries(self, provider, mock_baostock):
        """当持续返回 error_code != '0' 达到最大重试次数时，应抛出 BaostockCallError。"""
        from cq.data.provider.baostock_provider import BaostockCallError

        mock_fail_rs = MagicMock()
        mock_fail_rs.error_code = "-1"
        mock_fail_rs.error_msg = "网络接收错误。"

        mock_baostock.query_stock_basic.return_value = mock_fail_rs

        with pytest.raises(BaostockCallError, match="Baostock API Error"):
            provider.get_all_symbols("ashare.kline.1d.raw.baostock")

    def test_fetch_kline_recovers_from_transient_network_error(self, provider, mock_baostock):
        """测试 _fetch_kline 在遇到临时网络错误码时可成功恢复。"""
        mock_fail_rs = MagicMock()
        mock_fail_rs.error_code = "-1"
        mock_fail_rs.error_msg = "网络接收错误。"

        mock_ok_rs = MagicMock()
        mock_ok_rs.error_code = "0"
        mock_ok_rs.next.return_value = False

        mock_baostock.query_history_k_data_plus.side_effect = [mock_fail_rs, mock_ok_rs]

        df = provider.fetch("ashare.kline.1d.raw.baostock", "sh.600000", "2024-01-01", "2024-01-05")
        assert df.is_empty()
        assert mock_baostock.login.call_count >= 2

    def test_relogin_failure_raises_baostock_call_error_and_retries(self, provider, mock_baostock):
        """验证 _relogin 失败时抛出 BaostockCallError（而不是 RuntimeError），能被 tenacity 正确捕获并重试。"""
        from cq.data.provider.baostock_provider import BaostockCallError

        # 模拟每次调用 API 都返回网络接收错误
        mock_fail_rs = MagicMock()
        mock_fail_rs.error_code = "10002007"
        mock_fail_rs.error_msg = "网络接收错误。"
        mock_baostock.query_history_k_data_plus.return_value = mock_fail_rs

        # 模拟 login 也失败
        mock_login_fail = MagicMock()
        mock_login_fail.error_code = "10002007"
        mock_login_fail.error_msg = "网络接收错误。"
        mock_baostock.login.return_value = mock_login_fail

        # 应触发 tenacity 重试并最终抛出 BaostockCallError（而非短路为 RuntimeError）
        with pytest.raises(BaostockCallError, match="Baostock re-login failed"):
            provider.fetch("ashare.kline.1d.raw.baostock", "sh.600000", "2024-01-01", "2024-01-05")

        # 初始 1 次登录 + MAX_RETRIES (默认3次) 重重登录 = 4 次登录调用
        assert mock_baostock.login.call_count >= 3


class TestThreadSafety:
    """测试并发多线程调用的线程锁防护。"""

    def test_baostock_provider_thread_safety(self, provider, mock_baostock):
        """多线程并发调用 provider 应正常通过 RLock 互斥，不抛出异常。"""
        import concurrent.futures

        def _make_mock_rs():
            mock_rs = MagicMock()
            mock_rs.error_code = "0"
            mock_rs.next.side_effect = [True, False]
            mock_rs.get_row_data.return_value = ["sh.600000", "浦发银行", "1999-11-10", "", "1", "1"]
            return mock_rs

        mock_baostock.query_stock_basic.side_effect = _make_mock_rs

        def _worker(idx):
            return provider.get_all_symbols("aindex.kline.1d.raw.baostock")

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(_worker, i) for i in range(5)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        assert len(results) == 5
        for res in results:
            assert isinstance(res, list)


