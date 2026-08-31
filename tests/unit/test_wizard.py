"""
tests/unit/test_wizard.py

测试终端交互向导业务逻辑 (cq.data.service.wizard)。
"""

import pytest
from unittest.mock import patch, MagicMock
from cq.data.service.wizard import discover_supported_tables, start_wizard


class TestWizardService:
    """测试向导服务模块"""

    def test_discover_supported_tables(self):
        tables = discover_supported_tables()
        assert isinstance(tables, list)
        assert len(tables) >= 16
        assert "ashare.kline.1d.raw.baostock" in tables
        assert "ashare.kline.1d.raw.tdx" in tables
        assert "ashare.kline.1d.raw.stockdb" in tables
        assert "aetf.kline.1d.raw.stockdb" in tables

    @patch("cq.data.service.wizard.discover_supported_tables", return_value=[])
    @patch("builtins.print")
    def test_start_wizard_empty_tables(self, mock_print, mock_discover):
        """测试未发现表时的防御退出"""
        start_wizard()
        mock_print.assert_any_call("[!] 未发现可用数据表。")

    @patch("builtins.input")
    @patch("builtins.print")
    def test_start_wizard_cancel(self, mock_print, mock_input):
        """测试向导在用户拒绝确认时正常退出不抛出异常"""
        mock_input.side_effect = [
            "1",           # 切换选中第1项
            "",            # 回车确认选择跳出表循环
            "2024-01-01",  # 起始日期
            "2024-01-31",  # 结束日期
            "parquet",     # 存储格式
            "n",           # 不强制全量
            "50",          # batch_size
            "n",           # 取消确认
        ]
        start_wizard()
        mock_print.assert_any_call("\n[!] 任务已取消。")

    @patch("builtins.input")
    @patch("cq.data.service.wizard.sync")
    def test_start_wizard_flow(self, mock_sync, mock_input):
        """测试常规默认流程执行"""
        # 模拟交互输入: [1] 选第一项, [2] 日期留空, [3] 格式默认, [4] 覆盖否, [5] 确认
        mock_input.side_effect = [
            "1",           # 选择第1项
            "0",           # 确认选择
            "",            # 起始日期默认
            "",            # 结束日期默认
            "parquet",     # 格式
            "n",           # 强制覆盖否
            "50",          # 批大小
            "y"            # 确认启动
        ]

        start_wizard()
        assert mock_sync.called
        call_kwargs = mock_sync.call_args.kwargs
        assert call_kwargs["formats"] == ["parquet"]
        assert call_kwargs["batch_size"] == 50
        assert call_kwargs["force_refresh"] is False

    @patch("builtins.input")
    @patch("cq.data.service.wizard.sync")
    def test_start_wizard_selection_commands(self, mock_sync, mock_input):
        """测试向导全选 (*)、全不选 (-)、多选逗号分隔及切换选择"""
        mock_input.side_effect = [
            "*",           # 全选
            "-",           # 全不选
            "1, 2",        # 选择 1 和 2
            "999",         # 超出范围索引 (容错分支)
            "abc",         # 非法字符串 (容错分支)
            "2",           # 切换取消 2
            "0",           # 确认表格选择
            "2024-01-01",  # 起始日期
            "2024-12-31",  # 结束日期
            "parquet,csv", # 格式
            "y",           # 强制覆盖
            "200",         # 批大小
            "yes"          # 确认启动
        ]

        start_wizard()
        assert mock_sync.called
        call_kwargs = mock_sync.call_args.kwargs
        assert len(call_kwargs["table_ids"]) == 1
        assert call_kwargs["start_date"] == "2024-01-01"
        assert call_kwargs["end_date"] == "2024-12-31"
        assert call_kwargs["formats"] == ["parquet", "csv"]
        assert call_kwargs["force_refresh"] is True
        assert call_kwargs["batch_size"] == 200

    @patch("cq.data.provider.provider_manager.ProviderManager")
    def test_discover_supported_tables_custom_provider_error(self, mock_pm_cls):
        """测试动态注册的驱动在抛出异常时被容错捕获"""
        mock_pm = MagicMock()
        mock_bad_prov = MagicMock()
        mock_bad_prov.get_supported_tables.side_effect = RuntimeError("Broken custom provider")
        mock_pm._custom_providers = {"broken": mock_bad_prov}
        mock_pm_cls.return_value = mock_pm

        tables = discover_supported_tables()
        assert isinstance(tables, list)

    @patch("builtins.input")
    @patch("builtins.print")
    @patch("cq.data.service.wizard.sync")
    def test_start_wizard_zero_without_selection_then_proceed(self, mock_sync, mock_print, mock_input):
        """测试在未选中任何项时按 0 触发提示，随后输入 1 并继续完成流程"""
        mock_input.side_effect = [
            "0",           # 未选任何项直接按 0
            "1",           # 选中第 1 项
            "0",           # 确认选择
            "",            # 默认日期
            "",            # 默认日期
            "",            # 默认格式
            "n",           # 覆盖否
            "100",         # batch
            "y"            # 确认
        ]
        start_wizard()
        mock_print.assert_any_call("[!] 请至少选择一个同步对象！")
        assert mock_sync.called
