"""czsc_cli.batch 模块单元测试 (v5.2.3.5 真拆版).

覆盖:
  1. 模块结构 (10 函数真拆)
  2. is 关系 (10 batch 函数)
  3. _filter_bak_basic_dict 纯逻辑 (不需要 tushare)
  4. _execute_one_run 单 run 行为 (preset 判别)

v5.2.3.5 changes:
  - 移除 v5.1 lazy load 测试
  - 移除 _apply_preset / BUILTIN_PRESETS (v5.2.3.4 后这两个属 scanner 域, BUILTIN 留 czsc_signals)
  - 改为验证 10 函数真拆 + is 关系
"""
import argparse
import sys

import pytest

import czsc_signals
from czsc_cli import batch
from czsc_cli import scanner  # _apply_preset / BUILTIN_PRESETS 在 v5.2.3.4 已迁到 scanner


class TestBatchModuleStructure:
    """模块结构 + 暴露面 (v5.2.3.5 真拆后)."""

    def test_imports_ok(self):
        assert batch.__name__ == "czsc_cli.batch"

    def test_no_v51_lazy_load_marks(self):
        """v5.2.3.5: 不再有 v5.1 lazy load 标记."""
        assert not hasattr(batch, "_EXPORTS"), "_EXPORTS 应没了"
        assert not hasattr(batch, "_imported"), "_imported 标志应没了"
        assert not hasattr(batch, "__getattr__"), "__getattr__ 应没了"

    def test_10_functions_exported(self):
        """v5.2.3.5: 10 函数 (slack push + batch config + dry-run + filter + run + execute)."""
        must_have = [
            "_push_to_slack",
            "_load_batch_config",
            "_batch_dry_run",
            "_merge_scan_args_for_dry_run",
            "_filter_bak_basic_dict",
            "_print_filter_summary",
            "_fetch_basic_cached",
            "_load_watchlist_safe",
            "_run_batch",
            "_execute_one_run",
        ]
        for name in must_have:
            assert hasattr(batch, name), f"missing {name}"
            assert callable(getattr(batch, name)), f"{name} not callable"

    def test_no_apply_preset_in_batch(self):
        """v5.2.3.4: _apply_preset 已迁到 scanner 域 (不在 batch)."""
        assert not hasattr(batch, "_apply_preset")

    def test_no_builtin_presets_in_batch(self):
        """BUILTIN_PRESETS 留 czsc_signals (不在 batch)."""
        assert not hasattr(batch, "BUILTIN_PRESETS")


class TestBatchIsRelation:
    """跨模块函数 is-equal (单点真理)."""

    def test_run_batch_is_original(self):
        assert batch._run_batch is czsc_signals._run_batch

    def test_push_to_slack_is_original(self):
        assert batch._push_to_slack is czsc_signals._push_to_slack

    def test_load_batch_config_is_original(self):
        assert batch._load_batch_config is czsc_signals._load_batch_config

    def test_batch_dry_run_is_original(self):
        assert batch._batch_dry_run is czsc_signals._batch_dry_run

    def test_filter_bak_basic_dict_is_original(self):
        assert batch._filter_bak_basic_dict is czsc_signals._filter_bak_basic_dict

    def test_execute_one_run_is_original(self):
        assert batch._execute_one_run is czsc_signals._execute_one_run


class TestFilterBakBasicDict:
    """_filter_bak_basic_dict 纯逻辑 (本地 filter 不依赖 tushare API)."""

    def test_empty_args_no_filter(self):
        """industry / pe_max / pe_min / pb_max / mcap_min 全空时, 全部保留."""
        basic_cache = {
            "000001.SZ": {"name": "平安银行", "industry": "银行", "pe": 5.0, "pb": 0.5},
            "600519.SH": {"name": "贵州茅台", "industry": "白酒", "pe": 25.0, "pb": 8.0},
        }
        args = argparse.Namespace(industry="", pe_max=None, pe_min=None,
                                   pb_max=None, market_cap_min=None,
                                   exclude_st=False, exclude_keyword="")
        result = batch._filter_bak_basic_dict(basic_cache, args)
        assert set(result.keys()) == {"000001.SZ", "600519.SH"}

    def test_industry_filter(self):
        """industry='银行' 只保留 industry 含 '银行' 的股."""
        basic_cache = {
            "000001.SZ": {"name": "平安银行", "industry": "银行", "pe": 5.0, "pb": 0.5},
            "600519.SH": {"name": "贵州茅台", "industry": "白酒", "pe": 25.0, "pb": 8.0},
        }
        args = argparse.Namespace(industry="银行", pe_max=None, pe_min=None,
                                   pb_max=None, market_cap_min=None,
                                   exclude_st=False, exclude_keyword="")
        result = batch._filter_bak_basic_dict(basic_cache, args)
        assert "000001.SZ" in result
        assert "600519.SH" not in result

    def test_pe_max_filter(self):
        """pe_max=15.0 过滤 PE > 15 的股."""
        basic_cache = {
            "LOW": {"name": "低估值", "industry": "银行", "pe": 5.0, "pb": 0.5},
            "HIGH": {"name": "高估值", "industry": "白酒", "pe": 25.0, "pb": 8.0},
        }
        args = argparse.Namespace(industry="", pe_max=15.0, pe_min=None,
                                   pb_max=None, market_cap_min=None,
                                   exclude_st=False, exclude_keyword="")
        result = batch._filter_bak_basic_dict(basic_cache, args)
        assert "LOW" in result
        assert "HIGH" not in result

    def test_exclude_st_filter(self):
        """exclude_st=True 过滤 name 含 ST 的股."""
        basic_cache = {
            "OK": {"name": "正常股", "industry": "银行", "pe": 5.0, "pb": 0.5},
            "ST": {"name": "ST 测试", "industry": "其他", "pe": -1.0, "pb": 0.5},
        }
        args = argparse.Namespace(industry="", pe_max=None, pe_min=None,
                                   pb_max=None, market_cap_min=None,
                                   exclude_st=True, exclude_keyword="")
        result = batch._filter_bak_basic_dict(basic_cache, args)
        assert "OK" in result
        assert "ST" not in result

    def test_negative_pe_excluded(self):
        """PE<=0 (亏损) 在 pe_max 设了的情况下过滤掉."""
        basic_cache = {
            "OK": {"name": "盈利", "industry": "银行", "pe": 5.0, "pb": 0.5},
            "LOSS": {"name": "亏损", "industry": "银行", "pe": -1.0, "pb": 0.5},
        }
        args = argparse.Namespace(industry="", pe_max=15.0, pe_min=None,
                                   pb_max=None, market_cap_min=None,
                                   exclude_st=False, exclude_keyword="")
        result = batch._filter_bak_basic_dict(basic_cache, args)
        assert "OK" in result
        assert "LOSS" not in result
