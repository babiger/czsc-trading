"""czsc_cli.scanner 模块单元测试 (v5.2.3.4 真拆版).

覆盖:
  1. 模块结构 (v5.2.3.4 真拆后无 _EXPORTS)
  2. 6 函数 + cmd_list 迁出 (v5.2.3.4 决策)
  3. _parse_stocks / _sort_detail 纯函数
  4. is 关系 (函数)

v5.2.3.4 changes:
  - 移除 v5.1 lazy load 测试
  - cmd_list 验证不在 scanner (v5.2.3.4 迁到 signals 域)
  - filter helpers 验证不在 scanner (v5.1 误分类, 留给 batch v5.2.3.5)
"""
import pytest

import czsc_signals
from czsc_cli import scanner


class TestScannerModuleStructure:
    """模块结构 + 暴露面 (v5.2.3.4 真拆后)."""

    def test_imports_ok(self):
        assert scanner.__name__ == "czsc_cli.scanner"

    def test_no_v51_lazy_load_marks(self):
        """v5.2.3.4: 不再有 v5.1 lazy load 标记."""
        assert not hasattr(scanner, "_EXPORTS"), "_EXPORTS 应没了"
        assert not hasattr(scanner, "_imported"), "_imported 标志应没了"
        assert not hasattr(scanner, "__getattr__"), "__getattr__ 应没了"

    def test_6_core_functions_exported(self):
        """v5.2.3.4: 6 函数 (3 核心 + 3 scan entry)."""
        must_have = [
            "_parse_stocks",
            "_score_one_stock",
            "_sort_detail",
            "_apply_preset",
            "run_scan_signals",
            "cmd_scan",
        ]
        for name in must_have:
            assert hasattr(scanner, name), f"missing {name}"
            assert callable(getattr(scanner, name)), f"{name} not callable"

    def test_cmd_list_moved_to_signals(self):
        """v5.2.3.4 决策: cmd_list 迁到 signals 域 (列信号逻辑)."""
        assert not hasattr(scanner, "cmd_list"), \
            "cmd_list 不应属 scanner (v5.2.3.4 迁到 signals)"

    def test_filter_helpers_not_in_scanner(self):
        """v5.2.3.4 决策: filter helpers 留给 batch 域 (v5.2.3.5 真拆)."""
        for name in ["_filter_bak_basic_dict", "_print_filter_summary",
                      "_fetch_basic_cached", "_load_watchlist_safe"]:
            assert not hasattr(scanner, name), \
                f"{name} 不应属 scanner (v5.2.3.4 留给 batch)"


class TestScannerIsRelation:
    """跨模块函数 is-equal (单点真理)."""

    def test_cmd_scan_is_original(self):
        assert scanner.cmd_scan is czsc_signals.cmd_scan

    def test_run_scan_signals_is_original(self):
        assert scanner.run_scan_signals is czsc_signals.run_scan_signals

    def test_sort_detail_is_original(self):
        assert scanner._sort_detail is czsc_signals._sort_detail

    def test_score_one_stock_is_original(self):
        assert scanner._score_one_stock is czsc_signals._score_one_stock

    def test_parse_stocks_is_original(self):
        assert scanner._parse_stocks is czsc_signals._parse_stocks


class TestParseStocks:
    """_parse_stocks 解析 stock 列表 (空 watchlist 也能跑)."""

    def test_comma_separated(self, tmp_path):
        """逗号分隔的股票代码."""
        wl = tmp_path / "wl.txt"
        wl.write_text("")  # 空 watchlist
        result = scanner._parse_stocks("600519.SH,000001.SZ,300750.SZ", str(wl))
        assert result == ["600519.SH", "000001.SZ", "300750.SZ"]

    def test_whitespace_stripped(self, tmp_path):
        """空格和换行被 strip."""
        wl = tmp_path / "wl.txt"
        wl.write_text("")
        result = scanner._parse_stocks("  600519.SH  ,  000001.SZ  ", str(wl))
        assert result == ["600519.SH", "000001.SZ"]

    def test_empty_stocks_arg_uses_watchlist(self, tmp_path):
        """空 stocks_arg 应该从 watchlist 文件读."""
        wl = tmp_path / "wl.txt"
        wl.write_text("600519.SH\n000001.SZ\n300750.SZ\n")
        result = scanner._parse_stocks("", str(wl))
        assert result == ["600519.SH", "000001.SZ", "300750.SZ"]

    def test_dedup(self, tmp_path):
        """重复项应该去重."""
        wl = tmp_path / "wl.txt"
        wl.write_text("")
        result = scanner._parse_stocks("600519.SH,600519.SH,000001.SZ", str(wl))
        assert len(result) == 2


class TestSortDetail:
    """_sort_detail 纯逻辑 (不需要 tushare).

    实际数据结构:
      detail[ts_code] = {"composite": float, "total_mv": float, "turnover_rate": float,
                         "last_close": float, "per_signal": {alias: {"score": float}}}
    """

    def test_sort_by_composite_descending(self):
        """按 composite 升序 (reverse=True 表示降序 = 高在前)."""
        detail = {
            "A": {"composite": 50, "per_signal": {}},
            "B": {"composite": 80, "per_signal": {}},
            "C": {"composite": 30, "per_signal": {}},
        }
        # reverse=True -> 降序 (高在前, 默认用户视角)
        result = scanner._sort_detail(detail, sort_by="composite", reverse=True)
        codes = [r[0] for r in result]
        assert codes == ["B", "A", "C"]

    def test_sort_ascending(self):
        """reverse=False -> 升序 (低在前)."""
        detail = {
            "A": {"turnover_rate": 5.0, "per_signal": {}},
            "B": {"turnover_rate": 1.0, "per_signal": {}},
            "C": {"turnover_rate": 3.0, "per_signal": {}},
        }
        result = scanner._sort_detail(detail, sort_by="turnover_rate", reverse=False)
        codes = [r[0] for r in result]
        assert codes == ["B", "C", "A"]

    def test_sort_by_alias_via_per_signal(self):
        """按 alias 名 sort_by (向后兼容 v3.5): 走 per_signal.get(alias).get(score)."""
        detail = {
            "A": {"per_signal": {"一买": {"score": 50}}},
            "B": {"per_signal": {"一买": {"score": 80}}},
            "C": {"per_signal": {"一买": {"score": 30}}},
        }
        result = scanner._sort_detail(detail, sort_by="一买", reverse=True)
        codes = [r[0] for r in result]
        assert codes == ["B", "A", "C"]

    def test_empty_detail(self):
        """空 detail 应该返回空 list."""
        assert scanner._sort_detail({}, sort_by="composite") == []

    def test_missing_score_defaults_to_zero(self):
        """alias 不在 per_signal 里时, 默认 score=0.0 (不崩)."""
        detail = {
            "A": {"per_signal": {}},  # 没 一买
            "B": {"per_signal": {"一买": {"score": 80}}},
        }
        # 不应抛 KeyError
        result = scanner._sort_detail(detail, sort_by="一买", reverse=True)
        assert len(result) == 2