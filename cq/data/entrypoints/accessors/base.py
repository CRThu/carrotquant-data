"""
cqdata/entrypoints/accessors/base.py

OOP 访问层基础配置与公共基类。
"""

from abc import ABC
from typing import List, Optional, Union, Dict, Any
import polars as pl

from cq.data.entrypoints.python_api import read
from cq.data.provider.provider_manager import ProviderManager


class _BaseTable(ABC):
    """
    表具体访问类基类
    提取公共 get() 切片逻辑、属性控制与驱动校验。
    """
    _PREFIX: str = ""
    _FALLBACK_SOURCE: str = "baostock"
    _DEFAULT_FORMAT: str = "parquet"

    def __init__(self):
        self._source: Optional[str] = None
        self._format: Optional[str] = None

    @property
    def source(self) -> str:
        """返回当前表生效的数据源标识符"""
        return self._source if self._source is not None else self._FALLBACK_SOURCE

    @source.setter
    def source(self, value: Optional[str]) -> None:
        """设置当前表生效的数据源 (具备严格的合法性校验)"""
        if value is None:
            self._source = None
            return
        val = str(value).lower().strip()
        supported = self.supported_sources
        if val not in supported:
            raise ValueError(
                f"Unsupported source '{value}' for {self._PREFIX}. "
                f"Supported sources: {supported}"
            )
        self._source = val

    @property
    def format(self) -> str:
        """返回当前表生效的存储格式"""
        return self._format if self._format is not None else self._DEFAULT_FORMAT

    @format.setter
    def format(self, value: Optional[str]) -> None:
        """设置当前表生效的存储格式"""
        if value is None:
            self._format = None
            return
        val = str(value).lower().strip()
        if val not in ("parquet", "csv"):
            raise ValueError(
                f"Unsupported format '{value}' for {self._PREFIX}. "
                f"Supported formats: ['parquet', 'csv']"
            )
        self._format = val

    @property
    def supported_sources(self) -> List[str]:
        """返回当前表所支持的所有数据源标识符列表"""
        return ProviderManager().get_sources_for_prefix(self._PREFIX)

    @property
    def supported_formats(self) -> List[str]:
        """返回当前表所支持的所有存储格式列表"""
        return ["parquet", "csv"]

    def __repr__(self) -> str:
        return (
            f"<TableAccessor prefix={self._PREFIX!r}, "
            f"source={self.source!r}, "
            f"format={self.format!r}, "
            f"supported_sources={self.supported_sources!r}>"
        )

    def _resolve_source_format(
        self,
        source: Optional[str] = None,
        format: Optional[str] = None
    ) -> tuple[str, str]:
        resolved_source = source if source is not None else self.source
        resolved_format = format if format is not None else self.format
        return resolved_source, resolved_format

    @staticmethod
    def _apply_columns(df: pl.DataFrame, columns: Optional[Union[str, List[str]]]) -> pl.DataFrame:
        """按需进行列投影选择 (只选择指定的列返回)"""
        if df.is_empty() or not columns:
            return df
        col_list = [columns] if isinstance(columns, str) else columns
        valid_cols = [c for c in col_list if c in df.columns]
        if not valid_cols:
            return df
        return df.select(valid_cols)

    def _validate_table_id(self, table_id: str) -> None:
        """检查拼装出的 table_id 是否受底层数据源支持，不存在则抛出清晰的 ValueError"""
        try:
            provider = ProviderManager().get_provider(table_id)
            if table_id not in provider.get_supported_tables():
                raise ValueError(
                    f"Unsupported table_id '{table_id}'. "
                    f"Provider '{provider.__class__.__name__}' does not support this table ID or parameter combination."
                )
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"Invalid table_id '{table_id}': {e}") from e

    def _resolve_factor_source(
        self,
        kline_source: str,
        factor_prefix: str,
        fallback_factor_source: str
    ) -> str:
        """契约化动态探测：检查当前 K 线源是否提供对应复权因子表，若无则优雅回退至默认因子源"""
        candidate_table = f"{factor_prefix}.{kline_source}"
        try:
            prov = ProviderManager().get_provider(candidate_table)
            if candidate_table in prov.get_supported_tables():
                return kline_source
        except Exception:
            pass
        return fallback_factor_source

    def _read_table(
        self,
        table_id: str,
        symbols: Optional[Union[str, List[str]]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        columns: Optional[Union[str, List[str]]] = None,
        format: str = "auto"
    ) -> pl.DataFrame:
        self._validate_table_id(table_id)
        return read(
            table_id=table_id,
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            columns=columns,
            format=format
        )
