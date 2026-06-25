# batch 模块详细参考

> v5.2.2: 本文档是从 SKILL.md "## 模块参考"章节拆出的独立 chapter. 用户查阅 batch 模块 API 时按需读 references/batch.md..
> 原始行号: SKILL.md L2270-L2325, v5.2.3 真拆完成 commit 505ca07 后.

---

### batch 模块

**路径**: `skills/czsc-trading/czsc_cli/batch.py` (54 行)

**exports** (12 项):

| 名字 | 用途 | 依赖 |
|---|---|---|
| `_push_to_slack(...)` | 发送结果到 Slack webhook | ✅ 网络 |
| `_load_batch_config(path)` | 加载 YAML 批量配置 | ⚠️ 文件 |
| `_batch_dry_run(...)` | dry-run 模式: 只打印不执行 | ❌ |
| `_merge_scan_args_for_dry_run(...)` | 合并 config + CLI 参数 | ❌ |
| `_filter_bak_basic_dict(...)` | 内存级过滤 (PE/PB/市值/换手) | ❌ |
| `_print_filter_summary(...)` | 打印过滤统计 | ❌ |
| `_fetch_basic_cached(...)` | 带缓存的 tushare 基础数据 | ✅ tushare |
| `_load_watchlist_safe(...)` | 安全加载 watchlist 文件 | ⚠️ 文件 |
| `_run_batch(...)` | 执行批量扫描 (含 retry + error handling) | ✅ tushare |
| `_execute_one_run(...)` | 单次扫描执行 (batch 循环体) | ✅ tushare |
| `_apply_preset(args)` | 应用内置预设 (v3.9) | ❌ **纯逻辑** |
| `BUILTIN_PRESETS` | `dict` — 4 个内置预设配置 | — |

**内置预设 `BUILTIN_PRESETS`** (v5.2.0 提到模块级):

| 预设名 | 策略 | 核心参数 | 适合场景 |
|---|---|---|---|
| `value` | 价值投资 | PE≤15 / PB≤2 / 市值≥1000亿 / 综合分降序 | 低估蓝筹 |
| `bank` | 银行专场 | 行业=银行 / PE≤15 / PB≤1.5 / 市值≥2000亿 | 银行股筛选 |
| `momentum` | 动量策略 | 换手≥1% / 市值≥500亿 / 综合分降序 / 显示统计 | 趋势跟踪 |
| `bargain` | 抄底策略 | PE≤10 / 市值≥200亿 / 换手率升序 | 低估值捡漏 |

> v5.2.0 修复: `BUILTIN_PRESETS` 从 `_apply_preset()` 函数内 local dict 提到模块级, 解决 `from czsc_cli.batch import _apply_preset, BUILTIN_PRESETS` 全挂的 bug。

**典型用法**:
```bash
# 批量扫描 (使用预设)
python3 -m czsc_cli scan --preset value --watchlist wl.txt

# dry-run 模式
python3 -m czsc_cli batch --config batch.yml --dry-run
```

**测试覆盖** (v5.2.1, `tests/test_batch.py`, 16 tests):
- ✅ 模块结构: 12 exports, 全部 helper 存在
- ✅ lazy 转发: `_run_batch`/`_push_to_slack`/`_apply_preset` is 原函数
- ✅ `BUILTIN_PRESETS` 模块级 (v5.2.0 invariant)
- ✅ 内置预设 4 个 keys + 每个预设的配置完整性
- ✅ `_apply_preset` 行为: no-op / value 应用 / 用户值不覆盖 / 未知 preset exit(1)

**已知坑**:
- 批量模式依赖 YAML 配置文件, 不传 `--config` 则走默认路径
- Slack webhook 需要环境变量或配置指定
- Batch 重试策略: 默认 3 次, 间隔 5s (可配置)
- `_filter_bak_basic_dict` 是内存过滤 — 不触发 tushare, 但依赖数据已在 dict 里

---

**章节目录**:
- 上一节: [preset.md](preset.md)
- 回到索引: [SKILL.md 模块参考](../SKILL.md#模块参考-module-reference)
- 下一节: [scanner.md](scanner.md)
