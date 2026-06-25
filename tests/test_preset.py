"""czsc_cli.preset 模块单元测试 (v5.2.3.2 真拆版).

覆盖:
  1. 模块结构 (14 exports + v5.2.3.2 真拆后无 _EXPORTS)
  2. 9 cmd_preset_* 都在 module
  3. PRESET_DIR module-level (v5.2.3.2 搬到 preset)
  4. cmd_preset_* 验证 (不依赖磁盘)
  5. is 关系 (函数) + 同值 (常量)

v5.2.3.2 changes:
  - 移除 v5.1 lazy load 测试 (_EXPORTS / _imported / __getattr__)
  - 新增 v5.2.3.2 真拆 invariant: _EXPORTS/_imported 不存在, 9 个 cmd 可直接 attribute access
  - PRESET_DIR 现在归 preset (单点真理), from-import 创建新绑定, 测试改为验证 preset.PRESET_DIR
  - BUILTIN_PRESETS 留 czsc_signals (不在 preset)
"""
import argparse
from pathlib import Path

import pytest

import czsc_signals
from czsc_cli import preset


class TestPresetModuleStructure:
    """模块结构 + 暴露面 (v5.2.3.2 真拆后)."""

    def test_imports_ok(self):
        assert preset.__name__ == "czsc_cli.preset"

    def test_no_v51_lazy_load_marks(self):
        """v5.2.3.2: 不再有 v5.1 lazy load 标记."""
        assert not hasattr(preset, "_EXPORTS"), "_EXPORTS 应没了"
        assert not hasattr(preset, "_imported"), "_imported 标志应没了"
        assert not hasattr(preset, "__getattr__"), "__getattr__ 应没了"

    def test_all_9_subcommands_exported(self):
        """v5.2.3.2: 9 个 cmd_preset_* 子命令 (v5.2.1 写 8 个, 实际是 9)."""
        subcommands = [
            "cmd_preset_save", "cmd_preset_list", "cmd_preset_show",
            "cmd_preset_delete", "cmd_preset_export", "cmd_preset_import",
            "cmd_preset_diff", "cmd_preset_merge", "cmd_preset_validate",
        ]
        for cmd in subcommands:
            assert hasattr(preset, cmd), f"missing {cmd}"
            assert callable(getattr(preset, cmd)), f"{cmd} not callable"

    def test_all_4_helpers_exported(self):
        """v5.2.3.2: 4 helpers (save/load/apply/override)."""
        helpers = [
            "_save_user_preset", "_load_user_preset",
            "_apply_user_preset", "_override_preset_dir",
        ]
        for h in helpers:
            assert hasattr(preset, h), f"missing {h}"
            assert callable(getattr(preset, h)), f"{h} not callable"

    def test_module_state_exported(self):
        """v5.2.3.2: PRESET_DIR + PRESET_SAVE_FLAGS 都是 module-level."""
        assert isinstance(preset.PRESET_DIR, Path)
        assert isinstance(preset.PRESET_SAVE_FLAGS, tuple)
        assert len(preset.PRESET_SAVE_FLAGS) == 17


class TestPresetIsRelation:
    """跨模块函数 is-equal (单点真理)."""

    def test_cmd_preset_save_is_original(self):
        assert preset.cmd_preset_save is czsc_signals.cmd_preset_save

    def test_cmd_preset_list_is_original(self):
        assert preset.cmd_preset_list is czsc_signals.cmd_preset_list

    def test_cmd_preset_validate_is_original(self):
        assert preset.cmd_preset_validate is czsc_signals.cmd_preset_validate

    def test_save_user_preset_is_original(self):
        assert preset._save_user_preset is czsc_signals._save_user_preset

    def test_preset_save_flags_same_value(self):
        """PRESET_SAVE_FLAGS 是 tuple, from-import 不保持 is, 验证同值."""
        assert preset.PRESET_SAVE_FLAGS == czsc_signals.PRESET_SAVE_FLAGS


class TestBuiltinPresetsInCzscSignals:
    """BUILTIN_PRESETS 留 czsc_signals (v5.0 历史, 不掊避免多 module 依赖)."""

    def test_builtin_presets_in_czsc_signals(self):
        assert hasattr(czsc_signals, "BUILTIN_PRESETS")
        # 不在 preset
        assert not hasattr(preset, "BUILTIN_PRESETS")
        # 4 个内置预设
        assert set(czsc_signals.BUILTIN_PRESETS.keys()) == {"value", "bank", "momentum", "bargain"}


class TestPresetDirEnvOverride:
    """PRESET_DIR 环境变量 + _override_preset_dir 动态覆盖."""

    def test_preset_dir_is_path(self):
        """PRESET_DIR 必须是 Path 实例."""
        assert isinstance(preset.PRESET_DIR, Path)

    def test_default_preset_dir_value(self):
        """默认 PRESET_DIR 是 ~/.czsc-presets (可被 CZSC_PRESET_DIR 环境变量覆盖)."""
        # 默认应该是 home 下的 .czsc-presets (无环境变量时)
        assert ".czsc-presets" in str(preset.PRESET_DIR)


class TestPresetDirManipulation:
    """_override_preset_dir 修改 preset.PRESET_DIR (v5.2.3.2: 改 preset 模块全局)."""

    def teardown_method(self):
        """每个测试后恢复 PRESET_DIR 到原值."""
        # 注: czsc_signals.PRESET_DIR 是 from-import 的绑定, 改 preset.PRESET_DIR 不会同步
        #     因此只恢复 preset.PRESET_DIR
        preset.PRESET_DIR = Path(__import__('os').environ.get(
            "CZSC_PRESET_DIR", str(Path.home() / ".czsc-presets")
        )).expanduser()

    def test_override_changes_preset_dir(self, tmp_path):
        """_override_preset_dir 应该改 preset.PRESET_DIR 到新值.

        v5.2.3.2 注: 'global PRESET_DIR' 现在是 preset 模块全局 (不在 czsc_signals),
        因此修改的是 preset.PRESET_DIR, czsc_signals.PRESET_DIR 不会跟随
        (因为 from-import 创建的是新绑定, 不会被 module-level global 改变).
        实际 scan 调用会走 preset.PRESET_DIR, 所以业务逻辑正确.
        """
        new_dir = tmp_path / "custom_presets"
        args = argparse.Namespace(preset_dir=str(new_dir))
        preset._override_preset_dir(args)
        # preset.PRESET_DIR 已改 (v5.2.3.2 真拆行为)
        assert preset.PRESET_DIR == Path(str(new_dir)).expanduser()
