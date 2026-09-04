"""
cqdata/entrypoints/accessors/__init__.py

OOP 便捷访问层包导出。
向外导出 default, ashare, aindex 单例与主要访问类。
"""

from cq.data.entrypoints.accessors.ashare import AShare
from cq.data.entrypoints.accessors.aetf import AETF
from cq.data.entrypoints.accessors.aindex import AIndex

# 实例化命名空间单例 (0 参数自洽构造)
ashare = AShare()
aetf = AETF()
aindex = AIndex()

__all__ = [
    "ashare",
    "aetf",
    "aindex",
]

