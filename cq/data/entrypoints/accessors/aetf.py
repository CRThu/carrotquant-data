"""
cqdata/entrypoints/accessors/aetf.py

场内基金与 ETF 数据 OOP 访问类与命名空间实现。
遵循 a + 资产类别顶层市场规范，与 ashare 保持高度对称与物理隔离。
"""

from typing import List, Optional, Union
import polars as pl

from cq.data.entrypoints.accessors.base import _BaseTable, DefaultConfig
from cq.data.service.data_adjuster import DataAdjuster


class AETFKline(_BaseTable):
    """场内基金与 ETF K 线快捷访问类"""
    _PREFIX = "aetf.kline"
    _FALLBACK_SOURCE = "stockdb"
    _FACTOR_PREFIX = "aetf.adj_factor"
    _FACTOR_SOURCE = "stockdb"

    def get(
        self,
        freq: str = "1d",
        adj: str = "raw",
        symbols: Optional[Union[str, List[str]]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        columns: Optional[Union[str, List[str]]] = None,
        source: Optional[str] = None,
        format: Optional[str] = None
    ) -> pl.DataFrame:
        """
        读取场内基金与 ETF K 线数据。

        Args:
            freq: K 线频率，默认 '1d' (可选 '1d', '1m', '5m')
            adj: 复权方式，默认 'raw' (可选 'raw', 'adj')
            symbols: 代码或代码列表 (如 'sz.159919', 'sh.510300')
            start_date: 起始日期 ('YYYY-MM-DD')
            end_date: 结束日期 ('YYYY-MM-DD')
            columns: 选挑字段列表
            source: 指定 K 线数据源 (默认 'stockdb')
            format: K 线存储格式 ('parquet', 'csv', 'auto')

        Returns:
            pl.DataFrame
        """
        if adj not in ("raw", "adj"):
            raise ValueError(
                f"Unsupported adjustment mode '{adj}'. Only 'raw' and 'adj' are supported."
            )

        resolved_kline_source, resolved_kline_format = self._resolve_source_format(source, format)

        # 1. raw 模式：极速纯净直读原始行情
        if adj == "raw":
            table_id = f"{self._PREFIX}.{freq}.raw.{resolved_kline_source}"
            return self._read_table(
                table_id=table_id,
                symbols=symbols,
                start_date=start_date,
                end_date=end_date,
                columns=columns,
                format=resolved_kline_format
            )

        # 2. 复权模式 (adj)
        # 2.1 第一优先级：尝试直读已存在的静态 adj 表 (0 因子 IO，0 Join 开销)
        adj_table_id = f"{self._PREFIX}.{freq}.adj.{resolved_kline_source}"
        try:
            df_static = self._read_table(
                table_id=adj_table_id,
                symbols=symbols,
                start_date=start_date,
                end_date=end_date,
                columns=columns,
                format=resolved_kline_format
            )
            if not df_static.is_empty():
                return df_static
        except (ValueError, FileNotFoundError):
            # ValueError: 驱动不支持该静态表 (如 StockDB 仅提供 raw+factor)
            # FileNotFoundError: 驱动支持但本地未同步
            pass

        # 2.2 第二优先级（无静态表或未同步）：自动降级为 raw + factor 动态后复权折算
        raw_table_id = f"{self._PREFIX}.{freq}.raw.{resolved_kline_source}"
        df_kline = self._read_table(
            table_id=raw_table_id,
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            columns=None,
            format=resolved_kline_format
        )
        if df_kline.is_empty():
            return self._apply_columns(df_kline, columns)

        # 读取 ETF 独立复权因子表 (若未同步则直接抛出异常中断，严禁隐式静默假复权)
        factor_source = self._resolve_factor_source(
            kline_source=resolved_kline_source,
            factor_prefix=self._FACTOR_PREFIX,
            fallback_factor_source=self._FACTOR_SOURCE
        )
        factor_table_id = f"{self._FACTOR_PREFIX}.{factor_source}"
        df_factor = self._read_table(
            table_id=factor_table_id,
            symbols=symbols,
            start_date=None,
            end_date=end_date,
            columns=None,
            format=resolved_kline_format
        )

        # 执行动态向量化后复权计算 (针对次新 ETF 等无除权历史的标的，由 DataAdjuster 内部提供金融级 1.0 保底)
        df_adjusted = DataAdjuster.adjust(df_kline=df_kline, df_factor=df_factor)

        # 过滤用户指定的返回字段
        return self._apply_columns(df_adjusted, columns)


class AETFAdjFactor(_BaseTable):
    """场内基金与 ETF 独立复权因子快捷访问类"""
    _PREFIX = "aetf.adj_factor"
    _FALLBACK_SOURCE = "stockdb"

    def get(
        self,
        symbols: Optional[Union[str, List[str]]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        columns: Optional[Union[str, List[str]]] = None,
        source: Optional[str] = None,
        format: Optional[str] = None
    ) -> pl.DataFrame:
        resolved_source, resolved_format = self._resolve_source_format(source, format)
        table_id = f"{self._PREFIX}.{resolved_source}"
        return self._read_table(table_id, symbols, start_date, end_date, columns, resolved_format)


class AETF:
    """场内基金与 ETF 命名空间类"""

    def __init__(self, parent_default: DefaultConfig):
        self.default = DefaultConfig(parent=parent_default, fallback_source="stockdb")
        self.kline = AETFKline(parent_default=self.default)
        self.adj_factor = AETFAdjFactor(parent_default=self.default)

    @property
    def active_source(self) -> str:
        """返回当前 ETF 市场级最终生效的数据源"""
        return self.default.resolve_source()

    @property
    def source(self) -> str:
        """返回当前 ETF 市场级最终生效的数据源"""
        return self.active_source

    @source.setter
    def source(self, value: Optional[str]) -> None:
        """设置当前 ETF 市场级默认数据源覆盖值"""
        self.default.source = value

    @property
    def active_format(self) -> str:
        """返回当前 ETF 市场级最终生效的存储格式"""
        return self.default.resolve_format()

    @property
    def format(self) -> str:
        """返回当前 ETF 市场级最终生效的存储格式"""
        return self.active_format

    @format.setter
    def format(self, value: Optional[str]) -> None:
        """设置当前 ETF 市场级默认存储格式覆盖值"""
        self.default.format = value

    @property
    def supported_sources(self) -> List[str]:
        """返回当前场内基金与 ETF 市场支持的数据源列表"""
        sources = set()
        for tbl in (self.kline, self.adj_factor):
            sources.update(tbl.supported_sources)
        return sorted(list(sources))

    @property
    def supported_formats(self) -> List[str]:
        """返回当前 ETF 市场支持的物理存储格式"""
        return ["parquet", "csv"]

    def __repr__(self) -> str:
        return (
            f"<AETF active_source={self.active_source!r}, active_format={self.active_format!r}, "
            f"tables=['kline', 'adj_factor']>"
        )

