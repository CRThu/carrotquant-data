"""
CarrotQuant.Data (cqdata)

轻量级、模块化的本地金融数据同步与管理工具。

对外暴露的统一 Python SDK API:
- read: 统一切片读取 K 线/分笔/板块/龙虎榜等金融数据 (自动按分类智能路由)
- ashare / aetf / aindex: OOP 极简便捷数据访问命名空间 (如 cq.data.ashare.kline.get())
- configure: 全局配置函数 (支持配置文件与参数混合设置)
- settings: 全局 Settings 实例
- list_tables: 列出本地已有的全量数据表清单 (含 category 属性)
- list_formats: 查看某表已有的存储格式
- list_symbols: 查看某表已有的股票/指数代码列表
- get_time_range: 获取某表的时间起止跨度
- get_schema: 获取某表的字段列定义与类型
- get_row_count: 获取某表物理存储记录条数
- sync: 触发数据全自动同步
"""

from cq.data.entrypoints import (
    read,
    write,
    register_provider,
    list_tables,
    list_formats,
    list_symbols,
    get_time_range,
    get_schema,
    get_row_count,
    list_boards,
    sync,
    configure,
    ashare,
    aetf,
    aindex,
    list_sources
)
from cq.data.config import settings

__version__ = "1.7.3"

__all__ = [
    "read",
    "write",
    "register_provider",
    "list_sources",
    "list_tables",
    "list_formats",
    "list_symbols",
    "get_time_range",
    "get_schema",
    "get_row_count",
    "list_boards",
    "sync",
    "configure",
    "ashare",
    "aetf",
    "aindex",
    "settings",
    "__version__"
]

