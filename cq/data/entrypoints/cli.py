"""
cqdata/entrypoints/cli.py

cqdata 终端命令行控制台主入口 (Typer CLI)。
集成数据同步 (sync)、服务启动 (serve)、交互向导 (wizard)、表探索 (tables) 与信息探查 (info)。
"""

import sys
import threading
import webbrowser
import typer
import uvicorn
from typing import List, Optional
from pathlib import Path

import polars as pl
from cq.data.config import settings
from cq.data.entrypoints.python_api import (
    sync as api_sync,
    write,
    list_tables,
    list_symbols,
    get_time_range,
    get_schema,
    get_row_count,
    list_sources
)

from cq.data.provider.tdx_downloader import download_and_extract as tdx_download_and_extract
from cq.data.service.wizard import start_wizard as run_wizard
from cq.data.utils.logger_utils import setup_logger


app = typer.Typer(
    help="CarrotQuant.Data (cqdata) - 本地金融数据同步与管理工具 CLI",
    add_completion=False
)

tdx_app = typer.Typer(help="通达信数据源专属操作命令")
app.add_typer(tdx_app, name="tdx")


@app.command(name="sync")
def sync_cmd(
    tables: str = typer.Option(..., "--tables", "-t", help="需要同步的表 ID，多表用逗号分隔 (如 ashare.kline.1d.raw.baostock)"),
    formats: str = typer.Option("parquet,csv", "--formats", "-f", help="落地方式，逗号分隔 (如 parquet,csv)"),
    start: Optional[str] = typer.Option(None, "--start", "-s", help="起始日期 (YYYY-MM-DD)"),
    end: Optional[str] = typer.Option(None, "--end", "-e", help="结束日期 (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", help="是否强制全量覆盖刷新水位线"),
    batch: int = typer.Option(100, "--batch", help="批处理聚合长度"),
    limit: Optional[int] = typer.Option(None, "--limit", help="限制同步的证券数量 (常用于测试)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="自定义存储根目录"),
    log_dir: Optional[str] = typer.Option(None, "--log-dir", help="日志持久化落盘目录 (默认从 settings 或 logs 读取)"),
    log_level: Optional[str] = typer.Option(None, "--log-level", help="日志输出级别 (INFO/DEBUG/WARNING/ERROR)"),
    local: bool = typer.Option(False, "--local", help="TDX 驱动专用：是否使用本地 vipdoc 模式"),
    tdx_vipdoc: str = typer.Option(r"C:\new_tdx\vipdoc", "--tdx-vipdoc", help="TDX vipdoc 目录路径")
):
    """
    触发全自动数据同步流程
    """
    table_list = [t.strip() for t in tables.split(",") if t.strip()]
    format_list = [f.strip() for f in formats.split(",") if f.strip()]
    
    if log_dir:
        settings.log_dir = log_dir
    if log_level:
        settings.log_level = log_level.upper()
    setup_logger(log_level=settings.log_level, log_dir=settings.log_dir, log_file_prefix="cli_sync")

    provider_kwargs = {}
    if any(".tdx" in t for t in table_list):
        provider_kwargs["mode"] = "local" if local else "online"
        provider_kwargs["vipdoc_dir"] = tdx_vipdoc

    if output:
        settings.data_dir = output

    api_sync(
        table_ids=table_list,
        formats=format_list,
        start_date=start,
        end_date=end,
        force_refresh=force,
        batch_size=batch,
        symbol_limit=limit,
        provider_kwargs=provider_kwargs
    )


@app.command(name="server")
def server_cmd(
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="监听地址"),
    port: int = typer.Option(8888, "--port", "-p", help="监听端口"),
    reload: bool = typer.Option(False, "--reload", help="是否开启热重载"),
    open_browser: bool = typer.Option(False, "--open", "-o", help="服务启动后自动调起系统默认浏览器访问 Web 终端"),
    config: Optional[str] = typer.Option(None, "--config", "-c", help="加载指定 YAML 配置文件路径"),
    data_dir: Optional[str] = typer.Option(None, "--data-dir", help="指定数据存储根目录"),
    log_dir: Optional[str] = typer.Option(None, "--log-dir", help="指定日志存储目录"),
    log_level: Optional[str] = typer.Option(None, "--log-level", help="指定日志记录级别")
):
    """
    启动 FastAPI REST API HTTP 服务与 React Web 终端 (例如 cqdata server -p 8888 --open)
    """

    if config:
        settings.configure(config)
    if data_dir:
        settings.data_dir = data_dir
    if log_dir:
        settings.log_dir = log_dir
    if log_level:
        settings.log_level = log_level.upper()
    setup_logger(log_level=settings.log_level, log_dir=settings.log_dir, log_file_prefix="server")

    if open_browser:
        display_host = "localhost" if host in ("0.0.0.0", "127.0.0.1") else host
        url = f"http://{display_host}:{port}"
        typer.echo(f"[+] 正在准备自动唤醒默认浏览器打开 Web 终端: {url}")
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()

    typer.echo(f"[+] Starting cqdata REST API server on http://{host}:{port} (data_dir: {settings.data_dir})")
    uvicorn.run("cq.data.entrypoints.rest_api:app", host=host, port=port, reload=reload)



@app.command(name="wizard")
def wizard_cmd():
    """
    启动终端交互式同步向导
    """
    run_wizard()


@app.command(name="tables")
def tables_cmd(
    format: str = typer.Option("auto", "--format", "-f", help="指定物理存储格式 (auto, parquet, csv)")
):
    """
    查看本地已存储的所有数据表列表
    """
    all_tables = list_tables(format=format)
    series_tables = [t["table_id"] for t in all_tables if t["category"] == "timeseries"]
    event_tables = [t["table_id"] for t in all_tables if t["category"] == "event"]

    typer.echo("==================== 本地数据表概览 ====================")
    typer.echo("【时间序列 (TimeSeries) 表】:")
    if not series_tables:
        typer.echo("  (暂无时序表)")
    else:
        for t in series_tables:
            typer.echo(f"  - {t}")

    typer.echo("\n【事件/静态 (Event) 表】:")
    if not event_tables:
        typer.echo("  (暂无事件表)")
    else:
        for t in event_tables:
            typer.echo(f"  - {t}")
    typer.echo("==========================================================")


@app.command(name="sources")
def sources_cmd():
    """
    列出系统当前所有已注册/可用数据源驱动及其支持的数据表
    """
    from cq.data.provider.provider_manager import ProviderManager

    pm = ProviderManager()
    sources = list_sources()

    typer.echo("==================== 系统可用数据源 ====================")
    for src in sources:
        try:
            prov = pm._providers.get(src) or pm.get_provider(f"probe.{src}")
            supported_tables = prov.get_supported_tables()
        except Exception:
            supported_tables = []
        typer.echo(f"【数据源: {src}】(支持 {len(supported_tables)} 张表):")
        for t in supported_tables:
            typer.echo(f"  - {t}")
        typer.echo("")
    typer.echo("==========================================================")



@app.command(name="info")
def info_cmd(
    table_id: str = typer.Argument(..., help="数据表 ID (如 ashare.kline.1d.raw.baostock)"),
    format: str = typer.Option("auto", "--format", "-f", help="指定物理存储格式")
):
    """
    查看某数据表的详细元数据与物理统计信息
    """
    try:
        symbols = list_symbols(table_id, format=format)
        start_dt, end_dt = get_time_range(table_id, format=format)
        schema = get_schema(table_id, format=format)
        rows = get_row_count(table_id, format=format)

        typer.echo(f"==================== 表元数据: {table_id} ====================")
        typer.echo(f"记录总行数 (Total Rows): {rows:,}")
        typer.echo(f"代码总数量 (Symbol Count): {len(symbols):,}")
        typer.echo(f"时间跨度 (Time Range): {start_dt or 'N/A'} ~ {end_dt or 'N/A'}")
        typer.echo("\n【字段列定义 (Schema)】:")
        for col_name, dtype in schema.items():
            typer.echo(f"  - {col_name:<20} : {dtype}")

        if symbols:
            preview_syms = symbols[:5]
            typer.echo(f"\n【代码示例 (前5个)】: {', '.join(preview_syms)}{' ...' if len(symbols) > 5 else ''}")
        typer.echo("================================================================")
    except Exception as e:
        typer.echo(f"[!] Error fetching info for '{table_id}': {e}", err=True)


@tdx_app.command(name="download")
def tdx_download_cmd(
    vipdoc: str = typer.Option(r"C:\new_tdx\vipdoc", "--vipdoc", "-v", help="vipdoc 目录路径")
):
    """
    下载通达信日线 ZIP 包并解压 lday 数据到本地 vipdoc 目录
    """
    vipdoc_path = Path(vipdoc)
    tdx_download_and_extract(vipdoc_path)


@app.command(name="import")
def import_cmd(
    file: str = typer.Argument(..., help="要导入的外部数据文件路径 (.csv 或 .parquet)"),
    table_id: str = typer.Option(..., "--table", "-t", help="目标数据表 ID (如 my_custom_table)"),
    category: str = typer.Option("timeseries", "--category", "-c", help="数据表类别 ('timeseries' 或 'event')，默认为 'timeseries'"),
    formats: str = typer.Option("parquet", "--formats", "-f", help="目标存储格式，逗号分隔 (如 parquet,csv)"),
    mode: str = typer.Option("append", "--mode", "-m", help="写入模式 (append 增量合并，overwrite 覆盖)"),
    data_dir: Optional[str] = typer.Option(None, "--data-dir", help="指定数据存储根目录")
):
    """
    将外部 CSV 或 Parquet 文件导入并持久化到本地数据表中
    """
    if data_dir:
        settings.data_dir = data_dir

    file_path = Path(file)
    if not file_path.exists():
        typer.echo(f"[!] 错误: 文件 '{file}' 不存在。", err=True)
        raise typer.Exit(code=1)


    typer.echo(f"[*] 正在读取外部文件: {file_path}")
    if file_path.suffix.lower() == ".csv":
        df = pl.read_csv(file_path)
    elif file_path.suffix.lower() in (".parquet", ".pq"):
        df = pl.read_parquet(file_path)
    else:
        typer.echo(f"[!] 错误: 不支持的文件格式 '{file_path.suffix}'，仅支持 .csv 和 .parquet", err=True)
        raise typer.Exit(code=1)

    format_list = [fmt.strip() for fmt in formats.split(",") if fmt.strip()]
    result = write(
        table_id=table_id,
        df=df,
        category=category,
        formats=format_list,
        mode=mode
    )
    typer.echo(f"[+] 导入成功! 已写入 {result.get('rows_written', 0):,} 行记录至表 '{table_id}' ({format_list})")


if __name__ == "__main__":
    app()

