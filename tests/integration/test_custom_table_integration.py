"""
tests/integration/test_custom_table_integration.py

自定义数据表全链路集成测试：
覆盖 REST API 写入 (/api/v1/write)、REST API 切片查询 (/api/v1/query)、
元数据接口 (/api/v1/tables/detailed) 以及 CLI import 导入功能。
"""


import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner
import polars as pl
from pathlib import Path

from cq.data.entrypoints.rest_api import app
from cq.data.entrypoints.cli import app as cli_app
from cq.data.config import settings

client = TestClient(app)
runner = CliRunner()


def test_rest_api_custom_table_write_and_query(temp_data_dir):
    """测试通过 REST API 写入自定义时序数据并通过 /api/v1/query 查询"""
    # 1. 写入自定义数据表
    payload = {
        "table_id": "custom.factors.alpha_mom",
        "category": "timeseries",
        "formats": ["parquet", "csv"],
        "data": [
            {
                "symbol": "sh.600000",
                "timestamp": 1704067200000,
                "datetime": "2024-01-01T15:00:00.000+08:00",
                "momentum": 1.25,
                "volatility": 0.18
            },
            {
                "symbol": "sh.600000",
                "timestamp": 1704153600000,
                "datetime": "2024-01-02T15:00:00.000+08:00",
                "momentum": 1.32,
                "volatility": 0.19
            },
            {
                "symbol": "sz.000001",
                "timestamp": 1704067200000,
                "datetime": "2024-01-01T15:00:00.000+08:00",
                "momentum": 0.95,
                "volatility": 0.22
            }
        ]
    }
    
    resp_write = client.post("/api/v1/write", json=payload)
    assert resp_write.status_code == 200

    res_json = resp_write.json()
    assert res_json["status"] == "success"
    assert res_json["result"]["rows_written"] == 3
    
    # 2. 验证 /api/v1/tables 能够列出该自定义表
    resp_tables = client.get("/api/v1/tables")
    assert resp_tables.status_code == 200
    tables_list = resp_tables.json()["tables"]
    assert any(t["table_id"] == "custom.factors.alpha_mom" for t in tables_list)
    
    # 3. 验证 /api/v1/tables/detailed 返回包含正确的元数据与行数
    resp_detailed = client.get("/api/v1/tables/detailed")
    assert resp_detailed.status_code == 200
    detailed_tables = {t["table_id"]: t for t in resp_detailed.json()["tables"]}
    assert "custom.factors.alpha_mom" in detailed_tables
    meta = detailed_tables["custom.factors.alpha_mom"]
    assert meta["formats"]["parquet"]["exists"] is True
    assert meta["formats"]["parquet"]["total_bars"] == 3
    
    # 4. 验证 /api/v1/query 切片查询该自定义表 (带 symbols 过滤)
    resp_query = client.get("/api/v1/query", params={
        "table_id": "custom.factors.alpha_mom",
        "symbols": "sh.600000",
        "columns": "timestamp,momentum"
    })
    assert resp_query.status_code == 200
    q_data = resp_query.json()
    assert q_data["count"] == 2
    assert q_data["columns"] == ["timestamp", "momentum"]
    assert len(q_data["data"]) == 2


def test_cli_import_csv_and_parquet(temp_data_dir, tmp_path):
    """测试 CLI cqdata import 命令导入外部 CSV 与 Parquet 文件"""
    # 创建一个外部待导入的 CSV 文件
    csv_file = tmp_path / "external_data.csv"
    df_sample = pl.DataFrame({
        "symbol": ["sz.000002", "sz.000002"],
        "timestamp": [1704067200000, 1704153600000],
        "sentiment": [0.88, 0.92]
    })
    df_sample.write_csv(csv_file)
    
    # 执行 CLI 导入
    result = runner.invoke(cli_app, [
        "import",
        str(csv_file),
        "--table", "custom.sentiment.news",
        "--formats", "parquet,csv",
        "--data-dir", str(temp_data_dir)
    ])
    assert result.exit_code == 0
    assert "导入成功" in result.output
    
    # 通过 API 查询验证导入的数据
    resp_query = client.get("/api/v1/query", params={"table_id": "custom.sentiment.news"})
    assert resp_query.status_code == 200
    assert resp_query.json()["count"] == 2
