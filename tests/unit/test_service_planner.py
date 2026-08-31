import pytest
from unittest.mock import MagicMock, patch
from cq.data.service.task_planner import TaskPlanner
from cq.data.service.metadata_manager import MetadataManager
from cq.data.utils.time_utils import parse_date_to_ts, align_to_day_end, align_to_day_start

def test_plan_no_local_data_no_start_date():
    """
    测试本地无数据 + 无 start_date → 默认起点为 1970-01-01
    """
    metadata_mgr = MagicMock()
    metadata_mgr.load.return_value = {"statistics": {}}
    
    planner = TaskPlanner(metadata_mgr)
    
    tasks = planner.plan("test.table", ["csv"], ["sh.600000"])
    assert len(tasks) == 1
    assert tasks[0]["start"] == parse_date_to_ts("1970-01-01")
    assert tasks[0]["symbol"] == "sh.600000"

def test_plan_local_data_no_start_date():
    """
    测试本地已有数据（结束点为 T）+ 用户未传 start_date → req_start 必须等于 T（验证衔接逻辑）
    """
    metadata_mgr = MagicMock()
    # 模拟本地已有数据，结束时间为 2024-01-02
    local_end_ts = parse_date_to_ts("2024-01-02")
    metadata_mgr.load.return_value = {
        "statistics": {
            "start_timestamp": parse_date_to_ts("2024-01-01"),
            "end_timestamp": local_end_ts
        }
    }
    
    planner = TaskPlanner(metadata_mgr)
    
    # Mock time.time() 返回固定时间
    with patch('time.time', return_value=1704153600):  # 2024-01-02
        tasks = planner.plan("test.table", ["csv"], ["sh.600000"])
    
    # 验证 req_start 应该等于本地结束时间
    assert len(tasks) == 1
    task = tasks[0]
    assert task["start"] == local_end_ts
    assert task["symbol"] == "sh.600000"

def test_plan_multi_format_watermark():
    """
    测试多存储格式混合水位：CSV 到 20号，Parquet 到 18号 → 计算补丁必须从 18号开始（验证木桶原理）
    """
    metadata_mgr = MagicMock()
    
    # CSV 水位：2024-01-01 到 2024-01-20
    csv_metadata = {
        "statistics": {
            "start_timestamp": parse_date_to_ts("2024-01-01"),
            "end_timestamp": parse_date_to_ts("2024-01-20")
        }
    }
    
    # Parquet 水位：2024-01-01 到 2024-01-18
    parquet_metadata = {
        "statistics": {
            "start_timestamp": parse_date_to_ts("2024-01-01"),
            "end_timestamp": parse_date_to_ts("2024-01-18")
        }
    }
    
    # 根据格式返回不同的元数据
    def mock_load(table_id, fmt):
        if fmt == "csv":
            return csv_metadata
        elif fmt == "parquet":
            return parquet_metadata
        return {}
    
    metadata_mgr.load.side_effect = mock_load
    
    planner = TaskPlanner(metadata_mgr)
    
    # 请求从 2024-01-15 到 2024-01-25
    start_date = "2024-01-15"
    end_date = "2024-01-25"
    
    tasks = planner.plan("test.table", ["csv", "parquet"], ["sh.600000"], start_date, end_date)
    
    # 验证任务应该从 2024-01-18 开始（取 min 结束时间）
    assert len(tasks) == 1
    task = tasks[0]
    expected_start = parse_date_to_ts("2024-01-18")
    assert task["start"] == expected_start

def test_plan_force_refresh():
    """
    测试强制刷新模式：忽略本地水位，直接使用请求时间范围
    """
    metadata_mgr = MagicMock()
    metadata_mgr.load.return_value = {
        "statistics": {
            "start_timestamp": parse_date_to_ts("2024-01-01"),
            "end_timestamp": parse_date_to_ts("2024-01-10")
        }
    }
    
    planner = TaskPlanner(metadata_mgr)
    
    start_date = "2024-01-05"
    end_date = "2024-01-15"
    
    tasks = planner.plan("test.table", ["csv"], ["sh.600000"], start_date, end_date, force_refresh=True)
    
    # 强制刷新应该直接使用请求的时间范围 (end 对齐到当天结束)
    assert len(tasks) == 1
    task = tasks[0]
    assert task["start"] == parse_date_to_ts(start_date)
    assert task["end"] == align_to_day_end(parse_date_to_ts(end_date))

def test_plan_no_task_needed():
    """
    测试请求范围已被本地覆盖且非强制刷新：应该跳过，不生成任务
    """
    metadata_mgr = MagicMock()
    metadata_mgr.load.return_value = {
        "statistics": {
            "start_timestamp": parse_date_to_ts("2024-01-01"),
            "end_timestamp": parse_date_to_ts("2024-01-20")
        }
    }
    
    planner = TaskPlanner(metadata_mgr)
    
    # 请求范围完全在本地范围内
    start_date = "2024-01-05"
    end_date = "2024-01-15"
    
    tasks = planner.plan("test.table", ["csv"], ["sh.600000"], start_date, end_date)
    
    # 应该跳过，不生成任务
    assert len(tasks) == 0

def test_plan_multiple_symbols():
    """
    测试多个symbol的规划
    """
    metadata_mgr = MagicMock()
    metadata_mgr.load.return_value = {"statistics": {}}
    
    planner = TaskPlanner(metadata_mgr)
    
    symbols = ["sh.600000", "sz.000001", "sz.000002"]
    start_date = "2024-01-01"
    end_date = "2024-01-10"
    
    with patch('time.time', return_value=1704153600):
        tasks = planner.plan("test.table", ["csv"], symbols, start_date, end_date)
    
    # 应该为每个symbol生成一个任务
    assert len(tasks) == 3
    task_symbols = [task["symbol"] for task in tasks]
    assert set(task_symbols) == set(symbols)

def test_plan_invalid_time_range():
    """
    测试无效时间范围（起点 >= 终点）应该跳过
    """
    metadata_mgr = MagicMock()
    # 本地数据覆盖到 2024-01-20
    metadata_mgr.load.return_value = {
        "statistics": {
            "start_timestamp": parse_date_to_ts("2024-01-01"),
            "end_timestamp": parse_date_to_ts("2024-01-20")
        }
    }
    
    planner = TaskPlanner(metadata_mgr)
    
    # 请求范围结束时间早于本地数据结束时间
    start_date = "2024-01-05"
    end_date = "2024-01-15"  # 早于本地结束时间 2024-01-20
    
    tasks = planner.plan("test.table", ["csv"], ["sh.600000"], start_date, end_date)
    
    # 应该跳过，因为请求范围已被本地覆盖
    assert len(tasks) == 0

def test_plan_empty_formats():
    """
    测试空格式列表的处理：返回空任务列表
    """
    metadata_mgr = MagicMock()
    metadata_mgr.load.return_value = {"statistics": {}}
    
    planner = TaskPlanner(metadata_mgr)
    
    # 空格式列表应该返回空任务列表（因为没有格式需要同步）
    tasks = planner.plan("test.table", [], ["sh.600000"], "2024-01-01", "2024-01-10")
    assert len(tasks) == 0

def test_plan_empty_symbols():
    """
    测试空symbol列表的处理
    """
    metadata_mgr = MagicMock()
    metadata_mgr.load.return_value = {"statistics": {}}
    
    planner = TaskPlanner(metadata_mgr)
    
    tasks = planner.plan("test.table", ["csv"], [], "2024-01-01", "2024-01-10")
    
    # 空symbol列表应该返回空任务列表
    assert len(tasks) == 0


def test_plan_prepend_scenario():
    """
    测试前向补全 (Prepend) 场景：本地有 [2015, 2020]，请求同步 [2010, 2012]
    验证其自动向后对齐取 [2010, 2015] 的任务
    """
    metadata_mgr = MagicMock()
    
    # 本地已有 2015-2020 年的数据
    metadata_mgr.load.return_value = {
        "statistics": {
            "start_timestamp": parse_date_to_ts("2015-01-01"),
            "end_timestamp": parse_date_to_ts("2020-12-31")
        }
    }
    
    planner = TaskPlanner(metadata_mgr)
    
    # 请求同步 2010-2012 年的数据（在本地数据之前）
    start_date = "2010-01-01"
    end_date = "2012-12-31"
    
    tasks = planner.plan("test.table", ["csv"], ["sh.600000"], start_date, end_date)
    
    # 应该生成一个任务，从 2010-01-01 到 2012-12-31（仅下载请求范围，不超前补全）
    assert len(tasks) == 1
    task = tasks[0]
    assert task["symbol"] == "sh.600000"
    assert task["start"] == parse_date_to_ts("2010-01-01")
    assert task["end"] == align_to_day_end(parse_date_to_ts("2012-12-31"))


def test_plan_append_scenario():
    """
    测试后向拓展 (Append) 场景：本地已有旧数据，请求未来日期
    验证其自动从本地最大值开始同步
    """
    metadata_mgr = MagicMock()
    
    # 本地已有 2020-2023 年的数据
    metadata_mgr.load.return_value = {
        "statistics": {
            "start_timestamp": parse_date_to_ts("2020-01-01"),
            "end_timestamp": parse_date_to_ts("2023-12-31")
        }
    }
    
    planner = TaskPlanner(metadata_mgr)
    
    # 请求同步到 2025 年（拓展未来数据）
    start_date = "2020-01-01"
    end_date = "2025-12-31"
    
    tasks = planner.plan("test.table", ["csv"], ["sh.600000"], start_date, end_date)
    
    # 应该生成一个任务，从 2023-12-31 开始（后向拓展）
    assert len(tasks) == 1
    task = tasks[0]
    assert task["symbol"] == "sh.600000"
    # 任务应该从本地数据的结束时间开始（对齐到天起始）
    assert task["start"] == align_to_day_start(parse_date_to_ts("2023-12-31"))
    assert task["end"] == align_to_day_end(parse_date_to_ts("2025-12-31"))


def test_plan_full_patch_scenario():
    """
    测试双向穿透 (Full Patch) 场景：请求范围远超本地范围
    验证其抓取涵盖所有缺失区间的全量数据
    """
    metadata_mgr = MagicMock()
    
    # 本地只有 2018-2020 年的数据
    metadata_mgr.load.return_value = {
        "statistics": {
            "start_timestamp": parse_date_to_ts("2018-01-01"),
            "end_timestamp": parse_date_to_ts("2020-12-31")
        }
    }
    
    planner = TaskPlanner(metadata_mgr)
    
    # 请求同步 2015-2025 年的数据（远超本地范围）
    start_date = "2015-01-01"
    end_date = "2025-12-31"
    
    tasks = planner.plan("test.table", ["csv"], ["sh.600000"], start_date, end_date)
    
    # 应该生成两个任务：前向补全和后向拓展
    assert len(tasks) == 2, "应该生成两个任务"
    
    # 验证任务覆盖了缺失的区间
    total_start = min(task["start"] for task in tasks)
    total_end = max(task["end"] for task in tasks)
    
    # 任务应该覆盖从请求开始到请求结束的范围
    assert total_start <= parse_date_to_ts("2015-01-01"), \
        "任务起始时间应该早于或等于请求开始时间"
    assert total_end >= parse_date_to_ts("2025-12-31"), \
        "任务结束时间应该晚于或等于请求结束时间"
    
    # 验证两个任务不重叠且精准覆盖缺口
    prepend_task = [t for t in tasks if t["start"] == parse_date_to_ts("2015-01-01")][0]
    append_task = [t for t in tasks if t["end"] == align_to_day_end(parse_date_to_ts("2025-12-31"))][0]
    assert prepend_task["end"] == align_to_day_end(parse_date_to_ts("2018-01-01")), \
        "前向补全应精确到本地数据起点（对齐到天末尾）"
    assert append_task["start"] == align_to_day_start(parse_date_to_ts("2020-12-31")), \
        "后向拓展应精确从本地数据终点开始（对齐到天起始）"


def test_plan_edge_case_same_start_end():
    """
    测试边界情况：start_date == end_date（单点查询）
    单点查询应生成一个任务（fetch 会返回当天数据）
    """
    metadata_mgr = MagicMock()
    metadata_mgr.load.return_value = {"statistics": {}}
    
    planner = TaskPlanner(metadata_mgr)
    
    # 单点查询
    tasks = planner.plan("test.table", ["csv"], ["sh.600000"], "2024-01-01", "2024-01-01")
    
    # 单点查询应生成 1 个任务
    assert len(tasks) == 1
    assert tasks[0]["symbol"] == "sh.600000"


def test_plan_edge_case_start_after_end():
    """
    测试边界情况：start_date > end_date（无效范围）
    """
    metadata_mgr = MagicMock()
    metadata_mgr.load.return_value = {"statistics": {}}
    
    planner = TaskPlanner(metadata_mgr)
    
    # 无效范围：开始时间晚于结束时间
    tasks = planner.plan("test.table", ["csv"], ["sh.600000"], "2024-01-10", "2024-01-01")
    
    # 应该返回空任务列表
    assert len(tasks) == 0


def test_plan_partial_overlap_front():
    """
    测试部分重叠（前端）：请求范围部分覆盖本地数据的前端
    """
    metadata_mgr = MagicMock()
    
    # 本地有 2020-01-01 到 2020-12-31 的数据
    metadata_mgr.load.return_value = {
        "statistics": {
            "start_timestamp": parse_date_to_ts("2020-01-01"),
            "end_timestamp": parse_date_to_ts("2020-12-31")
        }
    }
    
    planner = TaskPlanner(metadata_mgr)
    
    # 请求 2019-06-01 到 2020-06-01（部分在本地数据之前）
    tasks = planner.plan("test.table", ["csv"], ["sh.600000"], "2019-06-01", "2020-06-01")
    
    # TaskPlanner 的逻辑是 task_end = min(req_end, loc_start) + align_to_day_end
    # 所以 task_end = align_to_day_end(min(2020-06-01, 2020-01-01)) = align_to_day_end(2020-01-01)
    assert len(tasks) == 1
    task = tasks[0]
    assert task["start"] == parse_date_to_ts("2019-06-01")
    assert task["end"] == align_to_day_end(parse_date_to_ts("2020-01-01"))


def test_plan_partial_overlap_back():
    """
    测试部分重叠（后端）：请求范围部分覆盖本地数据的后端
    """
    metadata_mgr = MagicMock()
    
    # 本地有 2020-01-01 到 2020-12-31 的数据
    metadata_mgr.load.return_value = {
        "statistics": {
            "start_timestamp": parse_date_to_ts("2020-01-01"),
            "end_timestamp": parse_date_to_ts("2020-12-31")
        }
    }
    
    planner = TaskPlanner(metadata_mgr)
    
    # 请求 2020-06-01 到 2021-06-01（部分在本地数据之后）
    tasks = planner.plan("test.table", ["csv"], ["sh.600000"], "2020-06-01", "2021-06-01")
    
    # 应该生成任务拓展 2020-12-31 到 2021-06-01 的部分（对齐到天边界）
    assert len(tasks) == 1
    task = tasks[0]
    assert task["start"] == align_to_day_start(parse_date_to_ts("2020-12-31"))
    assert task["end"] == align_to_day_end(parse_date_to_ts("2021-06-01"))


def test_plan_multiple_symbols_prepend():
    """
    测试多 symbol 的前向补全场景
    """
    metadata_mgr = MagicMock()
    
    # 本地已有 2020-2023 年的数据
    metadata_mgr.load.return_value = {
        "statistics": {
            "start_timestamp": parse_date_to_ts("2020-01-01"),
            "end_timestamp": parse_date_to_ts("2023-12-31")
        }
    }
    
    planner = TaskPlanner(metadata_mgr)
    
    symbols = ["sh.600000", "sz.000001", "sz.000002"]
    start_date = "2015-01-01"
    end_date = "2018-12-31"
    
    tasks = planner.plan("test.table", ["csv"], symbols, start_date, end_date)
    
    # 应该为每个 symbol 生成任务
    assert len(tasks) == 3
    
    # 验证所有任务都是前向补全
    for task in tasks:
        assert task["symbol"] in symbols
        assert task["start"] == parse_date_to_ts("2015-01-01")
        # 仅下载请求范围 [2015, 2018]，end 对齐到天末尾
        assert task["end"] == align_to_day_end(parse_date_to_ts("2018-12-31"))


def test_plan_same_day_incremental_refresh():
    """
    测试同一天增量刷新：本地数据结束于 2024-01-15，请求结束于 2024-01-15
    验证 req_end == loc_end 同一天时仍生成任务，确保当天不完整数据被刷新
    """
    metadata_mgr = MagicMock()
    
    # 本地已有数据，结束于 2024-01-15
    metadata_mgr.load.return_value = {
        "statistics": {
            "start_timestamp": parse_date_to_ts("2024-01-01"),
            "end_timestamp": parse_date_to_ts("2024-01-15")
        }
    }
    
    planner = TaskPlanner(metadata_mgr)
    
    # 请求结束时间与本地结束同一天
    tasks = planner.plan("test.table", ["csv"], ["sh.600000"], "2024-01-01", "2024-01-15")
    
    # 应生成任务，后向拓展覆盖 2024-01-15 当天
    assert len(tasks) == 1
    task = tasks[0]
    assert task["symbol"] == "sh.600000"
    # task_start = align_to_day_start(loc_end) = 2024-01-15T00:00
    assert task["start"] == align_to_day_start(parse_date_to_ts("2024-01-15"))
    # task_end = align_to_day_end(req_end) = 2024-01-15T23:59:59.999
    assert task["end"] == align_to_day_end(parse_date_to_ts("2024-01-15"))


def test_plan_local_data_force_refresh_no_start_date():
    """
    测试本地已有数据（2020-2024）+ 用户未传 start_date + 勾选 force_refresh=True
    验证 req_start 必须被重置为 1970-01-01 全量历史起点，而非本地结束时间
    """
    metadata_mgr = MagicMock()
    metadata_mgr.load.return_value = {
        "statistics": {
            "start_timestamp": parse_date_to_ts("2020-01-01"),
            "end_timestamp": parse_date_to_ts("2024-01-02"),
        }
    }

    planner = TaskPlanner(metadata_mgr)

    with patch('time.time', return_value=1704153600):  # 2024-01-02
        tasks = planner.plan("test.table", ["csv"], ["sh.600000"], force_refresh=True)

    assert len(tasks) == 1
    task = tasks[0]
    assert task["start"] == parse_date_to_ts("1970-01-01")
    assert task["symbol"] == "sh.600000"

