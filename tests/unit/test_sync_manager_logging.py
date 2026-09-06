import polars as pl
from unittest.mock import MagicMock, patch
import pytest
from cq.data.service.sync_manager import SyncManager

def test_sync_manager_time_range_logging(tmp_path):
    """
    验证 SyncManager 在启动、规划完成以及抓取每个标的时，
    均透明输出时间起止范围日志，杜绝'黑盒'。
    """
    table_id = "test.kline.1m.log_transparency"
    symbols = ["sh.600001"]

    sm = SyncManager(data_dir=str(tmp_path))

    # 模拟 Planner 返回固定时间范围 (例如 2025-01-01 到 2025-01-10)
    start_ts = 1735689600000  # 2025-01-01
    end_ts = 1736467200000    # 2025-01-10

    mock_provider = MagicMock()
    mock_provider.get_all_symbols.return_value = symbols
    mock_provider.get_table_category.return_value = "timeseries"
    mock_provider.get_sort_keys.return_value = ["symbol", "timestamp"]
    mock_provider.fetch.return_value = pl.DataFrame({
        "symbol": ["sh.600001"],
        "timestamp": [start_ts],
        "datetime": ["2025-01-01T08:00:00+08:00"],
        "close": [10.0]
    })

    logged_messages = []
    def fake_info(msg, *args, **kwargs):
        logged_messages.append(str(msg))

    with patch.object(sm.provider_mgr, "get_provider", return_value=mock_provider), \
         patch("cq.data.service.sync_manager.logger.info", side_effect=fake_info):
        sm.sync(table_id, formats=["parquet"], start_date="2025-01-01", end_date="2025-01-10")

    # 1. 验证启动日志包含了起止时间
    start_logs = [m for m in logged_messages if "Starting orchestrated sync" in m]
    assert len(start_logs) == 1
    assert "range=[2025-01-01 -> 2025-01-10]" in start_logs[0]

    # 2. 验证规划日志包含了实际规划的时间范围
    plan_logs = [m for m in logged_messages if "Task planning finished" in m]
    assert len(plan_logs) == 1
    assert "Time range: [2025-01-01 -> 2025-01-10]" in plan_logs[0]

    # 3. 验证单标的抓取日志包含了时间范围
    progress_logs = [m for m in logged_messages if "[PROGRESS]" in m]
    assert len(progress_logs) == 1
    assert "[2025-01-01 -> 2025-01-10]" in progress_logs[0]
