# czsc 1.0.0rc8 API 速查

> ⚠️ 本 skill 基于 `czsc==1.0.0rc8` 编写。1.0 正式版 API 有差异 (`zs_list` → `bars_ubi`),升级前先看 GitHub release notes。

## 核心对象

```python
from czsc import CZSC, Freq, format_standard_kline
```

| 对象 | 字段 | 说明 |
|---|---|---|
| `RawBar` | dt / symbol / freq / open / high / low / close / vol / amount | 单根 K 线 |
| `NewBar` | 多周期合成后的新 K 线 | 由 BarGenerator 产出 |
| `FX` (分型) | mark / dt / high / low / fx_a / fx_b | 顶/底分型 |
| `BI` (笔) | direction / sdt / edt / high / low / fx_a / fx_b / fxs | 至少 5 根 K 线 |
| `bars_ubi` | elements / high / low | 整合后的"中枢"形态 |

## CZSC 对象常用属性

```python
c = CZSC(bars)

c.symbol               # str
c.freq                 # Freq 枚举 (D/W/M/F30/F5...)
c.bars_raw             # List[RawBar] (输入的 K 线)
c.bars_raw_df          # pd.DataFrame
c.fx_list              # List[FX] (分型)
c.bi_list              # List[BI] (笔,含延伸)
c.finished_bis         # List[BI] (已完成的笔)
c.bars_ubi             # List[NewBar] (中枢/段)
c.ubi                  # dict (最新一段的快照)
c.signals              # OrderedDict[str, Any] (信号触发结果)
```

## Freq 枚举

| 枚举 | 含义 |
|---|---|
| `Freq.D` | 日线 |
| `Freq.W` | 周线 |
| `Freq.M` | 月线 |
| `Freq.F1` / `F5` / `F15` / `F30` / `F60` | 1/5/15/30/60 分钟 |

## akshare 数据转换模板

```python
import akshare as ak
import pandas as pd
from czsc import Freq, format_standard_kline

df = ak.stock_zh_a_hist(
    symbol="000001",
    period="daily",       # daily / weekly / monthly
    start_date="20240101",
    end_date="20260623",
    adjust="qfq",         # qfq 前复权 / hfq 后复权 / "" 不复权
)

df = df.rename(columns={
    "日期":"dt", "开盘":"open", "收盘":"close",
    "最高":"high", "最低":"low", "成交量":"vol", "成交额":"amount",
})
df["dt"] = pd.to_datetime(df["dt"])
df["symbol"] = "000001"

# 必须的列顺序
df = df[["dt","symbol","open","close","high","low","vol","amount"]]

bars = format_standard_kline(df, freq=Freq.D)
c = CZSC(bars)
```

## 可视化 (self-contained HTML)

```python
from czsc.utils.plotting.lightweight import plot_czsc

plot_czsc(c, output="html", path="/tmp/czsc.html")
# 单文件 HTML, 离线可打开, 浏览器交互 (缩放/十字光标/多周期叠加)
```

## 信号函数 (默认空,需自定义)

```python
# 定义信号序列
signals_seq = [
    "czsc._native.signals.bar.bar_end_V230331",
    "czsc._native.signals.cxt.cxt_bi_status_V230101",
]

from czsc import generate_czsc_signals, get_signals_config, get_signals_freqs

freqs = get_signals_freqs(signals_seq)
config = get_signals_config(signals_seq)
results = generate_czsc_signals(bars, signals_seq)
```

## CzscTrader (多周期联立决策)

```python
from czsc import CzscTrader
# 需要先准备 signals_seq + pos_seq (仓位规则)
trader = CzscTrader(bars, signals_seq, pos_seq)
print(trader.positions)  # 决策点
```

## 回测

```python
from czsc import WeightBacktest
# 配合 wbt 包使用
wb = WeightBacktest(dfw, fee_rate=0.0002)
print(wb.stats)
```

## 常见错误

| 错误 | 原因 | 解决 |
|---|---|---|
| `AttributeError: 'CZSC' has no attribute 'zs_list'` | 1.0+ 把中枢改名为 `bars_ubi` | 用 `c.bars_ubi` |
| `K 线数量不足` | bars < 50 根 | 拉更多天数 |
| `Rust 编译错误` | Python < 3.10 + 源码构建 | 装 Python 3.10+,或用预编译 wheel |
| `Empty klines` | 腾讯接口返回 qfqday+day 都是空 | 检查 ts_code 格式 (000001.SZ / 600519.SH) |
| `signal count = 0` | bars 太少 (< init_n=200) | 加大 --days 参数 |

## 信号函数 (czsc 1.0 native, 222 个内置)

本 skill 精选了 **11 个核心信号** 在 `czsc_signals.py`:

```python
from czsc._native import generate_czsc_signals

config = [
    {"name": "cxt_first_buy_V221126", "freq": "日线", "di": 1, "params": {}},
    {"name": "cxt_first_sell_V221126", "freq": "日线", "di": 1, "params": {}},
    {"name": "cxt_second_bs_V240524", "freq": "日线", "di": 1, "params": {}},
    {"name": "cxt_third_buy_V230228", "freq": "日线", "di": 1, "params": {}},
    {"name": "bar_td9_V240616", "freq": "日线", "di": 1, "params": {}},
    {"name": "tas_macd_first_bs_V221201", "freq": "日线", "di": 1, "params": {}},
    {"name": "tas_macd_second_bs_V221201", "freq": "日线", "di": 1, "params": {}},
    {"name": "tas_macd_bc_V221201", "freq": "日线", "di": 1, "params": {}},
    {"name": "tas_double_ma_V230511", "freq": "日线", "di": 1, "params": {}},
    {"name": "pressure_support_V240222", "freq": "日线", "di": 1, "params": {}},
    {"name": "byi_second_bs_V230324", "freq": "日线", "di": 1, "params": {}},
]

results = generate_czsc_signals(bars, config, sdt='20240101', init_n=200, df=True)
# 返回 DataFrame: 每个信号一列,每行一天,value 是信号状态
```

**结果 value 格式**: `"类型_详情_详情_分数"`,例:
- `其他_任意_任意_0` — 未触发
- `一买_17笔_任意_0` — 一买触发,17 笔触底
- `买点_9转_任意_0` — TD9 买点
- `卖点_9转_任意_0` — TD9 卖点

**筛选触发行**:
```python
sig_col = "日线_D1B_BUY1"
triggered = results[~results[sig_col].str.startswith("其他")]
```

## 进阶参考

- czsc 飞书 wiki: <https://s0cqcxuy3p.feishu.cn/wiki/wikcn3gB1MKl3ClpLnboHM1QgKf>
- czsc 项目主页: <https://github.com/waditu/czsc>
- czsc_skills (官方示例): <https://github.com/zengbin93/czsc_skills>
