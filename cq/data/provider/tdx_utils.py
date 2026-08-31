"""通达信数据工具。

两种数据获取模式:
  1. local:  读取本地通达信 vipdoc 目录 (由 cqdata tdx download 命令下载解压)
  2. online: 通过 tdxpy TCP 在线获取 (日线全历史, 5m~2年, 1m~5月)
"""

import os
from pathlib import Path
from typing import Any, List, Optional, Tuple, Dict

import polars as pl
from loguru import logger
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
from tdxpy.hq import TdxHq_API
from tdxpy.reader import TdxDailyBarReader, TdxLCMinBarReader

# tdxpy category 映射
_CATEGORY_MAP = {
    "1d": 4,
    "5m": 0,
    "1m": 7,
}

# tdxpy 市场映射
_MARKET_MAP = {
    "sh": 1,
    "sz": 0,
    "bj": 2,
}

# 单次最大获取量
_MAX_BARS_PER_REQUEST = 800

# vipdoc 频率子目录映射
_FREQ_TO_SUBDIR = {
    "1d": "lday",
    "5m": "minline",
    "1m": "minline",
}

# vipdoc 分钟线文件后缀映射
_FREQ_TO_EXT = {
    "1d": ".day",
    "5m": ".lc5",
    "1m": ".lc1",
}

# tdxpy reader 实例 (全局单例)
_daily_reader = TdxDailyBarReader()
_lc_min_reader = TdxLCMinBarReader()

# TDX 服务器候选池 (经过行情数据严格探针验证的高可用节点，包含最新实测极速节点与原可用节点)
_TDX_SERVERS = [
    ("180.153.18.170", 7709),
    ("218.75.126.9", 7709),
    ("115.238.56.198", 7709),
    ("60.191.117.167", 7709),
]

# 模块级 TCP 连接缓存，同进程复用同一服务器
_cached_api: TdxHq_API | None = None

_PROBE_TIMEOUT = 3.0
_PROBE_MAX_WORKERS = 12


def _probe_one_server(ip: str, port: int) -> tuple[str, int, float] | None:
    """探测单个服务器延迟及行情获取能力，返回 (ip, port, latency_ms) 或 None。"""
    import time as _time

    api = TdxHq_API()
    t0 = _time.monotonic()
    try:
        if api.connect(ip, port):
            # 真实行情探针：确保服务器不仅能建立 TCP 连接，还能正常响应行情请求
            res = api.get_security_bars(4, 0, "000001", 0, 1)
            latency = (_time.monotonic() - t0) * 1000
            api.disconnect()
            if res and len(res) > 0:
                return (ip, port, latency)
    except Exception:
        pass
    return None


def _probe_best_server() -> tuple[str, int, float]:
    """并发探测延迟最低的可用服务器，返回 (ip, port, latency_ms)。"""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    logger.debug(f"开始探测 TDX 服务器 ({len(_TDX_SERVERS)} 个候选)")
    best_ip, best_port, best_latency = None, None, float("inf")
    reachable = 0
    with ThreadPoolExecutor(max_workers=_PROBE_MAX_WORKERS) as pool:
        futures = {
            pool.submit(_probe_one_server, ip, port): (ip, port)
            for ip, port in _TDX_SERVERS
        }
        try:
            for f in as_completed(futures, timeout=_PROBE_TIMEOUT):
                try:
                    result = f.result()
                    if result:
                        reachable += 1
                        if result[2] < best_latency:
                            best_ip, best_port, best_latency = result
                            logger.debug(f"  新最快: {best_ip}:{best_port} ({best_latency:.0f}ms)")
                except Exception:
                    continue
        except TimeoutError:
            pass
    if best_ip is None:
        raise RuntimeError("TDX 服务器全部不可用，请检查网络")
    logger.info(f"TDX 服务器选定: {best_ip}:{best_port} ({best_latency:.0f}ms), 可达 {reachable}/{len(_TDX_SERVERS)}")
    return best_ip, best_port, best_latency


_tdxpy_patched = False


def _patch_tdxpy_once() -> None:
    """针对 tdxpy 补充 market=2 (BJ 北交所) 的安全 Monkeypatch。

    只在 market in (2, 'bj', 'BJ') 时生效，market in (0, 1) 完全原封不动透传。
    """
    global _tdxpy_patched
    if _tdxpy_patched:
        return
    try:
        import tdxpy.constants as c
        import tdxpy.helper as h

        c.SECURITY_COEFFICIENT["BJ_A_STOCK"] = [0.01, 0.01]
        c.SECURITY_COEFFICIENT["BJ_INDEX"] = [0.01, 1.0]

        orig_get_security_type = h.get_security_type

        def hooked_get_security_type(market: Any, code: Any) -> str:
            code_str = str(code)
            if market in ("BJ", "bj", 2):
                return "BJ_INDEX" if code_str.startswith("89") else "BJ_A_STOCK"
            return orig_get_security_type(market, code)

        h.get_security_type = hooked_get_security_type
        _tdxpy_patched = True
    except Exception as e:
        logger.warning(f"[TDX] Patching tdxpy for market=2 failed: {e}")


def _connect_tdx_api() -> TdxHq_API:
    """连接 TDX 服务器。复用已有连接，断线时才重新探测。"""
    global _cached_api
    _patch_tdxpy_once()
    if _cached_api is not None:
        return _cached_api

    best_ip, best_port, best_latency = _probe_best_server()
    api = TdxHq_API()
    api.connect(best_ip, best_port)
    _cached_api = api
    logger.debug(f"TDX connected: {best_ip}:{best_port} ({best_latency:.0f}ms)")
    return api


def _reconnect_tdx_api() -> TdxHq_API:
    """断线重连：清除缓存并重新探测。"""
    global _cached_api
    _cached_api = None
    return _connect_tdx_api()


# -----------------------------------------------------------------------
# 代码格式转换
# -----------------------------------------------------------------------

def tdx_code_to_standard(tdx_code: str) -> str:
    """通达信格式 → 标准格式 (sh600000 → sh.600000)。"""
    if len(tdx_code) >= 2:
        return f"{tdx_code[:2]}.{tdx_code[2:]}"
    return tdx_code


def standard_to_tdx_code(standard_code: str) -> str:
    """标准格式 → 通达信格式 (sh.600000 → sh600000)。"""
    return standard_code.replace('.', '')


# -----------------------------------------------------------------------
# 本地 vipdoc 目录读取
# -----------------------------------------------------------------------

def discover_tdx_symbols_from_local(vipdoc_dir: Path, market: str = "all") -> list[str]:
    """从本地 vipdoc lday 目录发现所有证券代码。"""
    symbols = set()
    lday_dir = vipdoc_dir / "lday"

    if not lday_dir.exists():
        for market_dir in ["sh", "sz", "bj"]:
            mlday = vipdoc_dir / market_dir / "lday"
            if mlday.exists():
                for f in mlday.iterdir():
                    if f.suffix == ".day":
                        code = f.stem
                        if market != "all" and not code.startswith(market):
                            continue
                        symbols.add(code)
    else:
        for f in lday_dir.iterdir():
            if f.suffix == ".day":
                code = f.stem
                if market != "all" and not code.startswith(market):
                    continue
                symbols.add(code)

    return sorted(symbols)


def read_tdx_file_from_local(
    vipdoc_dir: Path, tdx_code: str, freq: str = "1d"
) -> list[dict]:
    """从本地 vipdoc 目录读取指定证券的数据。

    使用 tdxpy reader 解析二进制文件，返回标准记录列表。
    """
    subdir = _FREQ_TO_SUBDIR.get(freq)
    ext = _FREQ_TO_EXT.get(freq)
    if not subdir or not ext:
        raise ValueError(f"不支持的频率: {freq}")

    market = tdx_code[:2]
    file_path = vipdoc_dir / market / subdir / f"{tdx_code}{ext}"

    if not file_path.exists():
        logger.warning(f"文件不存在: {file_path}")
        return []

    try:
        if freq == "1d":
            pdf = _daily_reader.get_df(str(file_path))
        else:
            pdf = _lc_min_reader.get_df(str(file_path))

        if pdf.empty:
            return []

        records = []
        for idx, row in pdf.iterrows():
            if freq == "1d":
                dt_str = idx.strftime("%Y-%m-%d")
                records.append({
                    "date": dt_str,
                    "open": round(float(row["open"]), 4),
                    "high": round(float(row["high"]), 4),
                    "low": round(float(row["low"]), 4),
                    "close": round(float(row["close"]), 4),
                    "volume": float(row["volume"]),
                    "amount": round(float(row["amount"]), 2),
                })
            else:
                dt_str = idx.strftime("%Y-%m-%d %H:%M:%S")
                date_part = idx.strftime("%Y-%m-%d")
                records.append({
                    "datetime": dt_str,
                    "date": date_part,
                    "time": idx.strftime("%H:%M:%S"),
                    "open": round(float(row["open"]), 4),
                    "high": round(float(row["high"]), 4),
                    "low": round(float(row["low"]), 4),
                    "close": round(float(row["close"]), 4),
                    "volume": float(row["volume"]),
                    "amount": round(float(row["amount"]), 2),
                })

        return records

    except Exception as e:
        logger.warning(f"解析失败: {file_path}, {e}")
        return []


# -----------------------------------------------------------------------
# 在线获取 (tdxpy TCP)
# -----------------------------------------------------------------------

_MAX_NETWORK_RETRIES = int(os.environ.get("MAX_RETRIES", "3"))


@retry(
    stop=stop_after_attempt(_MAX_NETWORK_RETRIES),
    wait=wait_exponential(multiplier=1, min=0.5, max=5),
    retry=retry_if_exception_type((ConnectionError, OSError, TimeoutError, RuntimeError)),
    reraise=True,
)
def _safe_tcp_call(callable_fn) -> list[dict] | None:
    """TCP 调用封装：连接/网络异常时自动重连换 IP 重试 (tenacity 指数退避)。"""
    global _cached_api
    try:
        # 若 _cached_api 为 None 或 client 状态断开，先尝试重新建立 TCP 连接
        if _cached_api is None or getattr(_cached_api, "client", None) is None:
            _connect_tdx_api()

        res = callable_fn()

        if res is None:
            # 检查调用过程中 socket 是否真正断开 (tdxpy 会在断线时将 client 设为 None)
            if _cached_api is None or getattr(_cached_api, "client", None) is None:
                logger.warning("[TDX] TCP Socket 已断开，尝试重连...")
                _reconnect_tdx_api()
                res = callable_fn()
                if res is None and (_cached_api is None or getattr(_cached_api, "client", None) is None):
                    raise ConnectionError("TDX TCP 无法获取数据 (服务器返回 None 或网络断开)")

        return res
    except (ConnectionError, OSError, TimeoutError, RuntimeError):
        _cached_api = None
        raise


def fetch_bars_online(
    symbol: str,
    freq: str = "1d",
    start_date: str = None,
    end_date: str = None,
    table_id: str = "",
) -> pl.DataFrame:
    """通过 TDX TCP 在线获取 K 线数据 (支持 offset 回溯)。"""
    tdx_code = standard_to_tdx_code(symbol)
    pure_code = tdx_code[2:]
    market_str = tdx_code[:2]
    market = _MARKET_MAP.get(market_str)
    if market is None:
        raise ValueError(f"未知市场前缀: {market_str}")

    category = _CATEGORY_MAP.get(freq)
    if category is None:
        raise ValueError(f"不支持的频率: {freq}")

    # 依据 Single Source of Truth (SSOT) 原则，仅由 table_id 前缀决定是否为指数表
    is_index = table_id.startswith("aindex")
    fetch_market = market

    is_minute = freq in ("5m", "1m")

    _connect_tdx_api()
    all_records = []
    offset = 0

    while True:
        if is_index:
            data = _safe_tcp_call(lambda: _cached_api.get_index_bars(category, fetch_market, pure_code, offset, _MAX_BARS_PER_REQUEST))
        else:
            data = _safe_tcp_call(lambda: _cached_api.get_security_bars(category, fetch_market, pure_code, offset, _MAX_BARS_PER_REQUEST))

        if not data:
            break

        for row in data:
            dt_str = str(row.get("datetime", ""))
            year = row.get("year", 0)

            # Fail-Fast 校验：通达信服务端错位解包或网络包损坏时，立即抛出 ValueError 终止流水线，防止水质污染与水位线误推进
            if not dt_str or dt_str.startswith("0-") or len(dt_str) < 8 or (year != 0 and (year < 1970 or year > 2100)):
                raise ValueError(f"[TDX Data Error] {symbol} 收到损坏的数据记录 (datetime='{dt_str}', year={year})，触发 Fail-Fast 保护")

            try:
                vol_val = float(row.get("vol", 0))
                amt_val = float(row.get("amount", 0))
            except (ValueError, TypeError) as e:
                raise ValueError(f"[TDX Data Error] {symbol} 数值解析失败: {e}") from e

            if not (0 <= vol_val < 1e18) or not (0 <= amt_val < 1e18):
                raise ValueError(f"[TDX Data Error] {symbol} 收到超范围异常数值 (volume={vol_val}, amount={amt_val})，触发 Fail-Fast 保护")

            date_part = dt_str[:10]
            rec = {
                "open": round(float(row.get("open", 0)), 4),
                "high": round(float(row.get("high", 0)), 4),
                "low": round(float(row.get("low", 0)), 4),
                "close": round(float(row.get("close", 0)), 4),
                "volume": vol_val,
                "amount": round(amt_val, 2),
            }
            if is_minute:
                rec["datetime"] = dt_str
                rec["date"] = date_part
            else:
                rec["date"] = date_part
            all_records.append(rec)

        if start_date and len(data) > 0:
            earliest = data[0]["datetime"][:10]
            if earliest <= start_date:
                break

        if len(data) < _MAX_BARS_PER_REQUEST:
            break

        offset += _MAX_BARS_PER_REQUEST

    if not all_records:
        return _empty_kline_df()

    if is_minute:
        df = pl.DataFrame(all_records, schema={
            "datetime": pl.String,
            "date": pl.String,
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume": pl.Float64,
            "amount": pl.Float64,
        })
    else:
        df = pl.DataFrame(all_records, schema={
            "date": pl.String,
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume": pl.Float64,
            "amount": pl.Float64,
        })

    df = df.with_columns(pl.lit(symbol).alias("symbol"))

    if start_date:
        df = df.filter(pl.col("date") >= start_date)
    if end_date:
        df = df.filter(pl.col("date") <= end_date)

    return df


def fetch_stock_list_online(market: str = "sh") -> list[str]:
    """通过 TDX TCP 获取股票列表。对 market=='bj' 静默返回 []。"""
    if market == "bj":
        return []

    market_code = _MARKET_MAP.get(market)
    if market_code is None:
        raise ValueError(f"未知市场: {market}")

    _connect_tdx_api()
    all_codes = []
    offset = 0
    while True:
        stocks = _safe_tcp_call(lambda: _cached_api.get_security_list(market_code, offset))
        if not stocks:
            break
        for row in stocks:
            code = str(row["code"]).strip()
            all_codes.append(f"{market}{code}")
        if len(stocks) < 1000:
            break
        offset += 1000

    return sorted(set(all_codes))


def _empty_kline_df() -> pl.DataFrame:
    """返回标准 schema 的空 K 线 DataFrame。"""
    return pl.DataFrame({
        "symbol": pl.Series([], dtype=pl.String),
        "datetime": pl.Series([], dtype=pl.String),
        "timestamp": pl.Series([], dtype=pl.Int64),
        "open": pl.Series([], dtype=pl.Float64),
        "high": pl.Series([], dtype=pl.Float64),
        "low": pl.Series([], dtype=pl.Float64),
        "close": pl.Series([], dtype=pl.Float64),
        "volume": pl.Series([], dtype=pl.Float64),
        "amount": pl.Series([], dtype=pl.Float64),
    })
