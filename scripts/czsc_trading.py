#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
czsc-trading CLI — 缠论技术分析工具 (Python wrapper for OpenClaw skill)

数据源: akshare (免费,无需 token)
分析库: czsc 1.0.0rc8 (Rust 加速, 246 个信号函数)
可视化: plotly → self-contained HTML

依赖:
  pip install --break-system-packages --index-url https://pypi.tuna.tsinghua.edu.cn/simple/ "czsc==1.0.0rc8" akshare

命令:
  analyze --ts-code 000001.SZ --days 250 --freq D --output /tmp/p.html
      完整缠论分析: 分型/笔/中枢 + 多周期信号叠加 + HTML 可视化

  signals --ts-code 000001.SZ
      只看买卖信号 (signals OrderedDict 摘要),文本输出

  report --ts-code 000001.SZ --output /tmp/report.html
      同 analyze 但额外输出 Markdown 文本摘要到 stdout

  doc
      打印 SKILL.md 摘要 + 命令清单

数据列映射 (akshare → czsc RawBar):
  日期 → dt
  开盘 → open
  收盘 → close
  最高 → high
  最低 → low
  成交量 → vol
  成交额 → amount
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

# czsc imports — Rust 加速版,Python 3.10+ 才支持
from czsc import CZSC, Freq, format_standard_kline
from czsc.utils.plotting.lightweight import plot_czsc


# ---------------------------------------------------------------------------
# 数据获取 (akshare 免费源)
# ---------------------------------------------------------------------------

def fetch_klines(ts_code: str, days: int = 250, freq: str = "D") -> "pd.DataFrame":
    """拉日 K 线 (默认走腾讯 ifzq.gtimg.cn, akshare fallback)

    腾讯接口是国内最稳的免费 K 线源。akshare 默认走东方财富 push2his
    接口, 飞牛 NAS 上经常被风控拒连 (RemoteDisconnected)。腾讯走的是
    财汇接口, 对 curl User-Agent 友好, 实测稳定。

    Args:
        ts_code: 000001.SZ / 600519.SH 格式 (会拆成 sh/sz + 6 位代码)
        days: 拉多少根 K 线
        freq: 仅支持 D (周月线可后续加)

    Returns:
        DataFrame with columns: dt, symbol, open, close, high, low, vol, amount
    """
    import pandas as pd
    import requests as _req

    if freq.upper() != "D":
        raise NotImplementedError(f"freq={freq} 暂未实现, 当前仅支持 D (日线)")

    # ts_code → 腾讯接口 secid (sh600519 / sz000001)
    symbol, market = ts_code.split(".")
    secid = f"{market.lower()}{symbol}"  # SH → sh, SZ → sz

    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={secid},day,,,{int(days*1.5)},qfq"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://gu.qq.com/",
    }
    resp = _req.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    if data.get("code") != 0:
        raise ValueError(f"腾讯接口返回错误: {data.get('msg')}")

    # qfqday = 前复权日 K, day = 不复权日 K
    klines = data["data"].get(secid, {}).get("qfqday") or data["data"].get(secid, {}).get("day")
    if not klines:
        raise ValueError(f"腾讯接口返回空 K 线: ts_code={ts_code}")

    rows = []
    for k in klines:
        # 腾讯字段: [日期, 开, 收, 高, 低, 成交量(手), 可选分红信息]
        # 成交量单位是 "手", 1 手 = 100 股; czsc 默认用股
        rows.append({
            "dt": k[0],
            "symbol": symbol,
            "open": float(k[1]),
            "close": float(k[2]),
            "high": float(k[3]),
            "low": float(k[4]),
            "vol": float(k[5]) * 100,  # 手 → 股
            "amount": 0.0,  # 腾讯不直接给成交额, czsc 不强依赖
        })

    df = pd.DataFrame(rows)
    df["dt"] = pd.to_datetime(df["dt"])
    df = df.tail(days).reset_index(drop=True)
    df = df[["dt", "symbol", "open", "close", "high", "low", "vol", "amount"]]
    return df


# ---------------------------------------------------------------------------
# 缠论分析
# ---------------------------------------------------------------------------

FREQ_MAP = {"D": Freq.D, "W": Freq.W, "M": Freq.M}


def run_czsc(df, freq_label: str = "D"):
    """运行 CZSC 分析, 返回 (czsc_obj, freq_enum)"""
    freq_enum = FREQ_MAP.get(freq_label.upper(), Freq.D)
    bars = format_standard_kline(df, freq=freq_enum)
    if len(bars) < 50:
        raise ValueError(f"K 线数量不足 ({len(bars)} 根), 至少需要 50 根做缠论分析")
    c = CZSC(bars)
    return c, freq_enum


def summarize(c) -> dict:
    """生成分析摘要 (纯文本可读)"""
    return {
        "symbol": c.symbol,
        "bars_total": len(c.bars_raw),
        "fx_count": len(c.fx_list),
        "bi_count_total": len(c.bi_list),
        "bi_finished": len(c.finished_bis),
        "ubi_count": len(c.bars_ubi),
        "signals_count": len(c.signals),
        "signals_triggered": [
            (k, str(v)) for k, v in list(c.signals.items())[:10]
        ],
    }


# ---------------------------------------------------------------------------
# 命令实现
# ---------------------------------------------------------------------------

def cmd_analyze(args):
    """完整缠论分析 + HTML 可视化"""
    print(f"[fetch] {args.ts_code} 最近 {args.days} 天 {args.freq} K 线 ...", file=sys.stderr)
    df = fetch_klines(args.ts_code, days=args.days, freq=args.freq)
    print(f"[fetch] 拉到 {len(df)} 根 K 线, 区间 {df['dt'].iloc[0].date()} → {df['dt'].iloc[-1].date()}",
          file=sys.stderr)

    print(f"[czsc] 跑缠论分析 ...", file=sys.stderr)
    c, freq = run_czsc(df, freq_label=args.freq)
    summary = summarize(c)
    print(f"[czsc] 分型 {summary['fx_count']} | 笔 {summary['bi_count_total']} "
          f"(完成 {summary['bi_finished']}) | 中枢 {summary['ubi_count']}",
          file=sys.stderr)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"[plot] 生成 self-contained HTML → {out_path}", file=sys.stderr)
    plot_czsc(c, output="html", path=str(out_path))
    print(f"[done] {out_path} ({out_path.stat().st_size // 1024} KB)", file=sys.stderr)
    print()
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def cmd_signals(args):
    """只看信号"""
    df = fetch_klines(args.ts_code, days=args.days, freq=args.freq)
    c, _ = run_czsc(df, freq_label=args.freq)
    summary = summarize(c)
    print(f"=== {summary['symbol']} 缠论信号摘要 ===")
    print(f"K 线: {summary['bars_total']} | 分型: {summary['fx_count']} | "
          f"笔: {summary['bi_count_total']} (完成 {summary['bi_finished']}) | "
          f"中枢: {summary['ubi_count']}")
    print(f"信号数: {summary['signals_count']}")
    print()
    if summary["signals_triggered"]:
        print("触发信号 (前 10):")
        for name, val in summary["signals_triggered"]:
            print(f"  • {name}: {val}")
    else:
        print("(无信号 — 默认 signals 配置为空, 需传入 signals_seq 启用)")


def cmd_report(args):
    """analyze + Markdown 文本摘要"""
    df = fetch_klines(args.ts_code, days=args.days, freq=args.freq)
    c, _ = run_czsc(df, freq_label=args.freq)
    summary = summarize(c)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plot_czsc(c, output="html", path=str(out_path))

    # Markdown 摘要
    print(f"# {summary['symbol']} 缠论分析报告\n")
    print(f"- K 线区间: {df['dt'].iloc[0].date()} → {df['dt'].iloc[-1].date()} ({summary['bars_total']} 根)")
    print(f"- 分型: {summary['fx_count']}")
    print(f"- 笔: {summary['bi_count_total']} (已完成 {summary['bi_finished']})")
    print(f"- 中枢: {summary['ubi_count']}")
    print(f"- HTML 可视化: `{out_path}`")
    if c.bi_list:
        last_bi = c.bi_list[-1]
        print(f"\n## 最近一笔\n- 方向: {last_bi.direction}\n- 高: {last_bi.high}\n- 低: {last_bi.low}")
    print(f"\n_Generated by czsc-trading skill at {datetime.now().isoformat()}_")


def cmd_doc(_args):
    """打印 SKILL 摘要"""
    skill_md = Path(__file__).parent.parent / "SKILL.md"
    if skill_md.exists():
        print(skill_md.read_text(encoding="utf-8")[:2000])
    else:
        print("SKILL.md not found")
    print()
    print("=== 命令清单 ===")
    print("analyze --ts-code 000001.SZ --days 250 --freq D --output /tmp/x.html")
    print("signals --ts-code 000001.SZ")
    print("report --ts-code 000001.SZ --output /tmp/x.html")
    print("doc")


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="czsc-trading — 缠论技术分析 CLI (akshare + czsc + plotly)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--ts-code", required=True, help="股票代码 (000001.SZ / 600519.SH)")
    common.add_argument("--days", type=int, default=250, help="拉多少天 K 线 (默认 250)")
    common.add_argument("--freq", default="D", choices=["D", "W", "M"], help="K 线周期")

    p_analyze = sub.add_parser("analyze", parents=[common], help="完整缠论分析 + HTML 输出")
    p_analyze.add_argument("--output", required=True, help="HTML 输出路径")
    p_analyze.set_defaults(func=cmd_analyze)

    p_signals = sub.add_parser("signals", parents=[common], help="只看信号摘要")
    p_signals.set_defaults(func=cmd_signals)

    p_report = sub.add_parser("report", parents=[common], help="analyze + Markdown 摘要")
    p_report.add_argument("--output", required=True, help="HTML 输出路径")
    p_report.set_defaults(func=cmd_report)

    p_doc = sub.add_parser("doc", help="打印 SKILL.md + 命令清单")
    p_doc.set_defaults(func=cmd_doc)

    args = parser.parse_args()
    try:
        args.func(args)
    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
