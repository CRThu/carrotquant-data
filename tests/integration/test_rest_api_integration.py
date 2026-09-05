"""
tests/integration/test_rest_api_integration.py

FastAPI REST API 全流程端到端集成测试。
测试从元数据探查、物理数据 GET 切片查询到同步触发的完整闭环。
"""

import pytest
from fastapi.testclient import TestClient
from pathlib import Path
from unittest.mock import patch
import polars as pl

from cq.data.entrypoints.rest_api import app
from cq.data.storage.storage_factory import StorageFactory
from cq.data.service.metadata_manager import MetadataManager

client = TestClient(app)


def test_rest_api_full_flow_with_physical_storage(temp_data_dir, monkeypatch):
    """
    测试 REST API 全流程集成 (包含物理文件读写与元数据探查)
    """
    monkeypatch.setattr("cq.data.config.settings.data_dir", str(temp_data_dir))
    table_id = "ashare.kline.1d.raw.baostock"
    fmt = "parquet"

    df = pl.DataFrame({
        "symbol": ["sh.600000", "sz.000001", "sh.600000"],
        "timestamp": [1704067200000, 1704153600000, 1704240000000],
        "datetime": ["2024-01-01T00:00:00.000+08:00", "2024-01-02T00:00:00.000+08:00", "2024-01-03T00:00:00.000+08:00"],
        "open": [10.0, 15.0, 10.5],
        "high": [10.5, 15.5, 10.8],
        "low": [9.8, 14.8, 10.2],
        "close": [10.2, 15.2, 10.6],
        "volume": [1000.0, 2000.0, 1500.0]
    })

    storage = StorageFactory.get_storage(storage_format=fmt, data_dir=str(temp_data_dir), category="timeseries")
    storage.write_series(table_id, df)

    meta_mgr = MetadataManager(str(temp_data_dir))
    meta_mgr.save(
        table_id=table_id,
        format=fmt,
        metadata={
            "table_id": table_id,
            "category": "timeseries",
            "schema": {"timestamp": "Int64", "datetime": "String", "symbol": "String", "open": "Float64", "high": "Float64", "low": "Float64", "close": "Float64", "volume": "Float64"},
            "statistics": {
                "start_datetime": "2024-01-01T15:00:00.000+08:00",
                "end_datetime": "2024-01-03T15:00:00.000+08:00",
                "total_bars": 3
            }
        }
    )

    # 2. 验证元数据 REST 接口
    resp_tables = client.get("/api/v1/tables")
    assert resp_tables.status_code == 200
    tables_list = resp_tables.json()["tables"]
    table_ids = [t["table_id"] for t in tables_list]
    assert table_id in table_ids

    resp_syms = client.get(f"/api/v1/tables/{table_id}/symbols")
    assert resp_syms.status_code == 200
    assert set(resp_syms.json()["symbols"]) == {"sh.600000", "sz.000001"}

    resp_schema = client.get(f"/api/v1/tables/{table_id}/schema")
    assert resp_schema.status_code == 200
    assert "close" in resp_schema.json()["schema"]

    # 3. 验证 GET 切片查询与物理分页 (page=1, page_size=2)
    query_url_p1 = f"/api/v1/query?table_id={table_id}&page=1&page_size=2"
    resp_q1 = client.get(query_url_p1)
    assert resp_q1.status_code == 200
    data_p1 = resp_q1.json()
    assert data_p1["total"] == 3
    assert data_p1["page"] == 1
    assert data_p1["page_size"] == 2
    assert data_p1["total_pages"] == 2
    assert data_p1["count"] == 2
    assert set(data_p1["columns"]) == {"timestamp", "datetime", "symbol", "open", "high", "low", "close", "volume"}
    assert len(data_p1["data"]) == 2

    # 验证 GET 切片查询 (page=2, page_size=2)
    query_url_p2 = f"/api/v1/query?table_id={table_id}&page=2&page_size=2"
    resp_q2 = client.get(query_url_p2)
    assert resp_q2.status_code == 200
    data_p2 = resp_q2.json()
    assert data_p2["page"] == 2
    assert data_p2["count"] == 1
    sym_idx = data_p2["columns"].index("symbol")
    assert data_p2["data"][0][sym_idx] in {"sh.600000", "sz.000001"}

    # 4. 验证带符号和列过滤的 GET 切片查询
    filtered_url = f"/api/v1/query?table_id={table_id}&symbols=sh.600000&columns=timestamp,symbol,close&page=1&page_size=10"
    resp_f = client.get(filtered_url)
    assert resp_f.status_code == 200
    data_f = resp_f.json()
    assert data_f["total"] == 2
    assert data_f["count"] == 2
    assert data_f["columns"] == ["timestamp", "symbol", "close"]
    for row in data_f["data"]:
        assert row[1] == "sh.600000"

    # 5. 验证通用动态业务语义端点 GET /api/v1/data/ashare/kline
    dynamic_url = "/api/v1/data/ashare/kline?symbols=sh.600000&freq=1d&adj=raw&columns=timestamp,symbol,close"
    resp_dyn = client.get(dynamic_url)
    assert resp_dyn.status_code == 200
    dyn_data = resp_dyn.json()
    assert dyn_data["market"] == "ashare"
    assert dyn_data["category"] == "kline"
    assert dyn_data["resolved_table_id"] == "ashare.kline.1d.raw.baostock"
    assert dyn_data["total"] == 2
    assert dyn_data["count"] == 2
    assert dyn_data["columns"] == ["timestamp", "symbol", "close"]


def test_rest_api_health_log_config():
    """验证 /api/v1/health 返回包含 log_dir 与 log_level"""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "log_dir" in data
    assert "log_level" in data
    assert data["log_level"] in ("INFO", "DEBUG", "WARNING", "ERROR")


def test_rest_api_sync_stream_snapshot():
    """验证 /api/v1/sync/stream SSE 连接端点参数、防缓冲 headers 与推流契约"""
    with patch("cq.data.entrypoints.rest_api.StreamingResponse") as mock_stream:
        mock_stream.return_value = {"status": "ok"}
        resp = client.get("/api/v1/sync/stream")
        assert resp.status_code == 200
        assert mock_stream.called
        _, kwargs = mock_stream.call_args
        assert kwargs.get("media_type") == "text/event-stream"
        assert kwargs.get("headers", {}).get("Content-Encoding") == "identity"
        assert kwargs.get("headers", {}).get("Cache-Control") == "no-cache"
        assert kwargs.get("headers", {}).get("X-Accel-Buffering") == "no"


def test_rest_api_logs_stream_headers():
    """验证 /api/v1/logs/stream 带有防 GZip 缓冲 headers"""
    with patch("cq.data.entrypoints.rest_api.StreamingResponse") as mock_stream:
        mock_stream.return_value = {"status": "ok"}
        resp = client.get("/api/v1/logs/stream")
        assert resp.status_code == 200
        assert mock_stream.called
        _, kwargs = mock_stream.call_args
        assert kwargs.get("media_type") == "text/event-stream"
        assert kwargs.get("headers", {}).get("Content-Encoding") == "identity"
        assert kwargs.get("headers", {}).get("Cache-Control") == "no-cache"
        assert kwargs.get("headers", {}).get("X-Accel-Buffering") == "no"

