"""
cqdata/entrypoints/accessors/ashare.py

A 股个股数据 OOP 访问类与命名空间实现。
"""

from typing import List, Optional, Union
import polars as pl

from cq.data.entrypoints.accessors.base import _BaseTable
from cq.data.service.data_adjuster import DataAdjuster


class AShareKline(_BaseTable):
    """A 股个股 K 线快捷访问类"""
    _PREFIX = "ashare.kline"
    _FALLBACK_SOURCE = "baostock"
    _FACTOR_PREFIX = "ashare.adj_factor"
    _FACTOR_SOURCE = "baostock"

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
        读取 A 股个股 K 线数据。

        Args:
            freq: K 线频率，默认 '1d' (可选 '1d', '5m', '1m')
            adj: 复权方式，默认 'raw' (可选 'raw', 'adj')
            symbols: 代码或代码列表 (如 'sh.600000')
            start_date: 起始日期 ('YYYY-MM-DD')
            end_date: 结束日期 ('YYYY-MM-DD')
            columns: 选挑字段列表
            source: 指定 K 线数据源 ('baostock', 'tdx' 等)
            format: K 线存储格式 ('parquet', 'csv', 'auto')

        Returns:
            pl.DataFrame
        """
        if adj not in ("raw", "adj"):
            raise ValueError(
                f"Unsupported adjustment mode '{adj}'. Only 'raw' and 'adj' are supported."
            )

        resolved_kline_source, resolved_kline_format = self._resolve_source_format(source, format)

        # 1. raw 模式：极速纯净直读原始行情 (零因子 IO，零 Join 开销)
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
            # ValueError: 驱动不支持该静态表 (如 TDX/StockDB)
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

        # 读取复权因子表 (不加 start_date 截断，仅限制 <= end_date 以向前追溯历史因子)
        # 若因子表本地未同步，直接抛出异常中断，严禁隐式静默假复权
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

        # 执行动态向量化后复权计算 (针对次新股等无除权历史的标的，由 DataAdjuster 内部提供金融级 1.0 保底)
        df_adjusted = DataAdjuster.adjust(df_kline=df_kline, df_factor=df_factor)

        # 过滤用户指定的返回字段
        return self._apply_columns(df_adjusted, columns)


class AShareAdjFactor(_BaseTable):
    """A 股复权因子快捷访问类"""
    _PREFIX = "ashare.adj_factor"
    _FALLBACK_SOURCE = "baostock"

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


class AShareConcept(_BaseTable):
    """A 股概念板块成分股快捷访问类"""
    _PREFIX = "ashare.concept"
    _FALLBACK_SOURCE = "eastmoney"

    def get(
        self,
        symbols: Optional[Union[str, List[str]]] = None,
        board_code: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        columns: Optional[Union[str, List[str]]] = None,
        source: Optional[str] = None,
        format: Optional[str] = None
    ) -> pl.DataFrame:
        """
        读取 A 股概念板块成分股数据。

        Args:
            symbols: 股票代码或代码列表 (例如 'sh.600000')
            board_code: 板块代码 (例如 'BK0612')，用于精确定向过滤该板块成分股
            start_date: 起始日期 ('YYYY-MM-DD')
            end_date: 结束日期 ('YYYY-MM-DD')
            columns: 选挑字段列表
            source: 指定数据源 ('eastmoney', 'stockdb' 等)
            format: 存储格式 ('parquet', 'csv', 'auto')

        Returns:
            pl.DataFrame
        """
        resolved_source, resolved_format = self._resolve_source_format(source, format)
        table_id = f"{self._PREFIX}.{resolved_source}"
        df = self._read_table(table_id, symbols, start_date, end_date, columns, resolved_format)
        if board_code and "board_code" in df.columns:
            df = df.filter(pl.col("board_code") == board_code.strip())
        return df


class AShareIndustry(_BaseTable):
    """A 股行业板块成分股快捷访问类"""
    _PREFIX = "ashare.industry"
    _FALLBACK_SOURCE = "eastmoney"

    def get(
        self,
        symbols: Optional[Union[str, List[str]]] = None,
        board_code: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        columns: Optional[Union[str, List[str]]] = None,
        source: Optional[str] = None,
        format: Optional[str] = None
    ) -> pl.DataFrame:
        """
        读取 A 股行业板块成分股数据。

        Args:
            symbols: 股票代码或代码列表 (例如 'sh.600000')
            board_code: 板块代码 (例如 'BK0475')，用于精确定向过滤该板块成分股
            start_date: 起始日期 ('YYYY-MM-DD')
            end_date: 结束日期 ('YYYY-MM-DD')
            columns: 选挑字段列表
            source: 指定数据源 ('eastmoney', 'stockdb' 等)
            format: 存储格式 ('parquet', 'csv', 'auto')

        Returns:
            pl.DataFrame
        """
        resolved_source, resolved_format = self._resolve_source_format(source, format)
        table_id = f"{self._PREFIX}.{resolved_source}"
        df = self._read_table(table_id, symbols, start_date, end_date, columns, resolved_format)
        if board_code and "board_code" in df.columns:
            df = df.filter(pl.col("board_code") == board_code.strip())
        return df


class AShareDragonTiger(_BaseTable):
    """A 股龙虎榜快捷访问类"""
    _PREFIX = "ashare.dragon_tiger"
    _FALLBACK_SOURCE = "eastmoney"

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


class AShareInstTrade(_BaseTable):
    """A 股机构交易每日统计快捷访问类"""
    _PREFIX = "ashare.inst_trade"
    _FALLBACK_SOURCE = "eastmoney"

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


class AShare:
    """A 股数据命名空间类"""

    def __init__(self):
        self.kline = AShareKline()
        self.adj_factor = AShareAdjFactor()
        self.concept = AShareConcept()
        self.industry = AShareIndustry()
        self.dragon_tiger = AShareDragonTiger()
        self.inst_trade = AShareInstTrade()

    def __repr__(self) -> str:
        return (
            "<AShare tables=['kline', 'adj_factor', 'concept', 'industry', 'dragon_tiger', 'inst_trade']>"
        )


