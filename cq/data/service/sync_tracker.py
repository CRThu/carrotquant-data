"""
cqdata/service/sync_tracker.py

后台数据同步进度与状态跟踪器服务 (单例模式)。
负责记录 SyncManager 执行过程中的精准进度 (current/total/percentage/current_symbol)、
命令行式动态提示信息 (message)、任务运行状态 (idle/running/success/failed) 以及错误信息 (error_msg)。
"""

import time
from threading import Lock
from typing import Dict, Any, Optional
from cq.data.service.sync_broadcaster import sync_broadcaster


class SyncTaskStatus:
    """单表同步任务的状态、精准进度与命令行提示信息数据结构"""
    def __init__(self, table_id: str):
        self.table_id: str = table_id
        self.status: str = "idle"  # idle | running | success | failed
        self.current: int = 0
        self.total: int = 0
        self.percentage: float = 0.0
        self.current_symbol: str = ""
        self.message: str = "就绪"  # 类似命令行日志的可读动态提示
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.error_msg: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "table_id": self.table_id,
            "status": self.status,
            "current": self.current,
            "total": self.total,
            "percentage": round(self.percentage, 1),
            "current_symbol": self.current_symbol,
            "message": self.message,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "error_msg": self.error_msg,
        }


class SyncProgressTracker:
    """
    全局/单例同步进度与状态跟踪器
    """

    _instance = None
    _lock = Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(SyncProgressTracker, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        self._initialized = True
        self.task_statuses: Dict[str, SyncTaskStatus] = {}
        self._lock = Lock()

    def _broadcast_change(self, status_obj: SyncTaskStatus):
        """辅助方法：广播单个任务的状态更新与当前活跃任务列表"""
        active_tasks = [tid for tid, s in self.task_statuses.items() if s.status == "running"]
        sync_broadcaster.broadcast({
            "type": "progress",
            "item": status_obj.to_dict(),
            "active_tasks": active_tasks
        })

    def start_task(self, table_id: str, message: str = "正在初始化同步任务..."):
        """标记某个表开启同步"""
        with self._lock:
            status_obj = self.task_statuses.get(table_id)
            if not status_obj:
                status_obj = SyncTaskStatus(table_id)
                self.task_statuses[table_id] = status_obj

            status_obj.status = "running"
            status_obj.current = 0
            status_obj.total = 0
            status_obj.percentage = 0.0
            status_obj.current_symbol = ""
            status_obj.message = message
            status_obj.start_time = time.time()
            status_obj.end_time = None
            status_obj.error_msg = None

            self._broadcast_change(status_obj)

    def update_progress(self, table_id: str, current: int, total: int, current_symbol: str = "", message: str = ""):
        """更新某个表的当前进度、正在下载的代码与命令行式动态提示"""
        with self._lock:
            status_obj = self.task_statuses.get(table_id)
            if not status_obj:
                status_obj = SyncTaskStatus(table_id)
                self.task_statuses[table_id] = status_obj

            status_obj.status = "running"
            status_obj.current = current
            status_obj.total = total
            status_obj.percentage = (current / total * 100.0) if total > 0 else 0.0
            if current_symbol:
                status_obj.current_symbol = current_symbol
            if message:
                status_obj.message = message

            self._broadcast_change(status_obj)

    def finish_task(self, table_id: str, success: bool = True, message: str = "", error_msg: str = None):
        """标记某个表完成同步 (成功或失败存入 message 与 error_msg)"""
        with self._lock:
            status_obj = self.task_statuses.get(table_id)
            if not status_obj:
                status_obj = SyncTaskStatus(table_id)
                self.task_statuses[table_id] = status_obj

            if success:
                status_obj.status = "success"
                status_obj.percentage = 100.0
                status_obj.message = message or "同步已成功完成"
                status_obj.error_msg = None
            else:
                status_obj.status = "failed"
                status_obj.message = message or f"同步失败: {error_msg}"
                status_obj.error_msg = error_msg

            status_obj.end_time = time.time()

            self._broadcast_change(status_obj)

    def get_all_statuses(self) -> Dict[str, Dict[str, Any]]:
        """获取所有任务的状态字典"""
        with self._lock:
            return {tid: obj.to_dict() for tid, obj in self.task_statuses.items()}


# 全局单例
sync_tracker = SyncProgressTracker()
