"""
tests/integration/test_cqdata_cli.py

cqdata Typer CLI 终端命令行全量子命令与选项集成测试
"""

from pathlib import Path
import pytest
from typer.testing import CliRunner
from unittest.mock import patch
from cq.data.entrypoints.cli import app
from cq.data.storage.storage_factory import StorageFactory
from cq.data.service.metadata_manager import MetadataManager
import polars as pl

runner = CliRunner(env={"COLUMNS": "200", "TERM": "dumb"})


@pytest.fixture
def mock_cli_storage(temp_data_dir):
    """初始化模拟存储用于 CLI 命令解析测试"""
    table_id = "ashare.kline.1d.raw.baostock"
    df = pl.DataFrame({
        "symbol": ["sh.600000"],
        "timestamp": [1700000000000],
        "datetime": ["2023-11-14T15:00:00.000+08:00"],
        "close": [10.0]
    })
    pq = StorageFactory.get_storage("parquet", str(temp_data_dir), "timeseries")
    pq.write_series(table_id, df)

    meta_mgr = MetadataManager(str(temp_data_dir))
    meta_mgr.save(table_id, "parquet", {
        "category": "timeseries",
        "schema": {
            "symbol": "String",
            "timestamp": "Int64",
            "datetime": "String",
            "close": "Float64"
        },
        "statistics": {
            "start_timestamp": 1700000000000,
            "end_timestamp": 1700000000000,
            "start_datetime": "2023-11-14T15:00:00.000+08:00",
            "end_datetime": "2023-11-14T15:00:00.000+08:00",
            "total_bars": 1
        }
    })
    return table_id


def test_cli_help():
    """测试 cqdata --help 命令"""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "cqdata" in result.stdout


def test_cli_tables_command(mock_cli_storage, temp_data_dir):
    """测试 cqdata tables 命令输出"""
    result = runner.invoke(app, ["tables", "-f", "parquet"])
    assert result.exit_code == 0
    assert "本地数据表概览" in result.stdout


def test_cli_sources_command():
    """测试 cqdata sources 命令输出"""
    result = runner.invoke(app, ["sources"])
    assert result.exit_code == 0
    assert "系统可用数据源" in result.stdout
    assert "baostock" in result.stdout
    assert "eastmoney" in result.stdout
    assert "tdx" in result.stdout
    assert "stockdb" in result.stdout



def test_cli_info_command(mock_cli_storage, temp_data_dir):
    """测试 cqdata info 命令输出"""
    table_id = mock_cli_storage
    result = runner.invoke(app, ["info", table_id, "-f", "parquet"])
    assert result.exit_code == 0
    assert "表元数据" in result.stdout
    assert "close" in result.stdout


def test_cli_sync_command(mock_cli_storage, temp_data_dir):
    """测试 cqdata sync 命令调用参数挂载"""
    with patch("cq.data.entrypoints.cli.api_sync") as mock_api_sync:
        result = runner.invoke(app, [
            "sync",
            "-t", "ashare.kline.1d.raw.baostock",
            "-f", "parquet",
            "-s", "2024-01-01",
            "-e", "2024-01-31",
            "--limit", "10"
        ])
        assert result.exit_code == 0
        assert mock_api_sync.called
        kwargs = mock_api_sync.call_args.kwargs
        assert kwargs["table_ids"] == ["ashare.kline.1d.raw.baostock"]
        assert kwargs["formats"] == ["parquet"]
        assert kwargs["start_date"] == "2024-01-01"
        assert kwargs["end_date"] == "2024-01-31"
        assert kwargs["symbol_limit"] == 10


def test_cli_server_help():
    """测试 cqdata server --help"""
    result = runner.invoke(app, ["server", "--help"])
    assert result.exit_code == 0
    assert "port" in result.stdout.lower()


def test_cli_tdx_help():
    """测试 cqdata tdx download --help"""
    result = runner.invoke(app, ["tdx", "download", "--help"])
    assert result.exit_code == 0
    assert "vipdoc" in result.stdout.lower()


def test_cli_tdx_download_command():
    """测试 cqdata tdx download 命令执行与路径透传"""
    with patch("cq.data.entrypoints.cli.tdx_download_and_extract") as mock_download:
        result = runner.invoke(app, ["tdx", "download", "--vipdoc", "C:/mock/vipdoc"])
        assert result.exit_code == 0
        assert mock_download.called
        assert str(mock_download.call_args[0][0]) == str(Path("C:/mock/vipdoc"))


def test_cli_wizard_help():
    """测试 cqdata wizard --help"""
    result = runner.invoke(app, ["wizard", "--help"])
    assert result.exit_code == 0


def test_cli_wizard_command():
    """测试 cqdata wizard 命令执行调用"""
    with patch("cq.data.entrypoints.cli.run_wizard") as mock_wizard:
        result = runner.invoke(app, ["wizard"])
        assert result.exit_code == 0
        assert mock_wizard.called


def test_cli_import_command(temp_data_dir):
    """测试 cqdata import 导入外部数据文件命令"""
    sample_csv = temp_data_dir / "sample_external.csv"
    sample_csv.write_text("symbol,date,close\nsh.600000,2024-01-02,10.5\n", encoding="utf-8")

    result = runner.invoke(app, [
        "import",
        str(sample_csv),
        "-t", "test.external.import",
        "-c", "event",
        "-f", "parquet",
        "--data-dir", str(temp_data_dir)
    ])
    assert result.exit_code == 0
    assert "导入成功" in result.stdout


def test_cli_sync_tdx_local_and_output(temp_data_dir):
    """测试 cqdata sync 对 TDX local 模式及自定义 output 目录的参数处理"""
    with patch("cq.data.entrypoints.cli.api_sync") as mock_api_sync:
        result = runner.invoke(app, [
            "sync",
            "-t", "ashare.kline.1d.raw.tdx",
            "--local",
            "--tdx-vipdoc", "D:/test/vipdoc",
            "-o", str(temp_data_dir)
        ])
        assert result.exit_code == 0
        assert mock_api_sync.called
        kwargs = mock_api_sync.call_args.kwargs
        assert kwargs["provider_kwargs"] == {"mode": "local", "vipdoc_dir": "D:/test/vipdoc"}


def test_cli_server_command():
    """测试 cqdata server 命令参数解析与 uvicorn.run / 浏览器唤醒"""
    with patch("uvicorn.run") as mock_uvicorn, \
         patch("webbrowser.open") as mock_open:
        result = runner.invoke(app, [
            "server",
            "-h", "127.0.0.1",
            "-p", "9999",
            "--open"
        ])
        assert result.exit_code == 0
        assert mock_uvicorn.called
        uvicorn_kwargs = mock_uvicorn.call_args.kwargs
        assert uvicorn_kwargs["host"] == "127.0.0.1"
        assert uvicorn_kwargs["port"] == 9999


def test_cli_tables_empty(temp_data_dir):
    """测试空存储目录下的 tables 输出提示"""
    with patch("cq.data.entrypoints.cli.list_tables", return_value=[]):
        result = runner.invoke(app, ["tables", "-f", "parquet"])
        assert result.exit_code == 0
        assert "暂无时序表" in result.stdout
        assert "暂无事件表" in result.stdout


def test_cli_import_parquet_and_unsupported(temp_data_dir):
    """测试 cqdata import 导入 parquet 格式及未知格式拦截"""
    df = pl.DataFrame({"symbol": ["sh.600000"], "timestamp": [1700000000000], "close": [10.0]})
    parquet_path = temp_data_dir / "sample.parquet"
    df.write_parquet(parquet_path)

    # 导入 parquet
    result = runner.invoke(app, [
        "import",
        str(parquet_path),
        "-t", "test.import.parquet",
        "-c", "timeseries",
        "-f", "parquet",
        "--data-dir", str(temp_data_dir)
    ])
    assert result.exit_code == 0
    assert "导入成功" in result.stdout

    # 未知扩展名拦截
    txt_path = temp_data_dir / "sample.txt"
    txt_path.write_text("dummy", encoding="utf-8")
    result_bad = runner.invoke(app, [
        "import",
        str(txt_path),
        "-t", "test.bad"
    ])
    assert result_bad.exit_code != 0


def test_cli_import_nonexistent_file():
    """测试 cqdata import 不存在文件时的防御退出"""
    result = runner.invoke(app, [
        "import",
        "nonexistent_file.csv",
        "-t", "test.table"
    ])
    assert result.exit_code != 0
    output_text = result.stdout + (result.stderr if hasattr(result, "stderr") and result.stderr else "")
    assert "不存在" in output_text or result.exit_code == 1


