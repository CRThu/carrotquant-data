import sys
from . import stockdb

# 保证外部 SDK (stock_sdk.py) 内部执行顶层绝对导入时能直接命中模块缓存，实现 0 sys.path 污染
if "stockdb" not in sys.modules:
    sys.modules["stockdb"] = stockdb

from . import stock_sdk
from cq.data.provider.stockdb.provider import StockDBProvider

__all__ = ["StockDBProvider", "stockdb", "stock_sdk"]

