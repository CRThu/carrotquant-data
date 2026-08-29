"""
cq/data/service/data_adjuster.py

数据复权计算服务模块。
提供基于 Polars 向量化计算的动态后复权算法，支持分钟线与日线跨频对齐、历史短切片前向填充、停牌与新股鲁棒防御。
"""

from typing import Optional, Sequence, Union
import warnings
import polars as pl


class DataAdjuster:
    """
    数据复权计算核心服务类。
    利用 Polars 内存向量化，将 K 线数据与复权因子数据按 [symbol, date] 关联并完成价格列的后复权折算。
    """

    PRICE_COLUMNS: Sequence[str] = ("open", "high", "low", "close", "preclose")

    @classmethod
    def adjust(
        cls,
        df_kline: pl.DataFrame,
        df_factor: Optional[pl.DataFrame] = None
    ) -> pl.DataFrame:
        """
        利用 Polars 向量化，将 df_kline 与 df_factor 关联并完成 5 大价格列的复权折算。
        具备自动 backward asof join、forward_fill、fill_null(1.0)、停牌与多标的分组安全隔离。

        Args:
            df_kline: 原始 K 线 DataFrame (需包含 symbol、datetime/timestamp 及 open/high/low/close 等)
            df_factor: 复权因子 DataFrame (包含 symbol、datetime/timestamp、back_adj_factor)

        Returns:
            pl.DataFrame: 后复权折算后的 K 线 DataFrame
        """
        if df_kline.is_empty():
            return df_kline

        # 检查是否有需要复权的价格列
        price_cols = [c for c in cls.PRICE_COLUMNS if c in df_kline.columns]
        if not price_cols:
            return df_kline

        # 如果因子表为空或不存在，默认全量因子为 1.0 (价格保持不变)
        if df_factor is None or df_factor.is_empty() or "back_adj_factor" not in df_factor.columns:
            return df_kline

        # 提取 K 线的日期匹配键 (_date_key)
        if "datetime" in df_kline.columns:
            kline_date_expr = pl.col("datetime").str.slice(0, 10)
        elif "date" in df_kline.columns:
            kline_date_expr = pl.col("date").str.slice(0, 10)
        elif "timestamp" in df_kline.columns:
            kline_date_expr = pl.from_epoch(pl.col("timestamp"), time_unit="ms").dt.strftime("%Y-%m-%d")
        else:
            return df_kline

        # 提取 因子表的日期匹配键 (_date_key)
        if "datetime" in df_factor.columns:
            factor_date_expr = pl.col("datetime").str.slice(0, 10)
        elif "date" in df_factor.columns:
            factor_date_expr = pl.col("date").str.slice(0, 10)
        elif "timestamp" in df_factor.columns:
            factor_date_expr = pl.from_epoch(pl.col("timestamp"), time_unit="ms").dt.strftime("%Y-%m-%d")
        else:
            return df_kline

        # 准备带日期键与原始索引的 K 线
        df_k = df_kline.with_columns(
            kline_date_expr.alias("_date_key")
        ).with_row_index("_orig_idx").sort("_date_key")

        # 准备因子表，按 symbol 和 _date_key 去重并排序 (保留当日最新因子)
        df_f = (
            df_factor.with_columns(factor_date_expr.alias("_date_key"))
            .select(["symbol", "_date_key", "back_adj_factor"])
            .filter(pl.col("back_adj_factor").is_not_null())
            .unique(subset=["symbol", "_date_key"], keep="last")
            .sort("_date_key")
        )

        # 执行 Asof Join (向后追溯最近的历史已知有效因子)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            df_joined = (
                df_k.join_asof(
                    df_f,
                    on="_date_key",
                    by="symbol",
                    strategy="backward"
                )
                .sort("_orig_idx")
                .drop(["_orig_idx", "_date_key"])
            )

        # 补全缺失因子为 1.0 (次新股或无因子记录标的保底)
        df_joined = df_joined.with_columns(
            pl.col("back_adj_factor").fill_null(1.0)
        )

        # 对价格列执行向量化乘法折算
        adjust_exprs = [
            (pl.col(c) * pl.col("back_adj_factor")).alias(c)
            for c in price_cols
        ]

        # 如果存在 adjust_flag 列，更新其标识为 'adj'
        if "adjust_flag" in df_joined.columns:
            adjust_exprs.append(pl.lit("adj").alias("adjust_flag"))

        df_result = df_joined.with_columns(adjust_exprs).drop("back_adj_factor")

        return df_result
