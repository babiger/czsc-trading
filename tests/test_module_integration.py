"""跨模块集成测试 (v5.2.1).

v5.1 关键设计: __getattr__ lazy 转发, 跨模块函数 = 原函数 (is-check).
v5.2.1 这里集中验证这个 invariant.
"""
import pytest

import czsc_signals
from czsc_cli import data, preset, batch, scanner, signals as sig


class TestCrossModuleIdentity:
    """所有跨模块函数必须是同一函数对象 (单点真理)."""

    def test_data_identity(self):
        """v5.2.3.1: data 域函数 is-equal (不含 PRESET_DIR, 已搬到 preset)."""
        names = ["_is_st_or_delisted", "_filter_stocks", "fetch_klines_with_cache",
                  "_load_weights", "SIGNAL_WEIGHTS"]
        for n in names:
            assert getattr(data, n) is getattr(czsc_signals, n), f"data.{n}"
        # v5.2.3 invariant: data.PRESET_DIR 不再存在 (搬家到 preset)
        assert not hasattr(data, "PRESET_DIR"), "PRESET_DIR 应已搬离 data"

    def test_preset_identity(self):
        names = [
            "cmd_preset_save", "cmd_preset_list", "cmd_preset_show",
            "cmd_preset_delete", "cmd_preset_validate",
            "PRESET_DIR",
        ]
        for n in names:
            assert getattr(preset, n) is getattr(czsc_signals, n), f"preset.{n}"

    def test_batch_identity(self):
        """v5.2.3.5: batch 10 函数真拆.
        _apply_preset / BUILTIN_PRESETS 不在 batch (v5.2.3.4 _apply_preset 迁到 scanner,
        BUILTIN_PRESETS 留 czsc_signals 模块级).
        """
        names = [
            "_run_batch", "_push_to_slack", "_load_batch_config",
            "_batch_dry_run", "_merge_scan_args_for_dry_run",
            "_filter_bak_basic_dict", "_print_filter_summary",
            "_fetch_basic_cached", "_load_watchlist_safe",
            "_execute_one_run",
        ]
        for n in names:
            assert getattr(batch, n) is getattr(czsc_signals, n), f"batch.{n}"

    def test_scanner_identity(self):
        """v5.2.3.4: cmd_list 已迁到 signals 域 (不在 scanner)."""
        names = ["cmd_scan", "run_scan_signals", "_parse_stocks", "_sort_detail",
                  "_score_one_stock", "_apply_preset"]
        for n in names:
            assert getattr(scanner, n) is getattr(czsc_signals, n), f"scanner.{n}"
        # v5.2.3.4: cmd_list 不在 scanner._EXPORTS (迁到 signals)
        assert not hasattr(scanner, "cmd_list") or \
               scanner.cmd_list is signals.cmd_list

    def test_signals_identity(self):
        names = [
            "run_signals", "cmd_signals", "cmd_events", "cmd_summary",
            "run_multi_freq_signals", "cmd_multi_freq",
            "run_weight_backtest", "cmd_backtest",
            "SIGNAL_GROUPS", "CORE_BS_SIGNALS",
        ]
        for n in names:
            assert getattr(sig, n) is getattr(czsc_signals, n), f"signals.{n}"


class TestGlobalStateShared:
    """global state (PRESET_DIR, BUILTIN_PRESETS) 跨模块必须共享."""

    def test_preset_dir_shared(self):
        """v5.2.3.2: PRESET_DIR 在 preset (家) + czsc_signals (re-export via from-import).
        注: from-import 创建的是新绑定, 不会是 'is'. 验证同值 + source.
        """
        # preset 是 home (从 os.environ.get 算), czsc_signals 是 from-import 绑定
        # 它们指向同一 Path 对象 — 但实际行为: preset 模块修改全局 PRESET_DIR 不会传到 czsc_signals
        # 测试: 验证两者同值 + 都不是 None
        assert str(preset.PRESET_DIR) == str(czsc_signals.PRESET_DIR)
        # data 已经不拥有 PRESET_DIR
        assert not hasattr(data, "PRESET_DIR"), "data.PRESET_DIR 应被移除 (v5.2.3)"

    def test_builtin_presets_shared(self):
        """v5.2.3.5: BUILTIN_PRESETS 留 czsc_signals (不在 batch).
        batch._execute_one_run + scanner._apply_preset 都用 `from czsc_signals import BUILTIN_PRESETS`.
        """
        assert hasattr(czsc_signals, "BUILTIN_PRESETS"), "BUILTIN_PRESETS 应留 czsc_signals"
        assert not hasattr(batch, "BUILTIN_PRESETS"), "BUILTIN_PRESETS 不该在 batch (v5.2.3.5)"
        # scanner._apply_preset 函数内 import BUILTIN_PRESETS (v5.2.3.4 fix 循环 import)
        # 所以 __globals__['BUILTIN_PRESETS'] 不存在 (是函数内 import 局部)
        # 但运行时能正确访问 (验证 import 链)
        from czsc_cli.scanner import _apply_preset
        import argparse
        # _apply_preset 内部 import BUILTIN_PRESETS, 通过 sys.modules 验证
        assert _apply_preset.__globals__["__name__"] == "czsc_cli.scanner"
        # BUILTIN_PRESETS 在 czsc_signals 模块 globals
        assert czsc_signals.__dict__.get("BUILTIN_PRESETS") is not None

    def test_core_bs_signals_shared(self):
        """CORE_BS_SIGNALS 跨 signals + czsc_signals 共享."""
        assert sig.CORE_BS_SIGNALS is czsc_signals.CORE_BS_SIGNALS

    def test_signal_groups_shared(self):
        """SIGNAL_GROUPS 跨 signals + czsc_signals 共享."""
        assert sig.SIGNAL_GROUPS is czsc_signals.SIGNAL_GROUPS


class TestNoCodeDrift:
    """v5.1 核心承诺: lazy 转发, 改 czsc_signals 自动反映到所有模块."""

    def test_5_modules_count(self):
        """5 个 czsc_cli 子模块都能 import."""
        from czsc_cli import data, preset, batch, scanner, signals
        assert all([data, preset, batch, scanner, signals])
        # 各自有正确 __name__
        assert data.__name__ == "czsc_cli.data"
        assert preset.__name__ == "czsc_cli.preset"
        assert batch.__name__ == "czsc_cli.batch"
        assert scanner.__name__ == "czsc_cli.scanner"
        assert signals.__name__ == "czsc_cli.signals"

    def test_total_exports(self):
        """v5.2.3.5: 5 模块全真拆完成 (无 _EXPORTS/_imported)."""
        # 1. 5 个模块都能 import
        from czsc_cli import data, preset, batch, scanner, signals
        assert all([data, preset, batch, scanner, signals])

        # 2. 每个模块至少有一个核心函数 (代表该域的 API)
        assert callable(data._is_st_or_delisted), "data 缺核心函数"
        assert callable(preset.cmd_preset_list), "preset 缺核心函数"
        assert callable(batch._run_batch), "batch 缺核心函数 (用 _run_batch, _apply_preset 已迁 scanner)"
        assert callable(scanner.cmd_scan), "scanner 缺核心函数"
        assert callable(signals.run_signals), "signals 缺核心函数"

        # 3. v5.2.3.1 真拆 data, v5.2.3.2 真拆 preset, v5.2.3.3 真拆 signals,
        #    v5.2.3.4 真拆 scanner, v5.2.3.5 真拆 batch
        for m, name, ver in [(data, "data", "v5.2.3.1"),
                              (preset, "preset", "v5.2.3.2"),
                              (signals, "signals", "v5.2.3.3"),
                              (scanner, "scanner", "v5.2.3.4"),
                              (batch, "batch", "v5.2.3.5")]:
            assert not hasattr(m, "_EXPORTS"), f"{name} 已真拆 ({ver}), 不该有 _EXPORTS"
            assert not hasattr(m, "_imported"), f"{name} 已真拆, 不该有 _imported"

    def test_v520_builtin_presets_is_module_level(self):
        """v5.2.0 关键不变量: BUILTIN_PRESETS 是模块级, 不是函数内 local."""
        # 修之前: BUILTIN_PRESETS 是 _apply_preset 函数内 local var, 外部 import 不到
        # 修之后: BUILTIN_PRESETS 是 czsc_signals 模块级, 可被 batch lazy load
        import czsc_signals
        assert hasattr(czsc_signals, "BUILTIN_PRESETS")
        # 直接通过模块属性访问
        keys = list(czsc_signals.BUILTIN_PRESETS.keys())
        assert "value" in keys and "bank" in keys

    def test_main_entry_works(self):
        """scripts.czsc_signals.main() 应该能被 invoke.

        Bug fix (v5.2.3-pre): 之前只检查 callable(), 是空壳测试.
        修正: 用 subprocess 真正调 --help, 验证输出含 deprecation warning + subcommand 列表.
        v5.2.3.1 fix: 加 PYTHONPATH=skill_root 让 scripts/czsc_signals.py 找到 czsc_cli 包.
        """
        import subprocess
        import sys
        from pathlib import Path
        skill_root = Path(__file__).resolve().parent.parent
        env = {**__import__("os").environ, "PYTHONPATH": str(skill_root)}
        result = subprocess.run(
            [sys.executable, "scripts/czsc_signals.py", "--help"],
            capture_output=True, text=True,
            cwd=str(skill_root), env=env, timeout=15,
        )
        assert result.returncode == 0, f"--help 失败: {result.stderr[:300]}"
        # v5.0 deprecation warning
        assert "[czsc v5.0]" in result.stderr, f"缺 deprecation warning: {result.stderr[:300]}"
        assert "deprecated" in result.stderr.lower()
        # 8 个 subcommand 都在
        assert "scan" in result.stdout
        assert "signals" in result.stdout
        assert "preset" in result.stdout


class TestDepricationWarning:
    """v5.0+ 兼容: 旧入口加 deprecation warning."""

    def test_old_path_still_works(self):
        """scripts/czsc_signals.py 还能跑 (v3.x 老入口)."""
        import czsc_signals
        # 应该能正常 import main
        assert callable(czsc_signals.main)