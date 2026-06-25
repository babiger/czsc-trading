#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
czsc_signals.py — 缠论买卖信号检测 (基于 czsc._native.generate_czsc_signals)

支持 4 类核心买卖点 + 7 个辅助信号:

  核心缠论买卖点 (cxt = 缠论):
    - cxt_first_buy_V221126      一买
    - cxt_first_sell_V221126     一卖
    - cxt_second_bs_V240524      二买卖 (双向)
    - cxt_third_buy_V230228      三买

  辅助信号:
    - bar_td9_V240616            神奇九转 (TD 序列)
    - tas_macd_first_bs_V221201  MACD 一买
    - tas_macd_second_bs_V221201 MACD 二买
    - tas_macd_bc_V221201        MACD 背驰
    - tas_double_ma_V230511      双均线
    - pressure_support_V240222   支撑压力
    - byi_second_bs_V230324      笔翼二买

输出:
    --df        完整 DataFrame (每行每天的 signal value)
    --events    只输出触发事件 (value 包含 买/卖 的行)
    --summary   统计每个信号触发次数 + 最近触发日期

数据源: 同 czsc_trading.py, 走腾讯 ifzq.gtimg.cn 免费接口
"""

import argparse
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

# v4.1: 自定义 preset 存储路径 (优先环境变量 CZSC_PRESET_DIR, 用于团队共享)
import os
# v5.2.3: 真拆 data 域函数到 czsc_cli.data (替代 v5.1 __getattr__ lazy 转发)
# 保留这里 re-export 以兼容旧路径 (scripts/czsc_signals.py 的 import)
from czsc_cli.data import (
    # tushare fetchers
    _fetch_st_names_via_tushare,
    _fetch_industry_via_tushare,
    _fetch_bak_basic_via_tushare,
    # filter helpers
    _filter_by_industry_pe,
    _filter_by_market_cap_turnover,
    _is_st_or_delisted,
    _filter_stocks,
    # weights (SIGNAL_WEIGHTS 单点真理在 data; scanner/_score_one_stock 跨域共享)
    _load_weights,
    SIGNAL_WEIGHTS,
    RECENCY_BONUS,
    # K 线
    fetch_klines_for_signals,
    _fetch_klines_uncached,
    fetch_klines_with_cache,
    _cache_path,
    _load_cache,
    _save_cache,
)

# v5.2.3.5: 真拆 batch 域到 czsc_cli.batch (替代 v5.1 __getattr__ lazy 转发)
# 10 函数 (slack push + batch config + dry-run + filter helpers + batch runner + execute)
from czsc_cli.batch import (
    _push_to_slack,
    _load_batch_config,
    _batch_dry_run,
    _merge_scan_args_for_dry_run,
    _filter_bak_basic_dict,
    _print_filter_summary,
    _fetch_basic_cached,
    _load_watchlist_safe,
    _run_batch,
    _execute_one_run,
)




# v5.2.3.2: PRESET_DIR 已掊到 czsc_cli.preset (下面的 from ... import 导入).
#            BUILTIN_PRESETS 留 czsc_signals (v5.0 历史, 不掊避免多 module 依赖).

# v3.9 + v5.2.0: 内置预设策略字典 (提到模块级, 让 czsc_cli.batch._EXPORTS 能 lazy load;
#                真拆函数实现是 v5.2.3 计划)
BUILTIN_PRESETS = {
    "value": {
        "pe_max": 15.0, "pb_max": 2.0, "market_cap_min": 1000.0,
        "sort_by": "composite",
    },
    "bank": {
        "industry": "银行", "pe_max": 15.0, "pb_max": 1.5, "market_cap_min": 2000.0,
        "sort_by": "composite",
    },
    "momentum": {
        "turnover_min": 1.0, "market_cap_min": 500.0,
        "sort_by": "composite", "show_stats": True,
    },
    "bargain": {
        # PE<10 + 换手升序 + 市场>200亿 = 抄底特征 (reverse=True 表示升序)
        "pe_max": 10.0, "market_cap_min": 200.0,
        "sort_by": "turnover_rate", "reverse": True,
    },
}


# v5.2.3.2: 真拆 preset 域到 czsc_cli.preset (替代 v5.1 __getattr__ lazy 转发)
# 9 cmd_preset_* + 4 helpers (save/load/apply/override) + PRESET_DIR + PRESET_SAVE_FLAGS
# BUILTIN_PRESETS 留 czsc_signals (v5.0 历史), 被这里 import 后保持 is 关系
from czsc_cli.preset import (
    # module-level state
    PRESET_DIR,
    PRESET_SAVE_FLAGS,
    # 3 user preset helpers
    _save_user_preset,
    _load_user_preset,
    _apply_user_preset,
    _override_preset_dir,
    # 9 cmd_preset_* subcommands
    cmd_preset_save,
    cmd_preset_list,
    cmd_preset_show,
    cmd_preset_delete,
    cmd_preset_export,
    cmd_preset_import,
    cmd_preset_diff,
    cmd_preset_merge,
    cmd_preset_validate,
)

# ---------------------------------------------------------------------------

# v5.2.3.3: 真拆 signals 域到 czsc_cli.signals (替代 v5.1 __getattr__ lazy 转发)
# 11 函数 (run_signals/cmd_signals/events/summary + resample_to_freq/multi_freq/cmd_multi_freq
#         + build_weight_with_stops/run_weight_backtest/format_bt_result/cmd_backtest)
# + 4 module-level 常量 (CORE_BS_SIGNALS / AUX_SIGNALS / ALL_SIGNALS / SIGNAL_GROUPS)
from czsc_cli.signals import (
    # module-level 常量
    CORE_BS_SIGNALS,
    AUX_SIGNALS,
    ALL_SIGNALS,
    SIGNAL_GROUPS,
    # 单股
    run_signals,
    cmd_signals,
    cmd_events,
    cmd_summary,
    # multi-freq
    resample_to_freq,
    run_multi_freq_signals,
    cmd_multi_freq,
    # backtest
    build_weight_with_stops,
    run_weight_backtest,
    format_bt_result,
    cmd_backtest,
)


# v3.5: 多股扫描 + 信号打分排名
# v4.6: Slack 推送
# ---------------------------------------------------------------------------


# v5.2.3.4: 真拆 scanner 域到 czsc_cli.scanner (替代 v5.1 __getattr__ lazy 转发)
# 6 函数 (3 核心: parse+score+sort + 3 scan entry: _apply_preset + run_scan + cmd_scan)
# 注: filter helpers 留给 batch 域 (v5.2.3.5 真拆时归位)
from czsc_cli.scanner import (
    # 3 核心
    _parse_stocks,
    _score_one_stock,
    _sort_detail,
    # 3 scan entry
    _apply_preset,
    run_scan_signals,
    cmd_scan,
)
# v5.2.3.4: cmd_list 重新归位到 signals 域 (v5.2.3.3 真拆时漏了)
from czsc_cli.signals import cmd_list


# v4.7: batch dry-run (模拟跑, 不拉数据, 预估 filter 后剩多少股 + 耗时)
# ---------------------------------------------------------------------------

# 估计 1 只股票拉 1 次 K 线 + signal 计算耗时
# 实测平均: K 线 0.3s + signal 0.1s = 0.4s
_STOCK_SEC_PER = 0.4



def main():
    parser = argparse.ArgumentParser(
        description="czsc-signals — 缠论买卖信号检测 (czsc 1.0 native signals, 腾讯免费行情)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # 通用
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--ts-code", help="股票代码 (000001.SZ / 600519.SH)")
    common.add_argument("--signal", nargs="+",
                        help="信号别名 (--list 看可用, 可多个或 'all')")
    common.add_argument("--days", type=int, default=500, help="拉多少天 (默认 500)")

    p_sig = sub.add_parser("signals", parents=[common],
                           help="最近 30 天信号状态 + 全部触发统计")
    p_sig.set_defaults(func=cmd_signals)

    p_evt = sub.add_parser("events", parents=[common], help="只输出触发事件")
    p_evt.set_defaults(func=cmd_events)

    p_sum = sub.add_parser("summary", parents=[common], help="信号摘要 (触发次数 + 最近日期)")
    p_sum.set_defaults(func=cmd_summary)

    p_lst = sub.add_parser("list", help="列出所有可用信号")
    p_lst.set_defaults(func=cmd_list)

    # v4.0: 自定义 preset 管理
    p_pre = sub.add_parser("preset", help="v4.0: 管理自定义策略预设 (save/list/show/delete)")
    pre_sub = p_pre.add_subparsers(dest="preset_cmd", required=True)
    p_pre_save = pre_sub.add_parser("save", help="保存当前 scan 参数为 preset")
    p_pre_save.add_argument("name", help="preset 名 (字母/数字/下划线)")
    p_pre_save.set_defaults(func=cmd_preset_save)
    p_pre_list = pre_sub.add_parser("list", help="列出所有自定义 preset")
    p_pre_list.add_argument("--tag", default="",
                          help="v4.3: 按 tag 过滤 (逗号分隔 OR 逻辑, e.g. 'bank,value')")
    p_pre_list.set_defaults(func=cmd_preset_list)
    p_pre_show = pre_sub.add_parser("show", help="显示指定 preset 的参数")
    p_pre_show.add_argument("name", help="preset 名")
    p_pre_show.set_defaults(func=cmd_preset_show)
    p_pre_del = pre_sub.add_parser("delete", help="删除指定 preset")
    p_pre_del.add_argument("name", help="preset 名")
    p_pre_del.set_defaults(func=cmd_preset_delete)

    # v4.1: 导出 preset 到文件 (可发邮件/微信分享)
    p_pre_exp = pre_sub.add_parser("export", help="导出 preset 到指定路径 (默认 stdout)")
    p_pre_exp.add_argument("name", help="preset 名")
    p_pre_exp.add_argument("--output", default="", help="导出路径 (默认 stdout)")
    p_pre_exp.set_defaults(func=cmd_preset_export)

    # v4.1: 从文件导入 preset
    p_pre_imp = pre_sub.add_parser("import", help="从 JSON 文件导入 preset")
    p_pre_imp.add_argument("name", help="导入后的 preset 名")
    p_pre_imp.add_argument("source", help="源 JSON 文件路径")
    p_pre_imp.set_defaults(func=cmd_preset_import)

    # v4.4: 对比两个 preset 的差异
    p_pre_diff = pre_sub.add_parser("diff", help="对比两个 preset 的差异 (git diff 风格)")
    p_pre_diff.add_argument("name_a", help="preset A 名")
    p_pre_diff.add_argument("name_b", help="preset B 名")
    p_pre_diff.add_argument("--format", default="text", choices=["text", "json"],
                          help="输出格式 (text=人类看 / json=程序消费)")
    p_pre_diff.set_defaults(func=cmd_preset_diff)

    # v4.5: 合并多个 preset (后者覆盖前者, 类似 git merge)
    p_pre_merge = pre_sub.add_parser("merge", help="合并多个 preset (后加载的覆盖先加载的)")
    p_pre_merge.add_argument("sources", nargs="+", help="源 preset 名 (2 个或更多, 后者覆盖前者)")
    p_pre_merge.add_argument("--name", required=True, help="合并后的 preset 名")
    p_pre_merge.add_argument("--preset-tag", default="", help="保存时打的标签 (逗号分隔)")
    p_pre_merge.set_defaults(func=cmd_preset_merge)

    # v4.6: 验证 preset 字段合法性 (手编辑 / 旧版本迁移检查)
    p_pre_val = pre_sub.add_parser("validate", help="验证 preset 字段合法性 (检出未知字段)")
    p_pre_val.add_argument("name", nargs="?", default="", help="preset 名 (不传则验证全部)")
    p_pre_val.add_argument("--fix", action="store_true", help="自动删除未知字段并保存")
    p_pre_val.set_defaults(func=cmd_preset_validate)

    # v4.1: 统一给 9 个 preset 子命令加 --preset-dir
    for p in [p_pre_save, p_pre_list, p_pre_show, p_pre_del, p_pre_exp, p_pre_imp, p_pre_diff, p_pre_merge, p_pre_val]:
        p.add_argument("--preset-dir", default="",
                          help="v4.1: 临时 preset 存储路径 (覆盖 CZSC_PRESET_DIR 环境变量和 ~/.czsc-presets)")

    # v3.5: 多股扫描 + 信号打分排名
    p_scan = sub.add_parser("scan", help="v3.5 多股扫描 + 信号打分排名")
    p_scan.add_argument("--stocks", default="",
                          help="股票列表 (逗号分隔, e.g. '000001.SZ,600519.SH')")
    p_scan.add_argument("--watchlist", default="",
                          help="watchlist 文件路径 (每行一只股, 支持注释/标题/空格)")
    p_scan.add_argument("--signal", nargs="+", default=None,
                          help="信号别名 (默认 all, 可多个或 'all')")
    p_scan.add_argument("--days", type=int, default=500,
                          help="拉多少天 K 线 (默认 500)")
    p_scan.add_argument("--rank-by", default="composite",
                          help="[别名] 排序字段 (向后兼容 v3.5), 优先用 --sort-by")
    p_scan.add_argument("--sort-by", default=None,
                          help="v3.7: 排序字段. composite/total_mv/turnover_rate/last_close/ts_code 或信号别名")
    p_scan.add_argument("--reverse", action="store_true",
                          help="v3.7: 反向排序 (默认降序, 加此 flag 升序)")
    p_scan.add_argument("--show-stats", action="store_true",
                          help="v3.7: 输出分布统计 (min/p25/p50/p75/max/mean) for composite/市值/换手率/收盘价")
    p_scan.add_argument("--preset", default="",
                          help="v3.9: 一键策略预设 (value/bank/momentum/bargain), 会设置多个 flag 默认值")
    p_scan.add_argument("--save-preset", default="",
                          help="v4.0: 保存当前所有 scan flag 为自定义 preset (~/.czsc-presets/<name>.json)")
    p_scan.add_argument("--preset-file", default="",
                          help="v4.0: 从 JSON 文件加载自定义 preset (覆盖 --preset 内置预设)")
    p_scan.add_argument("--preset-dir", default="",
                          help="v4.1: 临时 preset 存储路径 (覆盖 CZSC_PRESET_DIR 环境变量和 ~/.czsc-presets)")
    p_scan.add_argument("--batch-scan", default="",
                          help="v4.3: 批量跑多个 scan (YAML/JSON/TOML 配置文件, 按扩展名自动检测)")
    p_scan.add_argument("--batch-output", default="",
                          help="v4.3: 批量结果汇总到指定路径 (markdown 格式, 默认 stdout)")
    p_scan.add_argument("--batch-output-format", default="markdown",
                          choices=["markdown", "json", "html"],
                          help="v4.4: 汇总报告格式 (markdown=人看 / json=程序 / html=邮件)")
    p_scan.add_argument("--batch-parallel", type=int, default=1,
                          help="v4.5: 并行跑多少个 run (默认 1=串行, 3=3倍加速)")
    p_scan.add_argument("--batch-dry-run", action="store_true",
                          help="v4.7: 模拟跑 batch (不拉数据, 只看 filter 后剩多少股 + 预估耗时)")
    p_scan.add_argument("--batch-retry", type=int, default=0,
                          help="v4.8: 失败 run 重试次数 (默认 0=不重试, max=5, 指数退避 1/2/4/8/16s)")
    p_scan.add_argument("--batch-notify-on-success", action="store_true",
                          help="v4.9: 只在全部 run 成功时才推 Slack (失败静默, 避免噪音淹没)")
    p_scan.add_argument("--slack-webhook", default="",
                          help="v4.6: batch 跑完后推报告到 Slack webhook (环境变量 SLACK_WEBHOOK_URL 也可)")
    p_scan.add_argument("--preset-tag", default="",
                          help="v4.3: 保存 preset 时打的标签 (逗号分隔, e.g. 'bank,value')")
    p_scan.add_argument("--top", type=int, default=10,
                          help="只输出前 N 名 (默认 10)")
    p_scan.add_argument("--max-stocks", type=int, default=50,
                          help="最多支持多少只股 (默认 50, 防呆)")
    # v3.5.1 新增
    p_scan.add_argument("--output-csv", default="",
                          help="[别名] 输出 CSV, 推荐用 --output /tmp/x.csv")
    p_scan.add_argument("--output", default="",
                          help="v3.8: 通用输出路径 (配合 --format)")
    p_scan.add_argument("--format", default="",
                          help="v3.8: 输出格式 table/csv/markdown/json (默认从后缀猜)")
    p_scan.add_argument("--exclude-st", action="store_true",
                          help="过滤 ST/*ST/退市股 (需 tushare 基础权限)")
    p_scan.add_argument("--weights-file", default="",
                          help="自定义权重 JSON (e.g. {\"一买\": 6, \"三买\": 4})")
    # v3.6 新增
    p_scan.add_argument("--industry", default="",
                          help="行业关键字过滤 (逗号分隔, 包含匹配, e.g. '银行,白酒')")
    p_scan.add_argument("--pe-max", type=float, default=None,
                          help="静态 PE 上限 (e.g. 30, PE=0 亏损股永远过滤)")
    p_scan.add_argument("--pe-min", type=float, default=None,
                          help="静态 PE 下限 (e.g. 0 过滤 PE>0 的极低估, 默认不限)")
    p_scan.add_argument("--pb-max", type=float, default=None,
                          help="静态 PB 上限 (e.g. 5)")
    # v3.6.1 新增
    p_scan.add_argument("--market-cap-min", type=float, default=None,
                          help="总市值下限 (亿元, e.g. 500, 过滤小盘股)")
    p_scan.add_argument("--turnover-min", type=float, default=None,
                          help="换手率下限 (%% e.g. 1.0, 过滤冷门股)")
    p_scan.add_argument("--exclude-keyword", default="",
                          help="v3.8: 按股名关键字排除 (逗号分隔, e.g. '北交所,创业板,科创板')")
    p_scan.set_defaults(func=cmd_scan)

    # 多周期
    p_mf = sub.add_parser("multi", parents=[common], help="多周期信号扫描 (日/周/月)")
    p_mf.add_argument("--freqs", default="日线,周线,月线",
                       help="哪些周期 (逗号分隔, e.g. '日线,周线' / '周线,月线')")
    # 回测
    p_bt = sub.add_parser("backtest", parents=[common], help="信号回测 (信号触发→次日买入→N日后卖出)")
    p_bt.add_argument("--hold-days", type=int, default=5,
                       help="持仓天数 (默认 5, 触发后 N 日平仓)")
    p_bt.add_argument("--stop-loss", type=float, default=None,
                       help="止损比例 (e.g. -0.05 表示亏 5%% 平仓)")
    p_bt.add_argument("--take-profit", type=float, default=None,
                       help="止盈比例 (e.g. 0.10 表示赚 10%% 平仓)")
    p_bt.add_argument("--max-hold-days", type=int, default=None,
                       help="最长持仓天数 (时间止损, 默认 = hold-days)")
    p_bt.add_argument("--fee-rate", type=float, default=0.0002,
                       help="单边手续费率 (默认 0.0002 = 万二双边)")
    p_bt.add_argument("--detail", action="store_true", help="显示每笔交易明细")
    p_bt.set_defaults(func=cmd_backtest)

    args = parser.parse_args()
    try:
        args.func(args)
    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {e}", file=sys.stderr)
        import traceback; traceback.print_exc(file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# v3.3: 本地缓存 (parquet) — 避免重复拉 tushare
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # v5.0: deprecation warning 指向 python3 -m czsc_cli
    print("[czsc v5.0] ⚠️ scripts/czsc_signals.py 已deprecated, 请改用 'python3 -m czsc_cli'", file=sys.stderr)
    print("[czsc v5.0]   旧: python3 scripts/czsc_signals.py scan ...", file=sys.stderr)
    print("[czsc v5.0]   新: python3 -m czsc_cli scan ...", file=sys.stderr)
    main()
