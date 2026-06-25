# czsc-trading

缠论技术分析 OpenClaw skill — Python wrapper for `waditu/czsc` (基于 czsc 1.0.0rc8).

> **v5.2.3 真拆后状态**: 5 个 `czsc_cli/*` 模块从 lazy load 转**真实现**(2896 行), `scripts/czsc_signals.py` 从 2959 → 392 行收尾成纯 shim. 100 pytest pass + GitHub Actions CI 防回归.
>
> GitHub: <https://github.com/babiger/czsc-trading> (private) | tags: `v5.2.2`, `v5.2.3`, `v5.3.1`

## 一句话总结

```bash
python3 -m czsc_cli list                                # 列可用信号
python3 -m czsc_cli scan --watchlist wl.txt --top 5    # 多股扫描 + 排名
python3 -m czsc_cli preset list                         # 列预设
```

## 装机状态 (v5.3.1, 2026-06-25)

- **czsc**: 1.0.0rc8 (Rust 加速, 246 信号函数)
- **akshare**: 1.18.64 (备用数据源)
- **plotly**: 6.8.0 (self-contained HTML 可视化)
- **Python**: 3.10+ (3.10/3.11 已在 GitHub Actions 验证)
- **OpenClaw 集成**: `runtime.conf` 声明 python3 entry, 8 subcommand (`signals`/`events`/`summary`/`list`/`scan`/`multi`/`backtest`/`preset`)

## 触发场景 (Triggers)

用户说以下任何一句, 应该 **优先** 使用本 skill:

- "看一下 X 这只股的缠论结构"
- "用缠论分析 000001"
- "X 的买卖点 / 中枢 / 笔 在哪里"
- "X 是不是缠论一买 / 二买 / 三买"
- "扫一下自选股的缠论信号" / "多股信号扫描"
- "哪只股最近一买信号最密集"
- "用 preset 扫银行赛道"

## 快速使用

### 1. 列出可用信号 (无网络, 无 tushare)

```bash
python3 -m czsc_cli list
# 输出: 4 核心买卖点 (一买/一卖/二买卖/三买) + 7 辅助 (TD9/MACD/双均线/支撑压力/笔翼二买) + 6 信号组别名
```

### 2. 多股扫描 + 排名 (需 tushare / 腾讯)

```bash
# 用示例 watchlist 跑
python3 -m czsc_cli scan --watchlist examples/watchlist.sample.txt --top 5

# 限制行业 + PE
python3 -m czsc_cli scan --watchlist wl.txt --industry 银行 --pe-max 15

# 用 preset (一键银行赛道)
python3 -m czsc_cli scan --preset bank --watchlist wl.txt
```

### 3. 单股信号 (无 tushare, 只用腾讯)

```bash
python3 -m czsc_cli signals --ts-code 600519.SH --days 500
python3 -m czsc_cli events --ts-code 000001.SZ --signal 一买
python3 -m czsc_cli summary --ts-code 600519.SH
```

### 4. 止盈止损回测

```bash
python3 -m czsc_cli backtest --ts-code 600519.SH --hold-days 5 --stop-loss 0.05 --take-profit 0.1
```

### 5. 批量扫描 (yaml config + 汇总报告 + Slack 推送)

```bash
python3 -m czsc_cli scan --batch-scan daily.yml --batch-output /tmp/report.md
python3 -m czsc_cli scan --batch-scan daily.yml --batch-dry-run  # 不拉数据, 只模拟
```

## 架构 (v5.2.3 真拆后)

```
czsc-trading/
├── SKILL.md                          # 触发场景 + CLI 用法 + 安全声明 (2183 行, v5.2.2 拆分后)
├── README.md                         # 本文件
├── RELEASE_NOTES.md                  # v5.2 release notes (202 行)
├── runtime.conf                      # python3 entry + 依赖
├── .github/workflows/test.yml        # CI 防回归 (v5.3.1, pytest 100 pass in 0.92s)
├── czsc_cli/                         # 5 真拆模块 (2896 行)
│   ├── data.py    (510)  - tushare 拉数 + 筛选 + K 线 cache
│   ├── preset.py  (515)  - 9 cmd_preset_* + 4 helper + PRESET_DIR
│   ├── signals.py (716)  - 11 函数 + 4 常量 + cmd_list
│   ├── scanner.py (595)  - 6 函数 (parse+score+sort+scan+preset+cmd)
│   └── batch.py   (560)  - 10 函数 (slack push+dry-run+runner+execute)
├── scripts/
│   ├── czsc_trading.py               # 主 CLI (analyze/signals/report/doc) [v5.0 起, 273 行]
│   └── czsc_signals.py              # 纯 shim (392 行, v5.2.3 收尾) - from-import 5 模块 + main + argparse
├── tests/                            # 100 pytest (6 文件)
│   ├── conftest.py
│   ├── test_data.py            (17)
│   ├── test_preset.py          (13)
│   ├── test_signals.py         (19)
│   ├── test_scanner.py         (17)
│   ├── test_batch.py           (16)
│   └── test_module_integration.py (18)
├── examples/
│   ├── demo_mock.py                  # mock 数据 demo (不需联网)
│   └── watchlist.sample.txt          # 12 只示例 (主要行业覆盖)
├── references/                       # 5 模块 chapter + cheatsheet (v5.2.2 拆分)
│   ├── data.md
│   ├── preset.md
│   ├── signals.md
│   ├── scanner.md
│   ├── batch.md
│   ├── changelog.md
│   └── cheatsheet.md
└── output/                           # HTML 输出目录 (.gitignore)
```

**跨域依赖图 (v5.2.3 真拆后)**:
- `batch → {scanner, preset, data}` (10 函数)
- `scanner → {signals, data, preset, czsc_signals.BUILTIN_PRESETS}` (6 函数)
- `signals → data` (12 函数 + 4 常量)
- `preset → standalone` (9 cmd + 4 helper)
- `data → standalone` (14 函数 + 3 cache)

## 双入口 (兼容)

```bash
# 新入口 (推荐) - 走 czsc_cli 5 真拆模块
python3 -m czsc_cli --help

# 旧入口 (deprecated, 但兼容) - 走 scripts/czsc_signals.py
PYTHONPATH=scripts:. python3 scripts/czsc_signals.py --help
# ⚠️ 旧入口会打印 deprecation warning, 但业务 100% 兼容
```

## 测试

```bash
python3 -m pytest tests/        # 100 passed in ~1s (本地)
# GitHub Actions CI: pytest 100 passed in 0.92s on Python 3.11
```

## 安全 / 隐私

- **GitHub**: <https://github.com/babiger/czsc-trading> (private, v5.3.1)
- **上游**: <https://github.com/waditu/czsc> (Apache-2.0 / BSD, 6K+ stars)
- **数据源**: tushare (mcporter MCP, 需 token) + 腾讯 ifzq 免费接口 (默认) + akshare
- **pip**: tuna 镜像 (国内加速, `--index-url https://pypi.tuna.tsinghua.edu.cn/simple/`)
- **无外部脚本下载**, **无 API token 强依赖**, **无自动修改任何全局配置**

## v5.x 版本演进

| 版本 | 内容 | GitHub |
|---|---|---|
| v5.0 | 包结构重构 (czsc_cli/ 5 模块 + lazy load) | tag `v5.0.0` |
| v5.1 | 模块拆分 + 逻辑零重复 (`__getattr__` lazy 转发) | tag `v5.1.0` |
| v5.2.0 | BUILTIN_PRESETS 模块级 (修哑炮) | (in initial) |
| v5.2.1 | pytest 88 pass baseline | (in initial) |
| v5.2.2 | SKILL.md 拆 5 chapter + changelog | tag `v5.2.2` |
| v5.2.3 | 5 模块真拆函数实现 (lazy load → 真实现) | tag `v5.2.3` |
| v5.3.1 | GitHub Actions CI 防回归 | tag `v5.3.1` |

详细 release notes: [`RELEASE_NOTES.md`](RELEASE_NOTES.md)

## 链接

- 触发场景 + 详细 CLI 用法: [`SKILL.md`](SKILL.md)
- 详细 API 文档: [`references/<module>.md`](references/) (data/preset/signals/scanner/batch)
- czsc 1.0.0rc8 API 速查: [`references/cheatsheet.md`](references/cheatsheet.md)
- v5.2 release notes: [`RELEASE_NOTES.md`](RELEASE_NOTES.md)

---

🦐 Generated by 小虾 for 晓冬
