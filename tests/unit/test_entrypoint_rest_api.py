"""
tests/unit/test_entrypoint_rest_api.py

FastAPI REST 服务 endpoint 路由单元测试。
包含纯 HTTP GET 数据切片查询与 page / page_size 分页逻辑验证。
"""

import json
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import polars as pl

from cq.data.entrypoints.rest_api import app
from cq.data import __version__

client = TestClient(app)


def test_health_check():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["version"] == __version__


def test_list_all_tables():
    mock_tables = [
        {"table_id": "ashare.kline.1d.adj.baostock", "category": "timeseries"},
        {"table_id": "ashare.adj_factor.baostock", "category": "event"}
    ]
    with patch("cq.data.entrypoints.rest_api.list_tables", return_value=mock_tables):
        response = client.get("/api/v1/tables")
        assert response.status_code == 200
        data = response.json()
        assert data["tables"] == mock_tables
        assert data["total"] == 2


def test_list_formats():
    with patch("cq.data.entrypoints.rest_api.list_formats", return_value=["csv", "parquet"]):
        response = client.get("/api/v1/tables/ashare.kline.1d.adj.baostock/formats")
        assert response.status_code == 200
        assert response.json() == {
            "table_id": "ashare.kline.1d.adj.baostock",
            "formats": ["csv", "parquet"]
        }


def test_list_symbols():
    with patch("cq.data.entrypoints.rest_api.list_symbols", return_value=["sh.600000", "sz.000001"]):
        response = client.get("/api/v1/tables/ashare.kline.1d.adj.baostock/symbols")
        assert response.status_code == 200
        assert response.json() == {
            "table_id": "ashare.kline.1d.adj.baostock",
            "symbol_count": 2,
            "symbols": ["sh.600000", "sz.000001"]
        }


def test_get_time_range():
    with patch("cq.data.entrypoints.rest_api.get_time_range", return_value=("2024-01-01T15:00:00.000+08:00", "2024-05-20T15:00:00.000+08:00")):
        response = client.get("/api/v1/tables/ashare.kline.1d.adj.baostock/time_range")
        assert response.status_code == 200
        assert response.json()["start_datetime"] == "2024-01-01T15:00:00.000+08:00"


def test_get_schema():
    with patch("cq.data.entrypoints.rest_api.get_schema", return_value={"symbol": "String", "close": "Float64"}):
        response = client.get("/api/v1/tables/ashare.kline.1d.adj.baostock/schema")
        assert response.status_code == 200
        assert response.json()["schema"] == {"symbol": "String", "close": "Float64"}


def test_get_row_count():
    with patch("cq.data.entrypoints.rest_api.get_row_count", return_value=12345):
        response = client.get("/api/v1/tables/ashare.kline.1d.adj.baostock/row_count")
        assert response.status_code == 200
        assert response.json() == {"table_id": "ashare.kline.1d.adj.baostock", "row_count": 12345}


def test_get_query_basic_and_pagination():
    """测试统一 HTTP GET 切片查询与物理分页逻辑"""
    mock_df = pl.DataFrame({
        "timestamp": [100, 200, 300, 400, 500],
        "datetime": [f"2024-01-0{i}T15:00:00.000+08:00" for i in range(1, 6)],
        "symbol": ["sh.600000"] * 5,
        "close": [10.0 + i for i in range(5)]
    })

    with patch("cq.data.entrypoints.rest_api.read", return_value=mock_df) as mock_read:
        # 第一页，每页2条
        url = "/api/v1/query?table_id=ashare.kline.1d.adj.baostock&symbols=sh.600000,sz.000001&columns=timestamp,close&page=1&page_size=2"
        response = client.get(url)
        assert response.status_code == 200
        data = response.json()

        assert data["table_id"] == "ashare.kline.1d.adj.baostock"
        assert data["total"] == 5
        assert data["page"] == 1
        assert data["page_size"] == 2
        assert data["total_pages"] == 3
        assert data["count"] == 2
        assert data["columns"] == ["timestamp", "datetime", "symbol", "close"]
        assert len(data["data"]) == 2
        assert data["data"][0][0] == 100
        assert data["data"][1][0] == 200

        # 校验 mock 接收的参数
        mock_read.assert_called_with(
            table_id="ashare.kline.1d.adj.baostock",
            symbols=["sh.600000", "sz.000001"],
            start_date=None,
            end_date=None,
            columns=["timestamp", "close"],
            format="auto"
        )

        # 第二页，每页2条
        url_page2 = "/api/v1/query?table_id=ashare.kline.1d.adj.baostock&page=2&page_size=2"
        resp_p2 = client.get(url_page2)
        assert resp_p2.status_code == 200
        d2 = resp_p2.json()
        assert d2["page"] == 2
        assert d2["count"] == 2
        assert d2["data"][0][0] == 300
        assert d2["data"][1][0] == 400

        # 超出范围的页码
        url_p10 = "/api/v1/query?table_id=ashare.kline.1d.adj.baostock&page=10&page_size=2"
        resp_p10 = client.get(url_p10)
        assert resp_p10.status_code == 200
        d10 = resp_p10.json()
        assert d10["page"] == 10
        assert d10["count"] == 0
        assert d10["columns"] == ["timestamp", "datetime", "symbol", "close"]
        assert d10["data"] == []


def test_get_query_error_handling():
    """测试 GET /query 异常处理与 HTTP 状态码转化"""
    # 验证请求参数异常返回 400 Bad Request
    with patch("cq.data.entrypoints.rest_api.read", side_effect=ValueError("Test Invalid Parameter")):
        response_err = client.get("/api/v1/query?table_id=invalid_table")
        assert response_err.status_code == 400
        assert "Test Invalid Parameter" in response_err.json()["detail"]

    # 验证资源不存在异常返回 404 Not Found
    with patch("cq.data.entrypoints.rest_api.read", side_effect=FileNotFoundError("Table metadata missing")):
        response_err404 = client.get("/api/v1/query?table_id=missing_table")
        assert response_err404.status_code == 404
        assert "Table metadata missing" in response_err404.json()["detail"]

    # 验证系统内部异常返回 500 Internal Server Error
    with patch("cq.data.entrypoints.rest_api.read", side_effect=RuntimeError("Internal Server Exception")):
        response_err500 = client.get("/api/v1/query?table_id=error_table")
        assert response_err500.status_code == 500
        assert "Internal Server Exception" in response_err500.json()["detail"]


def test_cors_middleware_headers():
    """验证 CORS 跨域中间件响应头"""
    response = client.get("/api/v1/tables", headers={"Origin": "http://localhost:5173"})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "*"


def test_query_method_not_allowed_for_post():
    """验证 POST 方法请求切片查询路由被禁止 (返回 405 Method Not Allowed)"""
    response = client.post("/api/v1/query", json={"table_id": "ashare.kline.1d.adj.baostock"})
    assert response.status_code == 405


def test_post_sync_and_active_tasks():
    """验证 POST 数据同步与后台任务状态接口"""
    with patch("cq.data.entrypoints.rest_api.sync") as mock_sync:
        payload = {
            "table_ids": ["ashare.kline.1d.adj.baostock"],
            "formats": ["parquet"],
            "start_date": "2024-01-01"
        }
        response = client.post("/api/v1/sync", json=payload)
        assert response.status_code == 200
        assert response.json()["status"] == "accepted"

        # 验证 active_tasks
        resp_tasks = client.get("/api/v1/tasks")
        assert resp_tasks.status_code == 200


def test_spa_static_serving():
    """验证静态前端 SPA 页面托管与 API 404 回退"""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")

    response = client.get("/api/v1/non_existent_endpoint")
    assert response.status_code == 404


def test_filesystem_list(tmp_path):
    """验证 GET /api/v1/filesystem/list 本地文件系统探查 API 单元测试"""
    # 建立测试目录与文件
    test_dir = tmp_path / "test_vipdoc"
    test_dir.mkdir()
    sub_dir = test_dir / "sh"
    sub_dir.mkdir()
    sample_file = test_dir / "readme.txt"
    sample_file.write_text("hello tdx")

    # 1. 扫描文件夹路径
    resp = client.get("/api/v1/filesystem/list", params={"path": str(test_dir)})
    assert resp.status_code == 200
    data = resp.json()
    assert data["exists"] is True
    assert data["is_dir"] is True
    assert data["total"] == 2
    names = [item["name"] for item in data["items"]]
    assert "sh" in names
    assert "readme.txt" in names

    # 2. 扫描具体文件路径
    resp_file = client.get("/api/v1/filesystem/list", params={"path": str(sample_file)})
    assert resp_file.status_code == 200
    data_file = resp_file.json()
    assert data_file["exists"] is True
    assert data_file["is_dir"] is False
    assert data_file["items"][0]["name"] == "readme.txt"

    # 3. 扫描不存在路径
    resp_non = client.get("/api/v1/filesystem/list", params={"path": str(tmp_path / "non_existent")})
    assert resp_non.status_code == 200
    data_non = resp_non.json()
    assert data_non["exists"] is False
    assert data_non["total"] == 0


def test_list_tables_detailed_known_tables():
    """验证 GET /api/v1/tables/detailed 接口能正确返回全部 16 个内置预定义表元数据 (包含 TDX 指数与高频)"""
    response = client.get("/api/v1/tables/detailed")
    assert response.status_code == 200
    data = response.json()
    table_ids = [t["table_id"] for t in data["tables"]]
    assert len(table_ids) >= 16

    # 校验 TDX 的全部 6 个表
    expected_tdx = [
        "ashare.kline.1d.raw.tdx",
        "ashare.kline.5m.raw.tdx",
        "ashare.kline.1m.raw.tdx",
        "aindex.kline.1d.raw.tdx",
        "aindex.kline.5m.raw.tdx",
        "aindex.kline.1m.raw.tdx",
    ]
    for tid in expected_tdx:
        assert tid in table_ids, f"Expected TDX table '{tid}' to be present in /tables/detailed"

    # 校验 Baostock 指数与复权因子
    assert "aindex.kline.1d.raw.baostock" in table_ids
    assert "ashare.adj_factor.baostock" in table_ids
    assert "ashare.inst_trade.eastmoney" in table_ids


def test_log_broadcaster_and_stream():
    """验证 LogBroadcaster 日志广播单例与 GET /api/v1/logs/stream SSE 端点"""
    from cq.data.utils.logger_utils import log_broadcaster
    from fastapi.responses import StreamingResponse

    dummy_log = {
        "timestamp": "2026-08-11 22:50:00.000",
        "level": "INFO",
        "name": "test_module",
        "line": 42,
        "message": "Unit test broadcast message",
    }
    log_broadcaster.history.append(dummy_log)

    # 验证 get_history 能查到
    history = log_broadcaster.get_history()
    assert dummy_log in history

    # 测试 /api/v1/logs/stream SSE 端点 (使用有限生成器打桩，防止 TestClient 内存 ASGI 管道无法触发断连事件而死锁)
    async def dummy_gen():
        yield f"data: {json.dumps(dummy_log, ensure_ascii=False)}\n\n"

    with patch("cq.data.entrypoints.rest_api.StreamingResponse", return_value=StreamingResponse(dummy_gen(), media_type="text/event-stream")):
        response = client.get("/api/v1/logs/stream")
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")
        assert "Unit test broadcast message" in response.text


    resp_query = client.get("/api/v1/query", params={"table_id": "ashare.kline.1d.raw.baostock", "symbols": "sh.600000", "page_size": 10})
    assert resp_query.status_code == 200

    resp_boards = client.get("/api/v1/tables/ashare.concept.eastmoney/boards")
    assert resp_boards.status_code == 200

    resp_fs = client.get("/api/v1/filesystem/list")
    assert resp_fs.status_code == 200


def test_list_sources():
    """测试 GET /api/v1/sources 端点"""
    with patch("cq.data.entrypoints.rest_api.list_sources", return_value=["baostock", "eastmoney", "tdx", "stockdb"]):
        response = client.get("/api/v1/sources")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 4
        assert [item["source"] for item in data["sources"]] == ["baostock", "eastmoney", "tdx", "stockdb"]


