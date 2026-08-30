"""
cqdata/entrypoints/__init__.py

网关层统一导出
"""

from cq.data.entrypoints.python_api import (
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
    configure
)
from cq.data.entrypoints.accessors import (
    default,
    ashare,
    aindex
)

__all__ = [
    "read",
    "write",
    "register_provider",
    "list_tables",
    "list_formats",
    "list_symbols",
    "get_time_range",
    "get_schema",
    "get_row_count",
    "list_boards",
    "sync",
    "configure",
    "default",
    "ashare",
    "aindex"
]

