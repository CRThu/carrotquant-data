import pytest
import polars as pl
from fastapi.testclient import TestClient
from cq.data.entrypoints.rest_api import app
from cq.data.entrypoints.python_api import list_boards
from cq.data.service.metadata_manager import MetadataManager
from cq.data.config.settings import settings
from cq.data.storage.parquet_storage import ParquetStorage

client = TestClient(app)


def test_list_boards_and_api_endpoint(tmp_path, monkeypatch):
    """测试 python_api.list_boards 以及 REST API GET /tables/{table_id}/boards 极速列表端点"""
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    
    table_id = "ashare.concept.eastmoney"
    storage = ParquetStorage(str(tmp_path / "parquet"))
    
    df = pl.DataFrame({
        "board_code": ["BK0001", "BK0001", "BK0002"],
        "board_name": ["低空经济", "低空经济", "人工智能"],
        "symbol": ["sh.600000", "sz.000001", "sh.600000"],
        "stock_name": ["浦发银行", "平安银行", "浦发银行"]
    })
    
    storage.write_event(table_id, df, mode="overwrite")
    storage.finalize(table_id, mode="overwrite")
    
    meta_mgr = MetadataManager(str(tmp_path))
    dummy_meta = {
        "table_id": table_id,
        "category": "event",
        "format": "parquet",
        "partition": "none",
        "layout": "flat",
        "schema": {"board_code": "String", "board_name": "String", "symbol": "String", "stock_name": "String"},
        "statistics": {"total_bars": 3}
    }
    meta_mgr.save(table_id, "parquet", dummy_meta)
    
    # 1. 测试 Python SDK list_boards
    boards = list_boards(table_id, format="parquet")
    assert len(boards) == 2
    assert boards[0]["board_code"] == "BK0001"
    assert boards[0]["stock_count"] == 2
    assert boards[1]["board_code"] == "BK0002"
    assert boards[1]["stock_count"] == 1
    
    # 2. 测试 REST API GET /api/v1/tables/{table_id}/boards
    resp = client.get(f"/api/v1/tables/{table_id}/boards?format=parquet")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["boards"]) == 2
    assert data["boards"][0]["board_name"] == "低空经济"
    
    # 3. 测试带有 query 搜索参数的 REST API 过滤
    search_resp = client.get(f"/api/v1/tables/{table_id}/boards?query=低空&format=parquet")
    assert search_resp.status_code == 200
    search_data = search_resp.json()
    assert search_data["total"] == 1
    assert search_data["boards"][0]["board_code"] == "BK0001"

    # 4. 测试 /api/v1/query 带 board_code 过滤成分股
    query_resp = client.get(f"/api/v1/query?table_id={table_id}&board_code=BK0001&format=parquet")
    assert query_resp.status_code == 200
    q_data = query_resp.json()
    assert q_data["total"] == 2
    assert q_data["count"] == 2


def test_list_boards_industry(tmp_path, monkeypatch):
    """测试行业板块 (ashare.industry.eastmoney) 同样无缝通用支持"""
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    
    table_id = "ashare.industry.eastmoney"
    storage = ParquetStorage(str(tmp_path / "parquet"))
    
    df = pl.DataFrame({
        "board_code": ["BK0437", "BK0437"],
        "board_name": ["银行", "银行"],
        "symbol": ["sh.600000", "sz.000001"],
        "stock_name": ["浦发银行", "平安银行"]
    })
    
    storage.write_event(table_id, df, mode="overwrite")
    storage.finalize(table_id, mode="overwrite")
    
    meta_mgr = MetadataManager(str(tmp_path))
    dummy_meta = {
        "table_id": table_id,
        "category": "event",
        "format": "parquet",
        "partition": "none",
        "layout": "flat",
        "schema": {"board_code": "String", "board_name": "String", "symbol": "String", "stock_name": "String"},
        "statistics": {"total_bars": 2}
    }
    meta_mgr.save(table_id, "parquet", dummy_meta)
    
    resp = client.get(f"/api/v1/tables/{table_id}/boards?format=parquet")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["boards"][0]["board_code"] == "BK0437"
    assert data["boards"][0]["board_name"] == "银行"
    assert data["boards"][0]["stock_count"] == 2

