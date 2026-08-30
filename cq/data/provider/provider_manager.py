from typing import Dict, Union, Type
from cq.data.provider.base import BaseProvider
from cq.data.provider.baostock_provider import BaostockProvider
from cq.data.provider.eastmoney_provider import EastMoneyProvider
from cq.data.provider.tdx_provider import TDXProvider
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
    def register_provider(cls, source: str, provider: Union[BaseProvider, Type[BaseProvider]]):
        """
        注册自定义数据源驱动
        
        Args:
            source: 数据源标识符 (如 'my_source' 或 table_id 末段)
            provider: BaseProvider 实例或子类
        """
        if not source or not isinstance(source, str):
            raise ValueError("source must be a non-empty string.")
        cls._custom_providers[source] = provider
        if source in cls._providers:
            del cls._providers[source]

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
            else:
                raise ValueError(f"Unsupported data source: {source}")
                
        return self._providers[source]

