# signals 模块详细参考

> v5.2.2: 本文档是从 SKILL.md "## 模块参考"章节拆出的独立 chapter. 用户查阅 signals 模块 API 时按需读 references/signals.md..
> 原始行号: SKILL.md L2378-L2455, v5.2.3 真拆完成 commit 505ca07 后.

---

### signals 模块

**路径**: `skills/czsc-trading/czsc_cli/signals.py` (56 行)

**exports** (12 项):

| 名字 | 用途 | 依赖 |
|---|---|---|
| `run_signals(args)` | 单股信号检测 (主入口) | ✅ tushare + 腾讯 |
| `cmd_signals(args)` | `signals` 子命令 handler | ✅ tushare + 腾讯 |
| `cmd_events(args)` | `events` 子命令 handler (只输出触发事件) | ✅ tushare + 腾讯 |
| `cmd_summary(args)` | `summary` 子命令 handler (信号摘要) | ✅ tushare + 腾讯 |
| `resample_to_freq(df, freq)` | K 线重采样 (日→周/月) | ❌ **纯 pandas** |
| `run_multi_freq_signals(args)` | 多周期信号扫描 (日/周/月) | ✅ tushare + 腾讯 |
| `cmd_multi_freq(args)` | `multi` 子命令 handler | ✅ tushare + 腾讯 |
| `build_weight_with_stops(...)` | 构建带止盈止损的权重信号配置文件 | ❌ |
| `run_weight_backtest(...)` | 执行权重回测 | ✅ tushare + 腾讯 |
| `cmd_backtest(args)` | `backtest` 子命令 handler | ✅ tushare + 腾讯 |
| `SIGNAL_GROUPS` | `dict` — 信号分组配置 (6 组) | — |
| `CORE_BS_SIGNALS` | `list[dict]` — 4 个核心缠论买卖点 | — |

**核心缠论买卖点** (`CORE_BS_SIGNALS`, 4 个):

| 名字 | alias | 描述 |
|---|---|---|
| `cxt_first_buy_V221126` | 一买 | 下跌趋势底背驰后的转折点 |
| `cxt_first_sell_V221126` | 一卖 | 上涨趋势顶背驰后的转折点 |
| `cxt_second_bs_V240524` | 二买卖 | 一买/一卖后回调不破前低/前高 |
| `cxt_third_buy_V230228` | 三买 | 突破中枢后回踩不进中枢 |

**信号分组** (`SIGNAL_GROUPS`, 6 组):

| 组名 | 描述 | 包含信号 |
|---|---|---|
| `all_long` | 所有买入类信号 | 一买 + 二买 + 三买 + MACD 一买 + MACD 二买 + 笔翼二买 |
| `all_short` | 所有卖出类信号 | 一卖 + 二卖 + 三卖 + MACD 一卖 |
| `bs_core` | 核心缠论买卖点 | 一买 + 一卖 + 二买卖 + 三买 |
| `bs1` | 第一类买卖点 | 一买 + 一卖 |
| `momentum` | 动量类信号 | (扩展信号) |
| `reversal` | 反转类信号 | (扩展信号) |

**典型用法**:
```bash
# 单股信号检测
python3 -m czsc_cli signals --ts-code 600519.SH --days 500

# 只输出触发事件
events --ts-code 600519.SH --days 500

# 信号摘要 (触发次数 + 最近日期)
summary --ts-code 600519.SH --days 500

# 多周期信号扫描 (日/周/月)
multi --ts-code 600519.SH --days 500

# 回测 (信号触发→次日买入→5 日后卖出)
backtest --ts-code 600519.SH --signal all --hold-days 5 --days 1000

# 止盈止损回测
backtest --ts-code 600519.SH --stop-loss 0.05 --take-profit 0.1
```

**测试覆盖** (v5.2.1, `tests/test_signals.py`, 17 tests):
- ✅ 模块结构: 12 exports, 核心信号 API 都在
- ✅ lazy 转发: run_signals/run_multi_freq_signals/run_weight_backtest is 原函数
- ✅ `CORE_BS_SIGNALS` 跨模块共享 (list 对象同 id)
- ✅ CORE_BS_SIGNALS: 4 个信号, 格式完整性 (name/alias), 别名包含一买/一卖/二买卖/三买
- ✅ SIGNAL_GROUPS: dict 类型, 至少 6 组, 每组有 `description` + `signals` (list, 非空)
- ✅ `_filter_by_industry_pe` (无 filter 时全保留, pe_max 过滤时不崩)
- ⏳ `resample_to_freq` (空 df 跳过 — 需要具体列)

**已知坑**:
- 腾讯 API 单次最多 ~641 根 K 线, 超过 1000 天返回空 → `fetch_klines_for_signals` 自动 clamp
- 信号计算是 CPU 密集 (Pandas + numpy), 扫描多只时建议 `--top 5` 限制
- `SIGNAL_GROUPS` 里的 `momentum` / `reversal` 组信号可能为空 (扩展占位) — 已在 SKILL.md v4.9 记录
- 回测是简化版: 信号触发→次日开盘买入→N 日后卖出, 不包含滑点/手续费

---

**章节目录**:
- 上一节: [scanner.md](scanner.md)
- 回到索引: [SKILL.md 模块参考](../SKILL.md#模块参考-module-reference)
- 下一节: [changelog.md](changelog.md)
