"""
cqdata/config/settings.py

全局配置管理模块。
纯 Python 实现轻量 Settings，支持显式配置加载与程序化动态修改：
1. 环境变量 CQDATA_CONFIG_PATH / CQDATA_DATA_DIR (显式指定)
2. 显式 configure(config_path) 加载 YAML 配置文件
3. 显式修改 cq.data.settings 属性
"""

import os
from pathlib import Path
from typing import Optional, Union, Dict, Any
import yaml
from dotenv import load_dotenv
from cq.data.utils.logger_utils import setup_logger



class Settings:
    """
    全局 Settings 类 (纯 Python 实现，无 pydantic-settings 依赖)
    """

    def __init__(self):
        # 核心配置字段默认值
        self.data_dir: str = "data"
        self.log_dir: str = "logs"
        self.log_level: str = "INFO"

        # 初始化时自动加载配置
        self._load_initial_config()
        self._refresh_logger()

    def _load_initial_config(self) -> None:
        """
        按优先级规则初始化加载配置：
        1. 自动从当前目录下的 .env 文件加载环境变量 (override=True 确保本地 .env 显式定义即生效)
        2. 环境变量 CQDATA_CONFIG_PATH 显式指定 YAML 配置文件
        3. 环境变量 CQDATA_DATA_DIR 显式覆盖 data_dir
        4. 环境变量 CQDATA_LOG_DIR / CQDATA_LOG_LEVEL 显式覆盖日志配置
        """
        # 0. 自动加载当前目录下的 .env 文件
        env_file = Path(".env")
        if env_file.is_file():
            load_dotenv(dotenv_path=env_file, override=True)



        # 1. 环境变量 CQDATA_CONFIG_PATH 显式指定 YAML 配置文件
        config_path_env = os.getenv("CQDATA_CONFIG_PATH")
        if config_path_env:
            path = Path(config_path_env)
            if path.exists():
                self.load_from_file(path)

        # 2. 环境变量 CQDATA_DATA_DIR 显式覆盖 data_dir
        if os.getenv("CQDATA_DATA_DIR"):
            self.data_dir = os.getenv("CQDATA_DATA_DIR")

        # 3. 环境变量 CQDATA_LOG_DIR 显式覆盖 log_dir
        if os.getenv("CQDATA_LOG_DIR"):
            self.log_dir = os.getenv("CQDATA_LOG_DIR")

        # 4. 环境变量 CQDATA_LOG_LEVEL 显式覆盖 log_level
        if os.getenv("CQDATA_LOG_LEVEL"):
            self.log_level = os.getenv("CQDATA_LOG_LEVEL").upper()


    def load_from_file(self, config_path: Union[str, Path]) -> "Settings":
        """
        显式从指定 YAML 配置文件加载配置
        """
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(path, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f)

        if isinstance(config_data, dict):
            if "data_dir" in config_data:
                self.data_dir = str(config_data["data_dir"])

            if "log_dir" in config_data:
                self.log_dir = str(config_data["log_dir"])

            if "log_level" in config_data:
                self.log_level = str(config_data["log_level"]).upper()

    def configure(self, config_path: Union[str, Path]) -> "Settings":
        """
        从指定 YAML 配置文件加载全局参数。

        示例:
            cq.data.configure("./config.yaml")
        """
        self.load_from_file(config_path)
        self._refresh_logger()
        return self

    def _refresh_logger(self) -> None:
        """配置变更后安全刷新 loggerHandler"""
        try:
            setup_logger(log_level=self.log_level, log_dir=self.log_dir)
        except Exception:
            pass



# 全局 Settings 单例实例
settings = Settings()
