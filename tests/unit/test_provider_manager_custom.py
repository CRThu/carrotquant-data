"""
tests/unit/test_provider_manager_custom.py

自定义 Provider 注册与调度单元测试：
验证 ProviderManager.register_provider 的类和实例注册、缓存与异常分支。
"""

import pytest
import polars as pl
from cq.data.provider.base import BaseProvider
from cq.data.provider.provider_manager import ProviderManager
from cq.data.entrypoints.python_api import register_provider
from cq.data.service.sync_manager import sync
from cq.data.service.data_reader import read_events
from cq.data.config import settings



class MockCustomProvider(BaseProvider):
    """用于测试的自定义 Provider"""
    def __init__(self, api_key: str = "default_key"):
        self.api_key = api_key

    def fetch(self, table_id: str, symbol: str, start_time: int = None, end_time: int = None) -> pl.DataFrame:
        return pl.DataFrame({
            "symbol": [symbol],
            "timestamp": [1704067200000],
            "close": [99.9]
        })

    def get_all_symbols(self, table_id: str) -> list[str]:
        return ["custom.001", "custom.002"]

    def get_supported_tables(self) -> list[str]:
        return ["custom.kline.1d.my_source"]

    def get_table_category(self, table_id: str) -> str:
        return "timeseries"

    def get_sort_keys(self, table_id: str) -> list[str]:
        return ["timestamp", "symbol"]


def test_register_provider_class():
    """测试通过类注册自定义 Provider"""
    pm = ProviderManager()
    res = register_provider("my_source", MockCustomProvider)
    assert res is MockCustomProvider
    
    provider = pm.get_provider("custom.kline.1d.my_source", api_key="test_123")
    assert isinstance(provider, MockCustomProvider)
    assert provider.api_key == "test_123"
    assert provider.get_all_symbols("custom.kline.1d.my_source") == ["custom.001", "custom.002"]


def test_register_provider_decorator_positional():
    """测试通过位置参数类装饰器注册自定义 Provider"""
    pm = ProviderManager()

    @register_provider("decor_pos_source")
    class DecoratedPosProvider(BaseProvider):
        def fetch(self, table_id: str, symbol: str, start_time: int = None, end_time: int = None) -> pl.DataFrame:
            return pl.DataFrame({"symbol": [symbol], "timestamp": [1704067200000], "close": [10.5]})

        def get_all_symbols(self, table_id: str) -> list[str]:
            return ["decor.001"]

        def get_supported_tables(self) -> list[str]:
            return ["custom.kline.1d.decor_pos_source"]

        def get_table_category(self, table_id: str) -> str:
            return "timeseries"

        def get_sort_keys(self, table_id: str) -> list[str]:
            return ["timestamp"]

    # 验证装饰器返回原始类本身，类型与属性不丢失
    assert issubclass(DecoratedPosProvider, BaseProvider)
    
    provider = pm.get_provider("custom.kline.1d.decor_pos_source")
    assert isinstance(provider, DecoratedPosProvider)
    assert provider.get_all_symbols("custom.kline.1d.decor_pos_source") == ["decor.001"]


def test_register_provider_decorator_keyword():
    """测试通过关键字参数类装饰器注册自定义 Provider"""
    pm = ProviderManager()

    @register_provider(source="decor_kw_source")
    class DecoratedKwProvider(BaseProvider):
        def fetch(self, table_id: str, symbol: str, start_time: int = None, end_time: int = None) -> pl.DataFrame:
            return pl.DataFrame()

        def get_all_symbols(self, table_id: str) -> list[str]:
            return []

        def get_supported_tables(self) -> list[str]:
            return ["custom.kline.1d.decor_kw_source"]

        def get_table_category(self, table_id: str) -> str:
            return "timeseries"

        def get_sort_keys(self, table_id: str) -> list[str]:
            return ["timestamp"]

    assert issubclass(DecoratedKwProvider, BaseProvider)
    provider = pm.get_provider("custom.kline.1d.decor_kw_source")
    assert isinstance(provider, DecoratedKwProvider)


def test_register_provider_instance():
    """测试通过实例注册自定义 Provider"""
    pm = ProviderManager()
    instance = MockCustomProvider(api_key="instance_key")
    res = ProviderManager.register_provider("my_source_inst", instance)
    assert res is instance
    
    provider = pm.get_provider("custom.kline.1d.my_source_inst")
    assert provider is instance
    assert provider.api_key == "instance_key"


def test_register_provider_invalid():
    """测试非法注册参数抛出异常"""
    with pytest.raises(ValueError):
        ProviderManager.register_provider("", MockCustomProvider)
        
    with pytest.raises(ValueError):
        ProviderManager.register_provider(None, MockCustomProvider)

    # 装饰器模式下非法 source
    with pytest.raises(ValueError):
        @register_provider("")
        class BadProvider(BaseProvider):
            pass

    with pytest.raises(ValueError):
        @register_provider(None)
        class BadProvider2(BaseProvider):
            pass


class MockCustomEventProvider(BaseProvider):
    """自定义事件数据源驱动 (模拟单日包含多股票记录的龙虎榜事件表)"""
    def fetch(self, table_id: str, symbol: str, start_time: int = None, end_time: int = None) -> pl.DataFrame:
        return pl.DataFrame({
            "timestamp": [1704178800000, 1704178800000],
            "datetime": ["2024-01-02T15:00:00.000+08:00", "2024-01-02T15:00:00.000+08:00"],
            "symbol": ["sh.600000", "sz.000001"],
            "stock_name": ["浦发银行", "平安银行"],
            "buy_amount": [12000000.0, 9500000.0],
            "reason": ["涨幅偏离值达20%", "日换手率达20%"]
        })

    def get_all_symbols(self, table_id: str) -> list[str]:
        return ["_ALL_"]

    def get_supported_tables(self) -> list[str]:
        return ["custom.dragon_tiger.my_event_src"]

    def get_table_category(self, table_id: str) -> str:
        return "event"

    def get_sort_keys(self, table_id: str) -> list[str]:
        return ["timestamp", "symbol"]


def test_custom_event_provider_sync_and_read(tmp_path):
    """测试自定义事件 Provider 通过 sync() 调度流水线同步并完成切片查询"""
    orig_dir = settings.data_dir
    settings.data_dir = str(tmp_path)

    try:
        register_provider("my_event_src", MockCustomEventProvider)
        
        # 1. 触发同步
        sync(
            table_ids="custom.dragon_tiger.my_event_src",
            formats="parquet",
            force_refresh=True
        )
        
        # 2. 全量读取验证
        df = read_events("custom.dragon_tiger.my_event_src")
        assert df.height == 2
        assert set(df["symbol"].to_list()) == {"sh.600000", "sz.000001"}
        assert "buy_amount" in df.columns
        assert "reason" in df.columns
        
        # 3. 带 symbol 过滤读取验证
        df_single = read_events("custom.dragon_tiger.my_event_src", symbols=["sh.600000"])
        assert df_single.height == 1
        assert df_single["symbol"][0] == "sh.600000"
        assert df_single["buy_amount"][0] == 12000000.0
    finally:
        settings.data_dir = orig_dir

