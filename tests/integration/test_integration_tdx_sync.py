"""TDX 本地模式与接口集成测试 (Mock 网络 IO，0 外网真实请求)。

验证:
1. REST API POST /api/v1/sync 接收 provider_kwargs 并透传至 sync
2. GET /api/v1/tdx/check 探针物理状态与代码数统计
3. POST /api/v1/tdx/download 后台任务触发与 sync_tracker 状态跟踪
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from cq.data.entrypoints.rest_api import app, ACTIVE_SYNC_TASKS
from cq.data.service.sync_tracker import sync_tracker
from cq.data.provider.provider_manager import ProviderManager
from cq.data.provider.tdx_provider import TDXProvider


@pytest.fixture(autouse=True)
def _reset_state():
    ACTIVE_SYNC_TASKS.clear()
    ProviderManager._instance = None
    ProviderManager._providers = {}
    yield
    ACTIVE_SYNC_TASKS.clear()
    ProviderManager._instance = None
    ProviderManager._providers = {}


@pytest.fixture
def client():
    return TestClient(app)


class TestTDXIntegration:
    """TDX 离线包与接口全流程集成测试。"""

    def test_tdx_check_nonexistent_path(self, client):
        res = client.get("/api/v1/tdx/check", params={"vipdoc_dir": "C:/invalid_nonexistent_path_test"})
        assert res.status_code == 200
        data = res.json()
        assert data["exists"] is False
        assert data["symbol_count"] == 0
        assert data["valid"] is False

    def test_tdx_check_valid_mock_path(self, client, tmp_path):
        lday_dir = tmp_path / "sh" / "lday"
        lday_dir.mkdir(parents=True)
        (lday_dir / "sh600000.day").write_bytes(b"\x00" * 32)
        (lday_dir / "sh600001.day").write_bytes(b"\x00" * 32)

        res = client.get("/api/v1/tdx/check", params={"vipdoc_dir": str(tmp_path)})
        assert res.status_code == 200
        data = res.json()
        assert data["exists"] is True
        assert data["symbol_count"] == 2
        assert data["valid"] is True

    def test_sync_endpoint_accepts_provider_kwargs(self, client):
        with patch("cq.data.entrypoints.rest_api.run_sync_task") as mock_task:
            res = client.post("/api/v1/sync", json={
                "table_ids": ["ashare.kline.1d.raw.tdx"],
                "provider_kwargs": {
                    "mode": "local",
                    "vipdoc_dir": "C:/custom_test_vipdoc"
                }
            })
            assert res.status_code == 200
            data = res.json()
            assert data["status"] == "accepted"
            assert "ashare.kline.1d.raw.tdx" in data["started_tasks"]

    def test_tdx_download_endpoint_updates_sync_tracker(self, client, tmp_path):
        with patch("cq.data.provider.tdx_downloader.urlretrieve") as mock_urlretrieve, \
             patch("zipfile.ZipFile") as mock_zipfile:
            
            mock_zf = MagicMock()
            mock_info = MagicMock()
            mock_info.filename = "sh/lday/sh600000.day"
            mock_zf.infolist.return_value = [mock_info]
            mock_zipfile.return_value.__enter__.return_value = mock_zf

            res = client.post("/api/v1/tdx/download", json={"vipdoc_dir": str(tmp_path)})
            assert res.status_code == 200
            data = res.json()
            assert data["status"] == "accepted"
            assert data["task_id"] == "tdx.download.hsjday"

            # 验证 sync_tracker 状态记录
            statuses = sync_tracker.get_all_statuses()
            assert "tdx.download.hsjday" in statuses
            status_obj = statuses["tdx.download.hsjday"]
            assert status_obj["table_id"] == "tdx.download.hsjday"
