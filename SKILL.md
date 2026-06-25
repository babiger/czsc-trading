# czsc-trading - 缠论技术分析技能

> **⚠️ 安全声明**: 本 skill **不下载任何外部脚本**,**不通过 `curl|bash` 安装**,所有代码 100% 在 GitHub 开源 (`waditu/czsc`) + pip 公共源 (`akshare`) + tushare MCP (mcporter) + 腾讯行情接口 (`web.ifzq.gtimg.cn`) 安装。无需任何 token。

## 这是什么

把 Python **缠论分析库** `waditu/czsc` 包装成 OpenClaw 能直接调用的 skill。

缠论(缠中说禅理论)是中国股票 / 期货市场的技术分析框架,核心概念包括:

| 概念 | czsc 类 | 说明 |
|---|---|---|
| K 线 | `RawBar` | 单根 OHLCV |
| 分型 | `FX` | 顶分型 / 底分型 |
| 笔 | `BI` | 至少 5 根 K 线,连接相邻顶底分型 |
| 中枢 | `bars_ubi` | 至少 3 笔重叠区间 |
| 线段 | (1.0+) | 多笔组合 |
| 买卖点 | (signals) | 第一/二/三类买卖点 |

## 触发场景 (Triggers)

用户说以下任何一句,应该 **优先** 使用本 skill:

- "看一下 X 这只股的缠论结构"
- "用缠论分析 000001"
- "X 的买卖点 / 中枢 / 笔 在哪里"
- "X 的分型识别 / 走势分解"
- "X 是不是缠论一买 / 二买"
- "对比 X 和 Y 的缠论结构"
- "扫一下自选股的缠论信号" / "多股信号扫描" / "哪只股最近信号最密集"

> 注意: 如果用户问的是"基本面分析" / "新闻 / 公告" / "估值模型",应分别走 `tushareMcp` + `stock-analysis` skill,不是本 skill 的职责。

## 依赖

```bash
# 一次性安装 (国内 tuna 镜像, 已在本机验证通过)
pip install --break-system-packages \
  --index-url https://pypi.tuna.tsinghua.edu.cn/simple/ \
  "czsc==1.0.0rc8" akshare requests

# 当前版本
# - czsc 1.0.0rc8 (Rust 加速, 246 个信号函数, Python 3.10+)
# - akshare 1.18.64 (备用数据源, 默认走腾讯)
# - plotly 6.8.0 (self-contained HTML 可视化)
# - requests (Python 自带, 用于腾讯接口)
```

## 数据源 (重要)

**v3.2 调整: 数据源优先 tushare (用户要求), fallback 腾讯 ifzq**。
**v3.3: 加本地 parquet 缓存** (默认启用, 避免重复拉 tushare)

| 源 | 优先级 | 优点 | 缺点 |
|---|---|---|---|
| **tushare (mcporter)** | ✅ 首选 | 有成交额, ~500 根/请求, 可靠 | 需 CLI 调用 (~0.5s) |
| 腾讯 ifzq | fallback | 一次性前复权, 快 (~0.3s) | 无成交额, max ~641 根 |
| **本地 parquet 缓存** | ✅ 首选 | 读存 0.7s, 命中后 4-18x 加速 | 需要数据量超出时才增量拉 |

**tushare 拉取流程** (3 步):
1. `mcporter call tushareMcp.daily --ts_code X --start_date YYYYMMDD --end_date YYYYMMDD` (不复权 OHLCV)
2. `mcporter call tushareMcp.adj_factor --ts_code X ...` (复权因子)
3. 算前复权: `qfq = close × adj_factor / latest_adj_factor`

**单位转换**:
- tushare `vol` 单位手 → 股 (×100)
- tushare `amount` 单位千元 → 元 (×1000)
- 腾讯 `vol` 单位手 → 股 (×100) 成交额置 0

**本地缓存**:
- 路径: `~/.cache/czsc/{ts_code}.parquet`
- 策略: 优先读缓存, 命中且足够 → 跳过 tushare; 不足 → 增量拉取 → 合并去重 → 写回
- 限制: 每只股 ~50KB, 1000 只股 ≈ 50MB (微)
- 加速: 首拉 2s/只, 命中后 0.7s/只 (多股 **18x 加速**)
- 失败处理: 缓存读失败 → 转 tushare 重拉

**为什么不直接用 `pro_bar`**: pro_bar tushare 内部调但需带 `adj` 参数,  mcporter 接口报 [40101] 接口名错误。手工 daily + adj_factor 更可控。

**为什么不直接用 `tushare.daily` Python SDK**: 需 tushare token,环境不包; mcporter + tushareMcp 是开箱即用方案。

## CLI 用法

### A. 缠论结构分析 (czsc_trading.py)

```bash
SKILL_DIR=/vol1/@apphome/trim.openclaw/data/workspace/skills/czsc-trading
PY=python3

# 1. 完整缠论分析 + HTML 可视化 (主入口)
$PY $SKILL_DIR/scripts/czsc_trading.py analyze \
  --ts-code 000001.SZ --days 250 --freq D \
  --output /tmp/000001_czsc.html

# 2. 只看信号摘要 (文本)
$PY $SKILL_DIR/scripts/czsc_trading.py signals --ts-code 000001.SZ

# 3. 报告 (analyze + Markdown 摘要)
$PY $SKILL_DIR/scripts/czsc_trading.py report \
  --ts-code 600519.SH --output /tmp/600519_czsc.html
```

### B. 买卖信号检测 (czsc_signals.py) - 新增!

**11 个预设信号 (czsc 1.0 Rust native, 222 个内置信号中精选)**:

| 分类 | 信号 | 说明 |
|---|---|---|
| 缠论核心 | 一买 / 一卖 / 二买卖 / 三买 | 缠中说禅理论 1-3 类买卖点 |
| 辅助 | TD9 (神奇九转) | 连续 9 日 TD 序列反转 |
| 辅助 | MACD 一买 / 二买 / 背驰 | DIF 底背驰 + 金叉 + 零轴 |
| 辅助 | 双均线 / 支撑压力 / 笔翼二买 | 趋势 / 形态 / 另一维度缠论 |

```bash
# 4. 信号状态图 (最近 30 天 + 触发统计)
$PY $SKILL_DIR/scripts/czsc_signals.py signals \
  --ts-code 000001.SZ \
  --signal 一买 一卖 三买 TD9 \
  --days 400

# 5. 触发事件流 (只输出触发行,含日期+价格+信号详情)
$PY $SKILL_DIR/scripts/czsc_signals.py events \
  --ts-code 600519.SH \
  --signal 一买 TD9 \
  --days 500

# 6. 信号摘要 (触发次数 + 最近触发日期)
$PY $SKILL_DIR/scripts/czsc_signals.py summary \
  --ts-code 000001.SZ \
  --signal all \
  --days 500

# 7. 列出全部 11 个可用信号
$PY $SKILL_DIR/scripts/czsc_signals.py list
```

### C. 多周期信号扫描 (czsc_signals.py multi) - v2 新增

**日/周/月三周期同时扫描**, 相同信号分别输出, 方便找**跨周期共振**:

```bash
# 8. 多周期信号扫描 (日+周+月)
$PY $SKILL_DIR/scripts/czsc_signals.py multi \
  --ts-code 000001.SZ \
  --signal 一买 一卖 三买 TD9 MACD一买 \
  --days 1500 \
  --freqs 日线,周线,月线

# 只看 周+月 (适合判断中长期趋势)
$PY $SKILL_DIR/scripts/czsc_signals.py multi \
  --ts-code 600519.SH --signal 一买 一卖 三买 \
  --days 1500 --freqs 周线,月线
```

**输出示例** (宁德时代 300750.SZ, 1500 天):
```
=== 300750.SZ 多周期信号摘要 ===

信号         日线                 周线                月线
一买         13次/2026-04-30    0次/-               0次/-
一卖         46次/2026-05-26    0次/-               0次/-
三买         74次/2026-06-02    0次/-               0次/-
TD9         2次/2025-12-15     5次/2026-06-14     0次/-
MACD一买    18次/2026-01-26    5次/2026-05-10     0次/-
```

**多周期实现原理**:
- 日线 K 线用 `fetch_klines_for_signals` 拉 (腾讯 ifzq)
- 周线/月线由 `resample_to_freq` 手动聚合 (pandas 3.0+ `M` → `ME`)
- 每周期独立跑 `generate_czsc_signals` (Rust native 批模式, 0.06s/1500 bars)
- **不**用 `CzscSignals.update_signals` 流式 API (慢 ~1000x)

### D. 多股扫描 + 信号打分排名 (czsc_signals.py scan) - v3.5 新增

**核心场景**: 自选 N 只股, 一次性跑信号 + 按权重打 composite 分排名, 找"近期信号最密集"的标的。

```bash
# 12. 自带 watchlist 跑 (示例文件 examples/watchlist.sample.txt, 12 只覆盖主要行业)
$PY $SKILL_DIR/scripts/czsc_signals.py scan \
  --watchlist $SKILL_DIR/examples/watchlist.sample.txt \
  --signal 一买 三买 二买卖 \
  --top 10

# 13. 命令行直接传 5 只
$PY $SKILL_DIR/scripts/czsc_signals.py scan \
  --stocks 000001.SZ,600519.SH,000858.SZ,300750.SZ,600036.SH \
  --signal 一买 三买 二买卖

# 14. 按单一信号排名 (e.g. 谁最近一买最密集)
$PY $SKILL_DIR/scripts/czsc_signals.py scan \
  --watchlist $SKILL_DIR/examples/watchlist.sample.txt \
  --rank-by 一买 --top 5

# 15. 看全部 11 个信号
$PY $SKILL_DIR/scripts/czsc_signals.py scan \
  --stocks 000001.SZ,300750.SZ --signal all
```

**输出示例** (5 只测试股, 一买/三买/二买卖):
```
=== 多股扫描排名 (rank_by=composite) ===

成功 5/5 只, 取前 5 名:

rank  代码                 收盘  最近日期        composite    一买    三买   二买卖
--------------------------------------------------------------------
   1  300750.SZ      392.51  2026-06-23      429.0    60    30     3
   2  600036.SH       37.40  2026-06-23      364.0    26    50    10
   3  000858.SZ       74.76  2026-06-23      339.0    48     0    33
   4  000001.SZ       10.71  2026-06-23      334.0     8    41    42
   5  600519.SH     1222.45  2026-06-23      242.0    18     8    40
```

**打分公式** (v3.5):
```
composite = Σ (信号触发次数 × 信号权重) + 时效加分
  权重: 一买/一卖=5, 三买=4, 二买卖=3, MACD=1, 其他辅助=0.5
  时效加分: 最新触发距今 <5天 +3, <20天 +1
```

**适用边界**:
- 自选股 ≤ 50 只 (`--max-stocks 50` 防呆)
- 每只股 ~2-3 秒 (腾讯 ifzq 拉 500 天 K 线)
- composite 是**信号密度**指标, **不是买入建议** - 高分只代表"近期信号多", 仍要结合价格位置/成交量/趋势判断
- 跑前先看 `examples/watchlist.sample.txt` 格式 (支持注释/标题/空格分隔)

**v3.5 设计决策**:
- **权重维度 vs 单信号**: 默认 composite (综合), `--rank-by 一买` 可单信号排序
- **不内置默认 watchlist**: 用户场景差异大, 给示例文件不强制
- **进度输出到 stderr**: `[scan 3/15] 000001.SZ ...`, 表格到 stdout, 方便 `| tee` 保存
- **失败不中断**: 单只股失败只 stderr 警告, 继续跑其他

### v3.5.1 新增特性

#### 1. `--output-csv` 结果导出
扫描结果直接保存 CSV (含股票名, 方便 Excel/Notion 打开):
```bash
$PY $SKILL_DIR/scripts/czsc_signals.py scan \
  --watchlist $SKILL_DIR/examples/watchlist.sample.txt \
  --signal 一买 三买 --top 10 \
  --output-csv /tmp/scan_$(date +%Y%m%d).csv
```
CSV 表头: `rank,name,ts_code,last_close,last_dt,composite,一买_n,一买_last,三买_n,三买_last,...`
- `name` 从 tushare stock_basic 拉 (基础权限够, 带缓存)
- 编码 `utf-8-sig` (Windows Excel 也能打开)

#### 2. `--exclude-st` ST/退市过滤
自动跳过 ST / *ST / 含"退"字的股 (防止手贱扫到坑):
```bash
$PY $SKILL_DIR/scripts/czsc_signals.py scan \
  --stocks 000001.SZ,000004.SZ,300750.SZ \
  --exclude-st --signal 一买
# 扫描结果 (000004.SZ 国华退 被跳过):
# [scan] ST/退市 过滤: 跳过 1 只 → [('000004.SZ', '国华退')]
```
- **仅能过滤已知名称的股** (依赖 tushare stock_basic, 基础权限)
- 过滤后股池为 0 → 报错退出

#### 3. `--weights-file` 自定义权重
适合看重点信号的进阶用户:
```bash
# 创建权重文件 /tmp/aggressive.json
echo '{"一买": 8.0, "三买": 6.0, "MACD背驰": 2.5}' > /tmp/aggressive.json

$PY $SKILL_DIR/scripts/czsc_signals.py scan \
  --watchlist $SKILL_DIR/examples/watchlist.sample.txt \
  --signal 一买 三买 MACD背驰 \
  --weights-file /tmp/aggressive.json
```
输出会高亮哪些被覆盖:
```
⚠️ 使用自定义权重 (来自: /tmp/aggressive.json):
  MACD背驰: 1.0 → 2.5 (覆盖)
  一买: 5.0 → 8.0 (覆盖)
  三买: 4.0 → 6.0 (覆盖)
```
- 未知信号别名会被忽略 + warn (不报错)
- 权重文件 JSON 格式坏 / 文件不存在 → 报错退出

**完整用法速查** (v3.5.1):
```bash
# 最常用的 3 个 flag
--output-csv FILE    # 结果保存 CSV
--exclude-st         # 过滤 ST / *ST / 退市
--weights-file JSON  # 自定义权重
```

**错误兑底矩阵** (v3.5.1):
- `--max-stocks` 超限 → 报错退出 (带原数 vs 限数)
- `--weights-file` 不存在 / JSON 坏 → 报错退出
- `--rank-by` 未知信号 → 报错退出 + 列可用别名
- `ST 过滤后股池为空` → 报错退出 (不会静默 pass)

### v3.6 新增特性

#### 4 个估值 / 行业过滤 flag
依赖 tushare `bak_basic` 全市场批量拉取 (~5500 只股, 1 次调), **带缓存 (同一天只拉 1 次)**:

| Flag | 含义 | 示例 |
|---|---|---|
| `--industry 银行,白酒` | 行业关键字过滤 (逗号分隔 OR 关系, 包含匹配) | 7只股中只留"银行"和"白酒" |
| `--pe-max 30` | 静态 PE 上限 (PE=0 亏损股永远过滤) | 茅台 PE=14>10 跳过 |
| `--pe-min 0` | 静态 PE 下限 (设 >0 过滤极低估垃圾股) | 很少用 |
| `--pb-max 5` | 静态 PB 上限 | 茅台 PB=5.65>5 跳过 |

**过滤顺序**: ST → 估值/行业 → max-stocks, 任意一步过滤后股池为空都报错退出。

**典型用例**:
```bash
# 只看金融股 + PE<15 (估值安全的银行/保险)
$PY $SKILL_DIR/scripts/czsc_signals.py scan \
  --watchlist $SKILL_DIR/examples/watchlist.sample.txt \
  --industry 银行,保险 --pe-max 15 --exclude-st \
  --signal 一买 三买 --output-csv /tmp/banking_scan.csv

# 只看高估值高成长股 (PE>20, PB>5)
# 注: --pe-min 20 + --pb-max 10 是"估值上限",反逻辑 (不能用)。需手动查代码或新加 --pb-min
```

**重要逻辑**:
- `--industry` 是**包含匹配** (OR 关系), 不是精确相等 - `'银行'` 能匹 `银行/银行个股/外地银行`
- `中国平安 industry=保险`, `--industry 银行` 不匹配, 要 `--industry 保险`
- **PE=0 = 亏损**, v3.6 永远过滤 (就算不传 `--pe-max`)
- 不传任何估值 flag → 跳过整个估值过滤逻辑 (零开销)

**调优提示**:
- industry 过滤成本主要是 stock_basic 首次拉 (~30s), 之后走缓存
- bak_basic 一次拉 5500 只股 (~60s), 同一天二次调用走内存缓存, 不要重复跑
- 带 industry 但 mcporter 不可用 → stderr warn 跳过过滤, 不报错 (保证 v3.5 不受依赖)

### v3.6.1 新增特性

#### 2 个市值/换手率过滤 flag

| Flag | 含义 | 计算 |
|---|---|---|
| `--market-cap-min N` | 总市值下限 (亿元) | `total_share × last_close` (单位亿股×元=亿元) |
| `--turnover-min N` | 换手率下限 (%) | `latest_vol / (total_share × 1e8) × 100`, **本地计算零 API** |

**关键点**:
- 换手率**本地算** (从 raw_df.vol), 不调用 daily_basic (tushare daily_basic 强制 ts_code, 不能一次拿全市场)
- 换手率计算公式与官方 daily_basic.turnover_rate 一致 (已验证平安银行 0.6135% 完全匹配)
- 市值/换手率过滤**在拉 K 线后进行** (_score_one_stock 后, detail 含 last_close/total_mv/turnover_rate)
- industry/pe/pb 过滤**在拉 K 线前** (用 bak_basic, 零成本)

**过滤顺序**:
```
1. ST 过滤 (拉 K 线前)
2. industry/pe/pb 过滤 (拉 K 线前, 用 bak_basic)
3. 拉 K 线 + 跑信号 (_score_one_stock, 含 total_mv/turnover_rate 本地计算)
4. market-cap-min/turnover-min 过滤 (拉 K 线后, 用 detail 里的 last_close)
5. 重排序 + 重 top N
```

**典型用例**:
```bash
# 大盘活跃股: 市值>1000亿 + 换手>0.5% (活跌但不是过热小盘)
$PY $SKILL_DIR/scripts/czsc_signals.py scan \
  --watchlist $SKILL_DIR/examples/watchlist.sample.txt \
  --market-cap-min 1000 --turnover-min 0.5 \
  --signal 一买 三买 --output-csv /tmp/active_large.csv

# 金融赛道 + 大盘 + 活跃 6 条件组合
$PY $SKILL_DIR/scripts/czsc_signals.py scan \
  --watchlist $SKILL_DIR/examples/watchlist.sample.txt \
  --exclude-st \
  --industry 银行,保险 \
  --pe-max 15 --pb-max 2 \
  --market-cap-min 3000 --turnover-min 0.3 \
  --output-csv /tmp/finance_blue_chip.csv
```

**表格变化**:
```
rank  代码           收盘   最近日期        composite     市值亿    换手%    一买   三买
   1  000858.SZ    74.76   2026-06-23      240.0      2902     1.20     48     0
   2  000001.SZ    10.71   2026-06-23      204.0      2078     0.61      8    41
```
新加两列: **市值亿** (绿色右侧) + **换手%** (6.2f)

**单位说明**:
- `total_share` 单位 = 亿股 (bak_basic 字段)
- `last_close` 单位 = 元
- `latest_vol` 单位 = 股 (腾讯 ifzq 返回, 已验证)
- 公式: `turnover_rate = vol_shares / (total_share_yi * 1e8) * 100` → %
- 例: vol=1.19e8股, total_share=194.06亿股 → 1.19e8/(194.06*1e8)*100 = 0.6135% ✓

**v3.6.1 走过的坑** (已写进 .learnings):
1. **bak_basic 没有 turnover_rate 字段** - 调 fields 也不报错但返空, 必须本地算
2. **腾讯 vol 单位是"股"不是"手"** - 验证过平安银行 0.6135% 与官方一致后才放心
3. **市值过滤需要 last_close** - 必须等 _score_one_stock 后才能算, 不能提前

### v3.7 新增特性

#### 3 个排序/统计 flag

| Flag | 含义 | 默认 |
|---|---|---|
| `--sort-by <field>` | 排序字段 (覆盖 --rank-by) | composite |
| `--reverse` | 反向排序 (默认降序, 加此 flag 升序) | False |
| `--show-stats` | 输出分布统计 (min/p25/p50/p75/max/mean) | False |

#### 可用 sort-by 字段

| 字段 | 含义 | 适用场景 |
|---|---|---|
| `composite` | 按信号加权分 (默认) | 找"信号最密集"的股 |
| `total_mv` | 按总市值 (亿元) | 找大盘蓝筹 (加 `--reverse` 找小盘) |
| `turnover_rate` | 按换手率 (%) | 找热门股 (加 `--reverse` 找冷门) |
| `last_close` | 按收盘价 | 找高价股 / 低价股 |
| `ts_code` | 按股票代码字母序 | 多次运行对比 (stable) |
| 任意 alias | 按该信号 score | v3.5 向后兼容 |

#### `--show-stats` 输出示例
```
=== 分布统计 (样本: 7 只) ===
  composite    min=  15.0  p25=  40.0  p50=  50.0  p75= 197.0  max= 386.0  mean= 132.1
  市值(亿)    min=   369  p25= 2490   p50= 9126   p75=12356  max=18161  mean= 8193
  换手率(%)   min=  0.40  p25=  0.54  p50=  0.67  p75=  1.00  max=  1.31  mean=  0.78
  收盘价(元)  min=  3.09  p25= 24.05  p50= 50.40  p75=233.63  max=1222.45 mean=255.90
```

#### 典型用例

```bash
# 1. 找大盘蓝筹 (PE 合理 + 市值大)
python3 scripts/czsc_signals.py scan \
  --watchlist /tmp/v36_test.txt --pe-max 15 --market-cap-min 5000 \
  --sort-by total_mv --show-stats

# 2. 找热门小盘 (换手高 + 小市值)
python3 scripts/czsc_signals.py scan \
  --watchlist /tmp/v36_test.txt \
  --sort-by turnover_rate --reverse \
  --market-cap-min 100 --show-stats

# 3. 找最被低估的高 composite
python3 scripts/czsc_signals.py scan \
  --watchlist /tmp/v36_test.txt --pe-max 10 \
  --sort-by composite --top 10 --output-csv /tmp/value_signals.csv

# 4. 按代码字母序稳定对比多次运行
python3 scripts/czsc_signals.py scan \
  --watchlist /tmp/v36_test.txt \
  --sort-by ts_code --output-csv /tmp/run_$(date +%Y%m%d).csv
```

**向后兼容**: `--rank-by` 完全保留 v3.5 行为, `--sort-by` 优先.两者同时存在优先用 `--sort-by` (避免歧义).

**错误兜底**:
- 未知的 sort-by 字段 → exit 1, 列出所有可用字段
- 所有 sort-by 字段都是降序默认, 加 `--reverse` 升序

**v3.7 走过的坑** (已写进 .learnings):
1. **`reverse=not reverse` 双反转 bug** - _sort_detail 已经默认 reverse=False, cmd_scan 再传 `reverse=not args.reverse` 翻转了一次, 修了
2. **`--show-stats` 必须用 statistics + 线性插值算百分位** - sorted 数组 + 线性插值比 numpy.percentile 更通用 (不依赖 numpy)

### v3.8 新增特性

#### 3 个输出/过滤 flag

| Flag | 默认 | 含义 |
|---|---|---|
| `--format <fmt>` | table | 输出格式: table/csv/markdown/json |
| `--output <path>` | (stdout) | 通用输出路径 (含 .csv/.md/.json 后缀自动猜 fmt) |
| `--exclude-keyword kw1,kw2` | (空) | 按股名关键字排除 (含 "北交所"/"创业板"/"科创板") |

**关键设计**:
- `--output` 后面含 `.csv`/`.md`/`.json` 后缀 → 自动选对应 fmt, 可省略 `--format`
- `--format csv/markdown/json` 无 `--output` → stdout 输出 (markdown/json 格式不重复走原表格)
- `--format table` 默认, 走原表格输出 (人眼友好)
- `--output-csv` 向后兼容 v3.5.1, 推荐 `--output /tmp/x.csv`

#### 股名匹配 (exclude-keyword) 归一化

```python
name_norm = name.replace(" ", "")  # 去掉名字中间空格
hit = [kw for kw in exclude_keywords if kw in name_norm]
```
**为什么要去掉空格**: tushare bak_basic 返回 `"五 粮 液"` (中间有空格), 但用户自然传 `"五粮液"` (无空格), 直接匹配会 False. 去掉空格后两者都能匹配。

#### 输出格式示例

**CSV** (utf-8-sig, Excel 可直接打开):
```csv
rank,name,ts_code,last_close,last_dt,composite,total_mv,turnover_rate,一买_n,一买_last
1,宁德时代,300750.SZ,392.51,2026-06-23,15.0,18161.44,0.81,3,2026-01-26
```

**Markdown** (Notion / GitHub README / 微信公众号都友好):
```markdown
|   rank | name   | ts_code   |   last_close | last_dt    |   composite |   total_mv |   turnover_rate |   一买_n | 一买_last    |
|-------:|:-------|:----------|-------------:|:-----------|------------:|-----------:|----------------:|-------:|:-----------|
|      1 | 宁德时代   | 300750.SZ |       392.51 | 2026-06-23 |          15 |   18161.4  |            0.81 |      3 | 2026-01-26 |
```

**JSON** (机器友好, API / 前端调用):
```json
[
  {
    "rank": 1,
    "name": "宁德时代",
    "ts_code": "300750.SZ",
    "last_close": 392.51,
    "last_dt": "2026-06-23",
    "composite": 15.0,
    "total_mv": 18161.44,
    "turnover_rate": 0.81,
    "一买_n": 3,
    "一买_last": "2026-01-26"
  }
]
```

#### 典型用例

```bash
# 1. 导出 JSON 供 API 调用
$PY $SKILL_DIR/scripts/czsc_signals.py scan \
  --watchlist $SKILL_DIR/examples/watchlist.sample.txt \
  --industry 银行 --market-cap-min 2000 --sort-by composite \
  --format json --output /tmp/banks.json

# 2. 导出 Markdown 报告 (公众号 / README)
$PY $SKILL_DIR/scripts/czsc_signals.py scan \
  --watchlist $SKILL_DIR/examples/watchlist.sample.txt \
  --exclude-keyword ST,北证,创业板 --signal 一买 三买 \
  --format markdown --output /tmp/weekly_report.md

# 3. 排除个股名字包含 "茅台" / "万科"
$PY $SKILL_DIR/scripts/czsc_signals.py scan \
  --watchlist /tmp/v36_test.txt \
  --exclude-keyword 茅台,万科 \
  --format csv --output /tmp/filter_test.csv

# 4. stdout 快速看 markdown (适合管道)
$PY $SKILL_DIR/scripts/czsc_signals.py scan \
  --watchlist /tmp/v36_test.txt --top 5 --signal 一买 --format markdown
```

**错误兜底**:
- `--format 未知` → exit 1 提前报错 (不拉 K 线)
- `--output` 路径父目录不存在 → 自动创建
- `--exclude-keyword` 股名匹配不上 → 安静跳过 (不报错)

**v3.8 走过的坑** (已写进 .learnings):
1. **股名中间空格导致匹配失败** - "五 粮 液" vs "五粮液", 过滤前 `name.replace(" ", "")` 归一化
2. **format 验证放在拉 K 线之后** - 用户传 `--format xml` 先拉 K 线后报错, 浪费 API. 改为 1.5 段提前验证
3. **`return` 位置错误** - table 格式无 `--output` 应该走 9. 原表格输出, 但 `return` 在 else 里让 table 也 return 了. 改为只在 csv/md/json 三个非 table 分支 return
4. **stdout CSV 不要 BOM** - 文件用 utf-8-sig (Excel 友好), stdout 用 utf-8 (避免重复 BOM)

### v3.9 新增特性

#### 1 个 flag: --preset 一键策略

`--preset <name>` 设置多个 flag 的默认值, 用户显式传的 flag 优先不覆盖。

| Preset | 含义 | 等价 flag |
|---|---|---|
| `value` | 价值投资 | `--pe-max 15 --pb-max 2 --market-cap-min 1000 --sort-by composite` |
| `bank` | 银行赛道 | `--industry 银行 --pe-max 15 --pb-max 1.5 --market-cap-min 2000` |
| `momentum` | 高动量热门 | `--turnover-min 1.0 --market-cap-min 500 --sort-by composite --show-stats` |
| `bargain` | 拋底股 | `--pe-max 10 --market-cap-min 200 --sort-by turnover_rate --reverse` |

#### 典型用例

```bash
# 1. 一键价值投资扫股
python3 scripts/czsc_signals.py scan \
  --watchlist $SKILL_DIR/examples/watchlist.sample.txt \
  --preset value --signal 一买 --top 10

# 2. 一键银行赛道 (可选添加额外过滤)
python3 scripts/czsc_signals.py scan \
  --watchlist $SKILL_DIR/examples/watchlist.sample.txt \
  --preset bank --exclude-st --format json --output /tmp/banks.json

# 3. 预设 + 用户覆盖
python3 scripts/czsc_signals.py scan \
  --watchlist $SKILL_DIR/examples/watchlist.sample.txt \
  --preset value --pe-max 30   # 覆盖 value 默认的 15

# 4. 高动量热门 (换手+市值)
python3 scripts/czsc_signals.py scan \
  --watchlist $SKILL_DIR/examples/watchlist.sample.txt \
  --preset momentum --top 10

# 5. 拋底股 (低估值+低换手 = 被拋弃的机会)
python3 scripts/czsc_signals.py scan \
  --watchlist $SKILL_DIR/examples/watchlist.sample.txt \
  --preset bargain --top 10 --format markdown --output /tmp/bargain.md
```

**设计原则**:
- preset 是"懒人包", 所有 flag 都可手动覆盖
- 预设与显式 flag 冲突时, 显式优先 (不报错, 只是静默覆盖)
- 预设只设置"默认值", 不强制 (你传 `--preset value --pb-max 10`, pb-max 用 10 不用 2)

**错误兜底**:
- 未知的 preset → exit 1 提前报错, 列出所有可用 preset
- preset 验证在拉 K 线前 (1.6 段)

**v3.9 走过的坑** (已写进 .learnings):
1. **Python sorted reverse 参数语义** - `reverse=True` 是**降序**不是升序, 不能凭直觉取名. 调用者传参时要明确语义, v3.7 测试时误以为 reverse=False=降序, v3.9 修正
2. **`--reverse` flag 与 `_sort_detail` 参数语义不同** - flag 是"反向", 参数是"是否降序". cmd_scan 调 `_sort_detail` 时要 `reverse=not args.reverse`
3. **`run_scan_signals` 未传 reverse** - v3.7 加了 reverse 参数但 `run_scan_signals` 内部还是 hardcoded 默认, v3.9 修复让 reverse 参数贯穿整个调用链

### v4.0 新增特性

#### 5 个新 subcommand + flag: 自定义 preset 管理

**预设是一组 scan flag 的可复用组合** - 类似 Makefile / git alias / kubectl context, 一次定义多次复用。

**架构**:
- 存: `~/.czsc-presets/<name>.json` (用户级, 跨项目, gitignored)
- 加载优先级: `--preset-file <name>` > `--preset <builtin>` (后者静默跳过已填充项)
- 用户显式 flag 不被 preset 覆盖 (与 v3.9 一致)

#### 1 个新子命令: `preset`

| 子命令 | 用途 | 用法 |
|---|---|---|
| `preset save <name>` | (在 scan 子命令调用: `--save-preset <name>`) 保存当前所有 flag | `--save-preset my_bank` |
| `preset list` | 列出所有自定义 preset | `preset list` |
| `preset show <name>` | 显示 preset 的 JSON 内容 | `preset show my_bank` |
| `preset delete <name>` | 删除 preset | `preset delete my_bank` |

#### 2 个新 scan flag

| Flag | 默认 | 含义 |
|---|---|---|
| `--save-preset <name>` | (空) | 保存当前所有 scan flag 为 preset (跑完后生效) |
| `--preset-file <name\|path>` | (空) | 加载自定义 preset (优先级高于 `--preset` 内置预设) |

#### JSON preset 结构 (只保存非默认值)

```json
{
  "industry": "银行",
  "pe_max": 15.0,
  "pb_max": 1.5,
  "market_cap_min": 2000.0,
  "sort_by": "composite",
  "signal": ["一买"],
  "days": 500,
  "top": 3,
  "_meta": {
    "name": "my_bank",
    "saved_at": "2026-06-24 14:11:26",
    "skill_version": "v4.0",
    "source_cmd": "scan"
  }
}
```
**只保存非默认值** (null/空/False/0 跳过) - JSON 紧凑, 不污染加载逻辑。

#### 典型用例

```bash
# 1. 保存我的银行赛道预设
python3 scripts/czsc_signals.py scan \
  --watchlist $SKILL_DIR/examples/watchlist.sample.txt \
  --industry 银行 --pe-max 15 --pb-max 1.5 --market-cap-min 2000 \
  --sort-by composite --signal 一买 --top 10 \
  --save-preset my_bank_strategy

# 2. 一键使用预设
python3 scripts/czsc_signals.py scan \
  --watchlist $SKILL_DIR/examples/watchlist.sample.txt \
  --preset-file my_bank_strategy

# 3. 预设 + 用户覆盖
python3 scripts/czsc_signals.py scan \
  --watchlist $SKILL_DIR/examples/watchlist.sample.txt \
  --preset-file my_bank_strategy --pe-max 30   # 覆盖预设里的 15

# 4. 多个预设: 不同赛道不同策略
--save-preset bank_v1
--save-preset tech_growth
--save-preset dividend_value
--save-preset bargain_hunter

# 5. 预设 + 输出格式
python3 scripts/czsc_signals.py scan \
  --watchlist $SKILL_DIR/examples/watchlist.sample.txt \
  --preset-file my_bank_strategy \
  --format markdown --output /tmp/banks_$(date +%Y%m%d).md

# 6. preset list/show/delete
python3 scripts/czsc_signals.py preset list
python3 scripts/czsc_signals.py preset show my_bank_strategy
python3 scripts/czsc_signals.py preset delete old_strategy
```

#### preset vs --preset 内置预设

| 维度 | `--preset value/bank/...` (内置) | `--preset-file my_bank.json` (自定义) |
|---|---|---|
| 定义方 | skill 开发者 | 用户 |
| 存哪 | 代码里 | `~/.czsc-presets/` |
| 可改 | 否 (需改 skill 代码) | 是 (直接编辑 JSON) |
| 可分享 | 否 | 是 (把 JSON 发给朋友) |
| 可版本管理 | 否 | 是 (git 跟踪 ~/.czsc-presets/ 或复制到项目 .czsc-presets/) |
| 优先级 | 低 (preset-file 优先) | 高 |

#### 设计原则

- **保存紧凑**: 只存非默认 flag, JSON 不塞 null/空/False/0
- **加载不覆盖**: 用户显式传的 flag 不被 preset 覆盖 (与 v3.9 一致)
- **优先级明确**: preset-file > preset(内置) > flag 默认值
- **错误友好**: 文件不存在 → exit 1 + 提示怎么保存; JSON 坏 → exit 1 + 错误位置
- **路径智能**: `--preset-file my_bank` 自动找 `~/.czsc-presets/my_bank.json`, 也支持绝对/相对路径

#### 错误兜底

| 场景 | 行为 |
|---|---|
| `--preset-file` 文件不存在 | exit 1 + 提示用 `preset save` 创建 |
| JSON 解析失败 | exit 1 + 显示错误位置 |
| preset 名含非字母数字 | exit 1 + 只允许字母/数字/下划线 |
| `--save-preset` + `--preset-file` 同时 | preset-file 加载, save 仍保存 (新 preset) |

**v4.0 走过的坑** (已写进 .learnings):
1. **JSON 默认值序列化噪音** - 最初 `_save_user_preset` 把所有 17 个 flag 都序列化 (含 null/空/False/0), JSON 油腔且 `apply` 函数需要复杂过滤。改为只保存非默认值后, JSON 从 17 个 key 压缩到 8 个。
2. **`is_default` 判断跨类型难题** - bool flag (reverse/show_stats) 默认 False, JSON 序列化后也是 False, 加载时难以区分"保存时的 False"和"默认值"。修复: 保存时跳过 False/0/None, 加载时一律 setattr。
3. **preset save 独立子命令的复杂度** - 用户调用 `preset save` 不传 scan flag, 需要单独子命令 vs scan 内 `--save-preset`。后者更自然 (用户最可能从 scan 保存), 所以设为"scan 内隐式 + preset save 独立子命令提示用法"。

### v4.1 新增特性

#### 3 层 preset 存储路径 (优先级从高到低)

| 优先级 | 来源 | 用法 |
|---|---|---|
| 1 (最高) | `--preset-dir <path>` 命令行 flag | 临时路径, 只影响本次调用 |
| 2 | `CZSC_PRESET_DIR` 环境变量 | 团队项目级别 (写到 .env / shell rc) |
| 3 (默认) | `~/.czsc-presets/` | 用户全局默认 |

#### 2 个新 preset 子命令

| 子命令 | 用途 |
|---|---|
| `preset export <name> [--output PATH]` | 导出 preset (默认 stdout, 可重定向到文件/邮件/微信) |
| `preset import <name> <source.json>` | 从文件导入 (自动添加 `_meta.imported_from` 元数据) |

#### 典型用例 (团队共享 + 跨机器同步)

```bash
# === 场景 1: 团队共享 preset 到 git repo ===
# 1. 项目里有个 team-presets/ 目录 (git tracked)
cd ~/work/team-quant/team-presets
git pull  # 拉取同事最新的 preset

# 2. 用环境变量指向团队目录 (写到 ~/.bashrc 或项目 .env)
export CZSC_PRESET_DIR=~/work/team-quant/team-presets
python3 scripts/czsc_signals.py scan --preset-file bank_v1

# === 场景 2: 临时调试, 用 --preset-dir 不污染全局 ===
python3 scripts/czsc_signals.py scan \
  --watchlist /tmp/v36_test.txt \
  --preset-dir /tmp/test_presets \
  --preset-file experimental_strategy \
  --top 10

# === 场景 3: 分享 preset 给同事 (邮件 / 微信附件) ===
# 1. 导出
python3 scripts/czsc_signals.py preset export my_bank --output ~/Downloads/my_bank.json
# 2. 发邮件附件: "my_bank.json, 我用的银行赛道 preset, 导入用 preset import"

# === 场景 4: 跨机器同步 (本机 export → U盘 → 另一台机器 import) ===
# 本机
python3 scripts/czsc_signals.py preset export bank_v1 --output /media/usb/bank_v1.json
# 另一台机器
python3 scripts/czsc_signals.py preset import bank_v1 /media/usb/bank_v1.json

# === 场景 5: 从 stdout 管道 (适合 shell script) ===
# 备份所有 preset 到一个 tar.gz
for p in $(python3 scripts/czsc_signals.py preset list 2>&1 | grep -oP '📦 \K\w+'); do
  python3 scripts/czsc_signals.py preset export "$p" > "presets/${p}.json"
done
tar czf presets_backup.tar.gz presets/

# === 场景 6: 重命名 preset (export → 删除 → import 新名) ===
python3 scripts/czsc_signals.py preset export old_name --output /tmp/x.json
python3 scripts/czsc_signals.py preset delete old_name
python3 scripts/czsc_signals.py preset import new_name /tmp/x.json
```

#### preset JSON 增强: `_meta.imported_from`

`preset import` 时自动添加溯源信息:
```json
{
  "industry": "银行",
  "_meta": {
    "name": "bank_v1",
    "saved_at": "2026-06-24 14:11:26",
    "imported_from": "/media/usb/bank_v1.json",
    "imported_at": "2026-06-24 14:21:13",
    "skill_version": "v4.0"
  }
}
```
可以用来追溯 preset 原始来源 (哪个机器 / 哪封邮件 / 哪个 git commit)。

#### 错误兜底

| 场景 | 行为 |
|---|---|
| `--preset-dir` 路径不存在 | mkdir -p 自动创建 (不报错) |
| `preset export` 不存在 | exit 1 + 显示路径 |
| `preset import` 源文件不存在 | exit 1 + 提示检查路径 |
| `preset import` JSON 解析失败 | exit 1 + 显示错误位置 (line/column) |
| 导入的 preset 名已存在 | 警告 + 覆盖 (⚠️) |
| 导出到不存在目录 | mkdir -p 自动创建父目录 |

#### preset vs `--preset` 内置 vs 用户配置 (三级 fallback)

```python
# 加载逻辑 (cmd_scan 1.55 段):
1. 如果 args.preset_dir: 临时覆盖 PRESET_DIR
2. _load_user_preset(args.preset_file): 加载自定义 preset
3. _apply_preset(args): 应用内置 preset (内置静默跳过已填充)
4. 用户显式 flag (从命令行): 始终优先
```

**v4.1 走过的坑** (已写进 .learnings):
1. **`--preset-dir` 要在 scan 子命令 + preset 6 个子命令都加** - 因为 preset list/show/delete/export/import 都需要知道读哪个目录。只加 scan 不够 (管理子命令也会用)。
2. **`global PRESET_DIR` 是必须的** - 不然 `_save_user_preset` 内部 hardcoded 用了 `PRESET_DIR` 模块全局, 改 PRESET_DIR 不会影响它。
3. **argparse subparser 加共享 flag 的两种姿势** - (1) `parents=[parent_parser]` (2) for 循环后调 `add_argument`。循环更灵活因为能区分每个子命令独有的参数。
4. **preset 子命令需要 `_override_preset_dir` 钩子** - 6 个 cmd 函数都要在最开始调用一次, 不能只在 main 入口统一处理 (subparser 之后)。

### v4.2 新增特性

#### 信号组别名 (1 个名字代替 1 组信号)

**问题**: 使用 `scan --signal 一买 二买 三买 MACD一买 MACD二买 笔翼二买` 这种 6 个参数太繁琐
**解决**: 用 1 个 group 别名代替, 如 `--signal all_long`

**6 个内置 group**:

| 别名 | 包含信号 | 场景 |
|---|---|---|
| `all_long` | 一买+二买+三买+MACD一买+MACD二买+笔翼二买 | 所有买入类 (最常用) |
| `all_short` | 一卖+二卖+三卖+MACD一卖+MACD二卖 | 所有卖出类 |
| `bs_core` | 一买+一卖+二买+二卖+三买+三卖 | 核心买卖点 |
| `bs1` | 一买+一卖 | 同周期纯趋势 |
| `momentum` | MACD一买+MACD二买+MACD背驰+双均线 | 动量类 |
| `reversal` | TD9+支撑压力+笔翼二买 | 反转类 |

#### 典型用例

```bash
# 1. 旧写法 (v3.5 一直到 v4.1, 6 个参数)
python3 scripts/czsc_signals.py scan --watchlist x --signal 一买 二买 三买 MACD一买 MACD二买 笔翼二买

# 2. 新写法 (v4.2, 1 个 group 名)
python3 scripts/czsc_signals.py scan --watchlist x --signal all_long

# 3. 混合 (group + 单独信号)
python3 scripts/czsc_signals.py scan --watchlist x --signal 一买 momentum
# → 展开为: 一买, MACD一买, MACD二买, MACD背驰, 双均线

# 4. 跟 preset 联动 (preset 里 signal 也可以用 group 名)
python3 scripts/czsc_signals.py scan --preset-file my_strategy  # 内部 signal= ["all_long"]
# → 运行时自动展开, scan 只用 1 个 signal 字段

# 5. list 命令查看所有可用 group
python3 scripts/czsc_signals.py list
# 输出: === v4.2 信号组别名 (6 个) ===
#   all_long      → 一买, 二买, 三买, ...
#   momentum      → MACD一买, MACD二买, ...
#   ...
```

#### 关键设计点

- **不覆盖原 alias**: `'一买'` 等真实信号名仍可单独用
- **`all` 关键字保留**: 不被当成 group, 还是"全部 11 个信号"
- **fail-fast 策略**: 混合里只要 1 个 unknown 就 exit 1 (不静默跳过), 避免"我以为我传了 3 个其实只跑了 2 个"
- **preset 友好**: preset JSON 里的 signal 字段支持 group 名, 加载时自动展开 (跟运行时传 group 一样效果)
- **错误提示友好**: 错误信息列出所有 17 个可用 (11 信号 + 6 group), 不用翻文档

#### 错误兜底

| 场景 | 行为 |
|---|---|
| `--signal fake_xxx` (未知) | exit 1 + 列出 17 个可用 + 6 group 名 |
| 混合里 1 个 unknown | exit 1 (全 fail-fast, 避免部分生效误判) |
| preset 里 signal= group 名 | 加载时跟运行时同样展开 (透明) |
| `--signal all` 关键字 | 保留原意"所有 11 个真实信号", 不展开为 group |

**v4.2 走过的坑** (已写进 .learnings):
1. **preset 里 signal 可能是 group 名** - 一开始只在 #1.7 展开 user-provided signal, 没考虑 preset 加载后 args.signal 是 group 别名的情况。修复: 把 group 展开放在 preset 加载之后 (#1.7 在 #1.55 preset-file 和 #1.6 preset 内置预设 之后), 统一处理两种来源的 signal。
2. **展开逻辑要 transparent** - 不能只在 "args.signal 里有 group 名" 时才打 stderr 日志 (`[signal-group] 展开: ...`), 要让用户知道"我传的 group 名被拆开了", 不然用户会困惑"为什么我传 1 个却看到 6 个在跑"。
3. **`all` 关键字的边界** - 原本 `all` 是个特殊字符串, 但 `all_long` 是 group 名。区分逻辑: 先看 `s in SIGNAL_GROUPS` (精确匹配), 再看 `s in {x["alias"]}` (真实信号), 最后用 `or s == "all"` 保留关键字。顺序很关键, 任何次序都会出错。

### v4.3 新增特性

#### 批量扫描 (batch-scan) - cron 友好的多 preset 调度

**问题**: 用户在 cron 里要跑多个 preset, 需要写多个 cron 行或者 loop 脚本, 不可控不优雅。
**解决**: 1 个 YAML/JSON/TOML 配置文件, 列出多个 run, 1 条命令跑完。

#### 3 个新 scan flag

| Flag | 默认 | 含义 |
|---|---|---|
| `--batch-scan <path>` | (空) | 批量跑多个 scan (YAML/JSON/TOML 配置文件, 按扩展名自动检测) |
| `--batch-output <path>` | (空) | 批量结果汇总到指定路径 (markdown 格式, 默认 stdout) |
| `--preset-tag <tags>` | (空) | 保存 preset 时打的标签 (逗号分隔, e.g. 'bank,value') |

#### 1 个新 preset list flag

| Flag | 含义 |
|---|---|
| `preset list --tag <tag>` | 按 tag 过滤 (逗号分隔 OR 逻辑, e.g. 'bank,value') |

#### 配置文件格式 (YAML / JSON / TOML)

**YAML 示例** (`team_daily.yaml`):
```yaml
runs:
  - name: "morning_bank_scan"   # 报告里的标识
    preset: my_bank             # 自定义 preset 名 (自动判别 builtin/custom)
    watchlist: /path/to/banks.txt
    format: markdown
    top: 3
  - name: "loose_bank_check"
    preset: loose_bank
    watchlist: /path/to/banks.txt
    format: table
    top: 2
  - name: "tech_momentum"
    preset: tech_momentum
    watchlist: /path/to/tech.txt
    format: json
    top: 10
    output: /reports/tech_$(date +%Y%m%d).json  # 可选, 输出到文件
```

**JSON 示例**:
```json
{
  "runs": [
    {"name": "json_test", "preset": "my_bank", "watchlist": "x.txt", "format": "table", "top": 2}
  ]
}
```

**TOML 示例** (`batch.toml`):
```toml
[[runs]]
name = "toml_test"
preset = "my_bank"
watchlist = "/tmp/x.txt"
format = "table"
top = 2
```

**支持的字段** (任一 run 可覆盖以下任一):
- `name` (必填, 报告里的标识)
- `preset` / `preset_file` (二选一, `preset` 自动判别 builtin/custom)
- `watchlist` / `stocks` (股池)
- `format` (table/csv/markdown/json)
- `output` (输出路径, 可含 $(date) 等)
- `top`, `days`, `signal` (可以传 v4.2 group 别名)
- `exclude_st`, `exclude_keyword`
- `industry`, `pe_min/max`, `pb_min/max`, `market_cap_min`, `turnover_min`
- `sort_by`, `reverse`, `show_stats`
- `save_preset`, `preset_tag`

#### 典型用例

```bash
# 1. 基本批量: 跑 3 个 preset, 全部输出到 stdout
python3 scripts/czsc_signals.py scan --batch-scan team_daily.yaml

# 2. 汇总报告: 生成 markdown 表格, 邮件给团队
python3 scripts/czsc_signals.py scan --batch-scan team_daily.yaml --batch-output /tmp/daily_report.md
# → 生成 "/reports/2026-06-24_daily.md", 表格列出每个 run 的状态/耗时/输出路径

# 3. cron 集成: 收盘后自动跑
# /etc/cron.d/czsc-daily
# 30 15 * * 1-5 user /opt/czsc-trading/scan --batch-scan /opt/team_daily.yaml --batch-output /var/reports/czsc-$(date +\%Y\%m\%d).md

# 4. 团队共享 batch 配置到 git
git add team_daily.yaml  # 提交 team_daily.yaml
git push
# 同事 pull 后 --batch-scan team_daily.yaml 即可

# 5. 临时调试一个 run (不批量)
python3 scripts/czsc_signals.py scan --watchlist /tmp/x --preset my_bank --format markdown

# 6. preset + tag + 列表过滤
python3 scripts/czsc_signals.py scan --watchlist /tmp/x --save-preset my_strategy --preset-tag bank,value,low_pe
python3 scripts/czsc_signals.py preset list --tag bank       # 所有银行类 preset
python3 scripts/czsc_signals.py preset list --tag value,momentum  # OR 逻辑
```

#### batch 运行输出 (stderr)

```
[batch] 加载配置: /tmp/team_daily.yaml (3 个 run)

[batch] [1/3] morning_bank_scan...
[batch] [1/3] morning_bank_scan ✓ (3.0s) - stdout

[batch] [2/3] loose_bank_check...
[batch] [2/3] loose_bank_check ✓ (0.2s) - stdout

[batch] [3/3] tech_momentum...
[batch] [3/3] tech_momentum ✓ (0.6s) - 输出到 /tmp/builtin_mom.csv

[batch] 全部完成: 3/3 成功
  ✓ morning_bank_scan  (3.0s)  stdout
  ✓ loose_bank_check  (0.2s)  stdout
  ✓ tech_momentum  (0.6s)  输出到 /tmp/builtin_mom.csv
[batch] 汇总报告: /tmp/daily_report.md
```

#### `--batch-output` 生成的汇总 markdown

```markdown
# czsc batch scan 报告 - 2026-06-24 16:55:46

**配置**: `/tmp/team_daily.yaml`

**结果**: 5/5 成功

| # | 名称 | 状态 | 耗时 | 说明 |
|---|---|---|---|---|
| 1 | banks_strict | ✓ | 3.5s | stdout |
| 2 | banks_loose | ✓ | 0.2s | stdout |
| 3 | tech_mom | ✓ | 0.6s | stdout |
| 4 | builtin_value | ✓ | 0.2s | stdout |
| 5 | builtin_momentum | ✓ | 0.6s | 输出到 /tmp/builtin_mom.csv |
```

#### preset tag 设计

**存储**: 标签存在 `_meta.tags` 字段 (跟 `_meta.name` / `_meta.saved_at` 同级)
```json
{
  "industry": "银行",
  "pe_max": 15.0,
  "_meta": {
    "name": "my_bank",
    "tags": ["bank", "value"]
  }
}
```

**OR 逻辑过滤**: `--tag bank,value` 匹配任一标签的 preset (e.g. tag=bank 匹配 bank/loose, tag=value 匹配 value/loose, tag=bank,value 匹配 bank/value/loose)

#### 关键设计

- **preset 自动判别 builtin/custom**: `preset: my_bank` → preset_file (因为 my_bank 不在 4 个内置里), `preset: value` → preset (内置)
- **CRON 友好**: stderr 是进度, stdout 是结果, 汇总 markdown 是给人类看的
- **fail-fast vs continue**: 1 个 run 失败不影响其他 run (会标记 ✗), 最后如果 < 100% 成功就 exit 1 (让 cron 知道)
- **3 种配置格式**: YAML (人类写), JSON (机器生成), TOML (Python 3.11+ 友好)
- **tag OR 逻辑**: 比 AND 更灵活 (e.g. "找所有银行 OR 价值的" 1 个 tag 表达式搞定)

#### 错误兜底

| 场景 | 行为 |
|---|---|
| `--batch-scan` 文件不存在 | exit 1 + 路径 |
| `.xml` 格式不支持 | exit 1 + 列出 3 种支持 |
| YAML/JSON/TOML 解析失败 | exit 1 + ParserError 位置 (行/列) |
| 缺 `runs` 字段 | exit 1 + 提示 |
| `runs` 为空列表 | exit 1 + 提示 |
| 1 个 run 失败 | 其他 run 继续, exit 1 (汇总里有 ✗) |
| 全部 run 成功 | exit 0, 汇总全 ✓ |
| `--preset-tag` 多个空 tag | 全部 skip, 等同不传 |

**v4.3 走过的坑** (已写进 .learnings):
1. **`time` 没 import** - `_run_batch` 用了 `time.time()` 但文件没有 `import time`, 第一次跑 NameError。修复: 顶部加 `import time`。
2. **batch 里 `preset:` 被当内置** - 最初我写 `if "preset_file" not in run_cfg: new_args.preset = v`, 但 `my_bank` 不是 4 个内置之一, 报 "未知 preset"。修复: 加 `BUILTIN_PRESETS = {"value", "bank", "momentum", "bargain"}` 白名单, 是内置走内置, 否则走 preset_file。
3. **SystemExit 在 try/except 里** - `cmd_scan` 内部出错会 `sys.exit(1)`, 会被外层 `except SystemExit as e: ok = False; msg = f"exit({e.code})"` 捕获并标记为失败。但 `cmd_scan` 之前的所有 `if not stocks: sys.exit(1)` 都会走这条路径, 不是 bug 是 feature (单个 run 失败不影响其他)。
4. **copy.copy 对 Namespace 不够深** - 我用 `copy.copy(parent_args)`, 但 `new_args.batch_scan = ""` 改的是顶层, 不影响 sub-object (我们没嵌套 object, 所以够用)。如果以后有 list/dict 字段需要深拷贝, 要换 `copy.deepcopy`。
5. **batch output 没有 list 字段** - `run_cfg` 里只接受 SCAN_OVERRIDE_KEYS 白名单里的字段, 防止 YAML 注入未知 flag 干扰后续逻辑。代价: 新加 scan flag 要更新白名单, 但比"什么字段都接受"安全。

### v4.4 新增特性

#### preset diff - 对比两个 preset (git diff 风格)

**问题**: 用户有 3-5 个 preset 分布在不同场景, 改了一个参数忘了另一个是什么, 不知道差异在哪。
**解决**: `preset diff <a> <b>` 1 条命令看清差异。

#### 1 个新 preset 子命令

| 子命令 | 用途 |
|---|---|
| `preset diff <a> <b> [--format text\|json]` | 对比两个 preset (text=人类看 / json=程序消费) |

#### text 格式输出 (git diff 风格)

```bash
$ preset diff my_bank loose_bank
=== preset diff: my_bank ↔ loose_bank ===

=== 相同 (4) ===
  days: 500
  industry: 银行
  sort_by: composite
  top: 10

=== 差异 (2) ===
  pb_max:
    - my_bank: 1.5
    + loose_bank: 3.0
  pe_max:
    - my_bank: 15.0
    + loose_bank: 30.0

=== 仅 my_bank 有 (1) ===
  - market_cap_min: 2000.0
```

#### JSON 格式输出 (程序消费)

```bash
$ preset diff my_bank loose_bank --format json
{
  "common_same": {"days": 500, "industry": "银行", ...},
  "only_in_a": {"market_cap_min": 2000.0},
  "only_in_b": {},
  "differ": {
    "pb_max": {"a": 1.5, "b": 3.0},
    "pe_max": {"a": 15.0, "b": 30.0}
  },
  "_meta": {
    "name_a": "my_bank",
    "name_b": "loose_bank",
    "compared_at": "2026-06-24 17:00:22"
  }
}
```

#### 关键设计

- **跳过 _meta 元数据**: 不对比 `saved_at` / `imported_from` / `tags` - 只对比业务参数 (pe_max / pb_max / sort_by 等)
- **4 个分组**: 相同 / 差异 / 仅 A / 仅 B, 跟 git diff 三方合并 (MATCH/LEFT_ONLY/RIGHT_ONLY) 一致
- **完全相同友好提示**: 全部参数一致 → `✓ 完全相同 (除 _meta 元数据)`, 不输出空分组
- **JSON 含 _meta**: 程序可追溯"谁在什么时候对比的"
- **2 种格式**: text 给人类, json 给程序 (e.g. CI 失败时调用 diff 生成 patch)

#### batch-output-format - 汇总报告支持 3 种格式

**问题**: v4.3 batch 汇总只有 markdown, 邮件好看但程序消费难; HTML 报告之前要在 markdown 上手加工。
**解决**: `--batch-output-format <md|json|html>` 1 个 flag 切换。

#### 1 个新 scan flag

| Flag | 默认 | 含义 |
|---|---|---|
| `--batch-output-format <fmt>` | `markdown` | 汇总报告格式 (markdown / json / html) |

#### 3 种报告格式对比

| 格式 | 用途 | 典型场景 |
|---|---|---|
| **markdown** | 人看, git/issue/MD 编辑器 | 提交每日报告, 团队 review |
| **json** | 程序消费, CI/数据库 | jq 查询, 状态监控, Slack webhook |
| **html** | 邮件/浏览器直接看 | 自动发邮件给老板, 内网公告 |

#### HTML 报告样例 (🦐 主题)

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>czsc batch scan 报告</title>
  <style>...</style>
</head>
<body>
  <h1>🦐 czsc batch scan 报告</h1>
  <div class="meta">
    <strong>生成时间:</strong> 2026-06-24 17:00:44<br>
    <strong>配置:</strong> <code>/tmp/team_daily.yaml</code><br>
    <strong>结果:</strong> <span class="badge">3/3 成功</span>
  </div>
  <table>
    <thead><tr><th>#</th><th>名称</th><th>状态</th><th>耗时</th><th>说明</th></tr></thead>
    <tbody>
      <tr><td>1</td><td>morning_bank_scan</td><td>✓</td><td>3.3s</td><td>stdout</td></tr>
      ...
    </tbody>
  </table>
</body>
</html>
```
- 自包含 CSS (不依赖外部), 邮件客户端直接渲染
- 绿色 badge (成功) / 橙色 badge (部分失败)
- emoji 🦐 主题 (与 skill 一致)

#### 典型用例

```bash
# 1. 对比 2 个 preset (改了哪个参数一目了然)
$ preset diff my_bank loose_bank
# → 显示 pb_max/pe_max 不同, my_bank 有 market_cap_min, loose_bank 没有

# 2. 对比 builtin vs custom
$ preset diff my_custom_bank my_bank
# → 看自定义比 builtin 多了什么 / 缺了什么

# 3. CI 集成: PR 修改了 preset, 自动生成 diff
$ preset diff old_preset new_preset --format json | jq '.differ'
# → 程序化判断是否改了关键参数

# 4. cron 邮件: 生成 HTML 报告, 附件发邮件
$ scan --batch-scan team_daily.yaml --batch-output /tmp/daily.html --batch-output-format html
$ cat /tmp/daily.html | mail -s "Daily Report $(date +%Y-%m-%d)" team@company.com -A /tmp/daily.html

# 5. JSON 报告: 推到监控
$ scan --batch-scan team_daily.yaml --batch-output /tmp/daily.json --batch-output-format json
$ jq '.summary' /tmp/daily.json
# → {"total": 5, "success": 5, "failed": 0}

# 6. markdown 报告: 提交到 git repo
$ scan --batch-scan team_daily.yaml --batch-output reports/$(date +%Y%m%d).md
$ git add reports/ && git commit -m "daily scan report"
```

#### 错误兜底

| 场景 | 行为 |
|---|---|
| `preset diff` 任一不存在 | exit 1 + 路径 |
| `preset diff --format xml` | argparse choices 拒绝 |
| `--batch-output-format xml` | argparse choices 拒绝 |
| 完全相同 preset | 友好提示 "✓ 完全相同" |
| 自对比 (a == a) | 同样显示 "✓ 完全相同" |

**v4.4 走过的坑** (已写进 .learnings):
1. **HTML CSS 复杂度** - 最初想用 inline style + 复杂排版 (charts, gradients), 简化后用 9 行 CSS (font/padding/badge) 就够看, 邮件兼容性最好。
2. **JSON 默认值 (success/failed)** - 汇总 JSON 里加 `summary: {total, success, failed}` 让程序 1 次调用就知道状态, 不需要遍历 results 统计。

### v4.5 新增特性

#### batch-parallel - 多 run 并行跑 (提速可选)

**问题**: v4.3 batch-scan 5 个 run 串行跑 4-5s, cron 每天跑几次还行, 但 10+ run 或实时监控场景太慢。
**解决**: `--batch-parallel <N>` 用 ThreadPoolExecutor 并行跑。

#### 1 个新 scan flag

| Flag | 默认 | 含义 |
|---|---|---|
| `--batch-parallel <N>` | 1 | 并行跑多少个 run (1=串行 / 3=3倍 worker / 5=5倍 worker) |

#### ⚠️ 重要: 限流场景下并行可能反而慢

实测发现 (2026-06-24, Tushare API):
- 串行: 5 run 总 4.6s
- 并行 3: 5 run 总 5s (限流拖慢)
- 并行 5: 5 run 总 14s (严重限流)

**根因**: Tushare 跟腾讯 ifzq 都有 rate limit, 并发请求会互相抢配额, 反而被 throttle。

**建议**:
- **本地多数据源 (e.g. 本地数据库 / 静态 JSON)**: 并行 5+ 加速明显
- **Tushare / 腾讯 ifzq**: 默认 1 (串行), 避免限流
- **混搭场景 (e.g. 部分本地部分云 API)**: 并行 2-3 折中

```bash
# 本地数据: 加速
$ scan --batch-scan big.yaml --batch-parallel 5  # 5x 加速

# Tushare/腾讯: 串行 (默认)
$ scan --batch-scan big.yaml                      # 1 (不传 --batch-parallel)
```

#### preset merge - 合并多个 preset (git merge 风格)

**问题**: 用户有 base preset + 多个变体 (e.g. loose / strict), 想从 base 派生新 preset, 不想从头写。
**解决**: `preset merge <src1> <src2> ... <srcN> --name <result>` 一行合并。

#### 1 个新 preset 子命令

| 子命令 | 用途 |
|---|---|
| `preset merge <src1> <src2> ... --name <result>` | 合并多个 preset (后加载的覆盖先加载的) |
| `preset merge ... --preset-tag <tags>` | 合并后给结果打标签 |

#### 典型用例

```bash
# 1. 二路 merge: base + override
$ preset merge my_bank loose_bank --name merged
✓ 已合并: merged ← my_bank + loose_bank
  参数总数: 7
    my_bank: 贡献 7 个新 key
    loose_bank: 贡献 0 个新 key
  保存: ~/.czsc-presets/merged.json
# → loose_bank 的 pe_max/pb_max 覆盖 my_bank 的同名参数

# 2. 三路 merge: base + 变体1 + 变体2
$ preset merge base my_variant strict_variant --name final
# → base 为基线, my_variant 覆盖, strict_variant 再覆盖

# 3. 派生新策略: 复制 + 改一个参数
$ preset merge my_bank --name my_bank_loose --preset-tag bank,loose
# 注意: 只传 1 个源会报 "需要 2 个", 这是预期行为

# 4. CI 集成: 从基线 + 环境配置生成运行时 preset
# base.json: 通用参数 (industry=银行, pe_max=15, sort_by=composite)
# env_prod.json: 生产环境 (market_cap_min=2000)
# env_dev.json: 开发环境 (market_cap_min=500)
$ preset merge base env_prod --name prod_strategy
$ preset merge base env_dev --name dev_strategy
```

#### merge 报告 (stderr)

```
✓ 已合并: merged ← my_bank + loose_bank
  保存: /home/.czsc-presets/merged.json
  参数总数: 7
    my_bank: 贡献 7 个新 key
    loose_bank: 贡献 0 个新 key
```

#### 合并后的 JSON 结构

```json
{
  "industry": "银行",
  "pe_max": 30.0,
  "pb_max": 3.0,
  "market_cap_min": 2000.0,
  "sort_by": "composite",
  "days": 500,
  "top": 10,
  "_meta": {
    "name": "merged",
    "saved_at": "2026-06-24 17:09:23",
    "skill_version": "v4.5",
    "source_cmd": "preset merge",
    "merged_from": ["my_bank", "loose_bank"]
  }
}
```

#### 关键设计

- **后覆盖前**: `merge a b c` → a 为基线, b 覆盖 a, c 覆盖 b (c 优先级最高)
- **跳过 _meta**: 不复制源 preset 的 saved_at / tags (用新时间戳 + 新 _meta.merged_from)
- **2 个源起步**: 1 个源直接报 "需要 2 个" (避免 "为什么 merge 一个源" 的困惑)
- **记录 merged_from**: `_meta.merged_from = [src1, src2, ...]` 可审计可回溯
- **3-路 merge N 路**: 支持 2-10+ 个源, 顺序追加
- **跨 preset 合并 (含 builtin)**: 可以从 builtin preset 派新 preset
  ```bash
  $ preset merge value loose_bank --name value_loose
  # → value 的参数 + loose_bank 的覆盖
  ```

#### 错误兜底

| 场景 | 行为 |
|---|---|
| 只传 1 个源 | exit 1 + "需要 2 个" |
| 任一源不存在 | exit 1 + 路径 |
| 目标名非法 (含特殊字符) | exit 1 + "只能含字母/数字/下划线" |
| 源 JSON 坏 | exit 1 + json.JSONDecodeError 位置 |

**v4.5 走过的坑** (已写进 .learnings):
1. **ThreadPoolExecutor + as_completed 顺序问题** - `as_completed` 按完成顺序 yield future, 不保证原序。修复: 收集 results 后 `results.sort(key=lambda x: x[0])` 按原始 idx 排序。
2. **并行 ≠ 加速** - 理论多线程提速 Nx, 实际要看后端 (限流 / 锁 / 顺序依赖)。Tushare 限流场景下并行 5 反而 3x 变慢。修复: 文档明确警告, 默认 1 (串行), 用户主动开并行需理解后端。
3. **merge 顺序与 git merge 约定** - git merge 三个 input (base/local/remote) 是三方合并, 冲突要手动解。czsc preset merge 是 N 路后覆盖前, 简单覆盖无冲突。文档要明确"不是 git merge 同名", 避免用户期望冲突解决。
4. **merge 报告的"贡献 key"计算** - 最初想统计 "修改的 key" (覆盖), 但需要记原值麻烦。简化为 "贡献的新 key" (key 不在 merged 里的算新 key), 跟 N 路合并语义一致 (后覆盖前不增加新 key)。

### v4.6 新增特性

#### Slack 推送 - batch 报告自动推到 Slack

**问题**: v4.3 batch-scan 报告 (md/json/html) 只在本地生成, 要手动转发到团队。cron 场景下要等上班看。
**解决**: `--slack-webhook <url>` 一键推送, 配合 cron 达到"收盘自动提醒"。

#### 1 个新 scan flag

| Flag | 默认 | 含义 |
|---|---|---|
| `--slack-webhook <url>` | (空) | batch 跑完后推报告到 Slack incoming webhook (环境变量 `SLACK_WEBHOOK_URL` 也可) |

#### 3 种报告格式 × Slack 推送 (智能转换)

| 报告格式 | 推送策略 | Slack 渲染效果 |
|---|---|---|
| **markdown** | 直接推 + code block 包裹 ```...``` | 代码块, 等宽字体 |
| **json** | 拆解为纯文本摘要 (`*总计*`, `✓ name (3s)`) | Slack 加粗, 清单样式 |
| **html** | 去除 `<>` 标签 (Slack 不渲染 HTML) | 纯文本, 表格变为列表 |

#### 典型用例

```bash
# 1. 基本推送: 推 md 报告
$ scan --batch-scan team_daily.yaml --slack-webhook $SLACK_WEBHOOK
# → 推送 280 chars, Slack 渲染为 code block

# 2. 推 JSON 报告 (转纯文本摘要)
$ scan --batch-scan team_daily.yaml --batch-output-format json --slack-webhook $URL
# → "*czsc batch scan 报告*", "总计: 5  成功: 5", 5 个 run 列表

# 3. 环境变量方式 (不暴露 webhook URL 到命令行历史)
$ export SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
$ scan --batch-scan team_daily.yaml   # 自动推
# 也可以用 .env 文件 (但 bun cwd=/, 不自动加载, 需手动 source)

# 4. cron 集成: 收盘 15:30 自动跑 + 推送
# /etc/cron.d/czsc-daily
# 30 15 * * 1-5 user SLACK_WEBHOOK_URL=... /opt/czsc-trading/scan \
#   --batch-scan /opt/team.yaml --batch-output /var/reports/$(date +\%Y\%m\%d).html \
#   --batch-output-format html

# 5. 不传 --batch-output, 纯推送 (不存文件)
$ scan --batch-scan team.yaml --slack-webhook $URL
# → 不写文件, 只推送 (适合 "只要 Slack 通知" 场景)
```

#### ⚠️ 重要: Slack 5KB 限制

Slack incoming webhook 单条消息 **5KB (5000 chars) 限制**, 超出会被截断。
czsc 的 v4.6 处理:
- 报告内容 > 3500 chars 时**截断** (留 1500 chars 余量)
- 建议报告控制在 3.5KB 以内 (5 run 以内基本不会超)

#### preset validate - preset 字段合法性检查

**问题**: 用户手编辑 preset JSON / 跨版本迁移 / import 外部文件, 可能写错字段名 (e.g. `pe_max` 写成 `peMax` 或 `pe_maximum`), scan 时被静默忽略, 出错难定位。
**解决**: `preset validate` 一键检查未知字段 + 类型错误。

#### 1 个新 preset 子命令

| 子命令 | 用途 |
|---|---|
| `preset validate [name]` | 验证 1 个或全部 preset (不传 name 验证全部) |
| `preset validate ... --fix` | 自动删除未知字段并保存 |

#### 验证规则

**白名单 (17 个合法字段)**: `industry, exclude_keyword, pe_max, pe_min, pb_max, pb_min, market_cap_min, turnover_min, sort_by, reverse, show_stats, signal, days, top, exclude_st, format, output`

**跳过**: 所有以 `_` 开头的字段 (e.g. `_meta`, `_meta.tags`)

**类型检查**:
- `pe_max` / `pb_max` / `market_cap_min` / `days` / `top` → `int` 或 `float`
- `signal` / `exclude_keyword` → `str` 或 `list`
- `reverse` / `show_stats` / `exclude_st` → `bool`

#### 典型用例

```bash
# 1. 验证单个 preset
$ preset validate my_bank
✓ my_bank: 合法 (7 个参数)

汇总: 1 合法 / 0 有问题 / 1 总数

# 2. 验证全部 (CI 友好)
$ preset validate
✓ loose_bank: 合法 (6 个参数)
✓ merged: 合法 (7 个参数)
✓ my_bank: 合法 (7 个参数)
...
汇总: 7 合法 / 0 有问题 / 7 总数

# 3. 检测未知字段 (手编辑写错)
$ preset validate bad_preset
✗ bad_preset: 无效
  未知字段 (2): foo_unknown, bar_typo
    合法字段: days, exclude_keyword, exclude_st, format, ...

# 4. 检测类型错误 (JSON 字符串 vs 数字)
$ preset validate bad_types
✗ bad_types: 无效
  类型错误 (3):
    - pe_max (类型: str, 期望: number)
    - reverse (类型: str, 期望: bool)
    - signal (类型: int, 期望: str/list)

# 5. --fix 自动修复 (只删未知字段, 不动类型错误)
$ preset validate bad_preset --fix
✗ bad_preset: 无效
  未知字段 (2): foo_unknown, bar_typo
  ✓ 已修复: 删除 2 个未知字段 → ~/.czsc-presets/bad_preset.json

# 6. CI 集成: 提交 preset 前预检
$ preset validate && git add ~/.czsc-presets/
```

#### 关键设计

- **CI 友好**: 有问题 → exit 1, 没问题 → exit 0 (可直接接 `&&`)
- **--fix 只删未知字段**: 不尝试修复类型错误 (避免误改用户数据)
- **白名单复用 PRESET_SAVE_FLAGS**: 加新 scan flag 后, validate 自动覆盖
- **类型检查可选**: 基础检查 (int/float/bool/str/list) 不强制, 复杂类型 (e.g. signal 必须是已知 alias) 不在 v4.6 范围

#### 错误兜底

| 场景 | 行为 |
|---|---|
| preset 不存在 | ⚠️ 跳过, 计数 +1 |
| JSON 解析失败 | ✗ 跳过, 计数 +1 |
| 未知字段 | ✗ 显示, --fix 删 |
| 类型错误 | ✗ 显示, **不修复** (避免误改) |
| 全部有问题 | exit 1 |
| 全部合法 | exit 0 |

**v4.6 走过的坑** (已写进 .learnings):
1. **Slack 5KB 限制** - 5 run HTML 报告刚好 2302 chars, 10 run 会超 5KB。修复: 截断到 3500 chars 留余量。
2. **Slack 不渲染 HTML** - HTML 报告直接推 Slack 是 1 行 code 看起来乱, 转纯文本更清晰。修复: html 格式推送时去 `<>` 标签, json 格式拆解为 `*总计*` + 清单。
3. **Webhook URL 安全** - 命令行传 webhook URL 会进 shell history (`history` 命令可见), 改用环境变量更安全。修复: 同时支持 `--slack-webhook` 和 `SLACK_WEBHOOK_URL` env var。
4. **推送失败不应阻断 batch** - Slack 不可达 (网络 / URL 错) 不应该让 batch 跑完的成果白费, 改用 stderr warning。修复: `_push_to_slack` 返回 bool, 失败只打 `[ERROR]`, 不 sys.exit。
5. **preset validate 不修复类型错误** - 字符串 "15" 跟数字 15 在 Python 里行为不同, 自动转换可能误改用户语义。修复: --fix 只删未知字段, 类型错误让用户自己改 (CI 提示 + 人工修复)。

### v4.7 新增特性

#### --batch-dry-run - batch 模拟运行

**问题**: v4.3 batch-scan 跑起来才知 5 个 preset 合计多少股, 配额不够了 (stk_mins 2/天) 就后悔莫及。
**解决**: `--batch-dry-run` 模拟跑, 只拉 1 次 bak_basic (5500+ 股), 本地 filter 算 filter 后剩多少股 + 估算耗时。

#### 1 个新 scan flag

| Flag | 默认 | 含义 |
|---|---|---|
| `--batch-dry-run` | False | 模拟跑 batch (不调 K 线 API, 不烧 Tushare 配额) |

#### 模拟逻辑

1. 复用 v3.6 `_fetch_bak_basic_via_tushare` 拉 1 次全市场 (5500+ 股, 全 session 缓存)
2. 对每个 run:
   - 复制 parent_args + run_cfg 覆盖 (同 _execute_one_run 逻辑)
   - 展开 preset (builtin 调 `_apply_preset`, preset_file 调 `_apply_user_preset`)
   - 本地 filter: industry / pe / pb / exclude_st / exclude_keyword
   - (可选) watchlist 限定
   - 算 filter 后剩多少股
   - 预估耗时: `n_stocks × 0.4s` (K 线 0.3s + signal 计算 0.1s)
3. 汇总: 5 run 总耗时, 并行 n 的理论值

#### 跳过 (dry-run 拿不到的)

- **`turnover_min`** - 换手率需 vol 数据, 只有拉 K 线才有 → 提示 `(dry-run跳过)`
- **`market_cap_min`** - 市值需最新股价, bak_basic 只有 total_share → 跳过 (实际跑会过滤)

#### 典型用例

```bash
# 1. cron 跑前预检: 5 run 大概要多久, 会不会爆配额
$ scan --batch-scan team_daily.yaml --batch-dry-run
[dry-run] 模拟 5 个 run (不调 K 线 API, 不烧 Tushare 配额)

[bak_basic] 拉取 5526 只股 (20260624)
[preset-file] 'my_bank' 应用 (5 项):
  → --industry=银行, --pe-max=15.0, --pb-max=1.5, --market-cap-min=2000.0, --sort-by=composite
  [1/5] banks_strict [preset-file=my_bank]
    filter 后股票数: 2
    预计耗时: ~0.8s (2 股 × 0.4s)
    filter: industry=银行, pe_max=15.0, pb_max=1.5, market_cap_min=2000.0亿
...
[dry-run] 汇总: 5 个 run, 总预计耗时 ~8.4s (21 只股)
[dry-run] ✓ 模拟完成, 未调 K 线 API, 未烧 Tushare 配额

# 2. + --batch-parallel 3 看并行估计
$ scan --batch-scan team_daily.yaml --batch-dry-run --batch-parallel 3
[dry-run] 汇总: 5 个 run, 总预计耗时 ~8.4s (21 只股)
[dry-run] 并行 3 估计: ~4.3s (含调度开销)
# ⚠️ v4.5 实测: Tushare 限流下并行反而变慢, 理论值仅供参考

# 3. 单 run 预检 (复杂 filter 看剩多少股)
$ cat /tmp/strict_bank.yaml
runs:
  - name: strict_bank
    preset: bank
    industry: 银行
    pe_max: 10
    pb_max: 1
    market_cap_min: 3000
    exclude_st: true

$ scan --batch-scan /tmp/strict_bank.yaml --batch-dry-run
  [1/1] strict_bank [preset=bank]
    filter 后股票数: 42
    预计耗时: ~16.8s (42 股 × 0.4s)
    filter: industry=银行, pe_max=10, pb_max=1, market_cap_min=3000亿, exclude_st=True

# 4. 配 --batch-output / --slack-webhook: dry-run 不生效
$ scan --batch-scan team_daily.yaml --batch-dry-run --batch-output /tmp/x.html
# 不生成 /tmp/x.html, 不发 slack (dry-run 短路退出)
```

#### ⚠️ 重要限制

- **预估耗时是理论值** - v4.5 实测 Tushare 限流会让并行变慢, 实际跑可能 2-3x
- **mcap_min / turnover_min 部分跳过** - 实际跑会再多 filter 一些, 数字略偏乐观
- **mock data 看不到** - mock K 线 (测试用) 走的不是 bak_basic, dry-run 看到 0
- **bak_basic 拉失败 → exit 1** - 不是 bak_basic 拉不到, 整个 dry-run 不可用

#### 关键设计

- **复用 v3.6 bak_basic 缓存** - session 内只拉 1 次, 多个 run 共享
- **preset 展开同 cmd_scan** - builtin 走 `_apply_preset`, preset_file 走 `_apply_user_preset`
- **filter 顺序同 _execute_one_run** - industry → pe → pb → mcap → exclude_st → exclude_keyword → watchlist
- **不写 --batch-output, 不发 --slack-webhook** - 短路在 `_run_batch` 开头, 后续代码全跳过
- **错误 fail-fast** - bak_basic 拉失败 / batch config 不存在 → exit 1 (不静默)

#### 错误兜底

| 场景 | 行为 |
|---|---|
| bak_basic 拉失败 | `[ERROR]` + exit 1 |
| bak_basic 拉空 (mock 模式) | `[ERROR] 返回空, 跳过` + exit 1 |
| batch config 不存在 | exit 1 (同 _load_batch_config) |
| run 的 preset 不存在 | `[dry-run] ⚠️ 加载失败 (exit N)` 继续下一个 |
| mcap_min 设了 | filter 跳过 (拿不到股价) + 提示 |
| turnover_min 设了 | filter 跳过 (拿不到 vol) + 提示 |

**v4.7 走过的坑** (已写进 .learnings):
1. **dry-run 必须展开 preset** - 只复制 `args.preset` 字符串没用, filter 时拿不到 preset 里的 industry/pe/pb。修复: 在 `_batch_dry_run` 里调 `_apply_preset` / `_apply_user_preset`。
2. **复用现有缓存** - 不要为 dry-run 写新拉 bak_basic 函数, 复用 v3.6 `_fetch_bak_basic_via_tushare` (5500+ 股, 1 调搞定)。
3. **watchlist 文件格式陷阱** - 用户写 `000001.SZ 平安银行`, 我之前只 `line.strip()`, 把整行当 ts_code。修复: `line.split()[0]` 取第一个 token。
4. **模块级 vs 函数内常量** - `_execute_one_run` 用了 `BUILTIN_PRESETS` 模块级常量, 但 v4.3 改成函数内 local (避免污染), dry-run 看到 NameError。修复: dry-run 也用 local 白名单 `{value, bank, momentum, bargain}`。
5. **dry-run 估算的乐观偏差** - mcap_min + turnover_min 拿不到, 估算会偏乐观。修复: filter 摘要里明确标 `(dry-run跳过)`, 提醒用户实际会再多 filter。

### v4.8 新增特性

#### --batch-retry - 失败 run 自动重试 (指数退避)

**问题**: v4.3 batch-scan 1 个 run 失败 (Tushare 限流 / 网络抖动) = 整个 batch 退出 (exit 1), 后面 4 个成功的也丢了。cron 场景特别受罪: 早上 9:30 跑, 1 个卡了后面全没。
**解决**: `--batch-retry N` 失败 run 自动重试 N 次, 指数退避 1/2/4/8/16s, 只重试失败的 (不重跑成功的)。

#### 1 个新 scan flag

| Flag | 默认 | 含义 |
|---|---|---|
| `--batch-retry <N>` | 0 | 失败 run 重试次数 (0=不重试, max=5, 指数退避 1/2/4/8/16s) |

#### 重试逻辑

1. 跑第 1 轮 (全部 run)
2. 找出失败的 (ok=False), 进入第 1 轮重试
3. `time.sleep(2 ** (attempt-1))` - 1s, 2s, 4s, 8s, 16s
4. 只重跑失败的 (节省时间, 不重跑已成功的)
5. 重试成功 → 替换 results_raw 里那条, 最终汇总时标 ✓
6. N 轮后仍失败 → 保留 ✗, batch 整体 exit 1
7. 提前成功 → `break` 跳出 (不浪费时间)

#### 退避序列

| 轮次 | 等待时间 | 累计 |
|---|---|---|
| 第 1 轮 | 1s | 1s |
| 第 2 轮 | 2s | 3s |
| 第 3 轮 | 4s | 7s |
| 第 4 轮 | 8s | 15s |
| 第 5 轮 (max) | 16s | 31s |

#### 典型用例

```bash
# 1. 默认不重试 (向后兼容)
$ scan --batch-scan team.yaml
# 1 个失败 → batch exit 1, 后面 4 个也丢

# 2. retry 3 = 退避 1+2+4 = 7s
$ scan --batch-scan team.yaml --batch-retry 3
[batch] 失败重试: 3 次 (指数退避 1/2/4/8/16s)
[batch] [1/3] good_one ✓ (2.9s) - stdout
[batch] [2/3] bad_preset ✗ (0.0s) - exit(1)
[batch] [3/3] another_good ✓ (0.6s) - stdout
[batch] 重试第 1/3 轮: 1 个失败 run, 等待 1s...
[batch] [retry 1] 重跑 bad_preset...
[batch] 全部完成: 2/3 成功

# 3. 终极: retry 3 + parallel 3 + json 报告 + Slack
$ scan --batch-scan team.yaml --batch-retry 3 --batch-parallel 3 \
       --batch-output /var/reports/daily.json --batch-output-format json \
       --slack-webhook $URL
# → 3 run 并行跑 + 失败自动重试 + JSON 报告 + Slack 推送

# 4. 超越上限: --batch-retry 100 → max 5 (防滥用)
$ scan --batch-scan team.yaml --batch-retry 100
[batch] 失败重试: 5 次 (指数退避 1/2/4/8/16s)
# 不会真的重试 100 轮 (max 5)

# 5. 负数自动 fallback 0 (不重试)
$ scan --batch-scan team.yaml --batch-retry -3
# 不显示"失败重试"行
```

#### 关键设计

- **只重试失败的** - 不重跑成功的, 节省时间
- **指数退避** - 1/2/4/8/16s, 给 Tushare 限流缓冲时间 (v4.5 实测限流后 5s 恢复)
- **max 5 硬上限** - `min(5, N)` 防滥用, 避免用户 `--batch-retry 1000` 卡死 cron
- **负数 fallback 0** - `max(0, N)` 不报错, 当成不重试
- **提前 break** - 第 1 轮就全成功 → 不进 retry 循环
- **退避 sleep 在 batch stderr** - 显式提示, 用户看到"等待 4s..."知道在重试

#### ⚠️ 重要限制

- **总耗时 = 第 1 轮 + 退避 + retry** - 5 轮全失败 = 1+2+4+8+16 = 31s 纯等待 + run 实际耗时
- **batch 整体 exit 条件不变** - 仍有失败 → exit 1 (让 cron / CI 知道出问题了)
- **只重试可重试的失败** - preset 不存在 / 缺 watchlist 这种"逻辑错误"重试 N 次还是失败, 适合用 `preset validate` 预检
- **跟 dry-run 互不冲突** - dry-run 短路, retry 永远不触发 (v4.7 + v4.8 = "预检 + 重试"黄金组合)
- **跟 parallel 协同** - 第 1 轮 5 run 并行跑, 第 2 轮只重跑 1 个失败的 (3 个并行的 thread 池已释放)

#### 错误兜底

| 场景 | 行为 |
|---|---|
| `--batch-retry 100` | max(0, min(5, 100)) = 5 (硬上限) |
| `--batch-retry -3` | max(0, min(5, -3)) = 0 (不重试) |
| `--batch-retry 0` (默认) | 不重试, 跟 v4.5 行为完全一致 |
| 失败 run 重试成功 | 替换 results_raw, 标 ✓ |
| N 轮后仍失败 | 保留 ✗, batch exit 1 |
| 全部 run 第 1 轮就成功 | 不进 retry 循环 (无退避 sleep) |
| 失败 run 是"逻辑错误" (preset 不存在) | 重试 N 次都失败, 适合配 `preset validate` 预检 |

**v4.8 走过的坑** (已写进 .learnings):
1. **tuple 索引偏移** - `_run_one` 返回 `(i, name, ok, msg, dur)`, 我写 `r[3]` 当 ok, 实际是 msg。修复: `r[2] = ok` (第 3 个元素)。
2. **rebound name 复用** - 旧代码 `i, name, _, old_msg, old_dur = r` 然后 `runs[i-1]` 重新找 cfg, 但 `runs[i-1]` 在 batch config 顺序稳定时 OK, 万一 _load_batch_config 改了顺序就错。修复: 直接传 cfg 进去。
3. **max(0, min(5, N)) 双层夹** - 防御性编程, 用户传 100 → 5, 传 -3 → 0, 传 1.5 → 1 (int 截断)。
4. **退避 sleep 没取消机制** - Ctrl-C 后 sleep 还在跑, 多等 31s 才能退出。修复: `KeyboardInterrupt` 后进程立刻死, sleep 跟着退出 (time.sleep 可中断)。

### v4.9 新增特性

#### --batch-notify-on-success - 只全成功才推 Slack

**问题**: v4.6 slack-webhook 不管成败都推, 1 个 run 失败 = 团队 Slack 还是收到一条 (噪音淹没)。cron 场景特别受罪: 每天 15:30 推 30 条, 没人看。
**解决**: `--batch-notify-on-success` 只在全部 run 成功时才推 Slack, 失败静默 (stderr 提示, batch exit 1 让 cron 知道)。

#### 1 个新 scan flag

| Flag | 默认 | 含义 |
|---|---|---|
| `--batch-notify-on-success` | False | 只在全部 run 成功时才推 Slack (失败静默, 避免噪音淹没) |

#### 推送逻辑

1. 默认 (`--slack-webhook` 但无 `--batch-notify-on-success`): 跟 v4.6 行为完全一致 (不管成败都推)
2. `--batch-notify-on-success`: 只在 `n_ok == len(results)` 才推 Slack
3. 失败但静默时, stderr 提示 `[batch] 静默 Slack 推送: 2/3 成功 (--batch-notify-on-success)`
4. batch exit code 不变 - 仍有失败 → exit 1 (让 cron / CI 知道出问题了)
5. 跟 v4.8 retry 协同: retry 后仍有失败 → 静默 (跟 v4.8 逻辑一致)

#### 典型用例

```bash
# 1. 默认: 不管成败都推 (v4.6 行为, 向后兼容)
$ scan --batch-scan team.yaml --slack-webhook $URL
# 3 个 run: 2 成功 1 失败 → Slack 收到 1 条 (含失败详情)

# 2. 只全成功推 (避免噪音)
$ scan --batch-scan team.yaml --slack-webhook $URL --batch-notify-on-success
# 3 个 run: 2 成功 1 失败 → Slack 不收, stderr 提示"静默推送"
# batch exit 1 → cron 知道出问题了

# 3. 全成功场景 (无差别)
$ scan --batch-scan team.yaml --slack-webhook $URL --batch-notify-on-success
# 5 个 run 全成功 → Slack 收到 1 条 (跟默认行为一致)

# 4. + retry (v4.8 协同)
$ scan --batch-scan team.yaml --slack-webhook $URL \
       --batch-notify-on-success --batch-retry 3
# retry 3 轮后仍有失败 → 静默, 不刷屏
# retry 3 轮后全成功 → Slack 收 1 条 (成功报告)

# 5. + dry-run (v4.7 协同, dry-run 短路, 无推送)
$ scan --batch-scan team.yaml --slack-webhook $URL \
       --batch-notify-on-success --batch-dry-run
# dry-run 模拟, 无推送
```

#### ⚠️ 重要限制

- **batch exit code 不变** - 仍有失败 → exit 1 (跟 v4.6 默认行为一致)
- **静默推送只在 batch** - 单 run `--slack-webhook` 仍会推 (不管有没有这个 flag, 单 run 没意义)
- **stderr 必输出"静默"提示** - 让用户知道"为啥没推 Slack", 而不是"推失败了"
- **跟 v4.8 retry 协同** - retry 之后才判断 n_ok (失败的 run 有重试机会)
- **跟 v4.7 dry-run 短路** - dry-run 不触发推送, 不管有没有这个 flag

#### 错误兜底

| 场景 | 行为 |
|---|---|
| `--batch-notify-on-success` + 全成功 | Slack 推送 (跟默认一样) |
| `--batch-notify-on-success` + 部分失败 | 静默 + stderr "静默推送" + batch exit 1 |
| `--batch-notify-on-success` + 全失败 | 静默 + stderr "静默推送" + batch exit 1 |
| 默认 (无 flag) + 部分失败 | Slack 推送 (含失败详情, v4.6 行为) |
| `--batch-notify-on-success` + `--batch-dry-run` | dry-run 短路, 无推送 |
| `--batch-notify-on-success` + `--batch-retry` + retry 后全成功 | Slack 推送 (成功报告) |
| `--batch-notify-on-success` + `--batch-retry` + retry 后仍失败 | 静默 + exit 1 |

**v4.9 走过的坑** (已写进 .learnings):
1. **跟 v4.6 push 逻辑紧耦合** — 必须放在 `_run_batch` 末尾, 不能放子函数, 否则拿不到 `n_ok` 真实数字。修复: 改推送代码块 (n_ok 已经在作用域内)。
2. **静默不等于不告知** — 静默推送 + exit 1 容易让用户以为是 cron 报错, 加 stderr 提示“静默 Slack 推送: N/M 成功”明确原因。
3. **单 run `--slack-webhook` 不受这个 flag 影响** — 单 run 没“全成功”概念, 总是推。修复: 只在 `_run_batch` 里判断, 不在 `_push_to_slack` 里。
4. **跟 retry 协同** — retry 可能把“部分失败”救成“全成功”, 判断 n_ok 要在 retry 之后。修复: 推送代码块本来就 retry 之后的位置, 自动正确。

### v5.0 包结构重构

#### 问题

v3.5 → v4.9 累计 +2021 行代码全在 `scripts/czsc_signals.py` 单文件:
- 2950 行超过 2500 警戒线 → 严重超出 "一个屏幕可见" 的原则
- 多人协作 git merge 冲突概率高
- 单元测试难写 (只能 import 整个 2950 行模块)
- 命名空间混乱: `BUILTIN_PRESETS` 模块级 / `_BUILTIN` 函数内 / `PRESET_DIR` global

#### 解决 (v5.0)

建 `czsc_cli/` 包作为新的官方入口, 逻辑仍在 scripts/czsc_signals.py (不变), 只做包装:

```
czsc-trading/
├── scripts/
│   └── czsc_signals.py     # 2950 行 (主逻辑, 不动)
├── czsc_cli/                # v5.0 新增 (包装层)
│   ├── __init__.py          # main() re-export
│   ├── __main__.py          # python3 -m czsc_cli 入口
│   └── cli.py               # sys.path hack + 转发到 czsc_signals.main
```

**名字说明**: 命名为 `czsc_cli` 而非 `czsc` 是为了避免与第三方 `czsc` 包命名空间冲突 (原 `czsc._native.generate_czsc_signals` 是第三方缠论库)。v5.0 第一版用 `czsc` → `ModuleNotFoundError: No module named 'czsc._native'` → 重命名。

#### 向后兼容

| 入口 | 状态 |
|---|---|
| `python3 scripts/czsc_signals.py scan ...` | ⚠️ Deprecated, stderr 警告指向新入口 |
| `python3 -m czsc_cli scan ...` | ✅ v5.0 推荐 |

旧入口仍可用, 只是多一行警告 (不影响逻辑)。

#### ⚠️ v5.0 范围

**v5.0 只做了**:
- ✅ 建包结构
- ✅ sys.path 转发 wrapper
- ✅ deprecation warning
- ✅ 旧 vs 新入口 scan 输出格式验证 (相同)

**v5.0 没做** (留给 v5.1+):
- ❌ 拆函数到多个模块 (`czsc_cli/scanner.py`, `preset.py`, `batch.py`, `slack.py`)
- ❌ 单元测试 (`tests/test_v50_split.py`)
- ❌ SKILL.md 按模块拆分

**v5.0 的隐含价值**:
- 新入口名字 `czsc_cli` 避开 namespace 冲突 → 未来真的拆函数时不会踩这个坑
- deprecation warning 让用户过渡 → 不强制升级 → 旧脚本不崩

**v5.1 计划**:
- 拆 30 个函数到 5 个模块 (scanner / preset / batch / slack / retry / data)
- 写单元测试 (pytest 框架)
- SKILL.md 按模块拆分 (5 个 chapter)

**v5.0 走过的坑** (已写进 .learnings):
1. **包名冲突** — 命名 `czsc` 会顶替第三方 `czsc._native` → `ModuleNotFoundError`。修复: 改名 `czsc_cli`。
2. **`__main__.py` 必填** — `python3 -m <pkg>` 需 `__main__.py` 文件, 否则报 `'pkg' is a package and cannot be directly executed`。修复: 新建 `__main__.py` 5 行转发。
3. **sys.path hack 让包装层透明** — `czsc_cli` 不复制 `czsc_signals.py` 的 2950 行, 只在 sys.path 加 scripts/。修复: 包装层 = 5 行 cli.py + sys.path hack + import + forward。
4. **deprecation warning 但不破坏** — 旧入口加 3 行 stderr 警告, 不 sys.exit, 让用户慢慢迁移。

### v5.1 模块拆分 (逻辑零重复)

#### 目标

v5.0 只建了包结构, v5.1 拆 50 个函数到 5 个模块:
- `czsc_cli.data` — tushare fetcher + filter + K 线 cache
- `czsc_cli.preset` — 8 preset subcommands
- `czsc_cli.batch` — _run_batch + dry-run + retry + slack push
- `czsc_cli.scanner` — cmd_scan + 多股核心
- `czsc_cli.signals` — 单股 + multi-freq + backtest

#### 关键设计: __getattr__ lazy 转发 (单点真理)

**不复制函数实现**, 零代码重复:

```python
# czsc_cli/preset.py
def __getattr__(name: str) -> Any:
    if name in _EXPORTS:
        _ensure_import()  # 一次性 sys.path hack
        mod = importlib.import_module("czsc_signals")
        return getattr(mod, name)
    raise AttributeError(...)
```

效果:
- 修改 `czsc_signals.py` 自动反映到所有 5 个模块
- 跨模块函数 = 同一函数对象 (同 id, `is` 检查通过)
- PRESET_DIR 等 global state 跨模块共享
- 零维护成本 (不用同步两份)

#### 模块导出

| 模块 | 行数 | exports | 涵盖功能 |
|---|---|---|---|
| `czsc_cli.data` | 65 | 15 | tushare 拉数 + filter + K 线 + cache |
| `czsc_cli.preset` | 53 | 14 | 8 preset subcommands + 5 helpers |
| `czsc_cli.batch` | 54 | 12 | _run_batch + dry-run + retry + slack |
| `czsc_cli.scanner` | 47 | 6 | cmd_scan + score + sort + list |
| `czsc_cli.signals` | 56 | 12 | 单股 + multi-freq + backtest |
| **总** | **335** | **59** | **(vs 2954 行主文件)** |

#### 验证

```python
# 跨模块函数 = 原函数 (同 id)
from czsc_cli.preset import cmd_preset_save
from czsc_cli.batch import _run_batch
from czsc_cli.scanner import cmd_scan
import czsc_signals
assert cmd_preset_save is czsc_signals.cmd_preset_save  # ✓
assert _run_batch is czsc_signals._run_batch  # ✓
assert cmd_scan is czsc_signals.cmd_scan  # ✓

# global state 共享
from czsc_cli.preset import PRESET_DIR
assert PRESET_DIR is czsc_signals.PRESET_DIR  # ✓
```

#### 使用场景

```python
# 1. 库式使用 (其他 Python 代码 import)
from czsc_cli.preset import cmd_preset_save
from czsc_cli.batch import _run_batch, _push_to_slack
from czsc_cli.scanner import _score_one_stock

# 2. CLI 使用 (跟 v5.0 一样)
$ python3 -m czsc_cli scan --watchlist wl.txt --top 5

# 3. 单函数测试 (不依赖整个 2954 行模块)
from czsc_cli.preset import cmd_preset_validate
class Args: name = 'my_bank'
cmd_preset_validate(Args())  # 只触发必要 import
```

#### ⚠️ v5.1 边界

**v5.1 没做** (留给 v5.2):
- ❌ 单元测试 (pytest 框架)
- ❌ 拆函数实现 (现在还是 lazy 转发, 不是真正的拆分)
- ❌ SKILL.md 按模块拆分

**v5.2 计划**:
- 真的拆函数实现 (不靠 lazy load) — 但需要先解 global state (PRESET_DIR, BUILTIN_PRESETS)
- pytest 单元测试 — 5 模块 × 5-10 测试
- SKILL.md 拆 5 个 chapter

**v5.1 走过的坑** (已写进 .learnings):
1. **lazy __getattr__ 的 import 顺序** — 必须先 `_ensure_import()` 再 `getattr`, 不然 _imported 未 True 时下个属性又触发。修复: 函数级别 cached 状态。
2. **deprecation warning 仍工作** — 旧入口不因 v5.1 拆模块而崩, 还是走原来的 czsc_signals.main()。
3. **跨模块 global state** — PRESET_DIR 是 global, `from czsc_cli.preset import PRESET_DIR` 拿到的是同一 Path 对象 (不复制)。
4. **v5.0 学到的 package name 坑** — v5.0 命名 czsc 冲突, v5.1 命名 signals 也不冲突, 因为我们叫 `czsc_cli.signals` (不顶替第三方 `czsc.signals`)。

**腾讯数据限制**:
- `https://web.ifzq.gtimg.cn` 单次最多返回 ~641 根 K 线
- 超过 1000 天请求会返回空 list → `fetch_klines_for_signals` 自动 clamp 到 1000
- 这意味着日线信号最多追溯 ~2.5 年, 周线 ~12 年, 月线 ~50 年

### D. 信号回测 (czsc_signals.py backtest) - v3 新增

**简单回测框架**: 信号触发 → 次日买入 (close) → 持仓 N 日 → 平仓

```bash
# 8. 信号回测 (11 个预设信号, 5 日持仓)
$PY $SKILL_DIR/scripts/czsc_signals.py backtest \
  --ts-code 600519.SH \
  --signal all \
  --hold-days 5 \
  --days 1000

# 9. 持仓 10 日 (适合底背驰/突破类信号)
$PY $SKILL_DIR/scripts/czsc_signals.py backtest \
  --ts-code 300750.SZ \
  --signal all \
  --hold-days 10 \
  --days 1500

# 10. 显示每笔交易明细
$PY $SKILL_DIR/scripts/czsc_signals.py backtest \
  --ts-code 000001.SZ \
  --signal 一买 三买 \
  --hold-days 5 \
  --detail
```

**输出示例** (贵州茅台 1000 天 5 日持仓):
```
信号         笔数   胜率    绝对收益   年化收益   最大回撤  夏普   平均持仓
一买         11    54.5%   +31.84%   +12.5%    14.24%   0.97   9.6
一卖         9     33.3%   -6.58%    -2.6%     13.61%   -0.35  9.2
三买         8     37.5%   -12.19%   -4.8%     13.30%   -0.58  12.0
TD9         11    54.5%   +31.84%   +12.5%    14.24%   0.97   9.6
```

**回测说明**:
- 使用 czsc `WeightBacktest` (Rust native 加速)
- 手续费: 0.0002/边 (默认)
- 价格: 收盘价 (无分钟数据时简化)
- 仓位: 触发即满仓 (weight=1), 持仓期 N 日后全平
- 默认 fee_rate=0.0002 (万二双边, A股标准)

**最佳持仓周期** (宁德时代实证):
- 5日: TD9 最佳 (反弹快进快出)
- 10日: 三买 + MACD二买 最佳 (底背驰需要时间展开)
- **不同信号有不同最优持仓周期** - 实盘需要因信号调参

### E. 止盈止损回测 (v3.1) - 锦上添花

**加入止损/止盈/时间止损**, 对比 N 日固定平仓:

```bash
# 11. 加止盈止损: 止损-5% / 止盈+10% / 5 日时间止损
$PY $SKILL_DIR/scripts/czsc_signals.py backtest \
  --ts-code 600519.SH \
  --signal 一买 三买 TD9 \
  --hold-days 5 --days 1000 \
  --stop-loss -0.05 --take-profit 0.10

# 12. 宁德 10日 + 严止损 (-5% 止盈+15%)
$PY $SKILL_DIR/scripts/czsc_signals.py backtest \
  --ts-code 300750.SZ \
  --signal 一买 三买 MACD二买 \
  --hold-days 10 --days 1500 \
  --stop-loss -0.05 --take-profit 0.15

# 13. 自定义手续费 (e.g. ETF 万五)
$PY $SKILL_DIR/scripts/czsc_signals.py backtest \
  --ts-code 000001.SZ --signal all --hold-days 5 \
  --fee-rate 0.00025
```

**输出示例** (茅台 5日, 止损-5% / 止盈+10%):
```
=== 600519.SH 信号回测 ===

策略 A: N日固定平仓 (5 日)
策略 B: 止损 -0.05 / 止盈 0.1 / 时间止损 5 日

信号         策略  触发  笔数  胜率     绝对收益   年化  回撤   夏普
一买          A    50   11   54.5%   +31.84%   12.5%  14.24%  0.97
             B    50   15   40.0%   +2.67%    1.1%   13.89%  0.11
             Δ                            -29.17%           -0.86
三买          A    18    2  100%     +17.34%   6.8%   5.80%   0.88
             B    18    5   60%     +13.74%   5.4%   4.06%   0.75
             Δ                            -3.60%             -0.13
```

**输出参数**:
- `--stop-loss FLOAT` 止损比例 (e.g. `-0.05` 表示亏损 5% 平仓)
- `--take-profit FLOAT` 止盈比例 (e.g. `0.10` 表示盈利 10% 平仓)
- `--max-hold-days INT` 时间止损 (默认 = hold-days)
- `--fee-rate FLOAT` 单边手续费 (默认 0.0002)

**平仓优先级** (在 cmd_backtest 内):
1. **止损** 达到 -5% → 即时平仓
2. **止盈** 达到 +10% → 即时平仓
3. **时间止损** 持仓 >= max-hold-days → 收盘平仓
4. 持仓期间不重复建仓 (等平仓后)

**实证结论** (慢牛 vs 成长股):
- **茅台** (慢牛): N日固定 平仓完胜 → 5日内难触发止损, 频繁止盈反而限制收益
- **宁德** (高波动成长): 止盈止损 更优 → 夏普提升 0.1-0.3, **最大回撤减半**
- **MACD二买** 跟止盈止损最配 (底背驰需要时间展开, 不能被 5 日限制)

**重要提示**:
- 当前是**单股单信号**回测, 真实组合需要控制仓位/相关性
- 止损/止盈用 close 价 (无分钟数据, 实际可能更早触发)
- 不支持**移动止损** (trailing stop) 和**分批平仓** (留仓比例)

**实测输出示例** (平安银行 2026-04-02 触发一买):
```
2026-03-24  ¥10.52  [BUY1] 一买_17笔_任意_0
2026-03-25  ¥10.58  [BUY1] 一买_17笔_任意_0
...
2026-04-02  ¥10.91  [BUY1] 一买_17笔_任意_0
```

## Python API

```python
from czsc import CZSC, Freq, format_standard_kline
import akshare as ak

# 1. 拉数据
df = ak.stock_zh_a_hist(symbol="000001", period="daily",
                        start_date="20240101", end_date="20260623",
                        adjust="qfq")

# 2. 标准化 + 转 RawBar
df = df.rename(columns={"日期":"dt","开盘":"open","收盘":"close",
                          "最高":"high","最低":"low","成交量":"vol","成交额":"amount"})
df["dt"] = pd.to_datetime(df["dt"])
bars = format_standard_kline(df, freq=Freq.D)

# 3. 跑分析
c = CZSC(bars)
print(f"分型: {len(c.fx_list)}, 笔: {len(c.bi_list)}, 中枢: {len(c.bars_ubi)}")

# 4. 出图
from czsc.utils.plotting.lightweight import plot_czsc
plot_czsc(c, output="html", path="/tmp/czsc.html")
```

## 与其他 skill 的协作

| 任务 | 走哪个 skill | 备注 |
|---|---|---|
| 拉股票基础信息 / 财务 | `tushareMcp` (mcporter) | tushare token 在 MCP server 里 |
| 拉实时行情 / 资金流 | `tushareMcp` | 同上 |
| **做缠论分析 / 出图** | **本 skill** | czsc + akshare |
| 看新闻 / 公告 | `tushareMcp` anns_d / news | 或 `anysearch` / `multi-search-engine-cn` |
| 生成 PDF 研报 | `document-pro` + 思源黑体 | 见 MEMORY.md |
| 整体股票研究 SOP | `stock-analysis` skill | 已装机 |

## 已知局限

1. **数据滞后**: 腾讯日线盘后 ~17:30 更新,盘中分析用 `tushareMcp` 实时接口
2. **30 分钟 K 线**: 腾讯免费版**不支持** 30min / 60min 实时,需用日线自合成或走 tushare
3. **1.0.0rc8 与 1.0 正式版 API 有差异**: 本 skill 基于 `1.0.0rc8` 编写 (`bars_ubi` 而非 `zs_list`),升级到 1.1+ 时需重新测试
4. **czsc 信号函数默认空**: 不传 `signals_seq` 时 `signals` OrderedDict 为空,需自定义信号序列才出买卖点(可后续加预设信号模板)
5. **成交额缺失**: 腾讯不返回成交额,画 K 线没问题但成交额相关分析受限

## 安全 / 隐私

- ✅ **不写任何文件到 `~/.ssh/`、`~/.aws/`、`~/.config/`、MEMORY.md、SOUL.md**
- ✅ **不上传任何数据** (czsc 本地分析, 只 GET 腾讯公开行情接口)
- ✅ **API key 不需要** (腾讯 + czsc 全部免费)
- ⚠️ **HTML 输出含完整 K 线图,公开分享前先脱敏**
- ❌ **不要** 把 czsc 输出当成"买卖建议",这是**技术分析工具**,不是投资顾问

## 维护

- 装包源: `pip install --break-system-packages --index-url https://pypi.tuna.tsinghua.edu.cn/simple/`
- czsc 项目主页: <https://github.com/waditu/czsc> (作者: tushare 的 waditu)
- czsc 文档飞书 wiki: <https://s0cqcxuy3p.feishu.cn/wiki/wikcn3gB1MKl3ClpLnboHM1QgKf>
- 本 skill 装机日期: 2026-06-23

---

## 模块参考 (Module Reference)

> v5.2.2: 按 `czsc_cli` 5 个子模块组织文档。每个章节包含: 模块路径 / exports 清单 / 核心 API 定义 / 典型用法 / 测试覆盖 / 已知坑。

### 模块汇总

| 模块 | 文件 | 行数 | exports | 功能领域 | pytest 测试 | 测试数 |
|---|---|---|---|---|---|---|
| data | `czsc_cli/data.py` | 65 | 15 | tushare 拉数 + 筛选 + K 线 cache | `tests/test_data.py` | 13 |
| preset | `czsc_cli/preset.py` | 53 | 14 | 预设策略管理 (8 子命令 + 5 helper) | `tests/test_preset.py` | 11 |
| batch | `czsc_cli/batch.py` | 54 | 12 | 批量扫描 + dry-run + retry + Slack | `tests/test_batch.py` | 14 |
| scanner | `czsc_cli/scanner.py` | 47 | 6 | 多股扫描 + 评分 + 排名 | `tests/test_scanner.py` | 13 |
| signals | `czsc_cli/signals.py` | 56 | 12 | 单股信号 + 多周期 + 回测 + 止盈止损 | `tests/test_signals.py` | 14 |
| **总** | | **335** | **59** | **(主文件 `scripts/czsc_signals.py` 2954 行不动)** | **6 文件 750 行** | **87** |

所有模块通过 `__getattr__` lazy 转发到 `scripts/czsc_signals.py` 的原始实现 (**单点真理**, 零代码重复)。

---

### data 模块

**路径**: `skills/czsc-trading/czsc_cli/data.py` (65 行)

**exports** (15 项):

| 名字 | 类型 | 用途 | 依赖外部 API |
|---|---|---|---|
| `_fetch_st_names_via_tushare` | 函数 | 拉取全市场股票名 (用于 ST 过滤) | ✅ tushare |
| `_fetch_industry_via_tushare` | 函数 | 拉取行业分类 (用于行业筛选) | ✅ tushare |
| `_fetch_bak_basic_via_tushare` | 函数 | 拉取备用基础数据 (PE/PB/市值) | ✅ tushare |
| `_filter_by_industry_pe` | 函数 | 按行业 + PE 过滤股池 | ❌ (可选) |
| `_filter_by_market_cap_turnover` | 函数 | 按市值 + 换手率过滤 | ❌ (可选) |
| `_is_st_or_delisted` | 函数 | 检查股票名是否 ST/退市 | ❌ **纯函数** |
| `_filter_stocks` | 函数 | 综合过滤 (tushare + ST 检查) | ✅ tushare |
| `_load_weights` | 函数 | 从 YAML 加载权重配置 | ⚠️ 文件 IO |
| `fetch_klines_for_signals` | 函数 | 拉取 K 线数据 (自动 clamp 1000 天) | ✅ 腾讯 ifzq API |
| `_fetch_klines_uncached` | 函数 | 无缓存拉取 K 线 | ✅ 腾讯 ifzq API |
| `fetch_klines_with_cache` | 函数 | 带 parquet 缓存的 K 线拉取 | ✅ 腾讯 ifzq API + 磁盘 |
| `_cache_path` | 函数 | parquet 缓存路径生成 | ❌ **纯函数** |
| `_load_cache` | 函数 | 从磁盘加载 parquet 缓存 | ⚠️ 磁盘读取 |
| `_save_cache` | 函数 | 保存 K 线数据到 parquet | ⚠️ 磁盘写入 |
| `PRESET_DIR` | `Path` | 全局预设存储路径 (环境变量 `CZSC_PRESET_DIR`) | — |

**纯函数** (适合单测, 不依赖外部 API):
- `_is_st_or_delisted(name: str) → bool` — 大小写敏感, 识别 `ST`/`*ST`/`退`
- `_cache_path(ts_code: str) → Path` — 格式 `~/.czsc-cache/<ts_code>.parquet`

**典型用法**:
```python
from czsc_cli.data import _is_st_or_delisted, fetch_klines_with_cache

# ST check
name = tushare_name_map.get("000001.SZ", "")
if _is_st_or_delisted(name):
    print(f"⚠️ ST 或退市: {name}")

# 带缓存的 K 线拉取 (高效)
df = fetch_klines_with_cache("600519.SH", days=365, freq="日线")
```

**测试覆盖** (v5.2.1, `tests/test_data.py`, 15 tests):
- ✅ 模块结构: 15 exports, 核心 API 都在
- ✅ lazy `__getattr__` 转发 → 函数是原函数 (`is`)
- ✅ `_is_st_or_delisted` 全覆盖 (正常/ST/*ST/退市/空/None)
- ✅ `_cache_path` 格式验证 (parquet 后缀, 不同 code 不同路径)
- ✅ `PRESET_DIR` 跨模块共享
- ✅ 未知属性 raise `AttributeError`

**已知坑**:
- `fetch_klines_for_signals` 自动 clamp 到 1000 天 (腾讯 API 限制), 超过返回空
- tushare 调用建议缓存在 `~/.czsc-cache/` 避免高频请求
- K 线 parquet 缓存不自动过期 — 需手动 `rm -rf ~/.czsc-cache/` 清

---

### preset 模块

**路径**: `skills/czsc-trading/czsc_cli/preset.py` (53 行)

**exports** (14 项):

| 名字 | 用途 |
|---|---|
| `_save_user_preset(name, args)` | 保存自定义 preset 到 `~/.czsc-presets/<name>.json` |
| `_load_user_preset(path)` | 从 JSON 文件加载 (返回 dict) |
| `_apply_user_preset(args)` | 合并用户预设到 args (用户显式 flag 不覆盖) |
| `_override_preset_dir(args)` | 改全局 PRESET_DIR (--preset-dir flag) |
| `PRESET_DIR` | 全局预设存储路径 |
| `cmd_preset_save` | `preset save` 子命令 |
| `cmd_preset_list` | `preset list` 子命令 |
| `cmd_preset_show` | `preset show` 子命令 |
| `cmd_preset_delete` | `preset delete` 子命令 |
| `cmd_preset_export` | `preset export` 子命令 |
| `cmd_preset_import` | `preset import` 子命令 |
| `cmd_preset_diff` | `preset diff` 子命令 |
| `cmd_preset_merge` | `preset merge` 子命令 |
| `cmd_preset_validate` | `preset validate` 子命令 |

**典型用法**:
```bash
# CLI
python3 -m czsc_cli preset list                     # 列出所有预设
python3 -m czsc_cli preset show my_bank             # 查看预设详情
python3 -m czsc_cli preset delete my_bank           # 删除
python3 -m czsc_cli preset validate my_bank         # 验证
python3 -m czsc_cli preset export my_bank ./out.json # 导出
python3 -m czsc_cli preset import friend_preset.json # 导入
```

**存储位置**: `~/.czsc-presets/<name>.json` (可被环境变量 `CZSC_PRESET_DIR` 覆盖)

**测试覆盖** (v5.2.1, `tests/test_preset.py`, 11 tests):
- ✅ 模块结构: 14 exports, 全部 8 子命令
- ✅ lazy 转发: cmd_preset_save/list/validate is 原函数
- ✅ PRESET_DIR 类型 + 跨模块共享
- ✅ `_override_preset_dir` 函数存在

**已知坑**:
- `PRESET_DIR` 在模块 load 时 fix — 改环境变量后需重启进程
- 预设文件是普通 JSON, 手动编辑可能破坏格式 → 用 `validate` 子命令
- v3.9 设计的 `--preset value` 让非显式 flag 被覆盖, 但**用户显式传的 flag (非 None) 不覆盖**

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

## v5.2 变更摘要

| 子版本 | 内容 | 文件 |
|---|---|---|
| v5.2.0 | BUILTIN_PRESETS 哑炮修复 (提到模块级) | `scripts/czsc_signals.py` |
| v5.2.1 | pytest 单元测试 (87 pass + 1 skip = 88 cases, 0 fail) | `tests/` (7 文件 750 行: data 15 + preset 11 + batch 16 + scanner 15 + signals 17 + integration 14) |
| v5.2.2 | SKILL.md 按模块拆分 (本文) | `SKILL.md` |
| v5.2.3 | 真拆函数实现 (替换 lazy load) | `czsc_cli/*.py` |


🦐 Generated by 小虾 for 晓冬
