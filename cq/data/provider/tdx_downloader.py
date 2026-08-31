"""
cqdata/provider/tdx_downloader.py

通达信官方全量日线行情包 (hsjday.zip) 下载、解压部署与目录验证专用模块。
"""

import time
import tempfile
import zipfile
from pathlib import Path
from urllib.request import urlretrieve
from loguru import logger
from cq.data.service.sync_tracker import sync_tracker

# 通达信官方日线行情包下载 URL
TDX_DAILY_URL = "https://data.tdx.com.cn/vipdoc/hsjday.zip"
_EXTRACT_PREFIXES = ("sh/lday/", "sz/lday/", "bj/lday/")


def download_and_extract(output_dir: Path, task_id: str = "tdx.download.hsjday") -> None:
    """
    从官方服务器下载全量日线包 hsjday.zip 并解压到 vipdoc 目录，同时向 sync_tracker 注册并更新进度。
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    sync_tracker.start_task(task_id, message="正在准备从官方服务器下载通达信全量日线包 hsjday.zip...")

    last_log_time = 0.0
    last_downloaded = 0

    def progress_reporthook(block_num: int, block_size: int, total_size: int):
        """每秒平滑刷新一次下载百分比与实时速度日志，并同步给 sync_tracker。"""
        nonlocal last_log_time, last_downloaded
        now = time.time()
        downloaded = block_num * block_size

        if now - last_log_time >= 1.0 or (total_size > 0 and downloaded >= total_size):
            time_diff = now - last_log_time
            speed = (downloaded - last_downloaded) / time_diff if time_diff > 0 else 0
            speed_mb = speed / (1024 * 1024)
            downloaded_mb = downloaded / (1024 * 1024)

            if total_size > 0:
                total_mb = total_size / (1024 * 1024)
                pct = min(100.0, downloaded / total_size * 100)
                msg = f"[下载中] {pct:5.1f}% | {downloaded_mb:5.1f}/{total_mb:.1f} MB | 速度: {speed_mb:5.2f} MB/s"
                logger.info(msg)
                sync_tracker.update_progress(task_id, current=downloaded, total=total_size, message=msg)
            else:
                msg = f"[下载中] {downloaded_mb:5.1f} MB | 速度: {speed_mb:5.2f} MB/s"
                logger.info(msg)
                sync_tracker.update_progress(task_id, current=downloaded, total=downloaded, message=msg)

            last_log_time = now
            last_downloaded = downloaded

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            zip_path = Path(tmp_dir) / "hsjday.zip"

            logger.info(f"正在下载: {TDX_DAILY_URL}")
            urlretrieve(TDX_DAILY_URL, str(zip_path), reporthook=progress_reporthook)
            logger.info(f"下载完成: {zip_path}")

            logger.info(f"正在解压到: {output_dir}")
            sync_tracker.update_progress(task_id, current=1, total=1, message=f"正在解压至 {output_dir}...")
            extracted = 0
            with zipfile.ZipFile(zip_path, 'r') as zf:
                info_list = [i for i in zf.infolist() if any(i.filename.startswith(p) for p in _EXTRACT_PREFIXES)]
                total_info = len(info_list)
                for idx, info in enumerate(info_list):
                    zf.extract(info, str(output_dir))
                    extracted += 1
                    if idx % 500 == 0 or idx == total_info - 1:
                        sync_tracker.update_progress(task_id, current=idx + 1, total=total_info, message=f"正在解压行情包 ({idx + 1}/{total_info})...")

            success_msg = f"解压完成: 共部署 {extracted} 个代码的日线行情"
            logger.info(success_msg)
            sync_tracker.finish_task(task_id, success=True, message=success_msg)
    except Exception as e:
        error_msg = f"下载解压失败: {e}"
        logger.error(error_msg)
        sync_tracker.finish_task(task_id, success=False, message=error_msg, error_msg=str(e))
        raise e


def verify_vipdoc(vipdoc_dir: Path) -> bool:
    """验证 vipdoc 目录结构并统计代码数量。"""
    sh_count = 0
    sz_count = 0
    bj_count = 0

    for market_dir in ["sh", "sz", "bj"]:
        lday = vipdoc_dir / market_dir / "lday"
        if lday.exists():
            count = len(list(lday.glob("*.day")))
            if market_dir == "sh":
                sh_count = count
            elif market_dir == "sz":
                sz_count = count
            else:
                bj_count = count

    total = sh_count + sz_count + bj_count
    logger.info("vipdoc 目录统计:")
    logger.info("  沪市 (sh): %d 个代码", sh_count)
    logger.info("  深市 (sz): %d 个代码", sz_count)
    logger.info("  北交所 (bj): %d 个代码", bj_count)
    logger.info("  合计: %d 个代码", total)

    if total == 0:
        logger.warning("vipdoc 目录为空，请检查下载是否成功")
        return False

    return True
