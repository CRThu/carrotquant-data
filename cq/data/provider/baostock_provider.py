import os
import socket
import threading

import baostock as bs
import polars as pl
from datetime import datetime
from typing import Any
from loguru import logger
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
from cq.data.provider.base import BaseProvider
from cq.data.provider.data_cleaner import DataCleaner
from cq.data.utils.time_utils import ts_to_str

from cq.data.utils.logger_utils import SuppressOutput

_BS_MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "3"))


class BaostockCallError(RuntimeError):
    """Baostock API 调用返回非零错误码 (如网络接收错误/未登录) 时抛出的异常。"""
    pass


class BaostockProvider(BaseProvider):
    """
    Baostock 数据源驱动实现
    """
    
    # 类级别可重入线程锁，确保全局 baostock C/socket 模块调用的线程安全
    _lock = threading.RLock()

    # 类常量：table_id 到数据类别的映射
    _SUPPORTED_TABLE_MAP: dict[str, str] = {
        "ashare.kline.1d.adj.baostock": "timeseries",
        "ashare.kline.1d.raw.baostock": "timeseries",
        "ashare.kline.5m.adj.baostock": "timeseries",
        "ashare.kline.5m.raw.baostock": "timeseries",
        "aindex.kline.1d.raw.baostock": "timeseries",
        "ashare.adj_factor.baostock": "event"
    }

    def __init__(self):
        """
        初始化并登录 Baostock
        """
        with self._lock:
            with SuppressOutput():
                self.lg = bs.login()
                
            if self.lg.error_code != '0':
                logger.error(f"Baostock login failed: {self.lg.error_msg}")
            else:
                logger.info("Baostock login success")

    def __del__(self):
        """
        析构时退出 Baostock
        """
        try:
            with self._lock:
                with SuppressOutput():
                    bs.logout()
                logger.info("Baostock logout success")
        except Exception as e:
            logger.warning(f"Baostock logout error: {e}")

    def _relogin(self) -> None:
        """重新登录 Baostock (连接断开时调用)。"""
        with self._lock:
            try:
                with SuppressOutput():
                    bs.logout()
            except Exception:
                pass
            with SuppressOutput():
                result = bs.login()
            if result.error_code != '0':
                logger.error(f"Baostock re-login failed: {result.error_msg}")
                # 抛出 BaostockCallError 替代 RuntimeError，确保 tenacity 重试机制捕获并执行指数退避重试
                raise BaostockCallError(f"Baostock re-login failed: {result.error_msg}")
            logger.info("Baostock re-login success")

    def _safe_bs_call(self, func, *args, **kwargs):
        """Baostock 调用封装：网络异常及 API 返回错误码时 re-login 重试 (tenacity 指数退避)。"""
        @retry(
            stop=stop_after_attempt(_BS_MAX_RETRIES),
            wait=wait_exponential(multiplier=1, min=0.5, max=5),
            retry=retry_if_exception_type((socket.error, ConnectionError, OSError, BaostockCallError)),
            reraise=True,
        )
        def _call():
            with self._lock:
                try:
                    res = func(*args, **kwargs)
                except (socket.error, ConnectionError, OSError) as e:
                    logger.warning(f"Baostock socket exception: {e}, performing re-login and retry...")
                    self._relogin()
                    raise

                # 关键检查：Baostock 不抛出 Exception，而是返回 rs.error_code != '0' (如 '网络接收错误。' / '-1')
                if hasattr(res, "error_code") and res.error_code != "0":
                    logger.warning(
                        f"Baostock call returned error_code={res.error_code} ({res.error_msg}), performing re-login and retry..."
                    )
                    self._relogin()
                    raise BaostockCallError(f"Baostock API Error: {res.error_msg} (code={res.error_code})")
                return res
        return _call()

    def get_supported_tables(self) -> list[str]:
        """
        返回 Baostock 支持的所有 table_id 列表。
        """
        return list(self._SUPPORTED_TABLE_MAP.keys())
    
    def get_table_category(self, table_id: str) -> str:
        """
        返回指定 table_id 的数据类别 (TS 或 EV)。
        
        Args:
            table_id: 表标识符 (例如 ashare.kline.1d.adj.baostock)
            
        Returns:
            str: 数据类别，"timeseries" 表示时间序列数据，"event" 表示事件数据。
        """
        if table_id not in self._SUPPORTED_TABLE_MAP:
            raise ValueError(f"Table '{table_id}' is not supported by BaostockProvider.")
        return self._SUPPORTED_TABLE_MAP[table_id]

    def get_sort_keys(self, table_id: str) -> list[str]:
        """
        返回指定 table_id 的排序列列表。
        """
        category = self.get_table_category(table_id)
        if category == "timeseries":
            return ["timestamp"]
        return ["timestamp", "symbol"]

    def get_all_symbols(self, table_id: str) -> list[str]:
        """
        全量证券列表发现逻辑（基础信息库）。使用 query_stock_basic 获取全市场（含退市）的所有证券代码。
        
        解析 table_id 获取第一个分段 prefix:
        - 若 prefix == "ashare"：过滤 type == "1"（个股），确保包含退市股。
        - 若 prefix == "aindex"：过滤 type == "2"（指数）。
        - 其他：抛出 ValueError。
        """
        # 1. 预校验支持库
        if table_id not in self.get_supported_tables():
            raise ValueError(f"Table '{table_id}' is not supported by BaostockProvider.")
            
        # 解析 table_id 获取第一个分段 prefix
        prefix = table_id.split('.')[0]
        
        with SuppressOutput():
            rs = self._safe_bs_call(bs.query_stock_basic)
        
        if rs.error_code != '0':
            raise ValueError(f"Baostock discovery (basic) failed: {rs.error_msg}")
            
        data_list = []
        while (rs.error_code == '0') & rs.next():
            data_list.append(rs.get_row_data())
            
        if not data_list:
            raise ValueError(f"Baostock discovery (basic) returned empty list for table: {table_id}")
            
        # 根据返回列 ['code', 'code_name', 'ipoDate', 'outDate', 'type', 'status']
        # 提取 code (row[0])，根据 prefix 过滤 type (row[4])
        if prefix == "ashare":
            symbols = [row[0] for row in data_list if row[4] == "1"]
            logger.info(f"Discovered {len(symbols)} symbols for Universe 'ashare' (Stocks) from Baostock")
        elif prefix == "aindex":
            symbols = [row[0] for row in data_list if row[4] == "2"]
            logger.info(f"Discovered {len(symbols)} symbols for Universe 'aindex' (Indices) from Baostock")
        else:
            raise ValueError(f"Unsupported Universe prefix: {prefix}. Only 'ashare' and 'aindex' are supported.")
        
        return symbols

    def fetch(self, table_id: str, symbol: str, start_date: Any, end_date: Any, **kwargs) -> pl.DataFrame:
        """
        根据 table_id 路由至具体的下载逻辑。支持传入毫秒戳或日期字符串。
        """
        # 0. 预校验支持库
        supported = self.get_supported_tables()
        if table_id not in supported:
            raise ValueError(f"Table '{table_id}' is not supported by BaostockProvider.")

        # 1. 参数标准化：转换毫秒戳为 YYYY-MM-DD
        if isinstance(start_date, int):
            start_date = ts_to_str(start_date)
        if isinstance(end_date, int):
            end_date = ts_to_str(end_date)

        # 2. 空日期防御与 1970-01-01 起始兜底
        if not start_date:
            start_date = "1970-01-01"
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")

        # 3. 路由逻辑：解析 table_id 中间的部分 (如 kline, adj_factor)
        parts = table_id.split('.')
        if 'kline' in parts:
            return self._fetch_kline(table_id, symbol, start_date, end_date, **kwargs)
        elif 'adj_factor' in parts:
            return self._fetch_adj_factor(table_id, symbol, start_date, end_date, **kwargs)
        else:
            raise NotImplementedError(f"Table category not supported by Baostock: {table_id}")

    def _fetch_kline(self, table_id: str, symbol: str, start_date: str, end_date: str, **kwargs) -> pl.DataFrame:
        """
        私有方法：下载 K 线数据
        """
        # 解析频率和复权
        # table_id 格式示例: ashare.kline.1d.adj.baostock
        parts = table_id.split('.')
        prefix = parts[0]
        is_index = (prefix == "aindex")
        
        freq_raw = parts[2] if len(parts) > 2 else '1d'
        adj_raw = parts[3] if len(parts) > 3 else 'raw'
        
        # 映射频率
        freq_map = {'1d': 'd', '5m': '5'}
        freq = freq_map.get(freq_raw, 'd')
        is_day = (freq == 'd')
        
        # 映射复权
        adj_map = {'raw': '3', 'adj': '1'}
        adj = adj_map.get(adj_raw, '3')
        
        # Baostock K 线字段定义
        if is_index:
            # 指数 K 线字段 (日线) - 剔除返回 0 的无用字段
            #day_fields = "date,code,open,high,low,close,preclose,volume,amount,adjustflag,turn,tradestatus,pctChg"
            day_fields = "date,code,open,high,low,close,preclose,volume,amount,turn,pctChg"
            fields = day_fields
        else:
            # 个股 K 线字段 (日线, 五分钟)
            day_fields = "date,code,open,high,low,close,preclose,volume,amount,adjustflag,turn,tradestatus,pctChg,peTTM,pbMRQ,psTTM,pcfNcfTTM,isST"
            min_fields = "date,time,code,open,high,low,close,volume,amount,adjustflag"
            fields = day_fields if is_day else min_fields
        
        # 指数数据通常没有复权，强制使用不复权 (raw)
        if is_index:
            # 1. 校验复权：指数仅支持 raw，显式拦截其他请求
            if adj_raw != 'raw':
                raise ValueError(f"Baostock indices only support 'raw' (unadjusted) data, but '{adj_raw}' was requested for {symbol}.")
            
            # 2. 校验频率：指数仅支持日线，分钟数据极其不完整且不受官方正式支持，统一拦截
            if freq != 'd':
                raise ValueError(f"Baostock doesn't support reliable minute kline for indices: {symbol}.")
            
            adj = "3"
        
        logger.debug(f"Fetching {symbol} ({prefix}) kline from Baostock: {start_date} to {end_date} (freq={freq}, adj={adj})")
        
        with SuppressOutput():
            rs = self._safe_bs_call(
                bs.query_history_k_data_plus,
                symbol, fields,
                start_date=start_date, end_date=end_date,
                frequency=freq, adjustflag=adj
            )
        
        if rs.error_code != '0':
            raise RuntimeError(f"Baostock API Error: {rs.error_msg} (code={rs.error_code})")

        # 转换为 Polars DataFrame
        data_list = []
        while (rs.error_code == '0') & rs.next():
            data_list.append(rs.get_row_data())
            
        df = pl.DataFrame(data_list, schema={f: pl.String for f in fields.split(',')}, orient="row")
        
        # 字段清洗与重命名（无论是空数据还是有数据都需要重命名）
        rename_map = {
            "code": "symbol",
            "pctChg": "change_pct",
            "turn": "turnover_rate",
            "tradestatus": "trade_status",
            "isST": "is_st",
            "peTTM": "pe_ttm",
            "pbMRQ": "pb_mrq",
            "psTTM": "ps_ttm",
            "pcfNcfTTM": "pcf_ncf_ttm"
        }
        # 只重命名存在的列
        actual_rename = {k: v for k, v in rename_map.items() if k in df.columns}
        df = df.rename(actual_rename)
        
        
        # 处理 adjustflag 映射 (1:adj, 2:qfq, 3:raw)
        if "adjustflag" in df.columns:
            # 强制拦截前复权
            if (df["adjustflag"] == "2").any():
                raise ValueError("Detect Forward Adjustment (qfq) data, which is FORBIDDEN in this system.")
            
            df = df.with_columns(
                pl.col("adjustflag").replace_strict(
                    {"1": "adj", "3": "raw"}, default="unknown"
                ).alias("adjust_flag")
            ).drop("adjustflag")

        # 转换为数值类型（Baostock 返回的全是字符串）
        numeric_cols = [
            "open", "high", "low", "close", "preclose", "volume", "amount", 
            "change_pct", "turnover_rate", "pe_ttm", "pb_mrq", "ps_ttm", "pcf_ncf_ttm"
        ]
        for col in numeric_cols:
            if col in df.columns:
                df = df.with_columns(pl.col(col).cast(pl.Float64, strict=False))

        # 转换 is_st 为布尔类型 (Baostock "1" -> True, "0" -> False)
        if "is_st" in df.columns:
            df = df.with_columns(
                pl.when(pl.col("is_st") == "1").then(True).otherwise(False).cast(pl.Boolean).alias("is_st")
            )

        # 数据清洗与标准化
        # Baostock 数据源为北京时间 (UTC+8)，显式传入时区参数
        # 强制将日期时间对齐至收盘时间 15:00:00，以确保分区边界安全
        if is_day:
            return DataCleaner.standardize(df, "date", time_fmt="%Y-%m-%d", 
                                         source_tz="Asia/Shanghai", display_tz="Asia/Shanghai", time_shift_hours=15)
        else:
            # Baostock 分钟线 time 格式: YYYYMMDDHHMMSSsss (无小数点)
            # 此时 date 列是多余的，一并删除
            if "date" in df.columns:
                df = df.drop("date")
            return DataCleaner.standardize(df, "time", time_fmt="%Y%m%d%H%M%S%3f", 
                                         source_tz="Asia/Shanghai", display_tz="Asia/Shanghai")

    def _fetch_adj_factor(self, table_id: str, symbol: str, start_date: str, end_date: str, **kwargs) -> pl.DataFrame:
        """
        私有方法：下载复权因子数据 (Event)
        
        调用 bs.query_adjust_factor 接口获取指定股票的复权因子。
        按照清洗规范：
        1. 时间轴锚定：选用 dividOperateDate 作为时间主轴
        2. 字段物理剔除：删除 foreAdjustFactor 和 adjustFactor
        3. 字段保留与重命名：保留 backAdjustFactor 重命名为 back_adj_factor
        4. 类型强制转换：转换为 Float64
        5. 标准化清洗：通过 DataCleaner.standardize 补齐双时间轴字段
        """
        # Baostock 返回字段: code, dividOperateDate, foreAdjustFactor, backAdjustFactor, adjustFactor
        # 先获取所有字段，然后选择需要的字段
        all_fields = "code,dividOperateDate,foreAdjustFactor,backAdjustFactor,adjustFactor"
        
        logger.debug(f"Fetching {symbol} adj_factor from Baostock: {start_date} to {end_date}")
        
        # 调用 Baostock 复权因子查询接口
        with SuppressOutput():
            rs = self._safe_bs_call(
                bs.query_adjust_factor,
                code=symbol, start_date=start_date, end_date=end_date
            )
        
        if rs.error_code != '0':
            raise RuntimeError(f"Baostock API Error: {rs.error_msg} (code={rs.error_code})")
        
        # 转换为 Polars DataFrame
        data_list = []
        while (rs.error_code == '0') & rs.next():
            data_list.append(rs.get_row_data())
        
        # 使用所有字段创建 DataFrame
        df = pl.DataFrame(data_list, schema={f: pl.String for f in all_fields.split(',')}, orient="row")
        
        # 按照要求，只保留需要的字段并重命名
        # 1. 选择需要的列
        df = df.select(["code", "dividOperateDate", "backAdjustFactor"])
        
        # 2. 重命名字段
        rename_map = {
            "code": "symbol",
            "dividOperateDate": "date",
            "backAdjustFactor": "back_adj_factor"
        }
        df = df.rename(rename_map)
        
        # 转换为数值类型（复权因子必须是浮点数）
        # 处理可能的空值
        if "back_adj_factor" in df.columns:
            df = df.with_columns(
                pl.col("back_adj_factor")
                .cast(pl.Float64, strict=False)
            )
        
        # 数据清洗与标准化
        # Event 数据的 timestamp 必须是 date 的 15:00:00 (收盘时间) UTC+8 对应的毫秒戳
        return DataCleaner.standardize(df, "date", time_fmt="%Y-%m-%d", 
                                       source_tz="Asia/Shanghai", display_tz="Asia/Shanghai", time_shift_hours=15)

