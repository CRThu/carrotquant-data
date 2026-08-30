"""
cqdata/entrypoints/python_api.py

Python SDK API 接入面模块。
为 Python 量化脚本与交互环境提供干净、专一、直观的高阶函数调用。
"""

from typing import List, Tuple, Dict, Union, Optional, Any, Callable
from pathlib import Path
import polars as pl

from cq.data.service import data_reader as dr
from cq.data.service import metadata_reader as mr
from cq.data.service import sync_manager as sm
from cq.data.config import settings
from cq.data.service.metadata_manager import MetadataManager
from cq.data.service.data_writer import DataWriter
from cq.data.provider.provider_manager import ProviderManager



def read(
    table_id: str,
    symbols: Optional[Union[str, List[str]]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    columns: Optional[Union[str, List[str]]] = None,
    format: str = "auto"
) -> pl.DataFrame:
    """
    统一数据切片读取入口 (自动按 table_id 智能路由，支持内置及自定义数据表)

    Args:
        table_id: 数据集 ID (例如 'ashare.kline.1d.raw.baostock' 或 'custom_table')
        symbols: 证券代码或代码列表
        start_date: 起始日期 ('YYYY-MM-DD')
        end_date: 结束日期 ('YYYY-MM-DD')
        columns: 选挑字段清单 (例如 ['timestamp', 'close', 'volume'])
        format: 存储格式 ('auto', 'parquet', 'csv')

    Returns:
        pl.DataFrame
    """
    if not table_id or not isinstance(table_id, str):
        raise ValueError("table_id must be a non-empty string.")

    reader = dr.DataReader()
    actual_fmt = reader._determine_format(table_id, format)
    category = reader._get_table_category(table_id, actual_fmt)

    if category == "event":
        return dr.read_events(
            table_id=table_id,
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            columns=columns,
            format=format
        )
    else:
        return dr.read_series(
            table_id=table_id,
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            columns=columns,
            format=format
        )


def write(
    table_id: str,
    df: pl.DataFrame,
    category: str = "timeseries",
    formats: Union[List[str], str] = "parquet",
    mode: str = "append",
    sort_keys: Optional[List[str]] = None,
    data_dir: Optional[Union[str, Path]] = None
) -> Dict[str, Any]:
    """
    统一数据写入与导入入口。
    将外部 DataFrame 写入本地物理存储 (Parquet / CSV) 并自动生成/更新 metadata.json。

    Args:
        table_id: 数据表 ID (如 'my_factor' 或 'crypto.kline.1d.binance')
        df: 要写入的 Polars DataFrame
        category: 数据集类别 ('timeseries' 或 'event')，默认为 'timeseries'
        formats: 存储格式 ('parquet', 'csv' 或 ['parquet', 'csv'])
        mode: 写入模式 ('append' 或 'overwrite')
        sort_keys: 事件表排序字段列表
        data_dir: 自定义存储根目录 (可选)


    Returns:
        Dict[str, Any]: 包含 table_id, category, formats, rows_written 等信息的字典
    """
    writer = DataWriter(data_dir=data_dir)
    return writer.write(
        table_id=table_id,
        df=df,
        category=category,
        formats=formats,
        mode=mode,
        sort_keys=sort_keys
    )


def register_provider(source: str, provider: Optional[Any] = None) -> Union[Any, Callable]:
    """
    注册自定义数据源 Provider 驱动 (支持普通函数调用与类装饰器两种模式)。

    示例 1 (类装饰器模式):
        @cq.data.register_provider("stockdb")
        class StockDBProvider(BaseProvider):
            ...

    示例 2 (普通函数调用模式):
        cq.data.register_provider("stockdb", StockDBProvider)
        # 或
        cq.data.register_provider("stockdb", StockDBProvider())

    Args:
        source: 数据源标识 (table_id 末段，如 'stockdb')
        provider: Provider 类或实例 (可选，若为 None 则返回类装饰器)

    Returns:
        注册的 Provider 类/实例 (普通模式) 或 装饰器闭包 (装饰器模式)
    """
    return ProviderManager.register_provider(source=source, provider=provider)




def list_tables(format: str = "auto") -> List[Dict[str, str]]:
    """
    列出本地已存在的所有数据表清单及分类信息 (平铺对象列表)

    Returns:
        List[Dict[str, str]]: [{'table_id': '...', 'category': 'timeseries'|'event'}, ...]
    """
    series_tables = mr.list_series_tables(format=format)
    event_tables = mr.list_event_tables(format=format)

    tables = [{"table_id": tid, "category": "timeseries"} for tid in series_tables]
    tables.extend([{"table_id": tid, "category": "event"} for tid in event_tables])
    return tables


def list_formats(table_id: str) -> List[str]:
    """获取指定表在本地存在的所有存储格式"""
    return mr.list_formats(table_id=table_id)


def list_symbols(table_id: str, format: str = "auto") -> List[str]:
    """获取指定表在本地已存储的所有 symbol 股票/指数代码列表"""
    return mr.list_symbols(table_id=table_id, format=format)


def get_time_range(table_id: str, format: str = "auto") -> Tuple[str, str]:
    """获取指定表的全局起止 ISO 时间字符串 tuple (start_datetime, end_datetime)"""
    return mr.get_time_range(table_id=table_id, format=format)


def get_schema(table_id: str, format: str = "auto") -> Dict[str, str]:
    """获取指定表在元数据中的字段 Schema 映射字典 (列名 -> 类型名)"""
    return mr.get_schema(table_id=table_id, format=format)


def get_row_count(table_id: str, format: str = "auto") -> int:
    """获取指定表在物理存储中的总记录行数/条目数"""
    return mr.get_row_count(table_id=table_id, format=format)


def list_boards(table_id: str, format: str = "auto") -> List[Dict[str, Any]]:
    """获取板块概念/行业列表及各板块成分股计数"""
    df = read(table_id=table_id, format=format)
    if df.is_empty() or "board_code" not in df.columns:
        return []
    boards_df = df.group_by(["board_code", "board_name"]).agg(pl.len().alias("stock_count")).sort("board_code")
    return [{"board_code": row[0], "board_name": row[1], "stock_count": row[2]} for row in boards_df.iter_rows()]


def sync(
    table_ids: Union[List[str], str],
    formats: Union[List[str], str] = "parquet",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    force_refresh: bool = False,
    batch_size: int = 100,
    symbol_limit: Optional[int] = None,
    provider_kwargs: Optional[dict] = None
):
    """
    触发全自动化同步闭环的快捷函数
    
    Args:
        table_ids: 表 ID 或表 ID 列表
        formats: 落地格式 ('parquet', 'csv', 或 ['parquet', 'csv'])
        start_date: 起始日期 ('YYYY-MM-DD')
        end_date: 结束日期 ('YYYY-MM-DD')
        force_refresh: 是否强制全量覆盖刷新
        batch_size: 批处理数量
        symbol_limit: 限制处理的证券数
        provider_kwargs: 传递给 Provider 的选项字典
    """
    return sm.sync(
        table_ids=table_ids,
        formats=formats,
        start_date=start_date,
        end_date=end_date,
        force_refresh=force_refresh,
        batch_size=batch_size,
        symbol_limit=symbol_limit,
        provider_kwargs=provider_kwargs
    )


def configure(config_path: Union[str, Path]):
    """
    全局加载 YAML 配置文件。
    可以在 import cq.data 后在代码入口处显式调用。

    示例:
        import cq.data
        cq.data.configure("./config.yaml")
    """
    return settings.configure(config_path=config_path)

