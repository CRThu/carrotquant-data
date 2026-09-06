import pytest
import polars as pl
from unittest.mock import MagicMock, patch
from cq.data.service.sync_manager import SyncManager

@pytest.fixture
def sync_manager():
    with patch("cq.data.service.sync_manager.MetadataManager"), \
         patch("cq.data.service.sync_manager.TaskPlanner"), \
         patch("cq.data.service.sync_manager.ProviderManager"), \
         patch("cq.data.service.sync_manager.StorageFactory"):
        sm = SyncManager()
        yield sm

def test_sync_manager_batch_write(sync_manager):
    table_id = "test.table"
    format = "parquet"
    start_date = "2023-01-01"
    end_date = "2023-01-10"
    
    # 模拟 10 支股票
    symbols = [f"SZ{i:06d}" for i in range(10)]
    
    # 模拟 Planner
    sync_manager.planner.plan.return_value = [{"symbol": s, "start": 0, "end": 0} for s in symbols]
    
    # 模拟 Provider
    provider = MagicMock()
    # 每次 fetch 返回一个简单的 DataFrame
    provider.fetch.side_effect = lambda tid, sym, s, e: pl.DataFrame({
        "symbol": [sym],
        "timestamp": [1672531200000],
        "close": [10.0]
    })
    sync_manager.provider_mgr.get_provider.return_value = provider
    provider.get_all_symbols.return_value = symbols
    
    # 模拟 Provider
    provider.get_table_category.return_value = "timeseries"
    
    # 模拟 Storage
    storage = MagicMock()
    # 设置 Storage 返回规范值
    storage.get_all_symbols.return_value = symbols
    storage.get_total_bars.return_value = 10
    storage.get_global_time_range.return_value = (0, 0)
    storage.get_unique_timestamps.return_value = []
    storage.read.return_value = pl.DataFrame()
    storage.category = "timeseries"
    
    # 直接在 sync_manager 的 mock StorageFactory 上设置返回值
    from cq.data.service import sync_manager as sm_mod
    sync_manager.storage_root = "test_root"
    
    # 注意：sync_manager.py 中 StorageFactory 已被 fixture patch 为 MagicMock
    # 我们只需要配置这个已有的 mock
    with patch("cq.data.service.sync_manager.StorageFactory.get_storage", return_value=storage):
        # 设置 batch_size=3
        # 10 支股票，batch_size=3，应调用 storage.write_series 4 次 (3+3+3+1)
        sync_manager.sync(table_id, format, start_date, end_date, batch_size=3)
        
        # 验证调用次数：每批调用 write_series (写分片)，全部结束后调用 finalize (收敛)
        assert storage.write_series.call_count == 4
        assert storage.finalize.call_count == 1
        
        # 验证第一次写入分片的内容 (包含 3 支股票)
        first_write_df = storage.write_series.call_args_list[0][0][1] # 第二个参数是 df
        assert len(first_write_df) == 3
        assert first_write_df["symbol"].to_list() == symbols[:3]
        
        # 验证最后一次写入分片的内容
        last_write_df = storage.write_series.call_args_list[3][0][1]
        assert len(last_write_df) == 1
        assert last_write_df["symbol"].to_list() == symbols[9:]


def test_sync_manager_interrupted_batch_does_not_update_metadata(sync_manager):
    """
    测试当同步在中途某批次抛出异常中断时，
    已落盘数据成功下沉，但 _update_metadata 绝对不会提前被调用更新元数据，
    防止水位线虚高导致断网恢复后丢失历史数据，同时触发 cleanup_staging 清理临时分片。
    """
    table_id = "test.table"
    format = "parquet"
    symbols = [f"SZ{i:06d}" for i in range(6)]
    
    sync_manager.planner.plan.return_value = [{"symbol": s, "start": 0, "end": 0} for s in symbols]
    
    provider = MagicMock()
    # 模拟第 4 个 symbol 时抛出异常中断 (模拟断网)
    def mock_fetch(tid, sym, s, e):
        if sym == "SZ000003":
            raise ConnectionError("Network disconnected in batch 2")
        return pl.DataFrame({"symbol": [sym], "timestamp": [1672531200000], "close": [10.0]})
        
    provider.fetch.side_effect = mock_fetch
    sync_manager.provider_mgr.get_provider.return_value = provider
    provider.get_all_symbols.return_value = symbols
    provider.get_table_category.return_value = "timeseries"
    
    storage = MagicMock()
    storage.category = "timeseries"
    
    with patch("cq.data.service.sync_manager.StorageFactory.get_storage", return_value=storage), \
         patch.object(sync_manager, "_update_metadata") as mock_update_meta:
        # 设置 batch_size=3, 总共 6 支股票 (2 个批次)
        # 批次 1 (SZ000000~SZ000002) 成功，批次 2 (SZ000003...) 失败
        with pytest.raises(ConnectionError, match="Network disconnected in batch 2"):
            sync_manager.sync(table_id, format, batch_size=3)
            
        # 验证批次 1 确实落盘了 (write_series 调用了 1 次)
        assert storage.write_series.call_count == 1
        # 验证中断时执行了 cleanup
        assert storage.cleanup.call_count >= 1
        
        # 验证 _update_metadata 在中断发生时一次都没有被调用！(元数据未虚高盖章)
        assert mock_update_meta.call_count == 0


def test_sync_manager_real_parquet_staging_flow(tmp_path):
    """
    端到端集成测试：使用 tmp_path 隔离运行 SyncManager 真实落地，
    验证多批次暂存落盘 -> 最终收敛流式合并 -> 无 staging 残留。
    """
    from cq.data.service.sync_manager import SyncManager
    from cq.data.storage.parquet_storage import ParquetStorage

    table_id = "test.kline.1m.raw.staging_real"
    symbols = ["sh.600001", "sh.600002", "sh.600003", "sh.600004"]

    sm = SyncManager(data_dir=str(tmp_path))

    # Mock provider 返回两批数据
    mock_provider = MagicMock()
    mock_provider.get_all_symbols.return_value = symbols
    mock_provider.get_table_category.return_value = "timeseries"
    mock_provider.get_sort_keys.return_value = ["symbol", "timestamp"]
    mock_provider.fetch.side_effect = lambda tid, sym, s, e: pl.DataFrame({
        "symbol": [sym],
        "timestamp": [1735689600000],
        "datetime": ["2025-01-01T08:00:00+08:00"],
        "close": [10.0]
    })

    with patch.object(sm.provider_mgr, "get_provider", return_value=mock_provider):
        # 4 只股票，batch_size=2，分成 2 批处理
        sm.sync(table_id, formats=["parquet"], batch_size=2)

    final_file = tmp_path / "parquet" / table_id / "year=2025" / "data.parquet"
    assert final_file.exists()

    # 验证暂存目录已完全清除
    staging_dir = tmp_path / "parquet" / table_id / "year=2025" / ".staging"
    assert not staging_dir.exists()

    # 验证最终数据包含全量 4 只股票
    res = pl.read_parquet(final_file)
    assert len(res) == 4
    assert sorted(res["symbol"].to_list()) == symbols


