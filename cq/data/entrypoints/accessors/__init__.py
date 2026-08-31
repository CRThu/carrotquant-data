"""
cqdata/entrypoints/accessors/__init__.py

OOP 便捷访问层包导出。
向外导出 default, ashare, aindex 单例与主要访问类。
"""

from cq.data.entrypoints.accessors.base import DefaultConfig, default
from cq.data.entrypoints.accessors.ashare import AShare
from cq.data.entrypoints.accessors.aetf import AETF
from cq.data.entrypoints.accessors.aindex import AIndex

# 实例化命名空间单例
ashare = AShare(parent_default=default)
aetf = AETF(parent_default=default)
aindex = AIndex(parent_default=default)

__all__ = [
    "default",
    "ashare",
    "aetf",
    "aindex",
]
