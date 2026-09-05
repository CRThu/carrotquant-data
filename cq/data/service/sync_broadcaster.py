"""
cqdata/service/sync_broadcaster.py

同步进度与任务状态专用广播器 (SSE Broadcaster)。
维护活跃的 SSE 客户端订阅队列，在任务更新、完成或异常时，跨线程安全分发实时进度事件。
"""

import threading
import asyncio
from typing import Optional, Dict, Any


class SyncBroadcaster:
    """
    同步任务进度广播器单例。
    维护活跃的 SSE 客户端连接队列，通过 call_soon_threadsafe 保证跨线程安全唤醒主事件循环。
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(SyncBroadcaster, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        # 存储 (queue, loop) 元组集合
        self.subscribers: Dict[asyncio.Queue, Optional[asyncio.AbstractEventLoop]] = {}
        self._sub_lock = threading.Lock()

    def subscribe(self) -> asyncio.Queue:
        """注册一个新的 SSE 订阅队列，绑定当前调用者线程的 asyncio 事件循环"""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = None
        q: asyncio.Queue = asyncio.Queue()
        with self._sub_lock:
            self.subscribers[q] = loop
        return q

    def unsubscribe(self, q: asyncio.Queue):
        """解绑并注销一个 SSE 订阅队列"""
        with self._sub_lock:
            self.subscribers.pop(q, None)

    def broadcast(self, payload: Dict[str, Any]):
        """
        向所有在线 SSE 客户端分发最新的任务进度状态。
        使用 loop.call_soon_threadsafe 保证可在任何 OS 工作线程中安全调用。
        """
        with self._sub_lock:
            for q, loop in list(self.subscribers.items()):
                try:
                    if loop and not loop.is_closed():
                        loop.call_soon_threadsafe(q.put_nowait, payload)
                    else:
                        q.put_nowait(payload)
                except Exception:
                    pass


# 全局单例
sync_broadcaster = SyncBroadcaster()
