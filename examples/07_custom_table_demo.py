"""
examples/07_custom_table_demo.py

CarrotQuant.Data 自定义数据表 (Custom Tables) 读写与管理示例
演示如何使用 cq.data.write 写入自定义时序与事件表、自动生成元数据、
使用 cq.data.read 切片查询以及注册自定义数据源 Provider。
"""

import polars as pl
import cq.data
from cq.data.provider.base import BaseProvider


@cq.data.register_provider("my_binance")
class MyCryptoProvider(BaseProvider):
    """自定义加密货币数据源示例驱动 (使用类装饰器自动注册)"""
    def fetch(self, table_id: str, symbol: str, start_time: int = None, end_time: int = None) -> pl.DataFrame:
        return pl.DataFrame({
            "symbol": [symbol, symbol],
            "timestamp": [1704067200000, 1704153600000],
            "datetime": ["2024-01-01T15:00:00.000+08:00", "2024-01-02T15:00:00.000+08:00"],
            "close": [42500.0, 43200.0],
            "volume": [1200.5, 1350.2]
        })

    def get_all_symbols(self, table_id: str) -> list[str]:
        return ["BTC.USDT", "ETH.USDT"]

    def get_supported_tables(self) -> list[str]:
        return ["crypto.kline.1d.my_binance"]

    def get_table_category(self, table_id: str) -> str:
        return "timeseries"

    def get_sort_keys(self, table_id: str) -> list[str]:
        return ["timestamp", "symbol"]


def main():
    print("=== 1. 写入自定义量化因子时序表 (TimeSeries) ===")
    df_factor = pl.DataFrame({
        "symbol": ["sh.600000", "sh.600000", "sz.000001", "sz.000001"],
        "date": ["2024-01-02", "2024-01-03", "2024-01-02", "2024-01-03"],
        "alpha_momentum": [1.45, 1.52, 0.88, 0.91],
        "volatility_20d": [0.18, 0.19, 0.25, 0.24]
    })
    
    write_res = cq.data.write(
        table_id="custom.factor.alpha101",
        df=df_factor,
        formats=["parquet", "csv"],
        mode="append"
    )
    print(f"写入结果: {write_res}")

    print("\n=== 2. 写入自定义平铺事件表 (Flat Event) ===")
    df_board = pl.DataFrame({
        "board_code": ["BK_CUSTOM_01", "BK_CUSTOM_02"],
        "board_name": ["具身智能", "商业航天"],
        "lead_stock": ["sh.688001", "sz.300002"]
    })
    cq.data.write(
        table_id="custom.board.thematic",
        df=df_board,
        category="event",
        formats="parquet"
    )
    print("事件表写入完成！")

    print("\n=== 3. 探查本地数据表元数据 ===")
    all_tables = cq.data.list_tables()
    print("本地数据表总览:")
    for t in all_tables:
        if t["table_id"].startswith("custom."):
            print(f"  - [{t['category']}] {t['table_id']}")

    print(f"\ncustom.factor.alpha101 Schema: {cq.data.get_schema('custom.factor.alpha101')}")
    print(f"custom.factor.alpha101 时间跨度: {cq.data.get_time_range('custom.factor.alpha101')}")
    print(f"custom.factor.alpha101 记录条数: {cq.data.get_row_count('custom.factor.alpha101')}")

    print("\n=== 4. 切片读取自定义数据表 (带代码与字段过滤) ===")
    df_read = cq.data.read(
        table_id="custom.factor.alpha101",
        symbols=["sh.600000"],
        columns=["timestamp", "datetime", "alpha_momentum"]
    )
    print("[读取结果 Preview]:")
    print(df_read)

    print("\n=== 5. 调度通过类装饰器注册的自定义 Provider ===")
    cq.data.sync(
        table_ids="crypto.kline.1d.my_binance",
        formats="parquet",
        force_refresh=True
    )
    df_crypto = cq.data.read("crypto.kline.1d.my_binance")
    print("\n[自定义 Provider 同步与直读结果]:")
    print(df_crypto)


if __name__ == "__main__":
    main()
