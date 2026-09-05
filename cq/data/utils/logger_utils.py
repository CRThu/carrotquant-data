import sys
import os
import datetime
import threading
import asyncio
from collections import deque
from pathlib import Path
from typing import Optional, Union, Dict, Any, List, Set
from loguru import logger


class LogBroadcaster:
    """
    全局 Loguru 日志广播器单例。
    维护内存环形历史缓存 (History Buffer)，并将每条结构化日志实时分发给所有 active 的 SSE 订阅队列。
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(LogBroadcaster, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, max_history: Optional[int] = None):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self.history: deque = deque(maxlen=max_history or 1000)
        self.subscribers: Dict[asyncio.Queue, Optional[asyncio.AbstractEventLoop]] = {}
        self._sub_lock = threading.Lock()

    def subscribe(self) -> asyncio.Queue:
        """注册一个新的 SSE 订阅队列，记录当前正在运行的 asyncio 事件循环"""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        q: asyncio.Queue = asyncio.Queue()
        with self._sub_lock:
            self.subscribers[q] = loop
        return q

    def unsubscribe(self, q: asyncio.Queue):
        """解绑并移除一个 SSE 订阅队列"""
        with self._sub_lock:
            self.subscribers.pop(q, None)

    def get_history(self) -> List[Dict[str, Any]]:
        """获取当前内存中的历史日志列表"""
        with self._sub_lock:
            return list(self.history)

    def sink(self, message):
        """
        Loguru 自定义 Sink 回调函数。
        记录 timestamp, level, name, line, message，并推送到历史缓存与各个 SSE 订阅队列。
        若订阅者事件循环正在运行，使用 loop.call_soon_threadsafe 跨线程唤醒；否则直接写入队列。
        """
        record = message.record
        time_str = record["time"].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        log_entry = {
            "timestamp": time_str,
            "level": record["level"].name,
            "name": record["name"],
            "line": record["line"],
            "message": record["message"],
        }
        with self._sub_lock:
            self.history.append(log_entry)
            for q, loop in list(self.subscribers.items()):
                try:
                    if loop and loop.is_running():
                        loop.call_soon_threadsafe(q.put_nowait, log_entry)
                    else:
                        q.put_nowait(log_entry)
                except Exception:
                    pass


# 全局单例
log_broadcaster = LogBroadcaster()


def setup_logger(
    log_level: Optional[str] = None,
    log_file_prefix: str = "sync",
    log_dir: Optional[Union[str, Path]] = None
):
    """
    配置 loguru 日志，同时输出到控制台和文件，并挂载 LogBroadcaster。

    Args:
        log_level: 日志级别 (如 'INFO', 'DEBUG')，若为 None 从 settings 读取
        log_file_prefix: 日志文件前缀
        log_dir: 日志目录，若为 None 从 settings 读取
    """
    from cq.data.config.settings import settings

    if log_level is None:
        log_level = getattr(settings, "log_level", "INFO")

    if log_dir is None:
        log_dir = getattr(settings, "log_dir", "logs")

    log_dir_path = Path(log_dir)
    if not log_dir_path.is_absolute():
        # 相对路径以当前工作目录为参照
        log_dir_path = Path.cwd() / log_dir_path

    # 生成带时间戳的文件名
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"{log_file_prefix}_{timestamp}.log"
    log_path = log_dir_path / log_filename

    # 确保日志目录存在
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # 移除默认的配置 (默认只输出到 stderr)
    logger.remove()

    # 添加控制台输出 (优先原生 sys.__stderr__，防止测试重定向流关闭后引发 I/O operation on closed file)
    console_sink = sys.__stderr__ if sys.__stderr__ is not None else sys.stderr
    logger.add(
        console_sink, 
        level=log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    )

    # 添加文件输出
    logger.add(
        str(log_path),
        rotation="100 MB",     # 日志文件非常大时才轮转
        compression="zip",     # 压缩旧日志
        level=log_level,
        encoding="utf-8",
        enqueue=True,          # 线程安全
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}"
    )

    # 添加 LogBroadcaster 自定义 Sink，实时广播给 SSE Web 客户端
    logger.add(
        log_broadcaster.sink,
        level=log_level,
        enqueue=True,
    )

    return logger


class SuppressOutput:
    """
    上下文管理器，用于静默 stdout 和 stderr。
    常用于屏蔽 baostock 等库产生的非 log 打印。
    """
    _devnull_out = None
    _devnull_err = None
    _lock = threading.Lock()

    def __enter__(self):
        self._stdout = sys.stdout
        self._stderr = sys.stderr
        with SuppressOutput._lock:
            if SuppressOutput._devnull_out is None or SuppressOutput._devnull_out.closed:
                SuppressOutput._devnull_out = open(os.devnull, 'w')
            if SuppressOutput._devnull_err is None or SuppressOutput._devnull_err.closed:
                SuppressOutput._devnull_err = open(os.devnull, 'w')
        sys.stdout = SuppressOutput._devnull_out
        sys.stderr = SuppressOutput._devnull_err

    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stdout = self._stdout
        sys.stderr = self._stderr
