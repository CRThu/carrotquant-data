"""
cqdata/entrypoints/accessors/aindex.py

A 股指数数据 OOP 访问类与命名空间实现。
"""

from typing import List, Optional, Union
import polars as pl

from cq.data.entrypoints.accessors.base import _BaseTable


class AIndexKline(_BaseTable):
    """A 股指数 K 线快捷访问类 (指数固定 raw 无复权)"""
    _PREFIX = "aindex.kline"
    _FALLBACK_SOURCE = "baostock"

    def get(
        self,
        freq: str = "1d",
        symbols: Optional[Union[str, List[str]]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        columns: Optional[Union[str, List[str]]] = None,
        source: Optional[str] = None,
        format: Optional[str] = None
    ) -> pl.DataFrame:
        """
        读取 A 股指数 K 线数据 (指数无复权，固定 raw)。

        Args:
            freq: K 线频率，默认 '1d' (可选 '1d', '5m', '1m')
            symbols: 指数代码或代码列表 (如 'sh.000001')
            start_date: 起始日期 ('YYYY-MM-DD')
            end_date: 结束日期 ('YYYY-MM-DD')
            columns: 选挑字段列表
            source: 指定数据源 ('baostock', 'tdx' 等)
            format: 存储格式 ('parquet', 'csv', 'auto')

        Returns:
            pl.DataFrame
        """
        resolved_source, resolved_format = self._resolve_source_format(source, format)
        table_id = f"{self._PREFIX}.{freq}.raw.{resolved_source}"
        return self._read_table(
            table_id=table_id,
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            columns=columns,
            format=resolved_format
        )


class AIndex:
    """指数数据命名空间类"""

    def __init__(self):
        self.kline = AIndexKline()

    def __repr__(self) -> str:
        return "<AIndex tables=['kline']>"
