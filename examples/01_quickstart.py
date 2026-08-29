"""
examples/01_quickstart.py

CarrotQuant.Data Python SDK 快速上手示例
演示基于 OOP 便捷层与统一 read 函数的基础数据同步与读取流程。
"""

import cq.data


def main():
    table_id = "ashare.kline.1d.raw.baostock"

    print("=== 1. 触发数据同步 ===")
    cq.data.sync(
        table_ids=table_id,
        formats="parquet",
        start_date="2024-01-01",
        end_date="2024-01-10",
        symbol_limit=2,
        force_refresh=True  # 示例强刷 2 支股票样本数据
    )
    print("同步完成！")

    print("\n=== 2. 读取数据 (使用 OOP 便捷访问层) ===")
    # 2.1 默认 raw 零开销直读原始行情
    df_raw = cq.data.ashare.kline.get(
        symbols=["sh.600000"],
        start_date="2024-01-01",
        end_date="2024-01-10"
    )
    print("\n[OOP 原始行情 (raw) Preview]:")
    print(df_raw.head(5))

    # 2.2 显式 adj='adj' 自动进行动态向量化后复权折算
    df_adj = cq.data.ashare.kline.get(
        symbols=["sh.600000"],
        adj="adj",
        start_date="2024-01-01",
        end_date="2024-01-10"
    )
    print("\n[OOP 动态后复权 (adj) Preview]:")
    print(df_adj.head(5))

    print("\n=== 3. 读取数据 (使用经典统一 cq.data.read 入口) ===")
    df_read = cq.data.read(
        table_id=table_id,
        start_date="2024-01-01",
        end_date="2024-01-10"
    )
    print("\n[read() 切片读取结果 Preview]:")
    print(df_read.head(5))


if __name__ == "__main__":
    main()
