#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""czsc_cli.signals v5.2.3.3 — 信号层 (单股 + multi-freq + backtest).

v5.2.3.3 真拆: 替代 v5.1 __getattr__ lazy 转发, 直接实现在这里.
czsc_signals.py 里这些函数改为 `from czsc_cli.signals import ...`, 保持向后兼容 + `is` 关系.

包含:
  - 4 module-level 常量: CORE_BS_SIGNALS / AUX_SIGNALS / ALL_SIGNALS / SIGNAL_GROUPS
  - 4 单股函数: run_signals / cmd_signals / cmd_events / cmd_summary
  - 3 multi-freq 函数: resample_to_freq / run_multi_freq_signals / cmd_multi_freq
  - 4 backtest 函数: build_weight_with_stops / run_weight_backtest / format_bt_result / cmd_backtest

不依赖 preset/batch/scanner, 只依赖:
  - czsc_cli.data.fetch_klines_for_signals (data 域)
  - czsc.format_standard_kline, czsc.WeightBacktest (第三方缠论库)
  - czsc._native.generate_czsc_signals (第三方缠论库)
"""
import sys
from typing import Any

import pandas as pd

# v5.2.3.3: 从 data 域拉 K 线 (跨域依赖, 但 signals → data 是单向, 无循环)
from czsc_cli.data import fetch_klines_for_signals




# ---------------------------------------------------------------------------
# v5.2.3.3: 信号模板 + 单股命令 (从 czsc_signals 真拆)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------

CORE_BS_SIGNALS = [
    {
        "name": "cxt_first_buy_V221126",
        "alias": "一买",
        "description": "第一类买点 — 下跌趋势底背驰后的转折点",
        "freq": "日线",
        "di": 1,
    },
    {
        "name": "cxt_first_sell_V221126",
        "alias": "一卖",
        "description": "第一类卖点 — 上涨趋势顶背驰后的转折点",
        "freq": "日线",
        "di": 1,
    },
    {
        "name": "cxt_second_bs_V240524",
        "alias": "二买卖",
        "description": "第二类买卖点 — 一买/一卖后回调不破前低/前高",
        "freq": "日线",
        "di": 1,
    },
    {
        "name": "cxt_third_buy_V230228",
        "alias": "三买",
        "description": "第三类买点 — 突破中枢后回踩不进中枢",
        "freq": "日线",
        "di": 1,
    },
]

AUX_SIGNALS = [
    {
        "name": "bar_td9_V240616",
        "alias": "TD9",
        "description": "神奇九转 — 连续 9 日 TD 序列反转信号",
        "freq": "日线",
        "di": 1,
    },
    {
        "name": "tas_macd_first_bs_V221201",
        "alias": "MACD一买",
        "description": "MACD 一类买点 — DIF 底背驰",
        "freq": "日线",
        "di": 1,
    },
    {
        "name": "tas_macd_second_bs_V221201",
        "alias": "MACD二买",
        "description": "MACD 二类买点 — 金叉后回踩零轴",
        "freq": "日线",
        "di": 1,
    },
    {
        "name": "tas_macd_bc_V221201",
        "alias": "MACD背驰",
        "description": "MACD 顶/底背驰",
        "freq": "日线",
        "di": 1,
    },
    {
        "name": "tas_double_ma_V230511",
        "alias": "双均线",
        "description": "双均线交叉状态",
        "freq": "日线",
        "di": 1,
    },
    {
        "name": "pressure_support_V240222",
        "alias": "支撑压力",
        "description": "支撑位/压力位验证",
        "freq": "日线",
        "di": 1,
    },
    {
        "name": "byi_second_bs_V230324",
        "alias": "笔翼二买",
        "description": "笔翼二类买点",
        "freq": "日线",
        "di": 1,
    },
]

ALL_SIGNALS = CORE_BS_SIGNALS + AUX_SIGNALS

# v4.2: 信号组合别名 — 用 1 个名字代替 1 组信号, 简化 --signal 参数
# key: 别名 (英文短名, 方便在命令行打字)
# value: dict { "description": 中文, "signals": [信号 alias 列表] }
SIGNAL_GROUPS = {
    "all_long": {
        "description": "所有买入类信号 (一买+二买+三买+MACD一买+MACD二买+笔翼二买)",
        "signals": ["一买", "二买", "三买", "MACD一买", "MACD二买", "笔翼二买"],
    },
    "all_short": {
        "description": "所有卖出类信号 (一卖+二卖+三卖+MACD一卖+MACD二卖)",
        "signals": ["一卖", "二卖", "三卖", "MACD一卖", "MACD二卖"],
    },
    "bs_core": {
        "description": "核心买卖点 (一买+一卖+二买+二卖+三买+三卖)",
        "signals": ["一买", "一卖", "二买", "二卖", "三买", "三卖"],
    },
    "bs1": {
        "description": "一买一卖 (同周期纯趋势信号)",
        "signals": ["一买", "一卖"],
    },
    "momentum": {
        "description": "动量类 (MACD一买+MACD二买+MACD背驰+双均线)",
        "signals": ["MACD一买", "MACD二买", "MACD背驰", "双均线"],
    },
    "reversal": {
        "description": "反转类 (TD9+支撑压力+笔翼二买)",
        "signals": ["TD9", "支撑压力", "笔翼二买"],
    },
}


# ---------------------------------------------------------------------------
# v3.5: 信号权重表 (用于 scan subcommand 打分)
# 设计原则: 核心反转点权重大, 辅助验证权重小
# v5.2.3.1: SIGNAL_WEIGHTS + RECENCY_BONUS 移到了 czsc_cli.data 模块级 (打破循环 import),
#            上方 `from czsc_cli.data import ...` 已经 re-export 了.
# ---------------------------------------------------------------------------




# ---------------------------------------------------------------------------
# 信号生成
# ---------------------------------------------------------------------------

def run_signals(ts_code: str, signal_aliases: list, days: int = 500):
    """跑指定信号, 返回 (results_df, signal_alias_map)"""
    from czsc._native import generate_czsc_signals

    bars, raw_df = fetch_klines_for_signals(ts_code, days=days)

    # 找信号定义
    alias_to_def = {s["alias"]: s for s in ALL_SIGNALS}
    if signal_aliases == ["all"]:
        selected = ALL_SIGNALS
    else:
        selected = [alias_to_def[a] for a in signal_aliases if a in alias_to_def]
        unknown = [a for a in signal_aliases if a not in alias_to_def]
        if unknown:
            raise ValueError(f"未知信号: {unknown}. 可用: {list(alias_to_def.keys())}")

    # 构造 signals_config (name + freq + di + params)
    signals_config = [{"name": s["name"], "freq": s["freq"], "di": s["di"], "params": {}}
                       for s in selected]

    # sdt = 信号开始计算日期, 默认从 2018 开始 (足够历史)
    # init_n = 预热 K 线 (默认 200 根足够老算法稳定)
    sdt = raw_df['dt'].iloc[0].strftime('%Y%m%d') if len(raw_df) > 0 else "20180101"
    results = generate_czsc_signals(bars, signals_config, sdt=sdt,
                                     init_n=200, df=True)
    return results, selected, raw_df


# ---------------------------------------------------------------------------
# 命令实现
# ---------------------------------------------------------------------------

def cmd_signals(args):
    """检测信号, 默认输出最近触发的关键事件"""
    print(f"[fetch] {args.ts_code} ...", file=sys.stderr)
    results, selected, raw_df = run_signals(args.ts_code,
                                              args.signal or ["all"],
                                              days=args.days)
    print(f"[fetch] {len(raw_df)} K 线, 区间 {raw_df['dt'].iloc[0].date()} → {raw_df['dt'].iloc[-1].date()}",
          file=sys.stderr)

    # 信号列 = selected 的 key (去掉后缀 _B_BUY1 等)
    sig_cols = [col for col in results.columns if col.startswith(('日线_', '周线_', '月线_'))]
    print(f"[signals] 检测到 {len(sig_cols)} 个信号\n", file=sys.stderr)

    # 找最近 30 天的关键事件
    recent = results.tail(30)
    print(f"=== {args.ts_code} 最近 30 天信号状态 ===\n")
    print(f"{'日期':<12} {'收盘':>7}", end="")
    for col in sig_cols:
        short = col.split('_')[-1]  # BUY1 / SELL1 等
        print(f"  {short:>6}", end="")
    print()
    print("-" * (20 + 8 * len(sig_cols)))

    for _, row in recent.iterrows():
        dt_raw = row['dt']
        dt_str = pd.Timestamp(dt_raw).strftime('%m-%d') if not isinstance(dt_raw, str) else dt_raw[5:10]
        close = float(row['close'])
        print(f"{dt_str:<12} {close:>7.2f}", end="")
        for col in sig_cols:
            val = str(row[col])
            mark = "🟢" if "买" in val else "🔴" if "卖" in val else "·"
            print(f"  {mark:>6}", end="")
        print()

    # 统计触发次数
    print(f"\n=== 信号触发统计 (全部 {len(results)} 天) ===\n")
    for col in sig_cols:
        triggered = results[~results[col].str.startswith('其他', na=False)]
        if len(triggered) > 0:
            last_dt_raw = triggered['dt'].iloc[-1]
            last_dt = pd.Timestamp(last_dt_raw).strftime('%Y-%m-%d') if not isinstance(last_dt_raw, str) else last_dt_raw[:10]
            print(f"  {col}: 触发 {len(triggered)} 次, 最近 {last_dt}")
        else:
            print(f"  {col}: 未触发")


def cmd_events(args):
    """只输出触发事件"""
    print(f"[fetch] {args.ts_code} ...", file=sys.stderr)
    results, selected, raw_df = run_signals(args.ts_code,
                                              args.signal or ["all"],
                                              days=args.days)

    sig_cols = [col for col in results.columns if col.startswith(('日线_', '周线_', '月线_'))]
    print(f"\n=== {args.ts_code} 触发事件 ({len(results)} 天) ===\n")

    # 找所有非 "其他_..." 的值
    triggered = results[~results[[c for c in sig_cols]].apply(
        lambda row: all(str(v).startswith('其他') for v in row), axis=1
    )]
    print(f"触发事件行数: {len(triggered)}")

    for _, row in triggered.iterrows():
        dt_raw = row['dt']
        dt_str = pd.Timestamp(dt_raw).strftime('%Y-%m-%d') if not isinstance(dt_raw, str) else dt_raw[:10]
        close = float(row['close'])
        for col in sig_cols:
            val = str(row[col])
            if not val.startswith('其他'):
                short = col.split('_')[-1]
                print(f"  {dt_str}  ¥{close:.2f}  [{short}] {val}")


def cmd_summary(args):
    """统计每个信号的触发频次"""
    print(f"[fetch] {args.ts_code} ...", file=sys.stderr)
    results, selected, raw_df = run_signals(args.ts_code,
                                              args.signal or ["all"],
                                              days=args.days)

    sig_cols = [col for col in results.columns if col.startswith(('日线_', '周线_', '月线_'))]

    print(f"\n=== {args.ts_code} 信号摘要 ===\n")
    print(f"{'信号':<32} {'触发次数':>8}  {'最近触发日期':>12}  {'描述'}")
    print("-" * 90)
    for col, sig_def in zip(sig_cols, selected):
        triggered = results[~results[col].str.startswith('其他', na=False)]
        if len(triggered) > 0:
            last_dt_raw = triggered['dt'].iloc[-1]
            last_dt = pd.Timestamp(last_dt_raw).strftime('%Y-%m-%d') if not isinstance(last_dt_raw, str) else last_dt_raw[:10]
            n = len(triggered)
        else:
            last_dt = "—"
            n = 0
        desc = sig_def["description"][:30] + ("..." if len(sig_def["description"]) > 30 else "")
        print(f"{sig_def['alias']+' ['+sig_def['name']+']':<32} {n:>8}  {last_dt:>12}  {desc}")


# ---------------------------------------------------------------------------
# v3.5: 多股扫描 + 信号打分排名

# ---------------------------------------------------------------------------
# v5.2.3.3: 多周期支持 (从 czsc_signals 真拆)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------

def resample_to_freq(raw_df: pd.DataFrame, target_freq: str) -> pd.DataFrame:
    """日线 K 线 → 周线/月线

    target_freq: '周线' (W) / '月线' (ME, pandas 3.0+)
    """
    df = raw_df.copy()
    df["dt"] = pd.to_datetime(df["dt"])
    # pandas 3.0+: M → ME
    rule = "W" if target_freq == "周线" else "ME"
    df_r = df.set_index("dt").resample(rule).agg({
        "symbol": "first",
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "vol": "sum",
        "amount": "sum",
    }).dropna().reset_index()
    return df_r


def run_multi_freq_signals(ts_code: str, freqs: list, signal_aliases: list, days: int = 500):
    """多周期信号扫描

    freqs: ['日线', '周线', '月线'] 任选
    """
    from czsc._native import generate_czsc_signals
    from czsc import format_standard_kline

    # 1. 拉日线 (基础)
    bars_d, raw_df = fetch_klines_for_signals(ts_code, days=days)

    # 2. 找信号定义
    alias_to_def = {s["alias"]: s for s in ALL_SIGNALS}
    if signal_aliases == ["all"]:
        selected = ALL_SIGNALS
    else:
        selected = [alias_to_def[a] for a in signal_aliases if a in alias_to_def]

    all_results = {}

    for freq in freqs:
        # 准备 bars
        if freq == "日线":
            bars = bars_d
            init_n = 200
        elif freq == "周线":
            df_w = resample_to_freq(raw_df, "周线")
            if len(df_w) < 30:
                print(f"  [skip] 周线 K 线 {len(df_w)} 不足 30, 跳过")
                continue
            bars = format_standard_kline(df_w, freq="周线")
            init_n = 20  # 周线预热少点
        elif freq == "月线":
            df_m = resample_to_freq(raw_df, "月线")
            if len(df_m) < 12:
                print(f"  [skip] 月线 K 线 {len(df_m)} 不足 12, 跳过")
                continue
            bars = format_standard_kline(df_m, freq="月线")
            init_n = 8  # 月线预热再少
        else:
            print(f"  [skip] 未知周期: {freq}")
            continue

        # 配置 (改 freq 字段)
        config = [{"name": s["name"], "freq": freq, "di": s["di"], "params": {}}
                  for s in selected]

        sdt = raw_df["dt"].iloc[0].strftime("%Y%m%d") if hasattr(raw_df["dt"].iloc[0], "strftime") else "20180101"
        try:
            results = generate_czsc_signals(bars, config, sdt=sdt, init_n=init_n, df=True)
            all_results[freq] = results
        except Exception as e:
            print(f"  [error] {freq}: {e}")

    return all_results, selected


def cmd_multi_freq(args):
    """多周期信号扫描: 日线 + 周线 + 月线 同表展示"""
    print(f"[fetch] {args.ts_code} ...", file=sys.stderr)
    freqs = args.freqs.split(",") if args.freqs else ["日线", "周线", "月线"]
    all_results, selected = run_multi_freq_signals(
        args.ts_code, freqs, args.signal or ["all"], days=args.days
    )

    if not all_results:
        print("[ERROR] 没有周期产生结果")
        return

    print(f"\n=== {args.ts_code} 多周期信号摘要 ===\n")
    print(f"{'信号':<14}  {'日线':<22}  {'周线':<22}  {'月线':<22}")
    print("-" * 84)

    # 按 selected 顺序: signals_config 顺序 → 结果列顺序
    # 拿 freq 下所有信号列 (按 columns 顺序, 与 config 一致)
    freq_sig_cols = {}
    for freq in ["日线", "周线", "月线"]:
        if freq not in all_results:
            continue
        res = all_results[freq]
        # 信号列 = 以 {freq}_ 开头 且不是 dt/close/open 等基础字段
        base_cols = {'dt', 'symbol', 'close', 'open', 'high', 'low', 'vol', 'amount', 'id', 'freq'}
        cols = [c for c in res.columns if c.startswith(f"{freq}_") and c not in base_cols]
        freq_sig_cols[freq] = cols

    for i, sig in enumerate(selected):
        line = f"{sig['alias']:<14}"
        for freq in ["日线", "周线", "月线"]:
            if freq not in freq_sig_cols or i >= len(freq_sig_cols[freq]):
                line += f"  {'N/A':<22}"
                continue
            sig_col = freq_sig_cols[freq][i]
            res = all_results[freq]
            triggered = res[~res[sig_col].str.startswith("其他", na=False)]
            if len(triggered) > 0:
                last_dt_raw = triggered["dt"].iloc[-1]
                last_dt = pd.Timestamp(last_dt_raw).strftime("%Y-%m-%d") if not isinstance(last_dt_raw, str) else last_dt_raw[:10]
                line += f"  {len(triggered)}次/{last_dt:<10}"
            else:
                line += f"  0次/{'—':<10}"
        print(line)

    # 详细信息
    print(f"\n--- 详细触发列表 ---\n")
    for freq, res in all_results.items():
        print(f"[{freq}]")
        sig_cols = [c for c in res.columns if c.startswith(f"{freq}_")]
        for col in sig_cols:
            triggered = res[~res[col].str.startswith("其他", na=False)]
            if len(triggered) > 0:
                for _, row in triggered.tail(5).iterrows():
                    dt_raw = row["dt"]
                    dt_str = pd.Timestamp(dt_raw).strftime("%Y-%m-%d") if not isinstance(dt_raw, str) else dt_raw[:10]
                    close = float(row["close"])
                    val = str(row[col])
                    short = col.split("_")[-1]
                    print(f"  {dt_str}  ¥{close:.2f}  [{short}] {val}")
        print()




# ---------------------------------------------------------------------------
# 止盈止损回测 (v3.1) — 触发 → 止盈/止损/时间止损

# ---------------------------------------------------------------------------
# v5.2.3.3: 止盈止损回测 (从 czsc_signals 真拆)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------

def build_weight_with_stops(raw_df, trigger_indices, max_hold, 
                            stop_loss=None, take_profit=None):
    """根据触发集合 + 止盈止损/时间止损, 生成 weight 序列
    
    Args:
        raw_df: 含 close 的 DataFrame
        trigger_indices: 触发日在 raw_df 中的行号集合
        max_hold: 最长持仓天数
        stop_loss: 止损比例 (e.g. -0.05 亏 5% 平仓), None 不启用
        take_profit: 止盈比例 (e.g. 0.10 赚 10% 平仓), None 不启用
    
    Returns:
        list[int]: weight 序列 (0/1)
    
    规则:
        - 触发日 T: 不交易
        - 次日 T+1: 建仓 (weight=1)
        - 持仓期:
            - 跌至 entry * (1 + stop_loss)  → 即时平仓
            - 涨至 entry * (1 + take_profit) → 即时平仓
            - 持仓 >= max_hold 天            → 时间止损平仓
        - 持仓期内不重复建仓 (等平仓后才接受下一个信号)
    """
    n = len(raw_df)
    weights = [0] * n
    closes = raw_df["close"].astype(float).values
    
    in_pos = False
    entry_idx = -1
    entry_price = 0.0
    
    for i in range(n):
        # 平仓后允许接收下一个信号
        if not in_pos and (i - 1) in trigger_indices and i > 0:
            in_pos = True
            entry_idx = i
            entry_price = closes[i]
        
        if in_pos:
            cur_pnl = (closes[i] - entry_price) / entry_price if entry_price else 0
            days_held = i - entry_idx
            
            should_close = False
            reason = ""
            if stop_loss is not None and cur_pnl <= stop_loss:
                should_close = True
                reason = f"止损@{cur_pnl:.2%}"
            elif take_profit is not None and cur_pnl >= take_profit:
                should_close = True
                reason = f"止盈@{cur_pnl:.2%}"
            elif days_held >= max_hold:
                should_close = True
                reason = f"时间止损@{days_held}天"
            
            if should_close:
                weights[i] = 0
                in_pos = False
            else:
                weights[i] = 1
    return weights


def run_weight_backtest(raw_df, weights, ts_code, fee_rate=0.0002):
    """跑一次 WeightBacktest, 返回 stats + pairs"""
    from czsc import WeightBacktest
    df_w = pd.DataFrame({
        "dt": raw_df["dt"],
        "symbol": ts_code.split(".")[0],
        "weight": weights,
        "price": raw_df["close"].astype(float),
    })
    wb = WeightBacktest(df_w, fee_rate=fee_rate)
    return wb


def format_bt_result(wb, n_triggered):
    """格式化回测结果"""
    stats = wb.stats
    return {
        "trades": len(wb.pairs),
        "triggered": n_triggered,
        "win_rate": stats.get("交易胜率", 0),
        "total_return": stats.get("绝对收益", 0),
        "yearly_return": stats.get("年化收益", 0),
        "max_drawdown": stats.get("最大回撤", 0),
        "sharpe": stats.get("夏普比率", 0),
        "avg_hold": stats.get("持仓K线数", 0),
    }


def cmd_backtest(args):
    """信号回测: 触发→建仓→N日/止损/止盈/时间止损 平仓"""
    print(f"[fetch] {args.ts_code} ...", file=sys.stderr)

    from czsc._native import generate_czsc_signals  # 局部 import
    from czsc import WeightBacktest  # 局部 import

    # 1. 拉 K 线
    bars, raw_df = fetch_klines_for_signals(args.ts_code, days=args.days)
    raw_df = raw_df.copy()
    raw_df["dt"] = pd.to_datetime(raw_df["dt"])
    raw_df = raw_df.sort_values("dt").reset_index(drop=True)
    
    # 2. 找信号
    alias_to_def = {s["alias"]: s for s in ALL_SIGNALS}
    selected = [alias_to_def[a] for a in (args.signal or ["all"]) if a in alias_to_def]
    if args.signal == ["all"] or not args.signal:
        selected = ALL_SIGNALS
    
    # 3. 跑 signals
    config = [{"name": s["name"], "freq": "日线", "di": s["di"], "params": {}} for s in selected]
    sdt = raw_df["dt"].iloc[0].strftime("%Y%m%d")
    results = generate_czsc_signals(bars, config, sdt=sdt, init_n=200, df=True)
    
    # 4. 提取信号列
    base_ohlcv = {"open", "high", "low", "close", "vol", "amount", "id", "dt", "freq", "symbol"}
    sig_cols = []
    for c in results.columns:
        if c.startswith("日线_"):
            token = c[len("日线_"):]
            first = token.split("_")[0].lower()
            if first not in base_ohlcv:
                sig_cols.append(c)
    print(f"[backtest] 检出 {len(sig_cols)} 个信号列", file=sys.stderr)
    
    # 5. 策略 A: N 日固定平仓
    max_hold_a = args.hold_days
    
    # 6. 策略 B: 止盈止损 (如果用户指定)
    use_stops = (args.stop_loss is not None or args.take_profit is not None
                 or args.max_hold_days is not None)
    max_hold_b = args.max_hold_days if args.max_hold_days else args.hold_days
    
    print(f"\n=== {args.ts_code} 信号回测 (回看 {args.days} 天, 基础持仓 {args.hold_days} 日) ===\n")
    
    if use_stops:
        print(f"策略 A: N日固定平仓 ({max_hold_a} 日)")
        print(f"策略 B: 止损 {args.stop_loss or '关'} / 止盈 {args.take_profit or '关'} "
              f"/ 时间止损 {max_hold_b} 日")
        print()
        print(f"{'信号':<10} {'策略':<6} {'触发':>4} {'笔数':>4}  {'胜率':>6}  "
              f"{'绝对收益':>9}  {'年化收益':>9}  {'最大回撤':>9}  {'夏普':>6}  {'平均持仓':>7}")
        print("-" * 95)
    else:
        print(f"{'信号':<10} {'触发':>4} {'笔数':>4}  {'胜率':>6}  "
              f"{'绝对收益':>9}  {'年化收益':>9}  {'最大回撤':>9}  {'夏普':>6}  {'平均持仓':>7}")
        print("-" * 88)
    
    for i, sig_def in enumerate(selected):
        if i >= len(sig_cols):
            continue
        sig_col = sig_cols[i]
        alias = sig_def["alias"]
        
        triggered = results[~results[sig_col].str.startswith("其他", na=False)]
        if len(triggered) == 0:
            print(f"  {alias:<10}  无触发")
            continue
        
        trigger_dates = set(pd.to_datetime(triggered["dt"]).dt.date)
        raw_dates = raw_df["dt"].dt.date.values
        trig_indices = set(i for i, d in enumerate(raw_dates) if d in trigger_dates)
        
        # 策略 A: N 日固定平仓
        weights_a = [0] * len(raw_df)
        for trig_idx in trig_indices:
            for j in range(trig_idx + 1, min(trig_idx + max_hold_a + 1, len(raw_df))):
                weights_a[j] = 1
        wb_a = run_weight_backtest(raw_df, weights_a, args.ts_code, fee_rate=args.fee_rate)
        r_a = format_bt_result(wb_a, len(trig_indices))
        
        if use_stops:
            # 策略 B: 止盈止损
            weights_b = build_weight_with_stops(
                raw_df, trig_indices, max_hold_b,
                stop_loss=args.stop_loss, take_profit=args.take_profit
            )
            wb_b = run_weight_backtest(raw_df, weights_b, args.ts_code, fee_rate=args.fee_rate)
            r_b = format_bt_result(wb_b, len(trig_indices))
            
            # 打印 A
            print(f"  {alias:<10}  {'A':<6} {r_a['triggered']:>4} {r_a['trades']:>4}  "
                  f"{r_a['win_rate']:>5.1%}  {r_a['total_return']:>8.2%}  "
                  f"{r_a['yearly_return']:>8.1%}  {r_a['max_drawdown']:>8.2%}  "
                  f"{r_a['sharpe']:>5.2f}  {r_a['avg_hold']:>6.1f}")
            # 打印 B
            print(f"  {'':<10}  {'B':<6} {r_b['triggered']:>4} {r_b['trades']:>4}  "
                  f"{r_b['win_rate']:>5.1%}  {r_b['total_return']:>8.2%}  "
                  f"{r_b['yearly_return']:>8.1%}  {r_b['max_drawdown']:>8.2%}  "
                  f"{r_b['sharpe']:>5.2f}  {r_b['avg_hold']:>6.1f}")
            
            # 对比行
            delta_ret = r_b['total_return'] - r_a['total_return']
            delta_sharpe = r_b['sharpe'] - r_a['sharpe']
            print(f"  {'':<10}  {'Δ':<6} {'':>4} {'':>4}  {'':>6}  "
                  f"{delta_ret:>+8.2%}  {'':>8}  {'':>8}  {delta_sharpe:>+5.2f}  "
                  f"{r_b['avg_hold']-r_a['avg_hold']:>+6.1f}")
            print()
        else:
            print(f"  {alias:<10}  {r_a['triggered']:>4} {r_a['trades']:>4}  "
                  f"{r_a['win_rate']:>5.1%}  {r_a['total_return']:>8.2%}  "
                  f"{r_a['yearly_return']:>8.1%}  {r_a['max_drawdown']:>8.2%}  "
                  f"{r_a['sharpe']:>5.2f}  {r_a['avg_hold']:>6.1f}")
    
    # 详细
    if getattr(args, 'detail', False):
        print(f"\n--- 详细交易记录 (策略 A: N日固定平仓) ---\n")
        for i, sig_def in enumerate(selected):
            if i >= len(sig_cols):
                continue
            sig_col = sig_cols[i]
            alias = sig_def["alias"]
            
            triggered = results[~results[sig_col].str.startswith("其他", na=False)]
            if len(triggered) == 0:
                continue
            trigger_dates = set(pd.to_datetime(triggered["dt"]).dt.date)
            raw_dates = raw_df["dt"].dt.date.values
            trig_indices = set(i for i, d in enumerate(raw_dates) if d in trigger_dates)
            
            weights = [0] * len(raw_df)
            for trig_idx in trig_indices:
                for j in range(trig_idx + 1, min(trig_idx + max_hold_a + 1, len(raw_df))):
                    weights[j] = 1
            wb = run_weight_backtest(raw_df, weights, args.ts_code, fee_rate=args.fee_rate)
            pairs = wb.pairs
            if len(pairs) == 0:
                continue
            print(f"[{alias}]")
            print(pairs[['symbol', '交易方向', '开仓时间', '平仓时间', 
                         '开仓价格', '平仓价格', '盈亏比例', '持仓天数']].to_string())
            print()

# ---------------------------------------------------------------------------
# v3.3: 本地缓存 (parquet) — 避免重复拉 tushare


# ---------------------------------------------------------------------------
# v5.2.3.4: cmd_list 迁到 signals 域 (列信号逻辑属于 signals 域, v5.2.3.3 漏了)
# ---------------------------------------------------------------------------

def cmd_list(_args):
    """列出所有可用信号"""
    print("=== 核心买卖点 (4) ===\n")
    for s in CORE_BS_SIGNALS:
        print(f"  {s['alias']:<10}  {s['name']:<30}  {s['description']}")
    print(f"\n=== 辅助信号 ({len(AUX_SIGNALS)}) ===\n")
    for s in AUX_SIGNALS:
        print(f"  {s['alias']:<10}  {s['name']:<30}  {s['description']}")
    # v4.2: 信号组合别名
    print(f"\n=== v4.2 信号组别名 ({len(SIGNAL_GROUPS)} 个) ===\n")
    for gid, g in SIGNAL_GROUPS.items():
        print(f"  {gid:<12}  → {', '.join(g['signals'])}")
        print(f"  {'':<12}    {g['description']}")
    print(f"\n共 {len(ALL_SIGNALS)} 个信号 + {len(SIGNAL_GROUPS)} 个组别名. 用法:")
    print(f"  signals --ts-code 000001.SZ --signal 一买 一卖 三买")
    print(f"  signals --ts-code 000001.SZ --signal all")
    print(f"  scan --watchlist x --signal all_long       # v4.2: 所有买入类")
    print(f"  scan --watchlist x --signal momentum        # v4.2: 动量类")
    print(f"  events --ts-code 000001.SZ --signal all")
