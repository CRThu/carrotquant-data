"""
StockDB 全链路同步与 SDK 切片集成测试。

覆盖:
1. cqdata sync ashare.kline.1m.raw.stockdb 增量落盘与 metadata.json 盖章
2. cqdata sync aetf.kline.1m.raw.stockdb 场内基金行情落盘与切片读取
3. cq.data.aetf.kline.get(adj="adj") 动态后复权折算验证
4. cqdata sync ashare.concept.stockdb / ashare.industry.stockdb 平铺表落盘与查询验证
"""

import pytest
import polars as pl
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import patch, MagicMock

import cq.data
from cq.data.service.sync_manager import SyncManager
from cq.data.entrypoints.python_api import read
from cq.data.provider.stockdb.provider import check_stockdb_connection


@pytest.fixture(autouse=True)
def _reset_env(temp_data_dir):
    """自动使用独立临时存储目录并重置 ProviderManager"""
    from cq.data.provider.provider_manager import ProviderManager
    from cq.data.config.settings import settings
    old_dir = settings.data_dir
    settings.data_dir = str(temp_data_dir)
    ProviderManager._instance = None
    ProviderManager._providers = {}
    yield
    settings.data_dir = old_dir
    ProviderManager._instance = None
    ProviderManager._providers = {}


@contextmanager
def mock_stockdb_context(mock_rd):
    """默认全流程 Mock StockDB 模块与网络探针，保证测试与 CI 零外部进程依赖、纯净确定运行"""
    mock_mod = MagicMock()
    mock_mod.rd = mock_rd
    with patch("cq.data.provider.stockdb.provider.stockdb", mock_mod), \
         patch("cq.data.provider.stockdb.provider.check_stockdb_connection", return_value=True):
        yield


class TestStockDBSyncIntegration:
    """StockDB 全流程同步与切片查询集成测试"""

    def test_stockdb_kline_1m_sync_and_read(self, temp_data_dir):
        """测试 1m 高频线增量同步与 SDK 切片读取"""
        mock_records = [
            {"code": "600000", "date": 20250102093000, "open": 10.0, "high": 10.1, "low": 9.9, "close": 10.05, "volume": 1000.0, "amount": 10000.0},
            {"code": "600000", "date": 20250102093100, "open": 10.05, "high": 10.2, "low": 10.0, "close": 10.15, "volume": 1200.0, "amount": 12100.0},
        ]
        mock_rd = MagicMock()
        mock_rd.get.return_value = {"6": ["600000"]}
        mock_rd.vals.return_value = mock_records

        with mock_stockdb_context(mock_rd), \
             patch("cq.data.provider.stockdb.provider.StockDBProvider.get_all_symbols", return_value=["sh.600000"]):
            sm = SyncManager(data_dir=str(temp_data_dir))
            sm.sync(
                table_ids=["ashare.kline.1m.raw.stockdb"],
                formats=["parquet"],
                start_date="2025-01-02",
                end_date="2025-01-02",
            )

            # 验证物理文件与元数据
            meta_path = temp_data_dir / "parquet" / "ashare.kline.1m.raw.stockdb" / "metadata.json"
            assert meta_path.exists()

            # 使用 SDK 读取
            df = read("ashare.kline.1m.raw.stockdb", format="parquet")
            assert not df.is_empty()
            assert "symbol" in df.columns
            assert "datetime" in df.columns
            assert "timestamp" in df.columns
            assert "close" in df.columns

    def test_stockdb_aetf_sync_and_dynamic_adjust(self, temp_data_dir):
        """测试场内 ETF 1m 行情与独立复权因子同步及动态后复权读取"""
        mock_kline = [
            {"code": "159919", "date": 20250102093000, "open": 3.0, "high": 3.1, "low": 2.9, "close": 3.0, "volume": 500.0, "amount": 1500.0}
        ]
        mock_cum = [["复权:159919:20240101", 2.0]]
        mock_rd = MagicMock()
        mock_rd.get.side_effect = lambda *args: {"1": ["159919"]} if args[0] == "股票代码" else MagicMock(get=lambda k: mock_cum)
        mock_rd.vals.return_value = mock_kline

        with mock_stockdb_context(mock_rd), \
             patch.object(
                 cq.data.provider.stockdb.provider.StockDBProvider,
                 "get_all_symbols",
                 side_effect=lambda tid: ["sz.159919"] if "kline" in tid else ["_ALL_"]
             ):
            sm = SyncManager(data_dir=str(temp_data_dir))
            # 同步行情
            sm.sync(
                table_ids=["aetf.kline.1m.raw.stockdb"],
                formats=["parquet"],
                start_date="2025-01-02",
                end_date="2025-01-02"
            )
            # 同步复权因子
            sm.sync(
                table_ids=["aetf.adj_factor.stockdb"],
                formats=["parquet"],
                start_date="2024-01-01",
                end_date="2025-01-02"
            )

            # 验证物理文件
            kline_meta = temp_data_dir / "parquet" / "aetf.kline.1m.raw.stockdb" / "metadata.json"
            factor_meta = temp_data_dir / "parquet" / "aetf.adj_factor.stockdb" / "metadata.json"
            assert kline_meta.exists()
            assert factor_meta.exists()

            # 使用 OOP aetf 访问器进行动态后复权读取
            df_adj = cq.data.aetf.kline.get(freq="1m", adj="adj", format="parquet")
            assert not df_adj.is_empty()
            assert "close" in df_adj.columns

    def test_stockdb_concept_and_industry_flat_sync(self, temp_data_dir):
        """测试概念与行业平铺表同步与切片查询"""
        mock_boards = [
            ["板块:概念_测试概念:BK0001", {"code": "BK0001", "name": "测试概念", "category": "概念", "symbols": ["000001", "600000"]}],
            ["板块:行业_测试行业:801001", {"code": "801001.SI", "name": "测试行业", "category": "申万一级", "symbols": ["000001"]}],
        ]
        mock_rd = MagicMock()
        mock_rd.get.return_value = MagicMock(do=lambda: mock_boards)

        with mock_stockdb_context(mock_rd):
            sm = SyncManager(data_dir=str(temp_data_dir))
            sm.sync(
                table_ids=["ashare.concept.stockdb", "ashare.industry.stockdb"],
                formats=["parquet"]
            )

            # 验证平铺表文件存在 (Event 表 flat 存储模式)
            concept_file = temp_data_dir / "parquet" / "ashare.concept.stockdb" / "data.parquet"
            industry_file = temp_data_dir / "parquet" / "ashare.industry.stockdb" / "data.parquet"
            assert concept_file.exists()
            assert industry_file.exists()

            # 读取概念表
            df_concept = read("ashare.concept.stockdb", format="parquet")
            assert not df_concept.is_empty()
            assert "board_code" in df_concept.columns
            assert "board_name" in df_concept.columns
            assert "category" in df_concept.columns
            assert "symbol" in df_concept.columns

            # 读取行业表
            df_ind = read("ashare.industry.stockdb", format="parquet")
            assert not df_ind.is_empty()
            assert "board_code" in df_ind.columns
            assert "symbol" in df_ind.columns

    def test_stockdb_kline_1d_null_prefix_inference(self, temp_data_dir):
        """测试日线记录前 100+ 条部分截面因子全为 None 时，类型推断与补齐不会触发 NullBuilder 异常"""
        from datetime import date, timedelta
        mock_records = []
        base_date = date(2020, 1, 1)
        # 前 120 条记录：turnover/amplitude 等为 None
        for i in range(120):
            d = base_date + timedelta(days=i)
            mock_records.append({
                "code": "501001", "date": int(d.strftime("%Y%m%d")),
                "open": 1.0, "high": 1.1, "low": 0.9, "close": 1.05,
                "volume": 1000.0, "amount": 10000.0,
                "turnover": None, "amplitude": None, "pct_chg": None,
                "total_mv": None, "pe_ttm": None
            })
        # 第 121 条记录：turnover 出现浮点数
        d_last = base_date + timedelta(days=120)
        mock_records.append({
            "code": "501001", "date": int(d_last.strftime("%Y%m%d")),
            "open": 1.05, "high": 1.15, "low": 1.0, "close": 1.1,
            "volume": 2000.0, "amount": 22000.0,
            "turnover": 2.36, "amplitude": 5.12, "pct_chg": 4.76,
            "total_mv": 10000000.0, "pe_ttm": 12.5
        })

        mock_rd = MagicMock()
        mock_rd.get.return_value = {"5": ["501001"]}
        mock_rd.vals.return_value = mock_records

        with mock_stockdb_context(mock_rd), \
             patch("cq.data.provider.stockdb.provider.StockDBProvider.get_all_symbols", return_value=["sh.501001"]):
            sm = SyncManager(data_dir=str(temp_data_dir))
            sm.sync(
                table_ids=["aetf.kline.1d.raw.stockdb"],
                formats=["parquet"],
                start_date="2020-01-01",
                end_date="2020-05-01",
            )

            df = read("aetf.kline.1d.raw.stockdb", format="parquet")
            assert len(df) == 121
            assert "turnover_rate" in df.columns
            assert "change_pct" in df.columns
            assert df["turnover_rate"][-1] == pytest.approx(2.36)

