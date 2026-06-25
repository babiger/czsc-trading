# czsc-trading v5.2 Release Notes

> 2026-06-25 · GitHub: `babiger/czsc-trading` (private) · tags: `v5.2.2`, `v5.2.3`

## TL;DR (60 秒看完)

v5.2 是一个 **可维护性大重构**,把单文件 2959 行的 `scripts/czsc_signals.py` 拆成 5 个真实现的 `czsc_cli/*` 模块,加上 100 个 pytest 单测,SKILL.md 拆 5 个独立 chapter。

- ✅ **代码减重**: `czsc_signals.py` 2959 → **392 行** (-86.7%, 收尾成纯 shim)
- ✅ **模块化**: 5 个 `czsc_cli/*.py` 从 lazy load 转发转**真实现**(2896 行)
- ✅ **测试**: 0 → **100 pass** (6 文件, 1.85s)
- ✅ **文档**: SKILL.md 2468 → **2183 行** (-11.5%),详情挪 `references/` 6 文件
- ✅ **业务 100% 向后兼容**: 双入口 (`python3 -m czsc_cli` 新 + `python3 scripts/czsc_signals.py` 旧 deprecation warning) 都跑通

## v5.2 子版本演进

| 版本 | commit | tag | 内容 | 耗时 |
|---|---|---|---|---|
| v5.2.0 | (in initial) | — | BUILTIN_PRESETS 模块级(修哑炮) | < 1h |
| v5.2.1 | (in initial) | — | pytest 单元测试基线(88 pass + 1 skip) | ~2h |
| v5.2.2 | `0efc1da` | `v5.2.2` | SKILL.md 拆 5 chapter + changelog | ~1h |
| v5.2.3 | `505ca07` | `v5.2.3` | 5 模块从 lazy load 转真实现 | ~5h |

### v5.2.3 真拆函数实现 (5 子版本分阶段)

| 子版本 | 模块 | commit | 行数改前→改后 |
|---|---|---|---|
| v5.2.3.1 | data.py | (in `505ca07`) | 65 → 510 (+445) |
| v5.2.3.2 | preset.py | (in `505ca07`) | 53 → 515 (+462) |
| v5.2.3.3 | signals.py | (in `505ca07`) | 56 → 716 (+660) |
| v5.2.3.4 | scanner.py | (in `505ca07`) | 47 → 595 (+548) |
| v5.2.3.5 | batch.py | (in `505ca07`) | 54 → 560 (+506) |

## 架构演进 (v5.0 单文件 → v5.2 模块化)

```
v5.0 (2026-06-23):                v5.2.3 (2026-06-25):
                                  
czsc_signals.py (2959 行)        czsc_signals.py (392 行, 纯 shim)
┌─────────────────────┐          ┌─────────────────────┐
│ 56 顶层函数            │          │ imports 5 模块        │
│ 16 cmd_ 子命令         │          │ BUILTIN_PRESETS 模块级│
│ global state 散落    │    →     │ main() + argparse     │
│ 0 测试                │          └─────────────────────┘
└─────────────────────┘          
                                  czsc_cli/data.py (510)
v5.1 lazy load 中间状态:           czsc_cli/preset.py (515)
- 5 模块 + __getattr__ 转发      czsc_cli/signals.py (716)
- 88 行 lazy load 框架            czsc_cli/scanner.py (595)
                                  czsc_cli/batch.py (560)

                                  tests/ (6 文件, 100 pass)
```

## 关键设计决策 (v5.2.3 跨域依赖图)

```
┌─────────────────────────────────────────────────────────────┐
│  czsc_cli.batch (560)                                        │
│    _push_to_slack / _load_batch_config / _batch_dry_run      │
│    _filter_bak_basic_dict / _run_batch / _execute_one_run   │
└─────┬─────────────┬──────────────┬─────────────────────────┘
      │             │             │
      ▼             ▼             ▼
┌─────────────┐ ┌──────────────┐ ┌────────────┐
│ scanner (595)│ │ preset (515) │ │ data (510) │
│ _parse/      │ │ cmd_preset_* │ │ _fetch_*    │
│ _score/_sort │ │ PRESET_DIR   │ │ _filter_*   │
│ run_scan_*   │ │ _save/load/  │ │ fetch_klines│
└─────┬───────┘ │ apply_preset │ │ SIGNAL_WGTS│
      │         └──────────────┘ └─────┬──────┘
      ▼                                 │
┌─────────────┐                         │
│ signals (716)│─────────────────────────┘
│ run_signals │   fetch_klines_for_signals
│ multi_freq  │
│ backtest    │
└─────────────┘

   czsc_signals (392): BUILTIN_PRESETS 模块级, main() + argparse
```

## Python import 语义区分 (v5.2.3 设计精髓)

| 对象类型 | `from X import Y` 行为 | 测试方法 |
|---|---|---|
| 函数 | 保留 identity(同一对象) | `Y is Y` ✅ |
| list/dict (mutable) | 保留 identity(同一对象) | `Y is Y` ✅ |
| Path/tuple/str (immutable) | 创建新绑定 | `Y == Y` (值相同即可) |

**v5.2.3 实战验证**:
- 函数 `is-equal`: 47/47 ✅
- mutable 常量 `is-equal`: 6/6 ✅ (CORE_BS_SIGNALS / AUX_SIGNALS / ALL_SIGNALS / SIGNAL_GROUPS / BUILTIN_PRESETS / 等)
- immutable 常量 `==`: PRESET_DIR / SIGNAL_WEIGHTS / PRESET_SAVE_FLAGS ✅

## 打破循环 import (v5.2.3 关键 fix)

### 问题 1: data ↔ signals (v5.2.3.1 决策)
```
data._load_weights 用 SIGNAL_WEIGHTS
scanner._score_one_stock 也用 SIGNAL_WEIGHTS
```
→ `SIGNAL_WEIGHTS` 移到 `czsc_cli/data.py` 模块级 (打破循环)

### 问题 2: scanner ↔ czsc_signals (v5.2.3.4 fix)
```
scanner 顶层 from czsc_signals import BUILTIN_PRESETS
czsc_signals 顶层 from czsc_cli.scanner import (_parse_stocks, ...)
```
→ `BUILTIN_PRESETS` 改为在 `_apply_preset` **函数内** import(避开顶层循环)

## v5.2.3 误分类修正 (v5.1 lazy load 留下的坑)

| 项 | v5.1 误归 | v5.2.3 修正 |
|---|---|---|
| `_apply_preset` | batch | **scanner** (BUILTIN preset 在 scan 用) |
| `BUILTIN_PRESETS` | batch | **czsc_signals** (留, 单点真理) |
| `cmd_list` | scanner | **signals** (列 CORE/AUX/GROUPS 逻辑) |
| filter helpers (4 个) | scanner | **batch** (只在 dry-run 用) |

## 使用示例 (e2e 已验证)

```bash
# 1. 新入口 (推荐)
python3 -m czsc_cli --help
python3 -m czsc_cli list                                  # 列信号
python3 -m czsc_cli preset list                           # 列预设
python3 -m czsc_cli preset validate                       # 验证 9 个 preset

# 2. 旧入口 (deprecated, 但兼容)
PYTHONPATH=scripts:. python3 scripts/czsc_signals.py --help

# 3. 旧 pytest 验证
python3 -m pytest tests/                                  # 100 pass in 1.85s
```

## 测试覆盖明细

| 测试文件 | 测试数 | 覆盖范围 |
|---|---|---|
| `test_data.py` | 17 | data 域 14 函数真拆 + lazy load 标记全删 |
| `test_preset.py` | 13 | preset 域 13 函数真拆 + PRESET_DIR 副作用 |
| `test_signals.py` | 19 | signals 域 16 函数真拆 + 4 常量 + cmd_list |
| `test_scanner.py` | 17 | scanner 域 6 函数真拆 + filter helpers 排除 |
| `test_batch.py` | 16 | batch 域 10 函数真拆 + filter_bak_basic_dict |
| `test_module_integration.py` | 18 | 跨模块 is-equal + 共享状态 + lazy load 全删 |
| **总计** | **100** | **6 文件, 1.85s** |

## SKILL.md 拆分 (v5.2.2)

```
SKILL.md (2183 行, 主文件)
├── 这是什么 / 触发场景 / 依赖 / 数据源
├── CLI 用法 (8 subcommand + 15 例子)
├── Python API / 与其他 skill 协作 / 已知局限 / 安全 / 维护
└── 模块参考 (索引 + 链接, ~50 行)
    ↓ 链接
references/ (6 files, 详情)
├── data.md (66) - data 模块 API + 测试 + 已知坑
├── preset.md (60) - preset 模块
├── signals.md (90) - signals 模块
├── scanner.md (63) - scanner 模块
├── batch.md (67) - batch 模块
├── changelog.md (22) - v5.2 变更摘要
└── cheatsheet.md (168) - czsc 1.0.0rc8 API 速查 (原样)
```

每个 chapter 末尾有 cross-link (上一节 / 下一节 / 回到 SKILL.md 索引)。

## 备份 / 回滚

`tmp/v523-rollback/` (本地, 不入 git, 780KB):
- 4 个 `czsc_signals.py` 阶段快照 (v5.2.1 → v5.2.3.5)
- 5 个 v5.1 lazy load 版模块
- 5 个 test 备份 + SKILL.md 拆分前备份

```bash
# 回滚流程
git checkout v5.2.2              # 回到 v5.2.2
git checkout v5.2.3              # 回到 v5.2.3
git reset --hard 505ca07         # 重置到 v5.2.3 commit
git reset --hard 0efc1da         # 重置到 v5.2.2 commit
```

## 已知问题 / v5.3 计划

- **SKILL.md 测试数文档化**: 已修正 (从 65 改为 100)
- **Bash script 子命令中文逗号**: `--watchlist 123`, 与 `--watchlist 1,2,3` 都支持
- **`resample_to_freq` pandas 3.0+ ME rule**: 已用 `ME` 而非 `M`
- **mock data 模式**: 仍未做(v5.4 计划, 用 `examples/demo_mock.py` 简化测试)

## v5.3 候选 (待用户决定)

1. **推到 GitHub 公开** (现在是 private)
2. **写 README 改造** (更新装机说明 / 触发场景)
3. **写 pyproject.toml** (从 setup.py 升级, 现代化)
4. **加 GitHub Actions CI** (跑 pytest on push)
5. **发布到 PyPI** (作为 `czsc-trading` package)

---

🦐 Generated by 小虾 for 晓冬
