import abc
import polars as pl

class StorageManager(abc.ABC):
    """
    存储管理器抽象基类，定义统一的存储层接口。
    """

    def __init__(self, category: str = "timeseries"):
        self.category = category

    @property
    @abc.abstractmethod
    def partition(self) -> str:
        """分区策略: 'symbol' (按代码分片) 或 'none' (全量聚合)"""
        pass

    @property
    @abc.abstractmethod
    def layout(self) -> str:
        """布局类型: 'hive' (Hive分区样式) 或 'flat' (平铺目录)"""
        pass

    @abc.abstractmethod
    def read_series(self, table_id: str, symbol: str, year: int) -> pl.DataFrame:
        """
        读取时间序列数据 (TS)。按证券代码及年份查询单文件。
        
        Args:
            table_id: 表 ID
            symbol: 证券代码
            year: 年份
            
        Returns:
            pl.DataFrame: 读取到的数据
        """
        pass

    @abc.abstractmethod
    def read_event(self, table_id: str, year: int) -> pl.DataFrame:
        """
        读取事件数据 (EV)。按年份查询年度聚合文件，返回全量数据。
        
        Args:
            table_id: 表 ID
            year: 年份
            
        Returns:
            pl.DataFrame: 读取到的年度全量数据
        """
        pass

    @abc.abstractmethod
    def write_series(self, table_id: str, df: pl.DataFrame, mode: str = "append"):
        """
        写入时间序列数据 (TS) 分片。按 symbol 和 year 分区快速写入，
        所有批次写入完毕后，需调用 finalize 统一执行流式去重与排序落盘。
        
        Args:
            table_id: 表 ID
            df: 包含 symbol 和 timestamp 等字段的 DataFrame
            mode: 写入模式，支持 "overwrite" (覆盖) 或 "append" (增量)
        """
        pass

    @abc.abstractmethod
    def write_event(self, table_id: str, df: pl.DataFrame, mode: str = "append", sort_keys: list[str] = None):
        """
        写入事件数据 (EV) 分片。按 year 分区或平铺结构快速写入，
        所有批次写入完毕后，需调用 finalize 统一执行流式去重与排序落盘。
        
        Args:
            table_id: 表 ID
            df: 包含 timestamp 等字段的 DataFrame
            mode: 写入模式，支持 "overwrite" (覆盖) 或 "append" (增量)
            sort_keys: 排序列列表，由 Provider 显式指定
        """
        pass


    def finalize(
        self,
        table_id: str,
        mode: str = "append",
        sort_keys: list[str] = None,
        progress_callback: Any = None,
    ):
        """
        收敛暂存批次并执行流式去重与排序落盘。
        默认空操作，供需要分片合并的引擎 (如 ParquetStorage) 重写。
        
        Args:
            table_id: 表 ID
            mode: 写入模式 ("append" 或 "overwrite")
            sort_keys: 排序列列表
            progress_callback: 进度回调函数，签名 Callable[[str, int, int], None] (阶段/年份, 当前项, 总项数)
        """
        pass

    def cleanup(self, table_id: str):
        """
        清理该表的未提交临时分片文件，避免异常退出残留脏文件。
        默认空操作，供支持分片暂存的引擎重写。
        """
        pass

    @abc.abstractmethod
    def get_all_symbols(self, table_id: str) -> list[str]:
        """
        返回该数据集下所有的证券代码。
        """
        pass

    @abc.abstractmethod
    def get_total_bars(self, table_id: str) -> int:
        """
        返回该数据集的物理总行数。
        """
        pass

    @abc.abstractmethod
    def get_global_time_range(self, table_id: str) -> tuple[int, int]:
        """
        返回该数据集全局最小/最大毫秒戳。
        """
        pass

    @abc.abstractmethod
    def get_unique_timestamps(self, table_id: str) -> list[int]:
        """
        返回该数据集去重后的所有时间点（可选，性能敏感）。
        """
        pass
