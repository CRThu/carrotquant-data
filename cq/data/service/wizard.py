"""
cqdata/service/wizard.py

终端交互式数据同步向导业务逻辑。
"""

from typing import List
from cq.data.provider.baostock_provider import BaostockProvider
from cq.data.provider.eastmoney_provider import EastMoneyProvider
from cq.data.provider.tdx_provider import TDXProvider
from cq.data.provider.stockdb import StockDBProvider
from cq.data.provider.provider_manager import ProviderManager
from cq.data.entrypoints.python_api import sync


def discover_supported_tables() -> List[str]:
    """获取所有已注册驱动支持的 table_id 清单。"""
    all_tables: List[str] = []

    # 扫描四大内置驱动 (优先读取静态 _SUPPORTED_TABLE_MAP，避免初始化时的网络连接开销)
    for prov_cls in [BaostockProvider, EastMoneyProvider, TDXProvider, StockDBProvider]:
        try:
            if hasattr(prov_cls, "_SUPPORTED_TABLE_MAP"):
                all_tables.extend(list(prov_cls._SUPPORTED_TABLE_MAP.keys()))
            else:
                inst = prov_cls()
                all_tables.extend(inst.get_supported_tables())
        except Exception:
            pass

    # 扫描动态注册的自定义驱动
    pm = ProviderManager()
    for _, prov in pm._custom_providers.items():
        try:
            if hasattr(prov, "_SUPPORTED_TABLE_MAP"):
                all_tables.extend(list(prov._SUPPORTED_TABLE_MAP.keys()))
            else:
                inst = prov() if isinstance(prov, type) else prov
                all_tables.extend(inst.get_supported_tables())
        except Exception:
            pass

    return sorted(list(set(all_tables)))


def start_wizard() -> None:
    """启动数据同步交互向导"""
    print("=" * 60)
    print("      CarrotQuant.Data 数据同步向导 (Wizard V2.2)")
    print("=" * 60)
    print("\n[+] 正在加载可用数据表...")

    available_tables = discover_supported_tables()
    if not available_tables:
        print("[!] 未发现可用数据表。")
        return

    print("\n[1/5] 选择同步对象: 请通过编号选择或切换")
    selected_indices = set()

    while True:
        print("\n" + "-" * 40)
        for i, table in enumerate(available_tables, 1):
            mark = "[*]" if i in selected_indices else "[ ]"
            print(f"  {mark} {i:2}. {table}")
        print("-" * 40)
        print("指令: [编号] 切换状态 | [*] 全选 | [-] 全不选 | [0] 确认并继续")

        selection_input = input("请选择 (直接回车默认选中第1项): ").strip()
        if not selection_input:
            if not selected_indices:
                selected_indices.add(1)
            break

        if selection_input == '0':
            if not selected_indices:
                print("[!] 请至少选择一个同步对象！")
                continue
            break

        if selection_input == '*':
            selected_indices = set(range(1, len(available_tables) + 1))
            continue

        if selection_input == '-':
            selected_indices.clear()
            continue

        try:
            indices = [int(i.strip()) for i in selection_input.split(',') if i.strip()]
            for idx in indices:
                if 1 <= idx <= len(available_tables):
                    if idx in selected_indices:
                        selected_indices.remove(idx)
                    else:
                        selected_indices.add(idx)
                else:
                    print(f"[!] 编号 {idx} 超出范围。")
        except ValueError:
            print("[!] 输入无效，请重新输入。")

    target_tables = [available_tables[i - 1] for i in sorted(selected_indices)]

    # 2. 时间范围
    print("\n[2/5] 设置同步时间范围 (可选):")
    print("      提示: 留空则代表【增量同步】，自动续接断点水位线。")
    start_date = input("起始日期 (YYYY-MM-DD) [默认: 自动续接]: ").strip()
    end_date = input("结束日期 (YYYY-MM-DD) [默认: 至今]: ").strip()

    # 3. 存储格式
    print("\n[3/5] 选择存储格式:")
    formats_input = input("请输入格式 [默认: parquet,csv]: ").strip()
    formats = formats_input if formats_input else "parquet,csv"

    # 4. 批处理与覆盖
    print("\n[4/5] 同步策略配置:")
    force_refresh = input("是否强制全量覆盖更新? (y/N): ").strip().lower() == 'y'
    batch_size = input("批处理大小 (Batch Size) [默认: 100]: ").strip()
    batch_size = batch_size if batch_size else "100"

    # 5. 确认
    tables_to_sync = ",".join(target_tables)
    print("\n" + "=" * 60)
    print(" 任务清单确认:")
    print(f"  - 目标数量: {len(target_tables)} 个数据表")
    print(f"  - 数据列表: {tables_to_sync}")
    print(f"  - 同步模式: {'全量覆盖' if start_date or force_refresh else '增量同步'}")
    print(f"  - 时间区间: {start_date if start_date else '自动水位线'} -> {end_date if end_date else '至今'}")
    print(f"  - 存储格式: {formats}")
    print(f"  - 任务负荷: {batch_size}")
    print("=" * 60)

    confirm = input("\n[5/5] 确认启动同步任务? (Y/n): ").strip().lower()
    if confirm not in ['', 'y', 'yes']:
        print("\n[!] 任务已取消。")
        return

    sync(
        table_ids=target_tables,
        formats=formats.split(","),
        start_date=start_date or None,
        end_date=end_date or None,
        force_refresh=force_refresh,
        batch_size=int(batch_size)
    )
    print("\n[+] 同步任务执行完毕！")
