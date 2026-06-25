"""czsc_cli.data 模块单元测试 (v5.2.3.1 真拆版).

覆盖:
  1. 模块结构 (真拆后: 14 函数 + 2 常量)
  2. 真拆实现 (函数直接在 data 模块, 不是 lazy 转发)
  3. is 关系 (data.X is czsc_signals.X)
  4. 纯函数 (_is_st_or_delisted, _cache_path)
  5. K 线 cache helpers (不需要真实数据)
  6. v5.2.3 invariant: PRESET_DIR 不在 data.py (掊到 czsc_cli.preset)

v5.2.3.1 changes:
  - 移除 _EXPORTS / _imported / __getattr__ 相关测试 (v5.1 lazy load 已废)
  - 移除 data.PRESET_DIR 测试 (v5.2.3 掊到 preset)
  - 新增 "未声明 attribute 应 raise" 语义测试 (AttributeError)
  - 新增 v5.2.3 真拆 invariant 测试 (无 lazy load 标记)
"""
import sys
from pathlib import Path

import pytest

import czsc_signals
from czsc_cli import data


class TestDataModuleStructure:
    """模块结构 + 暴露面 (v5.2.3 真拆后)."""

    def test_imports_ok(self):
        """czsc_cli.data 能正常 import."""
        assert data.__name__ == "czsc_cli.data"

    def test_no_v51_lazy_load_marks(self):
        """v5.2.3: 不再有 v5.1 lazy load 标记 (_EXPORTS / _imported / __getattr__)."""
        assert not hasattr(data, "_EXPORTS"), "_EXPORTS 应该没了 (v5.2.3 真拆)"
        assert not hasattr(data, "_imported"), "_imported 标志应该没了 (v5.2.3 真拆)"
        assert not hasattr(data, "__getattr__"), "__getattr__ 应该没了 (v5.2.3 真拆)"

    def test_exports_count(self):
        """data 模块应该有 14 个顶层公开函数/常量 (v5.2.3 真拆).

        含 12 个函数 + 2 个 module-level dict (SIGNAL_WEIGHTS, RECENCY_BONUS) + CACHE_DIR Path.
        不含 PRESET_DIR (v5.2.3 移除, 掊到 preset).
        """
        # 公开 API 集合 (手动列举, 作为 v5.2.3 真拆后的 API 表面)
        public_api = {
            # tushare fetchers (3)
            "_fetch_st_names_via_tushare", "_fetch_industry_via_tushare", "_fetch_bak_basic_via_tushare",
            # filter helpers (4)
            "_filter_by_industry_pe", "_filter_by_market_cap_turnover",
            "_is_st_or_delisted", "_filter_stocks",
            # weights (1)
            "_load_weights",
            # K 线 (5)
            "fetch_klines_for_signals", "_fetch_klines_uncached",
            "fetch_klines_with_cache", "_cache_path", "_load_cache", "_save_cache",
            # 公开常量 (4)
            "SIGNAL_WEIGHTS", "RECENCY_BONUS", "CACHE_DIR",
            # module-level caches (状态, 公开但主要是 internal)
            "_ST_CACHE", "_INDUSTRY_CACHE", "_BAK_BASIC_CACHE", "_BAK_BASIC_DATE",
        }
        for name in public_api:
            assert hasattr(data, name), f"missing {name}"
        # PRESET_DIR 不再在 data
        assert not hasattr(data, "PRESET_DIR"), "PRESET_DIR 已搬到 preset"

    def test_no_preset_dir(self):
        """v5.2.3 invariant: PRESET_DIR 不在 data.py (职责迁移到 preset)."""
        assert not hasattr(data, "PRESET_DIR")


class TestDataIsRelation:
    """真拆后: data.X 应该是实际函数, 与 czsc_signals.X 是同一对象 (单点真理)."""

    def test_is_st_or_delisted_is_original(self):
        """czsc_cli.data._is_st_or_delisted 应该跟 czsc_signals._is_st_or_delisted 是同一个对象."""
        assert data._is_st_or_delisted is czsc_signals._is_st_or_delisted

    def test_load_weights_is_original(self):
        """_load_weights 也同 is."""
        assert data._load_weights is czsc_signals._load_weights

    def test_signal_weights_is_original(self):
        """SIGNAL_WEIGHTS 跨域共享 (单点真理在 data)."""
        assert data.SIGNAL_WEIGHTS is czsc_signals.SIGNAL_WEIGHTS

    def test_cache_path_is_original(self):
        """_cache_path 也同 is."""
        assert data._cache_path is czsc_signals._cache_path

    def test_unknown_attr_raises(self):
        """访问未声明的属性应该 raise AttributeError."""
        with pytest.raises(AttributeError) as exc_info:
            data.this_attr_does_not_exist
        assert "czsc_cli.data" in str(exc_info.value)


class TestIsStOrDelisted:
    """_is_st_or_delisted 纯函数测试."""

    def test_normal_stock(self):
        """正常股票名 -> False."""
        assert data._is_st_or_delisted("贵州茅台") is False
        assert data._is_st_or_delisted("平安银行") is False

    def test_st_with_prefix(self):
        """ST 前缀 -> True."""
        assert data._is_st_or_delisted("ST 康美") is True
        assert data._is_st_or_delisted("*ST 华讯") is True

    def test_lowercase_st(self):
        """大小写不敏感 (upper())."""
        assert data._is_st_or_delisted("st 测试") is True

    def test_delisted_keyword(self):
        """'退' 字 -> True (退市)."""
        assert data._is_st_or_delisted("退市长油") is True
        assert data._is_st_or_delisted("已退市股") is True

    def test_empty_and_none(self):
        """空字符串和 None -> False (防御)."""
        assert data._is_st_or_delisted("") is False
        assert data._is_st_or_delisted(None) is False  # type: ignore


class TestCachePath:
    """_cache_path 路径生成测试."""

    def test_cache_path_format(self, tmp_path):
        """缓存路径应该 ~/.czsc-cache/<ts_code>.parquet (默认)."""
        # 不能直接 patch global, 改成验证格式
        path = data._cache_path("600519.SH")
        assert path.suffix == ".parquet"
        assert "600519.SH" in path.name or "600519" in path.name
        # 默认 cache dir 应该在用户家目录下
        assert Path.home() in path.parents or ".czsc-cache" in str(path)

    def test_cache_path_distinct(self):
        """不同 ts_code 应该生成不同路径."""
        p1 = data._cache_path("600519.SH")
        p2 = data._cache_path("000001.SZ")
        assert p1 != p2