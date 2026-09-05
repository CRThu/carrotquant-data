"""
tests/unit/test_sync_tracker.py

SyncProgressTracker 单元测试。
验证精准进度 (current/total/percentage/current_symbol)、状态切换与 error_msg 捕获。
"""

import pytest
from cq.data.service.sync_tracker import SyncProgressTracker, sync_tracker


def test_sync_tracker_singleton():
    t1 = SyncProgressTracker()
    t2 = SyncProgressTracker()
    assert t1 is t2
    assert t1 is sync_tracker


def test_task_status_lifecycle():
    table_id = "test.table.baostock"

    # 开始任务
    sync_tracker.start_task(table_id)
    statuses = sync_tracker.get_all_statuses()
    assert table_id in statuses
    assert statuses[table_id]["status"] == "running"
    assert statuses[table_id]["percentage"] == 0.0

    # 更新精准进度、当前 Symbol 与命令行提示 message
    sync_tracker.update_progress(table_id, current=45, total=100, current_symbol="sh.600000", message="正在抓取 sh.600000 (45/100)")
    statuses = sync_tracker.get_all_statuses()
    assert statuses[table_id]["current"] == 45
    assert statuses[table_id]["total"] == 100
    assert statuses[table_id]["percentage"] == 45.0
    assert statuses[table_id]["current_symbol"] == "sh.600000"
    assert statuses[table_id]["message"] == "正在抓取 sh.600000 (45/100)"

    # 完成任务
    sync_tracker.finish_task(table_id, success=True, message="已成功同步完成 (100/100 代码)")
    statuses = sync_tracker.get_all_statuses()
    assert statuses[table_id]["status"] == "success"
    assert statuses[table_id]["percentage"] == 100.0
    assert statuses[table_id]["message"] == "已成功同步完成 (100/100 代码)"


def test_task_status_failure():
    table_id = "test.fail.table"
    sync_tracker.start_task(table_id, message="正在准备同步...")
    sync_tracker.finish_task(table_id, success=False, message="抓取失败: 网络超时", error_msg="Network connection timeout")

    statuses = sync_tracker.get_all_statuses()
    assert statuses[table_id]["status"] == "failed"
    assert statuses[table_id]["message"] == "抓取失败: 网络超时"
    assert statuses[table_id]["error_msg"] == "Network connection timeout"


def test_sync_broadcaster_event_dispatch():
    """验证 SyncBroadcaster 订阅与 sync_tracker 变更联动广播"""
    from cq.data.service.sync_broadcaster import sync_broadcaster

    q = sync_broadcaster.subscribe()
    try:
        assert q in sync_broadcaster.subscribers

        # 触发 start_task
        sync_tracker.start_task("table.stream.test", message="开始任务测试")
        msg = q.get_nowait()
        assert msg["type"] == "progress"
        assert msg["item"]["table_id"] == "table.stream.test"
        assert msg["item"]["status"] == "running"
        assert "table.stream.test" in msg["active_tasks"]

        # 触发 update_progress
        sync_tracker.update_progress("table.stream.test", current=10, total=20, current_symbol="sh.600000")
        msg2 = q.get_nowait()
        assert msg2["item"]["current"] == 10
        assert msg2["item"]["percentage"] == 50.0

        # 触发 finish_task
        sync_tracker.finish_task("table.stream.test", success=True)
        msg3 = q.get_nowait()
        assert msg3["item"]["status"] == "success"
        assert "table.stream.test" not in msg3["active_tasks"]
    finally:
        sync_broadcaster.unsubscribe(q)
        assert q not in sync_broadcaster.subscribers
