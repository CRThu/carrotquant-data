import pytest
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from cq.data.utils.time_utils import (
    parse_date_to_ts,
    ts_to_iso,
    ts_to_str,
    align_to_day_start,
    align_to_day_end
)

def test_parse_date_to_ts_asia_shanghai():
    """
    测试 parse_date_to_ts 是否准确生成 Asia/Shanghai 时区的毫秒戳
    """
    # 测试 2024-01-01 的解析
    ts = parse_date_to_ts("2024-01-01", source_tz="Asia/Shanghai")
    
    # 验证返回的是整数毫秒戳
    assert isinstance(ts, int)
    
    # 验证时区正确：Asia/Shanghai 的 2024-01-01 00:00:00
    expected_dt = datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    expected_ts = int(expected_dt.timestamp() * 1000)
    
    assert ts == expected_ts, f"预期 {expected_ts}，实际 {ts}"
    
    # 验证转换回日期时间是否正确
    actual_dt = datetime.fromtimestamp(ts / 1000, tz=ZoneInfo("Asia/Shanghai"))
    assert actual_dt.year == 2024
    assert actual_dt.month == 1
    assert actual_dt.day == 1
    assert actual_dt.hour == 0
    assert actual_dt.minute == 0
    assert actual_dt.second == 0

def test_parse_date_to_ts_cross_timezone():
    """
    验证同一挂钟时间在不同时区下生成的 timestamp 是否不同
    """
    # 同一挂钟时间 2024-01-01 00:00:00
    date_str = "2024-01-01"
    
    # Asia/Shanghai (UTC+8) 的 2024-01-01 00:00:00 = UTC 2023-12-31 16:00:00
    ts_shanghai = parse_date_to_ts(date_str, source_tz="Asia/Shanghai")
    
    # UTC 的 2024-01-01 00:00:00 = UTC 2024-01-01 00:00:00
    ts_utc = parse_date_to_ts(date_str, source_tz="UTC")
    
    # America/New_York (UTC-5) 的 2024-01-01 00:00:00 = UTC 2024-01-01 05:00:00
    ts_newyork = parse_date_to_ts(date_str, source_tz="America/New_York")
    
    # 验证三者不同
    assert ts_shanghai != ts_utc, "Asia/Shanghai 和 UTC 的 timestamp 应该不同"
    assert ts_utc != ts_newyork, "UTC 和 America/New_York 的 timestamp 应该不同"
    
    # 验证差值正确：
    # Asia/Shanghai 的挂钟时间比 UTC 早发生，所以 ts_utc - ts_shanghai = 8 小时
    assert ts_utc - ts_shanghai == 8 * 3600 * 1000, "UTC 应比 Asia/Shanghai 晚 8 小时"
    
    # America/New_York 的挂钟时间比 UTC 晚发生，所以 ts_newyork - ts_utc = 5 小时
    assert ts_newyork - ts_utc == 5 * 3600 * 1000, "America/New_York 应比 UTC 晚 5 小时"

def test_parse_date_to_ts_utc():
    """
    验证传入 source_tz="UTC" 时，生成的 timestamp 与挂钟时间完全一致
    """
    ts = parse_date_to_ts("2024-01-01", source_tz="UTC")
    
    # UTC 的 2024-01-01 00:00:00
    expected_dt = datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC"))
    expected_ts = int(expected_dt.timestamp() * 1000)
    
    assert ts == expected_ts, f"预期 {expected_ts}，实际 {ts}"

def test_parse_date_to_ts_integer_passthrough():
    """
    测试整数输入直接返回（透传）
    """
    test_ts = 1704067200000  # 2024-01-01 00:00:00 Asia/Shanghai
    result = parse_date_to_ts(test_ts)
    assert result == test_ts

def test_parse_date_to_ts_invalid_format():
    """
    测试无效格式抛出 ValueError
    """
    with pytest.raises(ValueError):
        parse_date_to_ts("2024/01/01")  # 错误的格式
    
    with pytest.raises(ValueError):
        parse_date_to_ts("invalid-date")

def test_ts_to_iso_format():
    """
    测试 ts_to_iso 的格式是否符合 ISO8601 with timezone offset
    """
    # 1704067200000 毫秒戳 = UTC 2024-01-01 00:00:00 = Asia/Shanghai 2024-01-01 08:00:00
    ts = 1704067200000
    iso_str = ts_to_iso(ts, display_tz="Asia/Shanghai")
    
    # 验证格式（Asia/Shanghai 时区，包含偏移）
    assert iso_str == "2024-01-01T08:00:00.000+08:00", f"预期 '2024-01-01T08:00:00.000+08:00'，实际 '{iso_str}'"
    
    # 验证包含 T 分隔符
    assert "T" in iso_str
    # 验证包含毫秒部分
    assert "." in iso_str
    # 验证包含时区偏移
    assert "+08:00" in iso_str

def test_ts_to_iso_cross_timezone():
    """
    验证 ts_to_iso 生成的字符串尾缀是否随 display_tz 参数动态变化
    """
    ts = 1704067200000  # UTC 2024-01-01 00:00:00
    
    # Asia/Shanghai
    iso_shanghai = ts_to_iso(ts, display_tz="Asia/Shanghai")
    assert iso_shanghai.endswith("+08:00"), f"Asia/Shanghai 应以 '+08:00' 结尾，实际: {iso_shanghai}"
    assert iso_shanghai == "2024-01-01T08:00:00.000+08:00"
    
    # UTC
    iso_utc = ts_to_iso(ts, display_tz="UTC")
    assert iso_utc.endswith("+00:00"), f"UTC 应以 '+00:00' 结尾，实际: {iso_utc}"
    assert iso_utc == "2024-01-01T00:00:00.000+00:00"
    
    # America/New_York (冬季 EST，UTC-5)
    iso_newyork = ts_to_iso(ts, display_tz="America/New_York")
    assert iso_newyork.endswith("-05:00"), f"America/New_York 应以 '-05:00' 结尾，实际: {iso_newyork}"
    assert iso_newyork == "2023-12-31T19:00:00.000-05:00"
    
    # Asia/Tokyo (UTC+9)
    iso_tokyo = ts_to_iso(ts, display_tz="Asia/Tokyo")
    assert iso_tokyo.endswith("+09:00"), f"Asia/Tokyo 应以 '+09:00' 结尾，实际: {iso_tokyo}"
    assert iso_tokyo == "2024-01-01T09:00:00.000+09:00"

def test_ts_to_iso_summer_time():
    """
    测试夏令时验证：使用 America/New_York 测试 6 月份数据，验证 datetime 后缀应自动为 -04:00
    """
    # 2024-06-01 12:00:00 UTC
    dt_utc = datetime(2024, 6, 1, 12, 0, 0, tzinfo=ZoneInfo("UTC"))
    ts = int(dt_utc.timestamp() * 1000)
    
    # America/New_York 在 6 月份使用 EDT (UTC-4)
    iso_newyork_summer = ts_to_iso(ts, display_tz="America/New_York")
    assert iso_newyork_summer.endswith("-04:00"), f"America/New_York 夏令时应以 '-04:00' 结尾，实际: {iso_newyork_summer}"
    # UTC 12:00 = EDT 08:00
    assert iso_newyork_summer == "2024-06-01T08:00:00.000-04:00"

def test_ts_to_iso_with_milliseconds():
    """
    测试带毫秒的时间戳转换
    """
    # 2024-01-01 12:30:45.123 Asia/Shanghai
    dt = datetime(2024, 1, 1, 12, 30, 45, 123000, tzinfo=ZoneInfo("Asia/Shanghai"))
    ts = int(dt.timestamp() * 1000)
    
    iso_str = ts_to_iso(ts, display_tz="Asia/Shanghai")
    assert iso_str == "2024-01-01T12:30:45.123+08:00"

def test_ts_to_str_custom_format():
    """
    测试 ts_to_str 自定义格式
    """
    ts = 1704067200000  # 2024-01-01 00:00:00 Asia/Shanghai
    
    # 测试日期格式
    date_str = ts_to_str(ts, fmt="%Y-%m-%d", display_tz="Asia/Shanghai")
    assert date_str == "2024-01-01"
    
    # 测试日期时间格式（Asia/Shanghai 时区）
    datetime_str = ts_to_str(ts, fmt="%Y-%m-%d %H:%M:%S", display_tz="Asia/Shanghai")
    assert datetime_str == "2024-01-01 08:00:00"
    
    # 测试中文格式
    cn_str = ts_to_str(ts, fmt="%Y年%m月%d日", display_tz="Asia/Shanghai")
    assert cn_str == "2024年01月01日"
    
    # 测试不同时区
    datetime_utc = ts_to_str(ts, fmt="%Y-%m-%d %H:%M:%S", display_tz="UTC")
    assert datetime_utc == "2024-01-01 00:00:00"

def test_ts_to_str_zero_and_none_input():
    """
    测试 ts=0 返回 1970-01-01，None 返回空字符串
    """
    assert ts_to_str(0) == "1970-01-01"
    assert ts_to_str(None) == ""
    assert ts_to_iso(0) == "1970-01-01T08:00:00.000+08:00"
    assert ts_to_iso(None) == ""

def test_parse_date_to_ts_pre_1970():
    """
    测试早于 1970 年的日期（如 1900-01-01 或空字符串）自动规正/下限截断为 ts=0
    """
    assert parse_date_to_ts("1900-01-01") == 0
    assert parse_date_to_ts("") == 0
    assert parse_date_to_ts(0) == 0

def test_cross_timezone_verification():
    """
    跨时区验证：如果 source_tz="UTC" 且 display_tz="Asia/Shanghai"，北京时间 8 点的数据生成的 timestamp 是否为 0？
    正确：UTC 0点即北京8点
    """
    # UTC 2024-01-01 00:00:00 = Asia/Shanghai 2024-01-01 08:00:00
    ts = parse_date_to_ts("2024-01-01", source_tz="UTC")
    
    # 验证 timestamp 为 0 (UTC epoch)
    # 注意：这个 timestamp 不是 0，而是 2024-01-01 00:00:00 UTC 的毫秒戳
    # 2024-01-01 00:00:00 UTC = 1704067200000 毫秒
    expected_ts = 1704067200000
    assert ts == expected_ts, f"预期 {expected_ts}，实际 {ts}"
    
    # 验证 display 为 Asia/Shanghai 时显示 08:00:00
    iso_str = ts_to_iso(ts, display_tz="Asia/Shanghai")
    assert iso_str == "2024-01-01T08:00:00.000+08:00"


def test_align_to_day_start_and_end():
    """测试 align_to_day_start 和 align_to_day_end 准确对齐到当天零点与末尾"""
    # 2024-06-01 15:30:45.123 Asia/Shanghai
    dt = datetime(2024, 6, 1, 15, 30, 45, 123000, tzinfo=ZoneInfo("Asia/Shanghai"))
    ts = int(dt.timestamp() * 1000)

    start_ts = align_to_day_start(ts, display_tz="Asia/Shanghai")
    end_ts = align_to_day_end(ts, display_tz="Asia/Shanghai")

    assert ts_to_iso(start_ts) == "2024-06-01T00:00:00.000+08:00"
    assert ts_to_iso(end_ts) == "2024-06-01T23:59:59.999+08:00"

    # 空值防御
    assert align_to_day_start(0) == 0
    assert align_to_day_end(0) == 0


def test_ts_to_str_microsecond_and_overflow():
    """测试 format 包含 %f 时的毫秒截断与溢出容错"""
    dt = datetime(2024, 6, 1, 12, 0, 0, 123456, tzinfo=ZoneInfo("Asia/Shanghai"))
    ts = int(dt.timestamp() * 1000)

    res = ts_to_str(ts, fmt="%Y-%m-%d %H:%M:%S.%f")
    assert res == "2024-06-01 12:00:00.123"

    # 极大溢出时间戳
    assert ts_to_str(10**18) == "1970-01-01"
    assert ts_to_iso(10**18) == ""