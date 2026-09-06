"""
tests/unit/test_storage_concurrency.py

高并发多线程物理文件落盘原子安全性与防冲突测试。
验证多线程同时调用 CSVStorage / ParquetStorage 写入同一 table_id 时，.tmp -> os.replace 策略的可靠性。
"""

import concurrent.futures
import polars as pl
from cq.data.storage.csv_storage import CSVStorage
from cq.data.storage.parquet_storage import ParquetStorage


def test_csv_storage_multithreaded_concurrency(tmp_path):
    """验证多线程并发向同一 CSVStorage 表写入时，原子落盘不报错且无废文件残留"""
    from cq.data.service.metadata_manager import MetadataManager
    storage = CSVStorage(str(tmp_path / "csv"))
    table_id = "ashare.kline.1d.raw.baostock"

    def worker_write(thread_id: int):
        df = pl.DataFrame({
            "timestamp": [1704067200000 + i * 86400000 for i in range(10)],
            "datetime": [f"2024-01-0{i+1}T15:00:00.000+08:00" for i in range(10)],
            "symbol": ["sh.600000"] * 10,
            "close": [10.0 + thread_id] * 10
        })
        storage.write_series(table_id, df, mode="append")

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(worker_write, tid) for tid in range(10)]
        for f in concurrent.futures.as_completed(futures):
            f.result()

    meta_mgr = MetadataManager(str(tmp_path))
    meta_mgr.save(table_id, "csv", {
        "table_id": table_id,
        "schema": {"timestamp": "Int64", "datetime": "String", "symbol": "String", "close": "Float64"}
    })

    df_read = storage.read_series(table_id, symbol="sh.600000", year=2024)
    assert len(df_read) == 10

    table_dir = tmp_path / "csv" / table_id
    tmp_files = list(table_dir.glob("**/*.tmp"))
    assert len(tmp_files) == 0


def test_parquet_storage_multithreaded_concurrency(tmp_path):
    """验证多线程并发向同一 ParquetStorage 表写入时，原子落盘不报错且无废文件残留"""
    from cq.data.service.metadata_manager import MetadataManager
    storage = ParquetStorage(str(tmp_path / "parquet"))
    table_id = "ashare.kline.1d.adj.baostock"

    def worker_write(thread_id: int):
        df = pl.DataFrame({
            "timestamp": [1704067200000 + i * 86400000 for i in range(10)],
            "datetime": [f"2024-01-0{i+1}T15:00:00.000+08:00" for i in range(10)],
            "symbol": ["sh.600000"] * 10,
            "close": [20.0 + thread_id] * 10
        })
        storage.write_series(table_id, df, mode="append")

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(worker_write, tid) for tid in range(10)]
        for f in concurrent.futures.as_completed(futures):
            f.result()

    storage.finalize(table_id)

    meta_mgr = MetadataManager(str(tmp_path))
    meta_mgr.save(table_id, "parquet", {
        "table_id": table_id,
        "schema": {"timestamp": "Int64", "datetime": "String", "symbol": "String", "close": "Float64"}
    })

    df_read = storage.read_series(table_id, symbol="sh.600000", year=2024)
    assert len(df_read) == 10

    table_dir = tmp_path / "parquet" / table_id
    tmp_files = list(table_dir.glob("**/*.tmp"))
    assert len(tmp_files) == 0
