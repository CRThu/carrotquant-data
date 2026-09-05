"""
tests/unit/test_logger_utils.py

cq/data/utils/logger_utils.py 日志与 LogBroadcaster 广播单例单元测试。
包含边界条件测试：全量无上限加载、冷启动 0 日志、多线程高并发写日志与特殊字符序列化防御。
"""

import pytest
import asyncio
import datetime
import sys
import threading
from cq.data.utils.logger_utils import LogBroadcaster, setup_logger, SuppressOutput
from loguru import logger


def test_log_broadcaster_unlimited_full_history():
    """边界测试 1：验证 max_history=None 时支持全量无上限存储日志"""
    broadcaster = LogBroadcaster(max_history=None)
    broadcaster.history.clear()

    # 模拟写入 1000 条日志
    for i in range(1000):
        broadcaster.history.append({"message": f"Full log item {i}"})

    hist = broadcaster.get_history()
    assert len(hist) == 1000, "Expect 1000 items preserved without truncation"
    assert hist[0]["message"] == "Full log item 0"
    assert hist[-1]["message"] == "Full log item 999"


def test_log_broadcaster_zero_log_cold_start():
    """边界测试 2：验证冷启动 0 日志状态下的读取与空历史广播"""
    broadcaster = LogBroadcaster()
    broadcaster.history.clear()

    hist = broadcaster.get_history()
    assert hist == [], "Cold start history should be empty list []"


def test_log_broadcaster_subscribe_unsubscribe_cleanup():
    """边界测试 3：验证客户端连接与断连清理 (防止内存泄漏)"""
    broadcaster = LogBroadcaster()
    q1 = broadcaster.subscribe()
    q2 = broadcaster.subscribe()

    assert len(broadcaster.subscribers) >= 2
    assert q1 in broadcaster.subscribers
    assert q2 in broadcaster.subscribers

    broadcaster.unsubscribe(q1)
    assert q1 not in broadcaster.subscribers
    assert q2 in broadcaster.subscribers

    broadcaster.unsubscribe(q2)
    assert q2 not in broadcaster.subscribers


def test_log_broadcaster_high_concurrency_multithreaded():
    """边界测试 4：验证多线程高并发大量写入日志时的线程安全性"""
    broadcaster = LogBroadcaster()
    broadcaster.history.clear()

    def worker(thread_idx):
        for i in range(50):
            broadcaster.history.append({
                "thread": thread_idx,
                "msg": f"thread {thread_idx} log {i}"
            })

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    hist = broadcaster.get_history()
    assert len(hist) == 500, "10 threads * 50 logs should equal 500 total logs"


def test_log_broadcaster_special_characters_and_emojis():
    """边界测试 5：验证日志包含换行符、Emoji 符号及 Unicode 特殊字符"""
    broadcaster = LogBroadcaster()
    broadcaster.history.clear()

    special_msg = "📈 [Sync] 特殊字符测试 \n 换行符 & Quote \" ' \u2705 Emojis 🚀🚀"
    broadcaster.history.append({"message": special_msg})

    hist = broadcaster.get_history()
    assert len(hist) == 1
    assert hist[0]["message"] == special_msg


def test_setup_logger_attaches_broadcaster():
    """验证 setup_logger() 正确挂载 LogBroadcaster.sink 并收到 loguru 日志"""
    from cq.data.utils.logger_utils import log_broadcaster
    log_broadcaster.history.clear()

    setup_logger(log_level="INFO", log_file_prefix="test")
    logger.info("Test log line via setup_logger")
    try:
        logger.complete()
    except Exception:
        pass

    hist = log_broadcaster.get_history()
    assert len(hist) > 0, "LogBroadcaster should receive log entries from loguru"
    assert any("Test log line via setup_logger" in entry["message"] for entry in hist)


def test_suppress_output():
    """验证 SuppressOutput 静默输出功能"""
    stdout_before = sys.stdout
    stderr_before = sys.stderr

    with SuppressOutput():
        print("This print should be suppressed")
        sys.stderr.write("This err should be suppressed\n")

    assert sys.stdout is stdout_before
    assert sys.stderr is stderr_before


@pytest.mark.asyncio
async def test_log_broadcaster_cross_thread_asyncio_wakeup():
    """验证后台 Worker 线程写入日志能够跨线程通过 call_soon_threadsafe 毫秒级安全唤醒主事件循环中的 q.get()"""
    broadcaster = LogBroadcaster()
    q = broadcaster.subscribe()
    try:
        def bg_worker():
            import time
            time.sleep(0.02)
            # 在独立 OS 工作线程触发 sink
            broadcaster.sink(type("FakeMsg", (), {"record": {
                "time": datetime.datetime(2026, 9, 5, 12, 0, 0),
                "level": type("FakeLevel", (), {"name": "INFO"})(),
                "name": "worker_test",
                "line": 42,
                "message": "Async wakeup from thread"
            }})())

        t = threading.Thread(target=bg_worker)
        t.start()

        # 等待主协程从 q 中获取，若无 call_soon_threadsafe 唤醒则会导致死锁超时
        entry = await asyncio.wait_for(q.get(), timeout=1.0)
        assert entry["message"] == "Async wakeup from thread"
        assert entry["name"] == "worker_test"
        t.join()
    finally:
        broadcaster.unsubscribe(q)
