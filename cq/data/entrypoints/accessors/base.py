"""
cqdata/entrypoints/accessors/base.py

OOP 访问层基础配置与公共基类。
"""

from typing import List, Optional, Union, Dict, Any
import polars as pl

from cq.data.entrypoints.python_api import read
from cq.data.provider.provider_manager import ProviderManager


class DefaultConfig:
    """
    三层链式默认值配置类 (全局 -> 市场级 -> 表级)
    小覆盖大，新覆盖旧。
    """

    def __init__(
        self,
        parent: Optional["DefaultConfig"] = None,
        fallback_source: Optional[str] = None,
        fallback_format: Optional[str] = None
    ):
        self._source: Optional[str] = None
        self._format: Optional[str] = None
        self.parent: Optional["DefaultConfig"] = parent
        self.fallback_source: Optional[str] = fallback_source
        self.fallback_format: Optional[str] = fallback_format

    @property
    def source(self) -> Optional[str]:
        return self._source

    @source.setter
    def source(self, value: Optional[str]):
        self._source = value

    @property
    def format(self) -> Optional[str]:
        return self._format

    @format.setter
    def format(self, value: Optional[str]):
        self._format = value

    def resolve_source(self) -> str:
        """向上递归解析最终生效的 source"""
        if self._source is not None:
            return self._source
        if self.parent is not None:
            return self.parent.resolve_source()
        return self.fallback_source or "baostock"

    def resolve_format(self) -> str:
        """向上递归解析最终生效的 format"""
        if self._format is not None:
            return self._format
        if self.parent is not None:
            return self.parent.resolve_format()
        return self.fallback_format or "parquet"

    def update_from_dict(self, data: Dict[str, Any]) -> None:
        """根据配置字典批量更新字段"""
        if not isinstance(data, dict):
            return
        if "source" in data:
            self._source = str(data["source"])
        if "format" in data:
            self._format = str(data["format"])

    def __repr__(self) -> str:
        res_src = self.resolve_source()
        res_fmt = self.resolve_format()
        return f"<DefaultConfig source={self._source!r} (resolved={res_src!r}), format={self._format!r} (resolved={res_fmt!r})>"


# 全局默认配置单例
default = DefaultConfig(fallback_source="baostock", fallback_format="parquet")


class _BaseTable:
    """
    表具体访问类基类
    提取公共 get() 切片逻辑与驱动校验
    """
    _PREFIX: str = ""
    _FALLBACK_SOURCE: str = "baostock"

    def __init__(self, parent_default: DefaultConfig):
        self.default = DefaultConfig(parent=parent_default, fallback_source=self._FALLBACK_SOURCE)

    def _resolve_source_format(
        self,
        source: Optional[str] = None,
        format: Optional[str] = None
    ) -> tuple[str, str]:
        resolved_source = source if source is not None else self.default.resolve_source()
        resolved_format = format if format is not None else self.default.resolve_format()
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
