"""
cqdata/entrypoints/rest_api.py

FastAPI RESTful HTTP API 接入面模块。
全面复用统一的 Service 探查与查询接口，为 Web 应用、微服务与跨语言客户端提供 HTTP 数据服务。
数据切片查询统一使用 HTTP GET 形式，并提供标准的 page / page_size 分页支持。
"""

import math
import json
import asyncio
import importlib.resources
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Union, Dict, Any
import polars as pl
from fastapi import FastAPI, HTTPException, BackgroundTasks, Query, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel
from loguru import logger
from cq.data.config import settings
from cq.data.utils.logger_utils import log_broadcaster, setup_logger
from cq.data import __version__
from cq.data.entrypoints.python_api import (
    read,
    write,
    list_tables,
    list_formats,
    list_symbols,
    get_time_range,
    get_schema,
    get_row_count,
    sync
)


class SPAStaticFiles(StaticFiles):
    """
    FastAPI / Starlette 标准 SPA 静态文件托管支持：
    - 已存在的静态文件 (JS/CSS/Font/Icon)：提供高性能异步流响应并支持 ETag 304 缓存
    - 前端 SPA 页面路由：文件不存在时自动回退渲染 index.html
    - /api/* 端点：未匹配时保持标准的 404 HTTP 异常
    """
    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as ex:
            if ex.status_code == 404:
                norm_path = path.replace("\\", "/")
                if norm_path.startswith("api/"):
                    raise StarletteHTTPException(status_code=404, detail=f"API endpoint '/{norm_path}' not found")
                return await super().get_response("index.html", scope)
            raise ex


# 初始化全系统 Loguru 日志，挂载 LogBroadcaster.sink 供 SSE 日志流使用
setup_logger()

app = FastAPI(title="CarrotQuant.Data REST API", version=__version__)

# 挂载 CORS 跨域中间件与 GZip 压缩中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)


@app.get("/api/v1/health")
async def api_health_check():
    """健康检查与系统运行状态探针"""
    return {
        "status": "ok",
        "version": __version__,
        "data_dir": str(settings.data_dir),
        "active_tasks": len(ACTIVE_SYNC_TASKS)
    }


def handle_endpoint_exception(e: Exception, endpoint_name: str):
    """
    REST API 精细化异常分发与 HTTP 状态码转换：
    - FileNotFoundError / KeyError -> 404 Not Found
    - ValueError -> 400 Bad Request
    - HTTPException -> 原样抛出
    - 其他未捕获系统异常 -> 500 Internal Server Error
    """
    if isinstance(e, HTTPException):
        raise e
    if isinstance(e, (FileNotFoundError, KeyError)):
        logger.warning(f"[REST API] {endpoint_name} 资源未找到: {e}")
        raise HTTPException(status_code=404, detail=f"Resource not found: {e}")
    if isinstance(e, ValueError):
        logger.warning(f"[REST API] {endpoint_name} 请求参数错误: {e}")
        raise HTTPException(status_code=400, detail=f"Bad request parameter: {e}")

    logger.error(f"[REST API] {endpoint_name} 服务器内部错误: {e}")
    raise HTTPException(status_code=500, detail=str(e))


# 全局并发锁集合，防止同一 table_id 重复并发同步
ACTIVE_SYNC_TASKS = set()


class SyncRequest(BaseModel):
    table_ids: List[str]
    formats: List[str] = ["parquet"]
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    force_refresh: bool = False
    batch_size: int = 100
    symbol_limit: Optional[int] = None
    provider_kwargs: Optional[Dict[str, Any]] = None


class TableWriteRequest(BaseModel):
    table_id: str
    data: List[Dict[str, Any]]
    category: str = "timeseries"
    formats: List[str] = ["parquet"]
    mode: str = "append"
    sort_keys: Optional[List[str]] = None




def parse_comma_param(val: Optional[str]) -> Optional[List[str]]:
    """将逗号分隔的 Query 字符串解析为 List[str] 清单"""
    if not val:
        return None
    items = [item.strip() for item in val.split(",") if item.strip()]
    return items if items else None


def run_sync_task(
    table_id: str,
    formats: List[str],
    start_date: Optional[str],
    end_date: Optional[str],
    force_refresh: bool,
    batch_size: int,
    symbol_limit: Optional[int],
    provider_kwargs: Optional[Dict[str, Any]] = None
):
    """后台同步任务执行器"""
    try:
        sync(
            table_ids=[table_id],
            formats=formats,
            start_date=start_date,
            end_date=end_date,
            force_refresh=force_refresh,
            batch_size=batch_size,
            symbol_limit=symbol_limit,
            provider_kwargs=provider_kwargs
        )
        logger.info(f"[REST API] Background sync finished for {table_id}")
    except Exception as e:
        logger.error(f"[REST API] Background sync failed for {table_id}: {e}")
    finally:
        ACTIVE_SYNC_TASKS.remove(table_id)


import json
from cq.data.service.metadata_manager import MetadataManager
from cq.data.service.sync_tracker import sync_tracker

# 所有支持的标准 Table ID 预定义字典与元数据映射 (全量 16 个内置数据表)
KNOWN_TABLE_DEFINITIONS = [
    # Baostock 6 表
    {
        "table_id": "ashare.kline.1d.raw.baostock",
        "name": "Baostock A股日线 (不复权)",
        "category": "timeseries",
        "source": "baostock",
        "description": "个股日线 OHLCV 数据，按 [symbol, year] CSV/Parquet 分片"
    },
    {
        "table_id": "ashare.kline.1d.adj.baostock",
        "name": "Baostock A股日线 (后复权)",
        "category": "timeseries",
        "source": "baostock",
        "description": "个股后复权 K 线数据"
    },
    {
        "table_id": "ashare.kline.5m.raw.baostock",
        "name": "Baostock A股5分钟线 (不复权)",
        "category": "timeseries",
        "source": "baostock",
        "description": "个股高频 5 分钟 K 线数据"
    },
    {
        "table_id": "ashare.kline.5m.adj.baostock",
        "name": "Baostock A股5分钟线 (后复权)",
        "category": "timeseries",
        "source": "baostock",
        "description": "个股高频 5 分钟后复权 K 线数据"
    },
    {
        "table_id": "aindex.kline.1d.raw.baostock",
        "name": "Baostock 指数日线 (不复权)",
        "category": "timeseries",
        "source": "baostock",
        "description": "大盘与主要指数日线 OHLCV 数据"
    },
    {
        "table_id": "ashare.adj_factor.baostock",
        "name": "Baostock A股后复权因子",
        "category": "event",
        "source": "baostock",
        "description": "个股历史除权除息与后复权因子 (Event 表)"
    },
    # EastMoney 4 表
    {
        "table_id": "ashare.concept.eastmoney",
        "name": "东方财富 概念板块与成分股",
        "category": "event",
        "source": "eastmoney",
        "description": "东财概念板块代码与成分股映射 (Event 表)"
    },
    {
        "table_id": "ashare.industry.eastmoney",
        "name": "东方财富 行业板块与成分股",
        "category": "event",
        "source": "eastmoney",
        "description": "东财行业板块成分股映射 (Event 表)"
    },
    {
        "table_id": "ashare.dragon_tiger.eastmoney",
        "name": "东方财富 龙虎榜每日统计",
        "category": "event",
        "source": "eastmoney",
        "description": "机构与营业部每日上榜明细 (Event 表)"
    },
    {
        "table_id": "ashare.inst_trade.eastmoney",
        "name": "东方财富 机构交易明细",
        "category": "event",
        "source": "eastmoney",
        "description": "机构席位买卖交易明细 (Event 表)"
    },
    # TDX (通达信) 6 表
    {
        "table_id": "ashare.kline.1d.raw.tdx",
        "name": "通达信 A股日线 (TDX)",
        "category": "timeseries",
        "source": "tdx",
        "description": "通达信本地 vipdoc 或在线日线数据"
    },
    {
        "table_id": "ashare.kline.5m.raw.tdx",
        "name": "通达信 A股5分钟线 (TDX)",
        "category": "timeseries",
        "source": "tdx",
        "description": "通达信本地 vipdoc 或在线 5 分钟线数据"
    },
    {
        "table_id": "ashare.kline.1m.raw.tdx",
        "name": "通达信 A股1分钟线 (TDX)",
        "category": "timeseries",
        "source": "tdx",
        "description": "通达信本地 vipdoc 或在线 1 分钟超高频数据"
    },
    {
        "table_id": "aindex.kline.1d.raw.tdx",
        "name": "通达信 指数日线 (TDX)",
        "category": "timeseries",
        "source": "tdx",
        "description": "通达信大盘与主要指数日线数据"
    },
    {
        "table_id": "aindex.kline.5m.raw.tdx",
        "name": "通达信 指数5分钟线 (TDX)",
        "category": "timeseries",
        "source": "tdx",
        "description": "通达信大盘与主要指数 5 分钟线数据"
    },
    {
        "table_id": "aindex.kline.1m.raw.tdx",
        "name": "通达信 指数1分钟线 (TDX)",
        "category": "timeseries",
        "source": "tdx",
        "description": "通达信大盘与主要指数 1 分钟线数据"
    }
]


# ==================== 元数据探查 Endpoints ====================

@app.get("/api/v1/tables")
def api_list_all_tables(format: str = "auto"):
    """获取所有本地数据表总览清单 (平铺对象列表，含 category 属性)"""
    try:
        tables = list_tables(format=format)
        return {
            "tables": tables,
            "total": len(tables)
        }
    except Exception as e:
        handle_endpoint_exception(e, "GET tables")


@app.get("/api/v1/tables/detailed")
def api_list_tables_detailed():
    """
    获取所有数据表及其各个存储格式 (Parquet / CSV) 独立物理元数据的详细列表。
    方便前端展现层级化数据管理表格与独立格式水位线。
    """
    try:
        meta_mgr = MetadataManager(settings.data_dir)
        disk_tables = {t["table_id"] for t in list_tables(format="auto")}
        result = []

        # 汇总所有的预定义表以及磁盘发现的其他表
        all_table_ids = set([t["table_id"] for t in KNOWN_TABLE_DEFINITIONS]) | disk_tables
        known_map = {t["table_id"]: t for t in KNOWN_TABLE_DEFINITIONS}

        for table_id in sorted(all_table_ids):
            base_info = known_map.get(table_id, {
                "table_id": table_id,
                "name": table_id,
                "category": "timeseries" if "kline" in table_id else "event",
                "source": table_id.split(".")[-1] if "." in table_id else "unknown",
                "description": f"自定义本地数据表 ({table_id})"
            })

            formats_info = {}
            for fmt in ["parquet", "csv"]:
                meta = meta_mgr.load(table_id, fmt)
                if meta and "statistics" in meta:
                    stats = meta["statistics"]
                    formats_info[fmt] = {
                        "exists": True,
                        "updated_at": stats.get("updated_at"),
                        "start_datetime": stats.get("start_datetime"),
                        "end_datetime": stats.get("end_datetime"),
                        "total_bars": stats.get("total_bars", 0),
                        "symbol_count": stats.get("symbol_count", 0),
                    }
                else:
                    formats_info[fmt] = {
                        "exists": False,
                        "updated_at": None,
                        "start_datetime": None,
                        "end_datetime": None,
                        "total_bars": 0,
                        "symbol_count": 0,
                    }

            table_entry = {
                **base_info,
                "formats": formats_info
            }
            result.append(table_entry)

        return {
            "tables": result,
            "total": len(result)
        }
    except Exception as e:
        handle_endpoint_exception(e, "GET tables/detailed")


@app.get("/api/v1/tables/{table_id}/formats")
def api_list_formats(table_id: str):
    """获取某表在本地已有的格式列表"""
    try:
        return {"table_id": table_id, "formats": list_formats(table_id)}
    except Exception as e:
        handle_endpoint_exception(e, f"GET formats for {table_id}")


@app.get("/api/v1/tables/{table_id}/symbols")
def api_list_symbols(table_id: str, format: str = "auto"):
    """获取某表包含的 symbol 唯一代码列表"""
    try:
        symbols = list_symbols(table_id, format=format)
        return {"table_id": table_id, "symbol_count": len(symbols), "symbols": symbols}
    except Exception as e:
        handle_endpoint_exception(e, f"GET symbols for {table_id}")


@app.get("/api/v1/tables/{table_id}/time_range")
def api_get_time_range(table_id: str, format: str = "auto"):
    """获取某表的时间跨度 (start_datetime, end_datetime)"""
    try:
        start_dt, end_dt = get_time_range(table_id, format=format)
        return {"table_id": table_id, "start_datetime": start_dt, "end_datetime": end_dt}
    except Exception as e:
        handle_endpoint_exception(e, f"GET time_range for {table_id}")


@app.get("/api/v1/tables/{table_id}/schema")
def api_get_schema(table_id: str, format: str = "auto"):
    """获取某表在元数据中的字段 Schema 列名与类型"""
    try:
        return {"table_id": table_id, "schema": get_schema(table_id, format=format)}
    except Exception as e:
        handle_endpoint_exception(e, f"GET schema for {table_id}")


@app.get("/api/v1/tables/{table_id}/row_count")
def api_get_row_count(table_id: str, format: str = "auto"):
    """获取某表在物理存储中的记录总行数/条目数"""
    try:
        return {"table_id": table_id, "row_count": get_row_count(table_id, format=format)}
    except Exception as e:
        handle_endpoint_exception(e, f"GET row_count for {table_id}")


@app.get("/api/v1/tables/{table_id}/boards")
def api_get_boards(
    table_id: str,
    query: Optional[str] = Query(None, description="搜索板块代码或名称 (如 BK0612 或 低空经济)"),
    format: str = Query("auto", description="存储格式"),
    page: int = Query(1, ge=1, description="当前页码"),
    page_size: int = Query(500, ge=1, description="每页板块数")
):
    """
    极速聚合获取板块概念/行业列表及各板块成分股计数 (轻量 20KB 数据包)
    """
    try:
        df = read(table_id=table_id, format=format)
        if df.is_empty() or "board_code" not in df.columns:
            return {"table_id": table_id, "boards": [], "total": 0, "page": page, "page_size": page_size}

        boards_df = (
            df.group_by(["board_code", "board_name"])
            .agg(pl.len().alias("stock_count"))
            .sort("board_code")
        )

        if query:
            q = query.strip()
            boards_df = boards_df.filter(
                pl.col("board_name").str.contains(f"(?i){q}") | pl.col("board_code").str.contains(f"(?i){q}")
            )

        total = boards_df.height
        offset = (page - 1) * page_size
        sliced = boards_df.slice(offset, page_size) if not boards_df.is_empty() else boards_df

        boards_list = [
            {
                "board_code": row[0],
                "board_name": row[1],
                "stock_count": row[2]
            }
            for row in sliced.iter_rows()
        ]

        return {
            "table_id": table_id,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": math.ceil(total / page_size) if total > 0 else 0,
            "boards": boards_list
        }
    except Exception as e:
        handle_endpoint_exception(e, f"GET boards for {table_id}")


# ==================== 数据切片查询 Endpoints (纯 HTTP GET 形式) ====================

@app.get("/api/v1/query")
def api_query(
    table_id: str = Query(..., description="数据表 ID (如 ashare.kline.1d.raw.baostock 或 ashare.dragon_tiger.eastmoney)"),
    symbols: Optional[str] = Query(None, description="股票代码或以逗号分隔的代码列表 (如 sh.600000,sz.000001)"),
    board_code: Optional[str] = Query(None, description="板块代码 (如 BK0612) 用于精确定向获取板块成分股"),
    start_date: Optional[str] = Query(None, description="起始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    columns: Optional[str] = Query(None, description="选挑字段清单，以逗号分隔 (如 timestamp,close)"),
    format: str = Query("auto", description="存储格式 (auto, parquet, csv)"),
    page: int = Query(1, ge=1, description="当前页码 (从1开始)"),
    page_size: int = Query(5000, ge=1, description="每页记录数")
):
    """
    统一切片查询接口 (自动按 table_id 智能路由)，支持 HTTP GET 查询参数与物理分页，输出二维 List 矩阵
    """
    try:
        parsed_symbols = parse_comma_param(symbols)
        parsed_columns = parse_comma_param(columns)

        df = read(
            table_id=table_id,
            symbols=parsed_symbols,
            start_date=start_date,
            end_date=end_date,
            columns=parsed_columns,
            format=format
        )

        # 支持按 board_code 过滤成分股
        if board_code and "board_code" in df.columns:
            df = df.filter(pl.col("board_code") == board_code.strip())

        total = df.height
        total_pages = math.ceil(total / page_size) if total > 0 else 0
        offset = (page - 1) * page_size

        sliced_df = df.slice(offset, page_size) if not df.is_empty() else df

        return {
            "table_id": table_id,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "count": sliced_df.height,
            "columns": sliced_df.columns,
            "data": sliced_df.rows() if not sliced_df.is_empty() else []
        }
    except Exception as e:
        handle_endpoint_exception(e, "GET query")


@app.post("/api/v1/write")
def api_write_data(request: TableWriteRequest):

    """
    统一数据写入/导入 API 端点。
    支持将外部 JSON 结构化数据写入本地指定的数据表，并自动生成/更新 metadata.json。
    """
    try:
        if not request.data:
            raise HTTPException(status_code=400, detail="Data payload cannot be empty.")

        df = pl.DataFrame(request.data)
        result = write(
            table_id=request.table_id,
            df=df,
            category=request.category,
            formats=request.formats,
            mode=request.mode,
            sort_keys=request.sort_keys
        )
        return {
            "status": "success",
            "table_id": request.table_id,
            "result": result
        }
    except Exception as e:
        handle_endpoint_exception(e, f"POST write for {request.table_id}")



# ==================== 同步与控制 Endpoints ====================

@app.post("/api/v1/sync")
async def api_sync_data(request: SyncRequest, background_tasks: BackgroundTasks):
    """异步触发数据同步 (写/非幂等操作，保留 HTTP POST 方法)"""
    processing_tables = []
    locked_tables = []

    for table_id in request.table_ids:
        if table_id in ACTIVE_SYNC_TASKS:
            locked_tables.append(table_id)
        else:
            ACTIVE_SYNC_TASKS.add(table_id)
            processing_tables.append(table_id)

    if locked_tables and not processing_tables:
        raise HTTPException(status_code=409, detail=f"Tasks already running for tables: {locked_tables}")

    for table_id in processing_tables:
        background_tasks.add_task(
            run_sync_task,
            table_id,
            request.formats,
            request.start_date,
            request.end_date,
            request.force_refresh,
            request.batch_size,
            request.symbol_limit,
            request.provider_kwargs
        )

    return {
        "status": "accepted",
        "started_tasks": processing_tables,
        "ignored_tasks": locked_tables,
        "message": "Sync tasks started in background."
    }


@app.get("/api/v1/tasks")
async def api_get_active_tasks():
    """获取正在运行的后台同步任务"""
    return {"active_tasks": list(ACTIVE_SYNC_TASKS)}


@app.get("/api/v1/sync/status")
async def api_get_sync_status():
    """获取所有同步任务的详细精准状态与进度 (含 current, total, percentage, symbol 与 error_msg)"""
    return {
        "active_tasks": list(ACTIVE_SYNC_TASKS),
        "statuses": sync_tracker.get_all_statuses()
    }


@app.get("/api/v1/logs/stream")
async def api_logs_stream(request: Request):
    """
    【SSE】Server-Sent Events 全局 Loguru 日志与任务进度实时推送流。
    握手时自动补发最新 100 条历史 Log 上下文，随后增量流式推送系统与数据引擎日志。
    """
    async def log_event_generator():
        q = log_broadcaster.subscribe()
        try:
            # 1. 先推送历史 Buffer 缓存
            history = log_broadcaster.get_history()
            for entry in history:
                yield f"data: {json.dumps(entry, ensure_ascii=False)}\n\n"
            
            # 2. 循环推送实时增量 Loguru 日志 (定期检查客户端断连状态，防止 TestClient / CI 卡死)
            while not await request.is_disconnected():
                try:
                    # 1 秒超时以高频响应客户端断连检测
                    entry = await asyncio.wait_for(q.get(), timeout=1.0)
                    yield f"data: {json.dumps(entry, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            log_broadcaster.unsubscribe(q)

    return StreamingResponse(log_event_generator(), media_type="text/event-stream")


# ==================== TDX 离线包与路径检查 Endpoints ====================

class TdxDownloadRequest(BaseModel):
    vipdoc_dir: str = r"C:\new_tdx\vipdoc"


@app.get("/api/v1/tdx/check")
def api_tdx_check(vipdoc_dir: str = Query(r"C:\new_tdx\vipdoc", description="通达信 vipdoc 目录路径")):
    """检查通达信 vipdoc 路径物理状态与包含的代码数量"""
    try:
        path = Path(vipdoc_dir)
        from cq.data.provider.tdx_utils import discover_tdx_symbols_from_local
        symbols = discover_tdx_symbols_from_local(path) if path.exists() else []
        return {
            "path": str(path),
            "exists": path.exists(),
            "symbol_count": len(symbols),
            "valid": len(symbols) > 0,
        }
    except Exception as e:
        handle_endpoint_exception(e, "GET tdx check")


def run_tdx_download_task(vipdoc_dir: str):
    """后台下载并解压通达信全量 hsjday.zip 包"""
    task_id = "tdx.download.hsjday"
    try:
        from scripts.download_tdx import download_and_extract
        download_and_extract(Path(vipdoc_dir), task_id=task_id)
    except Exception as e:
        logger.error(f"[REST API] TDX Zip download failed: {e}")
    finally:
        if task_id in ACTIVE_SYNC_TASKS:
            ACTIVE_SYNC_TASKS.remove(task_id)


@app.post("/api/v1/tdx/download")
async def api_tdx_download(request: TdxDownloadRequest, background_tasks: BackgroundTasks):
    """触发后台从通达信官方服务器下载 hsjday.zip 离线日线行情包并自动解压部署"""
    task_id = "tdx.download.hsjday"
    if task_id in ACTIVE_SYNC_TASKS:
        raise HTTPException(status_code=409, detail="TDX zip download task is already running.")

    ACTIVE_SYNC_TASKS.add(task_id)
    background_tasks.add_task(run_tdx_download_task, request.vipdoc_dir)

    return {
        "status": "accepted",
        "task_id": task_id,
        "vipdoc_dir": request.vipdoc_dir,
        "message": "TDX hsjday.zip download started in background."
    }


# ==================== 本地文件系统探查 Endpoints ====================

def _scan_directory(target_path: Path) -> Dict[str, Any]:
    """安全扫描目录内容并输出标准化文件/文件夹元数据列表"""
    if not target_path.exists():
        return {
            "path": str(target_path),
            "exists": False,
            "is_dir": False,
            "total": 0,
            "items": []
        }

    if not target_path.is_dir():
        stat = target_path.stat()
        mtime_iso = datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat()
        return {
            "path": str(target_path),
            "exists": True,
            "is_dir": False,
            "total": 1,
            "items": [
                {
                    "name": target_path.name,
                    "path": str(target_path),
                    "is_dir": False,
                    "size": stat.st_size,
                    "updated_at": mtime_iso,
                }
            ]
        }

    items = []
    try:
        for child in sorted(target_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            try:
                stat = child.stat()
                mtime_iso = datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat()
                items.append({
                    "name": child.name,
                    "path": str(child),
                    "is_dir": child.is_dir(),
                    "size": stat.st_size if child.is_file() else 0,
                    "updated_at": mtime_iso,
                })
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"[REST API] 扫描目录 {target_path} 异常: {e}")

    return {
        "path": str(target_path.resolve()),
        "exists": True,
        "is_dir": True,
        "total": len(items),
        "items": items
    }


@app.get("/api/v1/filesystem/list")
def api_filesystem_list(
    path: Optional[str] = Query(None, description="要查看的本地目录或文件路径，默认指向数据目录")
):
    """
    通用本地文件系统探查 API。
    用于极速查看文件夹/文件内容、层级探查与本地文件浏览器 Modal 渲染。
    """
    try:
        target = Path(path or settings.data_dir).expanduser().resolve()
        return _scan_directory(target)
    except Exception as e:
        handle_endpoint_exception(e, "GET filesystem list")


# ==================== 静态前端 UI 托管 (SPA 标准挂载) ====================

try:
    STATIC_DIR = Path(importlib.resources.files("cqdata") / "static")
except Exception:
    STATIC_DIR = Path(__file__).parent.parent / "static"

if STATIC_DIR.exists() and (STATIC_DIR / "index.html").exists():
    logger.info(f"[REST API] 已挂载静态前端 UI 托管: {STATIC_DIR}")
    app.mount("/", SPAStaticFiles(directory=STATIC_DIR, html=True), name="static")


