from typing import Dict, Union, Type, Optional, Callable, Any
from cq.data.provider.base import BaseProvider
from cq.data.provider.baostock_provider import BaostockProvider
from cq.data.provider.eastmoney_provider import EastMoneyProvider
from cq.data.provider.tdx_provider import TDXProvider
from cq.data.provider.stockdb import StockDBProvider
from cq.data.config.settings import settings


class ProviderManager:
    """
    驱动管理器，负责驱动的实例化、注册与缓存
    """
    
    _instance = None
    _providers: Dict[str, BaseProvider] = {}
    _custom_providers: Dict[str, Union[BaseProvider, Type[BaseProvider]]] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ProviderManager, cls).__new__(cls)
        return cls._instance

    @classmethod
    def register_provider(
        cls, 
        source: str, 
        provider: Optional[Union[BaseProvider, Type[BaseProvider]]] = None
    ) -> Union[Any, Callable]:
        """
        注册自定义数据源驱动 (支持普通调用与类装饰器两种模式)
        
        Args:
            source: 数据源标识符 (如 'my_source' 或 table_id 末段)
            provider: BaseProvider 实例或子类 (若为 None 则返回类装饰器)

        Returns:
            注册的 Provider (普通调用模式) 或 装饰器闭包函数 (装饰器模式)
        """
        if not source or not isinstance(source, str):
            raise ValueError("source must be a non-empty string.")

        if provider is None:
            def decorator(provider_cls: Union[BaseProvider, Type[BaseProvider]]):
                cls._custom_providers[source] = provider_cls
                if source in cls._providers:
                    del cls._providers[source]
                return provider_cls
            return decorator

        cls._custom_providers[source] = provider
        if source in cls._providers:
            del cls._providers[source]
        return provider

    def get_provider(self, table_id: str, **kwargs) -> BaseProvider:
        """
        根据 table_id 获取对应的 Provider

        table_id 格式: {market}.{category}.{freq}.{adj}.{source}
        例如: ashare.kline.1d.adj.baostock

        kwargs: 传递给 Provider 构造函数的额外参数 (如 TDXProvider 的 mode, vipdoc_dir)
        """
        source = table_id.split('.')[-1]
        
        if source in self._custom_providers:
            custom = self._custom_providers[source]
            if isinstance(custom, type):
                self._providers[source] = custom(**kwargs)
            else:
                self._providers[source] = custom
            return self._providers[source]

        if source not in self._providers:
            if source == 'baostock':
                self._providers[source] = BaostockProvider()
            elif source == 'eastmoney':
                self._providers[source] = EastMoneyProvider()
            elif source == 'tdx':
                self._providers[source] = TDXProvider(**kwargs)
            elif source == 'stockdb':
                self._providers[source] = StockDBProvider(**kwargs)
            else:
                raise ValueError(f"Unsupported data source: {source}")
                
        return self._providers[source]

    @classmethod
    def get_all_sources(cls) -> list[str]:
        """获取所有内置及自定义已注册的数据源标识符列表"""
        builtin = ["baostock", "eastmoney", "tdx", "stockdb"]
        custom = list(cls._custom_providers.keys())
        seen = set()
        result = []
        for s in builtin + custom:
            if s not in seen:
                seen.add(s)
                result.append(s)
        return result

    def get_sources_for_prefix(self, prefix: str) -> list[str]:
        """根据表 ID 前缀 (如 'ashare.kline') 探查所有支持该类数据的数据源标识符"""
        matching_sources = []
        for src in self.get_all_sources():
            try:
                prov = self._providers.get(src)
                if prov is None:
                    prov = self.get_provider(f"probe.{src}")
                tables = prov.get_supported_tables()
                if any(t.startswith(prefix + ".") or t == prefix for t in tables):
                    matching_sources.append(src)
            except Exception:
                continue
        return sorted(matching_sources)

