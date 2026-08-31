import socket
from datetime import datetime
from typing import Any, List, Dict, Optional, Set
import polars as pl
from loguru import logger

from cq.data.provider.base import BaseProvider
from cq.data.provider.data_cleaner import DataCleaner
from cq.data.utils.time_utils import ts_to_str

try:
    from cq.data.provider.stockdb import stockdb
except ImportError:
    try:
        import stockdb
    except ImportError:
        stockdb = None


def normalize_symbol(code: str) -> str:
    """给纯数字股票/基金代码添加标准市场前缀 (sh. / sz. / bj.)"""
    if not code:
        return code
    code_str = str(code).strip()
    if code_str.startswith(("sh.", "sz.", "bj.")):
        return code_str

    if code_str.startswith(("60", "68", "90", "5")):
        return f"sh.{code_str}"
    elif code_str.startswith(("00", "30", "20", "1")):
        return f"sz.{code_str}"
    elif code_str.startswith(("8", "4", "92")):
        return f"bj.{code_str}"
    return f"sz.{code_str}"


def strip_symbol_prefix(symbol: str) -> str:
    """移除 symbol 前缀得到纯数字代码，用于向 StockDB 底层查询"""
    if not symbol:
        return symbol
    symbol_str = str(symbol).strip()
    if symbol_str.startswith(("sh.", "sz.", "bj.")):
        return symbol_str[3:]
    return symbol_str


def check_stockdb_connection(host: str = "127.0.0.1", port: int = 7899, timeout: float = 0.05) -> bool:
    """快速探测 StockDB 本地守护进程 TCP 连通性 (<50ms)"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            return s.connect_ex((host, port)) == 0
    except Exception:
        return False


class StockDBProvider(BaseProvider):
    """
    StockDB 本地量化数据库驱动实现。
    
    支持通过原生 stockdb.pyd 二进制通道直连本地 LevelDB 时序引擎（127.0.0.1:7899），
    提供 A 股个股与场内 ETF 的 1 分钟/日线行情、除权除息复权因子以及概念与申万行业映射。
    """

    _SUPPORTED_TABLE_MAP: Dict[str, str] = {
        "ashare.kline.1m.raw.stockdb": "timeseries",
        "ashare.kline.1d.raw.stockdb": "timeseries",
        "ashare.adj_factor.stockdb": "event",
        "ashare.concept.stockdb": "event",
        "ashare.industry.stockdb": "event",
        "aetf.kline.1m.raw.stockdb": "timeseries",
        "aetf.kline.1d.raw.stockdb": "timeseries",
        "aetf.adj_factor.stockdb": "event",
    }

    def __init__(self, host: str = "127.0.0.1", port: int = 7899):
        self.host = host
        self.port = port
        self._rd = None

    def _ensure_connected(self):
        """确保 StockDB 二进制模块与 TCP 服务均可用，未就绪时立即 Fail-Fast 抛出强类型异常"""
        if stockdb is None:
            raise ImportError(
                "未能成功导入 'stockdb' 二进制模块。请确保 stockdb.pyd 位于当前环境且支持当前操作系统架构。"
            )
        if not check_stockdb_connection(self.host, self.port):
            raise ConnectionRefusedError(
                f"无法连接至 StockDB 服务端 ({self.host}:{self.port})。请先启动 stockdb.exe 后再执行同步。"
            )
        if self._rd is None:
            self._rd = stockdb.rd

    def get_supported_tables(self) -> List[str]:
        """返回 StockDB 驱动支持的所有 table_id 列表"""
        return list(self._SUPPORTED_TABLE_MAP.keys())

    def get_table_category(self, table_id: str) -> str:
        """返回指定 table_id 的数据类别 (timeseries 或 event)"""
        if table_id not in self._SUPPORTED_TABLE_MAP:
            raise ValueError(f"Table '{table_id}' is not supported by StockDBProvider.")
        return self._SUPPORTED_TABLE_MAP[table_id]

    def get_sort_keys(self, table_id: str) -> List[str]:
        """返回指定 table_id 的排序列"""
        if table_id in ("ashare.concept.stockdb", "ashare.industry.stockdb"):
            return ["board_code", "symbol"]
        elif table_id in ("ashare.adj_factor.stockdb", "aetf.adj_factor.stockdb"):
            return ["timestamp", "symbol"]
        return ["timestamp"]

    def get_all_symbols(self, table_id: str) -> List[str]:
        """
        全量标的发现接口。
        
        - ashare.kline.*: 发现 0/3/6/9 号段在市个股及退市股票（共 6,000+ 标的）
        - aetf.kline.*: 发现 1/5 号段场内交易型基金与 ETF（共 2,000+ 标的）
        - 板块表与复权表: 返回 ['_ALL_'] 触发批量极速同步
        """
        if table_id not in self.get_supported_tables():
            raise ValueError(f"Table '{table_id}' is not supported by StockDBProvider.")

        if table_id in (
            "ashare.concept.stockdb",
            "ashare.industry.stockdb",
            "ashare.adj_factor.stockdb",
            "aetf.adj_factor.stockdb",
        ):
            return ["_ALL_"]

        self._ensure_connected()
        code_dict = self._rd.get("股票代码") or {}

        if table_id.startswith("ashare.kline"):
            symbols_set: Set[str] = set()
            for k in ("0", "3", "6", "9"):
                if k in code_dict and isinstance(code_dict[k], list):
                    symbols_set.update(code_dict[k])
            
            # 合并退市股票列表 (排除基金等代码)
            try:
                retired = self._rd.vals("退市*") or []
                for r in retired:
                    r_str = str(r).strip()
                    if r_str and not r_str.startswith(("1", "5")):
                        symbols_set.add(r_str)
            except Exception as e:
                logger.warning(f"Failed to fetch retired stocks from StockDB: {e}")

            all_symbols = [normalize_symbol(s) for s in symbols_set if s]
            all_symbols.sort()
            logger.info(f"Discovered {len(all_symbols)} symbols for Universe 'ashare' (Stocks) from StockDB")
            return all_symbols

        elif table_id.startswith("aetf.kline"):
            symbols_set: Set[str] = set()
            for k in ("1", "5"):
                if k in code_dict and isinstance(code_dict[k], list):
                    symbols_set.update(code_dict[k])
            
            all_symbols = [normalize_symbol(s) for s in symbols_set if s]
            all_symbols.sort()
            logger.info(f"Discovered {len(all_symbols)} symbols for Universe 'aetf' (ETFs/Funds) from StockDB")
            return all_symbols

        raise ValueError(f"Unhandled table_id for get_all_symbols: {table_id}")

    def fetch(
        self, table_id: str, symbol: str, start_date: Any, end_date: Any, **kwargs
    ) -> pl.DataFrame:
        """
        原子化/批处理拉取接口。
        
        Args:
            table_id: 表标识符
            symbol: 证券代码或 '_ALL_'
            start_date: 起始日期 (YYYY-MM-DD 或毫秒时间戳)
            end_date: 结束日期 (YYYY-MM-DD 或毫秒时间戳)
        """
        if table_id not in self.get_supported_tables():
            raise ValueError(f"Table '{table_id}' is not supported by StockDBProvider.")

        self._ensure_connected()

        # 参数标准化：转换为 YYYY-MM-DD 字符串
        if isinstance(start_date, int):
            start_date = ts_to_str(start_date)
        if isinstance(end_date, int):
            end_date = ts_to_str(end_date)

        if not start_date:
            start_date = "1970-01-01"
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")

        if "kline.1m" in table_id:
            return self._fetch_kline_1m(table_id, symbol, start_date, end_date)
        elif "kline.1d" in table_id:
            return self._fetch_kline_1d(table_id, symbol, start_date, end_date)
        elif "adj_factor" in table_id:
            return self._fetch_adj_factor(table_id, symbol, start_date, end_date)
        elif "concept" in table_id:
            return self._fetch_concept(table_id, symbol)
        elif "industry" in table_id:
            return self._fetch_industry(table_id, symbol)
        else:
            raise NotImplementedError(f"Unsupported table category for StockDB: {table_id}")

    def _fetch_kline_1d(
        self, table_id: str, symbol: str, start_date: str, end_date: str
    ) -> pl.DataFrame:
        """
        拉取日 K 线行情。
        
        清洗规则：
        1. 剔除含有前复权快照的 pre_close 脏列；
        2. 将 turnover 归一化重命名为 turnover_rate，pct_chg 归一化为 change_pct；
        3. 全量保留截面因子（市值、股本、PE/PB、ST、量比、振幅）；
        4. 时间轴对齐至 15:00:00 收盘时刻。
        """
        raw_code = strip_symbol_prefix(symbol)
        norm_symbol = normalize_symbol(symbol)

        s_val = start_date.replace("-", "")
        e_val = end_date.replace("-", "")
        time_query = f"{s_val}>{e_val}"

        raw_records = self._rd.vals("日k", raw_code, time_query) or []
        records = [r for r in raw_records if isinstance(r, dict)]

        raw_schema = {
            "date": pl.String,
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume": pl.Float64,
            "amount": pl.Float64,
            "turnover": pl.Float64,
            "pct_chg": pl.Float64,
            "total_mv": pl.Float64,
            "float_mv": pl.Float64,
            "total_share": pl.Float64,
            "float_share": pl.Float64,
            "pe_ttm": pl.Float64,
            "pb": pl.Float64,
            "is_st": pl.Boolean,
            "vol_ratio": pl.Float64,
            "amplitude": pl.Float64,
        }

        df = pl.DataFrame(records, schema=raw_schema)
        df = df.rename({"turnover": "turnover_rate", "pct_chg": "change_pct"}).with_columns(
            pl.lit(norm_symbol).cast(pl.String).alias("symbol")
        )

        return DataCleaner.standardize(
            df, "date", time_fmt="%Y%m%d",
            source_tz="Asia/Shanghai", display_tz="Asia/Shanghai", time_shift_hours=15
        )

    def _fetch_kline_1m(
        self, table_id: str, symbol: str, start_date: str, end_date: str
    ) -> pl.DataFrame:
        """
        拉取 1 分钟线高频行情。
        
        时间戳格式为 14 位整数 (YYYYMMDDHHMMSS)，直接通过 time_shift_hours=0 标准化。
        """
        raw_code = strip_symbol_prefix(symbol)
        norm_symbol = normalize_symbol(symbol)

        s_val = start_date.replace("-", "") + "000000" if len(start_date.replace("-", "")) == 8 else start_date
        e_val = end_date.replace("-", "") + "235959" if len(end_date.replace("-", "")) == 8 else end_date
        time_query = f"{s_val}>{e_val}"

        raw_records = self._rd.vals("分钟k", raw_code, time_query) or []
        records = [r for r in raw_records if isinstance(r, dict)]

        raw_schema = {
            "date": pl.String,
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume": pl.Float64,
            "amount": pl.Float64,
        }

        df = pl.DataFrame(records, schema=raw_schema)
        df = df.with_columns(pl.lit(norm_symbol).cast(pl.String).alias("symbol"))

        return DataCleaner.standardize(
            df, "date", time_fmt="%Y%m%d%H%M%S",
            source_tz="Asia/Shanghai", display_tz="Asia/Shanghai", time_shift_hours=0
        )

    def _fetch_adj_factor(
        self, table_id: str, symbol: str, start_date: str, end_date: str
    ) -> pl.DataFrame:
        """
        拉取除权除息后复权因子 (cum -> back_adj_factor)。
        
        - ashare.adj_factor.stockdb: 提取股票除权除息因子 (0/3/6/9/8/4)
        - aetf.adj_factor.stockdb: 提取场内基金/ETF 拆分分红因子 (1/5)
        """
        is_aetf = table_id.startswith("aetf")
        raw_target_code = strip_symbol_prefix(symbol) if symbol != "_ALL_" else None

        raw_fq = self._rd.get("复权*").get("cum") or []
        rows = []

        s_clean = start_date.replace("-", "") if start_date else "19700101"
        e_clean = end_date.replace("-", "") if end_date else "99991231"

        for item in raw_fq:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            key_str = str(item[0])
            cum_val = float(item[1])
            parts = key_str.split(":")
            if len(parts) < 3:
                continue
            code = parts[1]
            date_str = parts[2]

            if raw_target_code is not None and code != raw_target_code:
                continue

            if is_aetf:
                if not code.startswith(("1", "5")):
                    continue
            else:
                if code.startswith(("1", "5")):
                    continue

            if date_str < s_clean or date_str > e_clean:
                continue

            rows.append({
                "symbol": normalize_symbol(code),
                "date": date_str,
                "back_adj_factor": cum_val,
            })

        schema = {
            "symbol": pl.String,
            "date": pl.String,
            "back_adj_factor": pl.Float64,
        }

        if not rows:
            empty_df = pl.DataFrame(schema=schema)
            return DataCleaner.standardize(
                empty_df, "date", time_fmt="%Y%m%d",
                source_tz="Asia/Shanghai", display_tz="Asia/Shanghai", time_shift_hours=15
            )

        df = pl.DataFrame(rows, schema=schema)
        return DataCleaner.standardize(
            df, "date", time_fmt="%Y%m%d",
            source_tz="Asia/Shanghai", display_tz="Asia/Shanghai", time_shift_hours=15
        )

    def _fetch_concept(self, table_id: str, symbol: str) -> pl.DataFrame:
        """
        拉取 1200+ 同花顺概念板块成分映射。
        
        平铺输出结构: [board_code, board_name, category, symbol]
        """
        boards = self._rd.get("板块*").do() or []
        rows = []

        for item in boards:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            board_dict = item[1]
            if not isinstance(board_dict, dict):
                continue

            cat = str(board_dict.get("category", "")).strip()
            if cat != "概念":
                continue

            board_code = str(board_dict.get("code", "")).strip()
            board_name = str(board_dict.get("name", "")).strip()
            symbols = board_dict.get("symbols", []) or []

            for s in symbols:
                s_str = str(s).strip()
                if s_str:
                    rows.append({
                        "board_code": board_code,
                        "board_name": board_name,
                        "category": cat,
                        "symbol": normalize_symbol(s_str),
                    })

        schema = {
            "board_code": pl.String,
            "board_name": pl.String,
            "category": pl.String,
            "symbol": pl.String,
        }

        if not rows:
            return pl.DataFrame(schema=schema)

        return pl.DataFrame(rows, schema=schema)

    def _fetch_industry(self, table_id: str, symbol: str) -> pl.DataFrame:
        """
        拉取申万一、二、三级行业板块成分映射。
        
        平铺输出结构: [board_code, board_name, category, symbol]
        """
        boards = self._rd.get("板块*").do() or []
        rows = []

        valid_categories = {"申万一级", "申万二级", "申万三级"}

        for item in boards:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            board_dict = item[1]
            if not isinstance(board_dict, dict):
                continue

            cat = str(board_dict.get("category", "")).strip()
            if cat not in valid_categories:
                continue

            board_code = str(board_dict.get("code", "")).strip()
            board_name = str(board_dict.get("name", "")).strip()
            symbols = board_dict.get("symbols", []) or []

            for s in symbols:
                s_str = str(s).strip()
                if s_str:
                    rows.append({
                        "board_code": board_code,
                        "board_name": board_name,
                        "category": cat,
                        "symbol": normalize_symbol(s_str),
                    })

        schema = {
            "board_code": pl.String,
            "board_name": pl.String,
            "category": pl.String,
            "symbol": pl.String,
        }

        if not rows:
            return pl.DataFrame(schema=schema)

        return pl.DataFrame(rows, schema=schema)
