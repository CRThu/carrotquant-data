import pytest
import polars as pl
from pathlib import Path
from cq.data.storage.parquet_storage import ParquetStorage
from cq.data.service.metadata_manager import MetadataManager


def _stamp_metadata(storage, table_id, df, category="timeseries", mode="append", sort_keys=None):
    """辅助函数：为测试收敛分片并生成元数据，完成任务生命周期闭环"""
    storage.finalize(table_id, mode=mode, sort_keys=sort_keys)
    meta_mgr = MetadataManager(storage.data_dir.parent)
    meta_mgr.save(table_id, "parquet", {
        "table_id": table_id, 
        "category": category, 
        "format": "parquet",
        "schema": {k: str(v) for k, v in df.schema.items()}
    })


def test_parquet_storage_write_read(temp_data_dir):
    """
    测试 Parquet 的 Hive 分区写入（按年/月分区）
    """
    storage = ParquetStorage(str(temp_data_dir / "parquet"))
    table_id = "test.parquet.write_read"
    
    # 写入 2023 年 1 月的数据
    df = pl.DataFrame({
        "timestamp": [1672531200000, 1672617600000],  # 2023-01-01, 2023-01-02
        "datetime": ["2023-01-01T00:00:00.000", "2023-01-02T00:00:00.000"],
        "symbol": ["sh.600000"] * 2,
        "open": [10.0, 10.5],
        "high": [10.5, 11.0],
        "low": [9.5, 10.0],
        "close": [10.2, 10.8],
        "volume": [1000000, 1100000]
    })
    
    storage.write_series(table_id, df)
    _stamp_metadata(storage, table_id, df)
    
    # 验证文件系统中是否生成了 year=2023/data.parquet 这种结构的路径
    year_dir = temp_data_dir / "parquet" / table_id / "year=2023"
    assert year_dir.exists(), "2023 年目录应该存在"
    
    parquet_file = year_dir / "data.parquet"
    assert parquet_file.exists(), "data.parquet 文件应该存在"
    
    # 验证读取回的数据顺序和长度
    read_df = storage.read_series(table_id, "sh.600000", 2023)
    assert len(read_df) == 2, "应该读取到 2 条记录"
    
    # 验证数据按 timestamp 升序排列
    timestamps = read_df["timestamp"].to_list()
    assert timestamps == sorted(timestamps), "数据应该按 timestamp 升序排列"
    
    # 验证数据内容
    assert read_df["symbol"].to_list() == ["sh.600000", "sh.600000"]
    assert read_df["close"].to_list() == [10.2, 10.8]


def test_parquet_storage_deduplication(temp_data_dir):
    """
    测试 Parquet 存储层的幂等/去重能力
    写入两条具有相同 symbol 和 timestamp 但数值不同的数据，验证读取时应仅保留最新的一条
    """
    storage = ParquetStorage(str(temp_data_dir / "parquet"))
    table_id = "test.parquet.dedup"
    
    # 第一次写入
    df1 = pl.DataFrame({
        "timestamp": [1672531200000, 1672617600000],
        "datetime": ["2023-01-01T00:00:00.000", "2023-01-02T00:00:00.000"],
        "symbol": ["sh.600000"] * 2,
        "close": [10.0, 10.5]
    })
    storage.write_series(table_id, df1)
    _stamp_metadata(storage, table_id, df1)
    
    # 第二次写入，包含相同 timestamp 但不同数值的数据
    df2 = pl.DataFrame({
        "timestamp": [1672617600000, 1672704000000],  # 2023-01-02 重复，2023-01-03 新增
        "datetime": ["2023-01-02T00:00:00.000", "2023-01-03T00:00:00.000"],
        "symbol": ["sh.600000"] * 2,
        "close": [99.9, 11.0]  # 01-02 的值被修改
    })
    storage.write_series(table_id, df2)
    storage.finalize(table_id, mode="append")
    
    # 读取数据
    read_df = storage.read_series(table_id, "sh.600000", 2023)
    
    # 验证去重逻辑：应该保留 3 条记录（01-01, 01-02, 01-03）
    assert len(read_df) == 3, "去重后应该有 3 条记录"
    
    # 验证 01-02 的值是最后一次写入的值（99.9）
    row_0102 = read_df.filter(pl.col("timestamp") == 1672617600000)
    assert row_0102["close"][0] == 99.9, "应该保留最后一次写入的数据"


def test_parquet_storage_sorting(temp_data_dir):
    """
    测试 Parquet 存储层的排序能力
    写入乱序的股票数据，验证物理磁盘上的 Parquet 文件内部是否已按照 timestamp 和 symbol 升序排列
    """
    storage = ParquetStorage(str(temp_data_dir / "parquet"))
    table_id = "test.parquet.sorting"
    
    # 写入乱序数据
    df = pl.DataFrame({
        "timestamp": [1672704000000, 1672531200000, 1672617600000, 1672531200000],
        "datetime": ["2023-01-03T00:00:00.000", "2023-01-01T00:00:00.000", 
                     "2023-01-02T00:00:00.000", "2023-01-01T00:00:00.000"],
        "symbol": ["sz.000001", "sh.600000", "sh.600000", "sz.000001"],
        "close": [20.0, 10.0, 10.5, 19.5]
    })
    
    storage.write_series(table_id, df)
    _stamp_metadata(storage, table_id, df)
    
    # 验证逻辑层面的排序（通过 get_all_symbols）
    symbols = storage.get_all_symbols(table_id)
    assert symbols == sorted(symbols), "symbol 列表应该按字母顺序排列"
    
    # 验证物理存储的排序（直接读取 Parquet 文件）
    parquet_file = temp_data_dir / "parquet" / table_id / "year=2023" / "data.parquet"
    assert parquet_file.exists(), "Parquet 文件应该存在"
    
    # 直接读取物理文件验证排序
    physical_df = pl.read_parquet(parquet_file)
    
    # 验证 Symbol-First 排序：1. symbol 有序；2. 同一 symbol 内 timestamp 有序
    
    # 1. 验证 symbol 列是有序的
    physical_symbols = physical_df["symbol"].to_list()
    assert physical_symbols == sorted(physical_symbols), "物理文件中 symbol 应该按升序排列 (Primary Key)"
    
    # 2. 验证相同 symbol 内 timestamp 是有序的 (Secondary Key)
    for symbol in set(physical_symbols):
        symbol_df = physical_df.filter(pl.col("symbol") == symbol)
        symbol_timestamps = symbol_df["timestamp"].to_list()
        assert symbol_timestamps == sorted(symbol_timestamps), \
            f"Symbol {symbol} 的 timestamp 应该按升序排列"


def test_parquet_storage_cross_year(temp_data_dir):
    """
    测试 Parquet 存储层的跨年分区能力
    """
    storage = ParquetStorage(str(temp_data_dir / "parquet"))
    table_id = "test.parquet.cross_year"
    
    # 写入跨年数据
    df = pl.DataFrame({
        "timestamp": [1735689599000, 1735689600000],  # 2024-12-31 23:59:59 和 2025-01-01 00:00:00
        "datetime": ["2024-12-31T23:59:59.000", "2025-01-01T00:00:00.000"],
        "symbol": ["sh.600000"] * 2,
        "close": [10.5, 10.6]
    })
    
    storage.write_series(table_id, df)
    _stamp_metadata(storage, table_id, df)
    
    # 验证 2024 年目录和文件
    year_2024_dir = temp_data_dir / "parquet" / table_id / "year=2024"
    assert year_2024_dir.exists(), "2024 年目录应该存在"
    assert (year_2024_dir / "data.parquet").exists(), "data.parquet 文件应该存在"
    
    # 验证 2025 年目录和文件
    year_2025_dir = temp_data_dir / "parquet" / table_id / "year=2025"
    assert year_2025_dir.exists(), "2025 年目录应该存在"
    assert (year_2025_dir / "data.parquet").exists(), "data.parquet 文件应该存在"


def test_parquet_storage_multiple_symbols(temp_data_dir):
    """
    测试 Parquet 存储层的多 symbol 支持
    """
    storage = ParquetStorage(str(temp_data_dir / "parquet"))
    table_id = "test.parquet.multi_symbols"
    
    # 写入多个 symbol 的数据
    df = pl.DataFrame({
        "timestamp": [1672531200000] * 3,
        "datetime": ["2023-01-01T00:00:00.000"] * 3,
        "symbol": ["sh.600000", "sz.000001", "sz.000002"],
        "close": [10.0, 20.0, 30.0]
    })
    
    storage.write_series(table_id, df)
    _stamp_metadata(storage, table_id, df)
    
    # 验证所有 symbol 都能正确读取
    symbols = storage.get_all_symbols(table_id)
    assert set(symbols) == {"sh.600000", "sz.000001", "sz.000002"}
    
    # 验证每个 symbol 的数据量
    for symbol in symbols:
        symbol_df = storage.read_series(table_id, symbol, 2023)
        assert len(symbol_df) == 1, f"Symbol {symbol} 应该有 1 条记录"
        assert symbol_df["symbol"][0] == symbol


def test_parquet_storage_empty_write(temp_data_dir):
    """
    测试 Parquet 存储层的空数据写入拦截
    """
    storage = ParquetStorage(str(temp_data_dir / "parquet"))
    table_id = "test.parquet.empty"
    
    # 写入空 DataFrame
    empty_df = pl.DataFrame()
    storage.write_series(table_id, empty_df)
    
    # 验证不应该创建表目录
    table_dir = temp_data_dir / "parquet" / table_id
    assert not table_dir.exists(), "空数据不应该创建表目录"


def test_parquet_storage_metadata_stats(temp_data_dir):
    """
    测试 Parquet 存储层的统计接口
    """
    storage = ParquetStorage(str(temp_data_dir / "parquet"))
    table_id = "test.parquet.stats"
    
    # 写入跨年、多 symbol 的数据
    df = pl.DataFrame({
        "timestamp": [1672531200000, 1672617600000, 1735689600000],
        "datetime": ["2023-01-01T00:00:00.000", "2023-01-02T00:00:00.000", "2025-01-01T00:00:00.000"],
        "symbol": ["sh.600000", "sh.600000", "sz.000001"],
        "close": [10.0, 10.5, 20.0]
    })
    
    storage.write_series(table_id, df)
    _stamp_metadata(storage, table_id, df)
    
    # 验证统计方法
    total_bars = storage.get_total_bars(table_id)
    assert total_bars == 3, "总行数应该是 3"
    
    symbols = storage.get_all_symbols(table_id)
    assert len(symbols) == 2, "symbol 数量应该是 2"
    
    timestamps = storage.get_unique_timestamps(table_id)
    assert len(timestamps) == 3, "唯一的 timestamp 数量应该是 3"
    
    time_range = storage.get_global_time_range(table_id)
    assert time_range[0] == 1672531200000, "最小时间戳应该是 2023-01-01"
    assert time_range[1] == 1735689600000, "最大时间戳应该是 2025-01-01"


def test_parquet_storage_ev_no_symbol(temp_data_dir):
    """
    测试 Parquet 存储对无 symbol 列 EV 数据的处理
    验证系统能够正确处理没有 symbol 列的宏观数据（如利率、指数成分变动）
    """
    storage = ParquetStorage(str(temp_data_dir / "parquet"), category="event")
    table_id = "test.parquet.ev_no_symbol"
    
    # 创建测试数据：没有 symbol 列，只有 timestamp 和 value
    df = pl.DataFrame({
        "timestamp": [1704067200000, 1704153600000, 1704240000000],  # 2024-01-01, 02, 03
        "value": [100.0, 101.0, 102.0]
    })
    
    # 写入数据
    storage.write_event(table_id, df, mode="overwrite", sort_keys=["timestamp"])
    _stamp_metadata(storage, table_id, df, category="event", mode="overwrite", sort_keys=["timestamp"])
    
    # 验证文件创建
    table_dir = temp_data_dir / "parquet" / table_id
    data_file = table_dir / "year=2024" / "data.parquet"
    
    assert data_file.exists(), "数据文件未创建"
    
    # 读取数据验证
    read_df = storage.read_event(table_id, 2024)
    
    # 验证数据完整性
    assert len(read_df) == 3, f"期望3行数据，实际得到{len(read_df)}行"
    assert "timestamp" in read_df.columns, "缺少timestamp列"
    assert "value" in read_df.columns, "缺少value列"
    assert "symbol" not in read_df.columns, "不应存在symbol列"
    
    # 测试增量写入（验证全行去重逻辑）
    df_new = pl.DataFrame({
        "timestamp": [
            1704067200000,  # 01-01: 与第一笔数据完全相同 -> 应被去重合并
            1704153600000,  # 01-02: timestamp 相同但 value 不同 -> 应均被保留 (README 规范：全行去重)
            1704326400000   # 01-04: 全新数据 -> 应新增
        ],
        "value": [100.0, 101.5, 103.0]
    })
    
    storage.write_event(table_id, df_new, mode="append", sort_keys=["timestamp"])
    storage.finalize(table_id, mode="append", sort_keys=["timestamp"])
    
    # 重新读取验证
    read_df_final = storage.read_event(table_id, 2024)
    
    # 验证去重结果：同样应为 5 行
    assert len(read_df_final) == 5, f"期望 5 行（验证全行去重）：原有3 + 新增2，当前 {len(read_df_final)}"
    
    # 测试 get_all_symbols 方法（应该返回空列表，因为没有 symbol 列）
    symbols = storage.get_all_symbols(table_id)
    assert symbols == [], f"期望返回空列表，实际得到 {symbols}"


def test_parquet_read_without_metadata_raises(temp_data_dir):
    """
    测试 Parquet 读取无 metadata.json 时应抛出 RuntimeError
    """
    storage = ParquetStorage(str(temp_data_dir / "parquet"))
    table_id = "test.parquet.no_metadata"

    # 手动创建 Parquet 文件但不创建 metadata.json
    year_dir = temp_data_dir / "parquet" / table_id / "year=2024"
    year_dir.mkdir(parents=True, exist_ok=True)
    parquet_file = year_dir / "data.parquet"

    df = pl.DataFrame({
        "timestamp": [1704067200000],
        "datetime": ["2024-01-01T00:00:00.000+08:00"],
        "symbol": ["sh.600000"],
        "close": [10.0]
    })
    df.write_parquet(parquet_file)

    # 读取应抛出 RuntimeError
    with pytest.raises(RuntimeError) as exc_info:
        storage.read_series(table_id, "sh.600000", 2024)
    assert "Metadata not found" in str(exc_info.value)


def test_parquet_read_with_schema_override(temp_data_dir):
    """
    测试 Parquet 读取支持 schema_override 参数
    """
    storage = ParquetStorage(str(temp_data_dir / "parquet"))
    table_id = "test.parquet.schema_override"

    df = pl.DataFrame({
        "timestamp": [1704067200000],
        "datetime": ["2024-01-01T00:00:00.000+08:00"],
        "symbol": ["sh.600000"],
        "close": [10.0]
    })
    storage.write_series(table_id, df)
    _stamp_metadata(storage, table_id, df)

    # 读取时传入 schema_override
    path = storage._get_series_path(table_id, 2024)
    read_df = storage._read_with_schema(table_id, path, schema_override={"timestamp": pl.Int64, "datetime": pl.String, "symbol": pl.String, "close": pl.Float64})
    assert len(read_df) == 1
    assert read_df["close"][0] == 10.0


def test_parquet_write_series_with_schema_cast(temp_data_dir):
    """
    测试 Parquet 写入后的数据类型一致性
    """
    storage = ParquetStorage(str(temp_data_dir / "parquet"))
    table_id = "test.parquet.schema_cast"

    df = pl.DataFrame({
        "timestamp": [1704067200000, 1704153600000],
        "datetime": ["2024-01-01T00:00:00.000+08:00", "2024-01-02T00:00:00.000+08:00"],
        "symbol": ["sh.600000", "sh.600000"],
        "open": [10.0, 10.5],
        "high": [10.5, 11.0],
        "low": [9.5, 10.0],
        "close": [10.2, 10.8],
        "volume": [1000000, 1100000]
    })
    storage.write_series(table_id, df)
    _stamp_metadata(storage, table_id, df)

    # 读取后验证所有数值列的类型（Parquet 读取按 metadata schema cast）
    read_df = storage.read_series(table_id, "sh.600000", 2024)
    assert read_df["timestamp"].dtype == pl.Int64
    assert read_df["open"].dtype == pl.Float64
    assert read_df["high"].dtype == pl.Float64
    assert read_df["low"].dtype == pl.Float64
    assert read_df["close"].dtype == pl.Float64
    assert read_df["symbol"].dtype == pl.String


# ---------------------------------------------------------------------------
# 批处理分片暂存 (Staging) 与流式合并 (Finalize / Cleanup) 机制测试
# ---------------------------------------------------------------------------

def test_parquet_write_series_staging_and_finalize(tmp_path: Path):
    """验证 TS 模式下的分片写入与最终收敛合并 (Finalize)"""
    storage = ParquetStorage(data_dir=str(tmp_path), category="timeseries")
    table_id = "test.kline.1m.raw.mock"

    # Batch 1: symbol 000001
    df1 = pl.DataFrame({
        "symbol": ["000001", "000001"],
        "timestamp": [1735689600000, 1735689660000],  # 2025-01-01
        "datetime": ["2025-01-01T08:00:00+08:00", "2025-01-01T08:01:00+08:00"],
        "close": [10.0, 10.5],
    })

    # Batch 2: symbol 000002
    df2 = pl.DataFrame({
        "symbol": ["000002", "000002"],
        "timestamp": [1735689600000, 1735689660000],  # 2025-01-01
        "datetime": ["2025-01-01T08:00:00+08:00", "2025-01-01T08:01:00+08:00"],
        "close": [20.0, 20.5],
    })

    # 写入两个批次的分片
    storage.write_series(table_id, df1)
    storage.write_series(table_id, df2)

    stage_dir = tmp_path / table_id / "year=2025" / ".staging"
    final_file = tmp_path / table_id / "year=2025" / "data.parquet"

    # 验证此时分片在 .staging 中，final 尚未落盘
    assert stage_dir.exists()
    staging_parts = list(stage_dir.glob("*.parquet"))
    assert len(staging_parts) == 2
    assert not final_file.exists()

    # 执行收敛合并
    storage.finalize(table_id, mode="append")

    # 验证收敛后 .staging 已清除，final_file 生成且数据完整
    assert not stage_dir.exists()
    assert final_file.exists()

    res = pl.read_parquet(final_file)
    assert len(res) == 4
    assert res["symbol"].to_list() == ["000001", "000001", "000002", "000002"]


def test_parquet_staging_append_override(tmp_path: Path):
    """验证 finalize(mode='append') 时对同一 [symbol, timestamp] 的新数据覆盖更新"""
    storage = ParquetStorage(data_dir=str(tmp_path), category="timeseries")
    table_id = "test.kline.1m.raw.mock"

    # 初始历史数据写入并 finalize 提交
    old_df = pl.DataFrame({
        "symbol": ["000001", "000002"],
        "timestamp": [1735689600000, 1735689600000],
        "datetime": ["2025-01-01T08:00:00+08:00", "2025-01-01T08:00:00+08:00"],
        "close": [10.0, 20.0],
    })
    storage.write_series(table_id, old_df)
    storage.finalize(table_id, mode="overwrite")

    # 增量批次写入分片 (更新 000001，新增 000003)
    patch_df = pl.DataFrame({
        "symbol": ["000001", "000003"],
        "timestamp": [1735689600000, 1735689660000],
        "datetime": ["2025-01-01T08:00:00+08:00", "2025-01-01T08:01:00+08:00"],
        "close": [15.5, 30.0],  # 000001 更新为 15.5
    })
    storage.write_series(table_id, patch_df)

    # 执行 finalize
    storage.finalize(table_id, mode="append")

    final_file = tmp_path / table_id / "year=2025" / "data.parquet"
    res = pl.read_parquet(final_file)
    assert len(res) == 3

    # 验证 000001 价格被更新为 15.5
    row_000001 = res.filter(pl.col("symbol") == "000001")
    assert row_000001["close"][0] == 15.5


def test_parquet_staging_overwrite(tmp_path: Path):
    """验证 finalize(mode='overwrite') 时丢弃旧数据，仅保留新暂存数据"""
    storage = ParquetStorage(data_dir=str(tmp_path), category="timeseries")
    table_id = "test.kline.1m.raw.mock"

    old_df = pl.DataFrame({
        "symbol": ["OLD_SYM"],
        "timestamp": [1735689600000],
        "datetime": ["2025-01-01T08:00:00+08:00"],
        "close": [99.9],
    })
    storage.write_series(table_id, old_df)
    storage.finalize(table_id, mode="overwrite")

    new_df = pl.DataFrame({
        "symbol": ["NEW_SYM"],
        "timestamp": [1735689600000],
        "datetime": ["2025-01-01T08:00:00+08:00"],
        "close": [1.1],
    })
    storage.write_series(table_id, new_df)

    # 强制覆盖收敛
    storage.finalize(table_id, mode="overwrite")

    final_file = tmp_path / table_id / "year=2025" / "data.parquet"
    res = pl.read_parquet(final_file)
    assert len(res) == 1
    assert res["symbol"][0] == "NEW_SYM"


def test_parquet_cleanup(tmp_path: Path):
    """验证异常时 cleanup 清理全部临时分片"""
    storage = ParquetStorage(data_dir=str(tmp_path), category="timeseries")
    table_id = "test.kline.1m.raw.mock"

    df = pl.DataFrame({
        "symbol": ["000001"],
        "timestamp": [1735689600000],
        "datetime": ["2025-01-01T08:00:00+08:00"],
        "close": [10.0],
    })
    storage.write_series(table_id, df)

    stage_dir = tmp_path / table_id / "year=2025" / ".staging"
    assert stage_dir.exists()

    storage.cleanup(table_id)
    assert not stage_dir.exists()


def test_parquet_write_event_staging_flat_and_partitioned(tmp_path: Path):
    """验证 EV 模式下平铺与 Hive 分区的暂存合并"""
    # 1. 平铺 EV (无 timestamp)
    storage_flat = ParquetStorage(data_dir=str(tmp_path), category="event")
    flat_table = "test.concept.mock"
    df_flat1 = pl.DataFrame({"board_code": ["BK001"], "symbol": ["000001"]})
    df_flat2 = pl.DataFrame({"board_code": ["BK001"], "symbol": ["000002"]})

    storage_flat.write_event(flat_table, df_flat1, sort_keys=["board_code", "symbol"])
    storage_flat.write_event(flat_table, df_flat2, sort_keys=["board_code", "symbol"])

    storage_flat.finalize(flat_table, mode="append", sort_keys=["board_code", "symbol"])
    flat_res = pl.read_parquet(tmp_path / flat_table / "data.parquet")
    assert len(flat_res) == 2
    assert flat_res["symbol"].to_list() == ["000001", "000002"]

    # 2. Hive 分区 EV (有 timestamp)
    storage_part = ParquetStorage(data_dir=str(tmp_path), category="event")
    part_table = "test.adj_factor.mock"
    df_part1 = pl.DataFrame({
        "symbol": ["000001"],
        "timestamp": [1735689600000],
        "datetime": ["2025-01-01T08:00:00+08:00"],
        "back_adj_factor": [1.0],
    })
    df_part2 = pl.DataFrame({
        "symbol": ["000002"],
        "timestamp": [1735689600000],
        "datetime": ["2025-01-01T08:00:00+08:00"],
        "back_adj_factor": [1.5],
    })
    storage_part.write_event(part_table, df_part1, sort_keys=["timestamp", "symbol"])
    storage_part.write_event(part_table, df_part2, sort_keys=["timestamp", "symbol"])

    storage_part.finalize(part_table, mode="append", sort_keys=["timestamp", "symbol"])
    part_res = pl.read_parquet(tmp_path / part_table / "year=2025" / "data.parquet")
    assert len(part_res) == 2
    assert sorted(part_res["symbol"].to_list()) == ["000001", "000002"]


def test_parquet_large_batch_streaming_simulation(tmp_path: Path):
    """
    模拟高频分钟线多批次落盘场景：
    连续 5 个批次，每批 20,000 行（累计 10 万行），验证分片暂存与最终流式合并零内存故障。
    """
    storage = ParquetStorage(data_dir=str(tmp_path), category="timeseries")
    table_id = "test.kline.1m.large_simulation"

    total_rows = 0
    base_ts = 1735689600000  # 2025-01-01 08:00:00

    # 模拟 5 个批次分片写入
    for batch_i in range(5):
        n_rows = 20000
        sym = f"sh.60000{batch_i}"
        df_batch = pl.DataFrame({
            "symbol": [sym] * n_rows,
            "timestamp": [base_ts + i * 60000 for i in range(n_rows)],
            "datetime": ["2025-01-01T08:00:00+08:00"] * n_rows,
            "open": [10.0] * n_rows,
            "high": [11.0] * n_rows,
            "low": [9.0] * n_rows,
            "close": [10.5] * n_rows,
            "volume": [1000.0] * n_rows,
        })
        storage.write_series(table_id, df_batch)
        total_rows += n_rows

    stage_dir = tmp_path / table_id / "year=2025" / ".staging"
    assert stage_dir.exists()
    assert len(list(stage_dir.glob("*.parquet"))) == 5

    # 最终统一收敛
    storage.finalize(table_id, mode="append")

    assert not stage_dir.exists()
    final_file = tmp_path / table_id / "year=2025" / "data.parquet"
    assert final_file.exists()

    # 验证行数与标的数
    scan_df = pl.scan_parquet(final_file)
    assert scan_df.select(pl.len()).collect().item() == total_rows
    unique_syms = scan_df.select("symbol").unique().collect()["symbol"].to_list()
    assert len(unique_syms) == 5


def test_parquet_storage_edge_cases_and_defense(tmp_path: Path):
    """
    边界与防御路径测试：
    1. write_event 空 DataFrame 拦截
    2. 平铺模式分片暂存后调用 cleanup 彻底清理
    3. read_series / read_event 未传 year 参数的参数校验拦截
    4. 不存在的 table_id 调用 finalize 和 cleanup 保证安全幂等不报错
    """
    storage_ts = ParquetStorage(data_dir=str(tmp_path), category="timeseries")
    storage_ev = ParquetStorage(data_dir=str(tmp_path), category="event")
    table_id = "test.parquet.defense"

    # 1. 空 DataFrame 写入防呆
    storage_ev.write_event(table_id, pl.DataFrame())
    assert not (tmp_path / table_id).exists()

    # 2. 平铺模式下的分片暂存与 cleanup
    flat_table = "test.concept.flat_cleanup"
    flat_df = pl.DataFrame({"board_code": ["BK001"], "symbol": ["000001"]})
    storage_ev.write_event(flat_table, flat_df, sort_keys=["board_code", "symbol"])
    flat_staging = tmp_path / flat_table / ".staging"
    assert flat_staging.exists()
    storage_ev.cleanup(flat_table)
    assert not flat_staging.exists()

    # 3. read 未指定 year 异常抛出
    with pytest.raises(ValueError, match="Year must be specified for reading series data"):
        storage_ts.read_series(table_id, "000001", year=None)

    with pytest.raises(ValueError, match="Year must be specified for partitioned event data"):
        storage_ev.read_event(table_id, year=None)

    # 4. 幂等安全性：对不存在的 table 执行 finalize / cleanup
    non_existent_table = "test.parquet.non_existent"
    storage_ts.finalize(non_existent_table)
    storage_ts.cleanup(non_existent_table)


def test_parquet_finalize_anti_join_overwrite_and_progress_callback(tmp_path: Path):
    """
    深度验证：
    1. mode="append" 且旧文件存在时，新数据对旧数据精准覆盖 (Anti-Join keep="last" 语义)
    2. progress_callback 进度回调函数在收敛落盘时被准确触发
    """
    storage = ParquetStorage(data_dir=str(tmp_path), category="timeseries")
    table_id = "test.kline.1m.anti_join_test"

    # 1. 模拟旧主库：2025年有 000001 和 000002 两个标的，各 2 条历史记录 (close=10.0)
    old_df = pl.DataFrame({
        "symbol": ["000001", "000001", "000002", "000002"],
        "timestamp": [1735689600000, 1735689660000, 1735689600000, 1735689660000],
        "datetime": [
            "2025-01-01T08:00:00+08:00",
            "2025-01-01T08:01:00+08:00",
            "2025-01-01T08:00:00+08:00",
            "2025-01-01T08:01:00+08:00",
        ],
        "close": [10.0, 10.0, 20.0, 20.0],
    })
    storage.write_series(table_id, old_df)
    storage.finalize(table_id, mode="overwrite")

    # 2. 模拟增量同步新分片：
    # 000001 在 1735689660000 发生修正 (close 从 10.0 覆盖为 99.0)，并新增 1735689720000 (close=100.0)
    # 000003 为全新加入标的
    patch_df = pl.DataFrame({
        "symbol": ["000001", "000001", "000003"],
        "timestamp": [1735689660000, 1735689720000, 1735689600000],
        "datetime": [
            "2025-01-01T08:01:00+08:00",
            "2025-01-01T08:02:00+08:00",
            "2025-01-01T08:00:00+08:00",
        ],
        "close": [99.0, 100.0, 30.0],
    })
    storage.write_series(table_id, patch_df)

    progress_records = []
    def record_progress(stage: str, cur: int, total: int):
        progress_records.append((stage, cur, total))

    # 3. 执行 finalize(mode="append")，带 progress_callback
    storage.finalize(table_id, mode="append", progress_callback=record_progress)

    # 验证 progress_callback 被触发
    assert len(progress_records) == 1
    assert progress_records[0] == ("year=2025", 1, 1)

    # 4. 验证合并后结果
    res = pl.read_parquet(tmp_path / table_id / "year=2025" / "data.parquet")
    
    # 总行数：旧4条 - 重叠1条 + 新3条 = 6条
    assert len(res) == 6

    # 验证 000001 在 1735689660000 的 close 已经被新数据 99.0 覆盖
    overwritten_row = res.filter(
        (pl.col("symbol") == "000001") & (pl.col("timestamp") == 1735689660000)
    )
    assert len(overwritten_row) == 1
    assert overwritten_row["close"][0] == 99.0

    # 验证未被重叠的 000001 第一条 (close=10.0) 和 000002 依然完整保留
    row_000001_first = res.filter(
        (pl.col("symbol") == "000001") & (pl.col("timestamp") == 1735689600000)
    )
    assert row_000001_first["close"][0] == 10.0

    row_000002 = res.filter(pl.col("symbol") == "000002")
    assert len(row_000002) == 2
    assert row_000002["close"].to_list() == [20.0, 20.0]

    # 验证全新标的 000003 正确补入
    row_000003 = res.filter(pl.col("symbol") == "000003")
    assert len(row_000003) == 1
    assert row_000003["close"][0] == 30.0

