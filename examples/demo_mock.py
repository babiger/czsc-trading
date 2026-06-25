#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
demo_mock.py — 用 czsc 自带 mock 数据演示缠论分析 (无需联网)

用法:
  python3 examples/demo_mock.py
"""
import sys
from pathlib import Path

# 把 skill 根目录加进 path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from czsc_trading import summarize  # noqa: E402

from czsc.mock import generate_symbol_kines  # noqa: E402
from czsc import CZSC, Freq, format_standard_kline  # noqa: E402
from czsc.utils.plotting.lightweight import plot_czsc  # noqa: E402


def main():
    # 生成 6 个月 30 分钟模拟 K 线 (平安银行 000001)
    df = generate_symbol_kines("000001", "30分钟", "20240101", "20240601")
    print(f"mock K 线: {len(df)} 根, {df['dt'].iloc[0]} → {df['dt'].iloc[-1]}")

    bars = format_standard_kline(df, freq=Freq.F30)
    c = CZSC(bars)

    summary = summarize(c)
    print("\n=== 缠论分析摘要 ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")

    # 出图
    out_path = Path(__file__).parent.parent / "output" / "demo_mock.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plot_czsc(c, output="html", path=str(out_path))
    print(f"\nHTML → {out_path} ({out_path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
