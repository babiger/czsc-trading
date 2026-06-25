# scanner 模块详细参考

> v5.2.2: 本文档是从 SKILL.md "## 模块参考"章节拆出的独立 chapter. 用户查阅 scanner 模块 API 时按需读 references/scanner.md..
> 原始行号: SKILL.md L2326-L2377, v5.2.3 真拆完成 commit 505ca07 后.

---

### scanner 模块

**路径**: `skills/czsc-trading/czsc_cli/scanner.py` (47 行)

**exports** (6 项):

| 名字 | 用途 | 依赖 |
|---|---|---|
| `_parse_stocks(stocks_arg, watchlist)` | 解析股票列表 (逗号/文件/去重) | ❌ **纯函数** |
| `_score_one_stock(ts_code, weight)` | 对单只股票评分 | ✅ tushare + 腾讯 |
| `_sort_detail(detail, sort_by, reverse)` | 排序扫描结果 | ❌ **纯函数** |
| `run_scan_signals(args)` | 执行多股扫描 (主入口) | ✅ tushare + 腾讯 |
| `cmd_scan(args)` | `scan` 子命令 handler | ✅ tushare + 腾讯 |
| `cmd_list(args)` | `list` 子命令 handler (列出可用信号) | ❌ |

**评分排序逻辑** (`_sort_detail`):
- `composite` — 按信号加权综合分 (默认, 降序)
- `total_mv` — 按总市值降序
- `turnover_rate` — 按换手率降序
- `last_close` — 按最新收盘价降序
- `ts_code` — 按股票代码字母序 (stable, 便于对比)
- `任意 alias` — 按该信号 score 降序 (向后兼容 v3.5)

**纯函数** (适合单测):
- `_parse_stocks(stocks_arg: str, watchlist: str) → list` — 逗号分隔 / 文件行 / 去重 / strip
- `_sort_detail(detail: dict, sort_by: str, reverse: bool) → list` — 按指定 key 排序

**典型用法**:
```bash
# 多股扫描 + 综合排名 (top 5)
python3 -m czsc_cli scan --watchlist wl.txt --top 5

# 指定股票 + 按市值排序
python3 -m czsc_cli scan --stocks 600519.SH,000001.SZ --sort-by total_mv

# 列出可选信号
python3 -m czsc_cli list
```

**测试覆盖** (v5.2.1, `tests/test_scanner.py`, 15 tests):
- ✅ 模块结构: 6 exports, 核心 API 都在
- ✅ lazy 转发: cmd_scan/run_scan_signals/_sort_detail is 原函数
- ✅ `_parse_stocks`: 逗号 / strip / watchlist 回退 / 去重
- ✅ `_sort_detail`: composite 升序/降序 / per_signal alias 排序 / 空 detail / 缺失 key 默认 0

**已知坑**:
- `_score_one_stock` 是扫描核心 — 最重操作, 每次调用都触发网络请求 (tushare + 腾讯)
- `_sort_detail` reverse 语义: `reverse=True` = 降序 (大在前), `reverse=False` = 升序 (小在前)
  - 用户 `--reverse` flag 在调用前已做语义取反 (args.reverse=False → 降序, 用户视角的默认行为)

---

**章节目录**:
- 上一节: [batch.md](batch.md)
- 回到索引: [SKILL.md 模块参考](../SKILL.md#模块参考-module-reference)
- 下一节: [signals.md](signals.md)
