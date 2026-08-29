"""
tests/unit/test_data_adjuster.py

单元测试：DataAdjuster 动态后复权引擎与七大核心边界防御测试。
"""

import polars as pl
import pytest

from cq.data.service.data_adjuster import DataAdjuster


class TestDataAdjusterEdgeCases:
    """测试 DataAdjuster 复权计算的七大核心边界条件与异常防御。"""

    def test_normal_daily_adjustment(self):
        """标准日线后复权折算测试。"""
        df_kline = pl.DataFrame({
            "symbol": ["sh.600000", "sh.600000"],
            "datetime": ["2024-06-01T15:00:00.000+08:00", "2024-06-02T15:00:00.000+08:00"],
            "timestamp": [1717225200000, 1717311600000],
            "open": [10.0, 10.5],
            "high": [11.0, 11.2],
            "low": [9.8, 10.3],
            "close": [10.2, 11.0],
            "preclose": [9.9, 10.2],
            "volume": [1000.0, 1200.0],
            "amount": [10200.0, 13200.0],
        })

        df_factor = pl.DataFrame({
            "symbol": ["sh.600000", "sh.600000"],
            "datetime": ["2024-06-01T15:00:00.000+08:00", "2024-06-02T15:00:00.000+08:00"],
            "timestamp": [1717225200000, 1717311600000],
            "back_adj_factor": [1.5, 2.0],
        })

        df_res = DataAdjuster.adjust(df_kline, df_factor)

        # 验证价格列乘以对应因子
        assert df_res["open"].to_list() == [15.0, 21.0]
        assert df_res["high"].to_list() == [16.5, 22.4]
        assert df_res["low"].to_list() == pytest.approx([14.7, 20.6])
        assert df_res["close"].to_list() == pytest.approx([15.3, 22.0])
        assert df_res["preclose"].to_list() == pytest.approx([14.85, 20.4])

        # 验证非价格列保持物理原样
        assert df_res["volume"].to_list() == [1000.0, 1200.0]
        assert df_res["amount"].to_list() == [10200.0, 13200.0]

    def test_minute_kline_alignment(self):
        """边界5：高频分钟线 (1m/5m) 与日线因子对齐，同日所有 Bar 共享当日因子。"""
        df_kline = pl.DataFrame({
            "symbol": ["sh.600000", "sh.600000", "sh.600000"],
            "datetime": [
                "2024-06-01T09:30:00.000+08:00",
                "2024-06-01T09:35:00.000+08:00",
                "2024-06-01T15:00:00.000+08:00",
            ],
            "timestamp": [1717205400000, 1717205700000, 1717225200000],
            "open": [10.0, 10.2, 10.8],
            "high": [10.3, 10.5, 11.0],
            "low": [9.9, 10.1, 10.7],
            "close": [10.1, 10.4, 10.9],
            "volume": [100.0, 150.0, 300.0],
        })

        df_factor = pl.DataFrame({
            "symbol": ["sh.600000"],
            "datetime": ["2024-06-01T15:00:00.000+08:00"],
            "timestamp": [1717225200000],
            "back_adj_factor": [1.5],
        })

        df_res = DataAdjuster.adjust(df_kline, df_factor)

        # 3 个分钟 Bar 全部正确乘以当日 1.5 因子
        assert df_res["close"].to_list() == pytest.approx([15.15, 15.6, 16.35])
        assert df_res["volume"].to_list() == [100.0, 150.0, 300.0]

    def test_date_range_truncation_backward_fill(self):
        """边界2：日期区间截断断流，K 线在 2024-06，因子在 2023-05，正确前向继承历史累计因子。"""
        df_kline = pl.DataFrame({
            "symbol": ["sh.600000", "sh.600000"],
            "datetime": ["2024-06-01T15:00:00.000+08:00", "2024-06-05T15:00:00.000+08:00"],
            "timestamp": [1717225200000, 1717570800000],
            "close": [10.0, 10.5],
        })

        # 因子表包含历史 2023-05-10 的因子 1.2，以及 2024-06-03 的新除权因子 1.5
        df_factor = pl.DataFrame({
            "symbol": ["sh.600000", "sh.600000"],
            "datetime": ["2023-05-10T15:00:00.000+08:00", "2024-06-03T15:00:00.000+08:00"],
            "timestamp": [1683702000000, 1717398000000],
            "back_adj_factor": [1.2, 1.5],
        })

        df_res = DataAdjuster.adjust(df_kline, df_factor)

        # 2024-06-01 继承 2023-05-10 的 1.2 因子 -> 10.0 * 1.2 = 12.0
        # 2024-06-05 匹配 2024-06-03 的 1.5 因子 -> 10.5 * 1.5 = 15.75
        assert df_res["close"].to_list() == pytest.approx([12.0, 15.75])

    def test_new_stock_without_factor(self):
        """边界3：次新股或从未除权的标的，因子表中无记录，自动保底为 1.0，价格不变。"""
        df_kline = pl.DataFrame({
            "symbol": ["sh.688001"],
            "datetime": ["2024-06-01T15:00:00.000+08:00"],
            "timestamp": [1717225200000],
            "open": [50.0],
            "close": [52.0],
        })

        # 因子表无该标的记录
        df_factor = pl.DataFrame({
            "symbol": ["sh.600000"],
            "datetime": ["2024-06-01T15:00:00.000+08:00"],
            "timestamp": [1717225200000],
            "back_adj_factor": [1.5],
        })

        df_res = DataAdjuster.adjust(df_kline, df_factor)
        assert df_res["open"].to_list() == [50.0]
        assert df_res["close"].to_list() == [52.0]

    def test_multi_symbol_batch_isolation(self):
        """边界4：批量多标的查询，标的 A 的因子绝不污染标的 B。"""
        df_kline = pl.DataFrame({
            "symbol": ["sh.600000", "sz.000001", "sh.600000", "sz.000001"],
            "datetime": [
                "2024-06-01T15:00:00.000+08:00",
                "2024-06-01T15:00:00.000+08:00",
                "2024-06-02T15:00:00.000+08:00",
                "2024-06-02T15:00:00.000+08:00",
            ],
            "timestamp": [1717225200000, 1717225200000, 1717311600000, 1717311600000],
            "close": [10.0, 20.0, 10.5, 21.0],
        })

        # sh.600000 因子为 1.5，sz.000001 因子为 2.0
        df_factor = pl.DataFrame({
            "symbol": ["sh.600000", "sz.000001"],
            "datetime": ["2024-06-01T15:00:00.000+08:00", "2024-06-01T15:00:00.000+08:00"],
            "timestamp": [1717225200000, 1717225200000],
            "back_adj_factor": [1.5, 2.0],
        })

        df_res = DataAdjuster.adjust(df_kline, df_factor)
        assert df_res["close"].to_list() == pytest.approx([15.0, 40.0, 15.75, 42.0])

    def test_partial_symbols_missing_factor(self):
        """边界6：多股票查询中部分股票缺失因子，缺失者保底 1.0，其余正常复权。"""
        df_kline = pl.DataFrame({
            "symbol": ["sh.600000", "sh.688999"],
            "datetime": ["2024-06-01T15:00:00.000+08:00", "2024-06-01T15:00:00.000+08:00"],
            "timestamp": [1717225200000, 1717225200000],
            "close": [10.0, 88.0],
        })

        df_factor = pl.DataFrame({
            "symbol": ["sh.600000"],
            "datetime": ["2024-06-01T15:00:00.000+08:00"],
            "timestamp": [1717225200000],
            "back_adj_factor": [1.5],
        })

        df_res = DataAdjuster.adjust(df_kline, df_factor)
        assert df_res["close"].to_list() == pytest.approx([15.0, 88.0])

    def test_suspension_preserves_status_and_volume(self):
        """边界1：停牌期间价格折算，但 trade_status 与 volume 严格保持物理原样。"""
        df_kline = pl.DataFrame({
            "symbol": ["sh.600000"],
            "datetime": ["2024-06-01T15:00:00.000+08:00"],
            "timestamp": [1717225200000],
            "close": [10.0],
            "volume": [0.0],
            "trade_status": ["0"],
        })

        df_factor = pl.DataFrame({
            "symbol": ["sh.600000"],
            "datetime": ["2024-06-01T15:00:00.000+08:00"],
            "timestamp": [1717225200000],
            "back_adj_factor": [1.5],
        })

        df_res = DataAdjuster.adjust(df_kline, df_factor)
        assert df_res["close"].to_list() == [15.0]
        assert df_res["volume"].to_list() == [0.0]
        assert df_res["trade_status"].to_list() == ["0"]

    def test_null_price_preservation(self):
        """边界7：价格列含 null (如上市首日 preclose) 自动保留 null，不因标量计算报错。"""
        df_kline = pl.DataFrame({
            "symbol": ["sh.600000"],
            "datetime": ["2024-06-01T15:00:00.000+08:00"],
            "timestamp": [1717225200000],
            "open": [10.0],
            "close": [10.5],
            "preclose": [None],
        }, schema={
            "symbol": pl.String,
            "datetime": pl.String,
            "timestamp": pl.Int64,
            "open": pl.Float64,
            "close": pl.Float64,
            "preclose": pl.Float64,
        })

        df_factor = pl.DataFrame({
            "symbol": ["sh.600000"],
            "datetime": ["2024-06-01T15:00:00.000+08:00"],
            "timestamp": [1717225200000],
            "back_adj_factor": [1.5],
        })

        df_res = DataAdjuster.adjust(df_kline, df_factor)
        assert df_res["open"].to_list() == [15.0]
        assert df_res["close"].to_list() == [15.75]
        assert df_res["preclose"].to_list() == [None]

    def test_adjust_flag_updated_to_adj(self):
        """若原始 K 线包含 adjust_flag 列，复权计算后应更新为 'adj'。"""
        df_kline = pl.DataFrame({
            "symbol": ["sh.600000"],
            "datetime": ["2024-06-01T15:00:00.000+08:00"],
            "timestamp": [1717225200000],
            "close": [10.0],
            "adjust_flag": ["raw"],
        })

        df_factor = pl.DataFrame({
            "symbol": ["sh.600000"],
            "datetime": ["2024-06-01T15:00:00.000+08:00"],
            "timestamp": [1717225200000],
            "back_adj_factor": [1.5],
        })

        df_res = DataAdjuster.adjust(df_kline, df_factor)
        assert df_res["adjust_flag"].to_list() == ["adj"]

    def test_empty_dataframe_handling(self):
        """空 DataFrame 防御：空输入直接返回，不抛出异常。"""
        df_empty_kline = pl.DataFrame()
        df_factor = pl.DataFrame({
            "symbol": ["sh.600000"],
            "datetime": ["2024-06-01T15:00:00.000+08:00"],
            "timestamp": [1717225200000],
            "back_adj_factor": [1.5],
        })

        assert DataAdjuster.adjust(df_empty_kline, df_factor).is_empty()

        df_kline = pl.DataFrame({"symbol": ["sh.600000"], "close": [10.0]})
        # factor 为 None 或空表时返回原样
        assert DataAdjuster.adjust(df_kline, None)["close"].to_list() == [10.0]
        assert DataAdjuster.adjust(df_kline, pl.DataFrame())["close"].to_list() == [10.0]
