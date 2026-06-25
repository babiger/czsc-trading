#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# czsc_cli.scanner v5.2.3.4 - 扫描层 (cmd_scan + 多股核心)
#
# v5.2.3.4 真拆: 替代 v5.1 __getattr__ lazy 转发, 直接实现在这里.
#
# 包含 (6 函数):
#   - 3 核心: _parse_stocks / _score_one_stock / _sort_detail
#   - 3 scan entry: _apply_preset / run_scan_signals / cmd_scan
#
# 注: filter helpers (_filter_bak_basic_dict 等) 留给 batch 域 (v5.2.3.5 真拆).
#
# 跨域依赖:
#   - czsc_cli.data / .preset / .signals (单向, 无循环)
#   - czsc_signals.BUILTIN_PRESETS (留 czsc_signals, v5.2.3.2 决定)

import sys
from pathlib import Path

import pandas as pd

# v5.2.3.4: 跨域 import (单向, 无循环)
from czsc_cli.data import (
    _fetch_bak_basic_via_tushare,
    _filter_stocks,
    _filter_by_industry_pe,
    _filter_by_market_cap_turnover,
    _fetch_st_names_via_tushare,
    _load_weights,
    SIGNAL_WEIGHTS,
    RECENCY_BONUS,
)
from czsc_cli.preset import (
    _load_user_preset,
    _apply_user_preset,
    _save_user_preset,
    PRESET_DIR,
)
from czsc_cli.signals import run_signals, ALL_SIGNALS, SIGNAL_GROUPS

# BUILTIN_PRESETS 留 czsc_signals (v5.2.3.2 决定)
# v5.2.3.4 fix: 不能顶层 import (会跟 czsc_signals 顶层 import 循环)
#    改为函数内 import (只 _apply_preset 需要)


# ---------------------------------------------------------------------------
# v5.2.3.4: 解析器 + 单股打分 + 排序器 (从 czsc_signals 真拆)
# ---------------------------------------------------------------------------

def _parse_stocks(stocks_arg: str, watchlist: str) -> list:
    """从 --stocks (逗号分隔) 和/或 --watchlist (文件, 每行一只) 解析股池"""
    out = []
    if stocks_arg:
        out.extend([s.strip() for s in stocks_arg.split(",") if s.strip()])
    if watchlist:
        path = Path(watchlist)
        if not path.exists():
            raise FileNotFoundError(f"watchlist 文件不存在: {watchlist}")
        for line in path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            # 跳过空行 / 注释 / 表头
            if not s or s.startswith("#") or s.startswith("//") or "代码" in s and "名称" in s:
                continue
            # 兼容 "000001.SZ 平安银行" / "000001.SZ,平安银行" / "000001.SZ"
            for token in s.replace(",", " ").split():
                if "." in token and len(token) >= 9:  # e.g. 000001.SZ
                    out.append(token)
    # 去重保序
    seen, dedup = set(), []
    for s in out:
        if s not in seen:
            seen.add(s)
            dedup.append(s)
    return dedup


def _score_one_stock(ts_code: str, signal_aliases: list, days: int, today: pd.Timestamp,
                      weights: dict = None):
    """跑一只股的信号统计 + composite 打分. 返回 dict 或 None (失败)

    weights: 自定义权重 dict (默认 SIGNAL_WEIGHTS)
    """
    weights = weights or SIGNAL_WEIGHTS
    try:
        results, selected, raw_df = run_signals(ts_code, signal_aliases, days=days)
    except Exception as e:
        print(f"[scan] {ts_code} 失败: {type(e).__name__}: {str(e)[:80]}", file=sys.stderr)
        return None

    # 找信号列 (selected 是用户传的那些, 顺序与 alias 一致)
    sig_cols = [col for col in results.columns if col.startswith("日线_")]
    # 用 alias 找列 (selected 的顺序就是列的顺序)
    alias_to_col = {}
    for col, sig_def in zip(sig_cols, selected):
        alias_to_col[sig_def["alias"]] = col

    # 收盘价 + 最新日期
    last_close = float(raw_df["close"].iloc[-1])
    last_dt = pd.Timestamp(raw_df["dt"].iloc[-1])
    if last_dt.tz is not None:
        last_dt = last_dt.tz_localize(None)

    # 各信号触发次数 + 最近日期 + composite 分数
    per_signal = {}
    composite = 0.0
    for alias, col in alias_to_col.items():
        weight = weights.get(alias, 0.5)
        triggered = results[~results[col].str.startswith("其他", na=False)]
        n = len(triggered)
        if n > 0:
            last_dt_raw = triggered["dt"].iloc[-1]
            last_dt_sig = pd.Timestamp(last_dt_raw) if not isinstance(last_dt_raw, str) else pd.Timestamp(last_dt_raw)
            if last_dt_sig.tz is not None:
                last_dt_sig = last_dt_sig.tz_localize(None)
            days_ago = (today - last_dt_sig).days
            score = n * weight
            # 时效加分
            for thresh, bonus in RECENCY_BONUS.items():
                if days_ago < thresh:
                    score += bonus
        else:
            last_dt_sig = None
            days_ago = None
            score = 0.0
        per_signal[alias] = {"n": n, "last": last_dt_sig, "days_ago": days_ago, "score": score, "weight": weight}
        composite += score

    # v3.6.1: 市值/换手率 (从 bak_basic cache 拿, 拿不到默认 0)
    bak = _fetch_bak_basic_via_tushare()
    info = bak.get(ts_code, {})
    total_share = info.get("total_share", 0)  # 亿股
    total_mv = round(total_share * last_close, 2) if total_share else 0  # 亿元
    # v3.6.1: 本地换手率 = 今日 vol / total_share * 1e8
    # raw_df['vol'] 单位是股 (已验证), total_share 单位是亿股 (1e8)
    latest_vol_shares = float(raw_df["vol"].iloc[-1]) if len(raw_df) > 0 else 0
    turnover_rate = round(latest_vol_shares / (total_share * 1e8) * 100, 2) if total_share else 0

    return {
        "ts_code": ts_code,
        "last_close": last_close,
        "last_dt": last_dt,
        "composite": round(composite, 2),
        "total_mv": total_mv,
        "turnover_rate": turnover_rate,
        "per_signal": per_signal,
    }


def _sort_detail(detail: dict, sort_by: str = "composite", reverse: bool = False) -> list:
    """v3.7: 统一排序器.
    sort_by 取值:
        - "composite"       按信号加权分 (默认)
        - "total_mv"        按总市值 (亿元) 降序
        - "turnover_rate"   按换手率 (%%) 降序
        - "last_close"      按最新收盘价
        - "ts_code"         按股票代码字母序 (stable, 多次运行对比)
        - 任意 alias 名    按该信号 score 降序 (向后兼容 v3.5)
    reverse 参数语义 (Python sorted 标准):
        - False (默认)  升序 (score 低→高)
        - True          降序 (score 高→低)
    用户侧 `--reverse` flag (args.reverse) 语义是"反向", 与参数 reverse 取反:
        - args.reverse=False (默认) → 函数 reverse=True → 降序 (高在前, 默认)
        - args.reverse=True          → 函数 reverse=False → 升序 (低在前)
    """
    # 调用者负责传递正确的 reverse 值 (已经处理过语义取反)
    def get_key(kv):
        ts_code, r = kv
        if sort_by == "composite":
            return r.get("composite", 0.0)
        if sort_by == "total_mv":
            return r.get("total_mv", 0.0)
        if sort_by == "turnover_rate":
            return r.get("turnover_rate", 0.0)
        if sort_by == "last_close":
            return r.get("last_close", 0.0)
        if sort_by == "ts_code":
            return ts_code
        # 向后兼容: 作为 alias 名处理
        return r["per_signal"].get(sort_by, {}).get("score", 0.0)
    return sorted(detail.items(), key=get_key, reverse=reverse)


# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# v5.2.3.4: scan entry + BUILTIN preset (从 czsc_signals 真拆)
# ---------------------------------------------------------------------------

def _apply_preset(args) -> None:
    """v3.9 + v5.2.0: 应用预设策略, 修改 args 属性 (用户显式传的 flag 不覆盖).
    预设提供"一键策略组合"降低使用门槛.

    v5.2.0: 从模块级 BUILTIN_PRESETS 取 (代替原函数内 local dict), 让 czsc_cli.batch 能 lazy load.
    v5.2.3.4 fix: 函数内 import BUILTIN_PRESETS (避免与 czsc_signals 顶层循环 import).
    """
    # v5.2.3.4 fix: 函数内 import (不走顶层, 避免循环)
    from czsc_signals import BUILTIN_PRESETS

    preset = args.preset
    if not preset:
        return
    if preset not in BUILTIN_PRESETS:
        print(f"[ERROR] --preset 未知: {preset} (可选: {', '.join(BUILTIN_PRESETS.keys())})", file=sys.stderr)
        sys.exit(1)
    cfg = BUILTIN_PRESETS[preset]
    print(f"[preset] '{preset}' 应用:", file=sys.stderr)
    applied = []
    for attr, val in cfg.items():
        cur = getattr(args, attr, None)
        # 判断 "用户未传": None / 空串 / False / 0 / 0.0
        is_default = cur is None or cur == "" or cur is False or cur == 0 or cur == 0.0
        if is_default:
            setattr(args, attr, val)
            if isinstance(val, bool):
                applied.append(f"--{attr.replace('_', '-')}")
            else:
                applied.append(f"--{attr.replace('_', '-')}={val}")
    print(f"  → {', '.join(applied)}", file=sys.stderr)


def run_scan_signals(stocks: list, signal_aliases: list, days: int = 500,
                      rank_by: str = "composite", top: int = 10,
                      weights: dict = None, reverse: bool = False):
    """跑多股扫描, 返回 (ranking_df, detail_dict)

    ranking_df: 按 rank_by 降序排的表 (ts_code / last_close / composite / rank / 各信号n)
    detail_dict: {ts_code: {alias: {n, last, days_ago, score, weight}}}
    weights: 自定义权重 dict
    reverse: True 升序 (默认 False 降序)
    """
    weights = weights or SIGNAL_WEIGHTS
    today = pd.Timestamp.today().normalize()
    if today.tz is not None:
        today = today.tz_localize(None)
    detail = {}
    n = len(stocks)
    for i, ts_code in enumerate(stocks, 1):
        print(f"[scan {i}/{n}] {ts_code} ...", file=sys.stderr)
        r = _score_one_stock(ts_code, signal_aliases, days, today, weights)
        if r is not None:
            detail[ts_code] = r

    if not detail:
        return pd.DataFrame(), {}

    # v3.7: 统一排序器 (sort_by + reverse)
    items = _sort_detail(detail, sort_by=rank_by, reverse=reverse)

    # 构造 ranking DataFrame
    all_aliases = list(detail[items[0][0]]["per_signal"].keys())
    rows = []
    for rank, (ts_code, r) in enumerate(items[:top], 1):
        row = {
            "rank": rank,
            "ts_code": ts_code,
            "last_close": r["last_close"],
            "last_dt": r["last_dt"].strftime("%Y-%m-%d"),
            "composite": r["composite"],
            "total_mv": r.get("total_mv", 0),
            "turnover_rate": r.get("turnover_rate", 0),
        }
        for alias in all_aliases:
            row[f"{alias}_n"] = r["per_signal"][alias]["n"]
            row[f"{alias}_last"] = r["per_signal"][alias]["last"].strftime("%Y-%m-%d") if r["per_signal"][alias]["last"] else "—"
        rows.append(row)
    return pd.DataFrame(rows), detail


def cmd_scan(args):
    """v3.5.1: 多股扫描 + 信号打分排名 (含 CSV/ST/权重文件)"""
    # v4.3: batch-scan 模式 — 加载 config, 逐个跑, 汇总结果
    if args.batch_scan:
        return _run_batch(args)

    # 1. 解析股池
    try:
        stocks = _parse_stocks(args.stocks or "", args.watchlist or "")
    except Exception as e:
        print(f"[ERROR] 解析股池失败: {e}", file=sys.stderr)
        sys.exit(1)

    if not stocks:
        print("[ERROR] --stocks 和 --watchlist 至少传一个", file=sys.stderr)
        sys.exit(1)

    # 1.5 v3.8: 验证 --format (提前检查避免拉 K 线后才发现)
    if args.format and args.format not in ("table", "csv", "markdown", "json"):
        print(f"[ERROR] --format 未知: {args.format} (可选: table/csv/markdown/json)", file=sys.stderr)
        sys.exit(1)

    # 1.55 v4.0: 加载 --preset-file (优先级高于 --preset 内置预设)
    # v4.1: --preset-dir 临时覆盖全局 PRESET_DIR (仅本次调用)
    global PRESET_DIR
    if args.preset_dir:
        PRESET_DIR = Path(args.preset_dir).expanduser()
    if args.preset_file:
        cfg = _load_user_preset(args.preset_file)
        _apply_user_preset(args, cfg)

    # 1.6 v3.9: 应用 preset (放在最前面, 后面所有逻辑看 preset 设的默认值)
    _apply_preset(args)

    # 1.7 v4.2: 展开 --signal 的 group 别名 (e.g. --signal all_long → 6 个真实信号)
    # 必须在 preset 之后, 因为 preset 里的 signal 也可能是 group 名
    if args.signal:
        expanded = []
        unknown_groups = []
        for s in args.signal:
            if s in SIGNAL_GROUPS:
                expanded.extend(SIGNAL_GROUPS[s]["signals"])
            elif s in {x["alias"] for x in ALL_SIGNALS} or s == "all":
                expanded.append(s)
            else:
                unknown_groups.append(s)
        if unknown_groups:
            valid = sorted({x["alias"] for x in ALL_SIGNALS} | SIGNAL_GROUPS.keys())
            print(f"[ERROR] --signal 含未知信号: {unknown_groups}", file=sys.stderr)
            print(f"  可选: {', '.join(valid[:10])}... (共 {len(valid)} 个)", file=sys.stderr)
            print(f"  v4.2 可用 group: {', '.join(SIGNAL_GROUPS.keys())}", file=sys.stderr)
            sys.exit(1)
        if expanded != args.signal:
            print(f"[signal-group] 展开: {args.signal} → {expanded}", file=sys.stderr)
            args.signal = expanded

    # 2. v3.5.1: ST 过滤
    if args.exclude_st:
        kept, filtered = _filter_stocks(stocks, exclude_st=True)
        if filtered:
            print(f"[scan] ST/退市 过滤: 跳过 {len(filtered)} 只 → {filtered[:5]}{'...' if len(filtered)>5 else ''}",
                  file=sys.stderr)
        stocks = kept
        if not stocks:
            print("[ERROR] ST 过滤后股池为空", file=sys.stderr)
            sys.exit(1)

    # 2.5 v3.6: Industry + PE/PB 估值过滤
    industries = [s.strip() for s in (args.industry or "").split(",") if s.strip()] if args.industry else []
    pe_max = args.pe_max
    pe_min = args.pe_min
    pb_max = args.pb_max
    exclude_keywords = [k.strip() for k in args.exclude_keyword.split(",") if k.strip()]
    if industries or pe_max is not None or pe_min is not None or pb_max is not None or exclude_keywords:
        before = len(stocks)
        stocks, dropped = _filter_by_industry_pe(stocks, industries,
                                                    pe_max=pe_max, pe_min=pe_min, pb_max=pb_max,
                                                    exclude_keywords=exclude_keywords)
        if dropped:
            reason_counts = {}
            for _, _, reason in dropped:
                key = reason.split("=")[0].split(">")[0].split("<")[0]
                reason_counts[key] = reason_counts.get(key, 0) + 1
            summary = ", ".join(f"{k}:{v}" for k, v in sorted(reason_counts.items()))
            print(f"[scan] 估值/行业过滤: {before} → {len(stocks)} 只, 跳过 {len(dropped)} ({summary})",
                  file=sys.stderr)
            for s, name, reason in dropped[:5]:
                print(f"        - {s} {name}: {reason}", file=sys.stderr)
            if len(dropped) > 5:
                print(f"        ... +{len(dropped)-5} more", file=sys.stderr)
        if not stocks:
            print("[ERROR] 估值/行业过滤后股池为空", file=sys.stderr)
            sys.exit(1)

    # 3. 限流保护 (ST 过滤后再检查)
    if len(stocks) > args.max_stocks:
        print(f"[ERROR] 股票数 {len(stocks)} 超过 --max-stocks {args.max_stocks}, 请缩小范围或调大阈值",
              file=sys.stderr)
        sys.exit(1)

    # 4. 默认信号: all
    signal_aliases = args.signal or ["all"]

    # 5. v3.7: 验证 sort_by (--rank-by 别名保留向后兼容)
    # v3.7: --sort-by 优先, --rank-by 向后兼容
    sort_by = args.sort_by if args.sort_by else args.rank_by
    valid_sort_keys = {"composite", "total_mv", "turnover_rate", "last_close", "ts_code"}
    alias_to_def = {s["alias"] for s in ALL_SIGNALS}
    valid_sort_keys |= alias_to_def
    if sort_by not in valid_sort_keys:
        print(f"[ERROR] --sort-by/--rank-by 未知字段: {sort_by}", file=sys.stderr)
        print(f"  可用: composite, total_mv, turnover_rate, last_close, ts_code, 或任意信号别名", file=sys.stderr)
        print(f"  信号别名: {', '.join(sorted(alias_to_def))}", file=sys.stderr)
        sys.exit(1)
    args.rank_by = sort_by  # 后面统一用 args.rank_by

    # 6. v3.5.1: 加载自定义权重
    try:
        weights = _load_weights(args.weights_file or "")
    except Exception as e:
        print(f"[ERROR] 权重文件加载失败: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"[scan] 共 {len(stocks)} 只股, 信号={signal_aliases}, rank_by={args.rank_by}, top={args.top}",
          file=sys.stderr)

    # 7. 跑
    df, detail = run_scan_signals(stocks, signal_aliases, days=args.days,
                                    rank_by=args.rank_by, top=args.top,
                                    weights=weights, reverse=not args.reverse)

    if df.empty:
        print("[ERROR] 全部股票都失败, 无结果", file=sys.stderr)
        sys.exit(1)

    # 7.5 v3.6.1: 市值 + 换手率过滤 (需要 detail 含 last_close/turnover_rate)
    if args.market_cap_min is not None or args.turnover_min is not None:
        before = len(detail)
        detail, dropped = _filter_by_market_cap_turnover(detail,
                                                          market_cap_min=args.market_cap_min,
                                                          turnover_min=args.turnover_min)
        if dropped:
            reason_counts = {}
            for _, _, reason in dropped:
                key = reason.split("=")[0].split("<")[0].split(">")[0]
                reason_counts[key] = reason_counts.get(key, 0) + 1
            summary = ", ".join(f"{k}:{v}" for k, v in sorted(reason_counts.items()))
            print(f"[scan] 市值/换手过滤: {before} → {len(detail)} 只, 跳过 {len(dropped)} ({summary})",
                  file=sys.stderr)
            for s, name, reason in dropped[:5]:
                print(f"        - {s} {name}: {reason}", file=sys.stderr)
            if len(dropped) > 5:
                print(f"        ... +{len(dropped)-5} more", file=sys.stderr)
        if not detail:
            print("[ERROR] 市值/换手过滤后股池为空", file=sys.stderr)
            sys.exit(1)
        # 重排序 + 重 top (从已过滤的 detail 重建 df, 用 v3.7 _sort_detail)
        items = _sort_detail(detail, sort_by=args.rank_by, reverse=not args.reverse)
        # 重建 df (同 run_scan_signals 末尾逻辑)
        if items:
            all_aliases = list(items[0][1]["per_signal"].keys())
            rows = []
            for rank, (ts_code, r) in enumerate(items[:args.top], 1):
                row = {"rank": rank, "ts_code": ts_code,
                       "last_close": r["last_close"],
                       "last_dt": r["last_dt"].strftime("%Y-%m-%d"),
                       "composite": r["composite"],
                       "total_mv": r.get("total_mv", 0),
                       "turnover_rate": r.get("turnover_rate", 0)}
                for alias in all_aliases:
                    row[f"{alias}_n"] = r["per_signal"][alias]["n"]
                    row[f"{alias}_last"] = r["per_signal"][alias]["last"].strftime("%Y-%m-%d") \
                        if r["per_signal"][alias]["last"] else "—"
                rows.append(row)
            df = pd.DataFrame(rows)

    # 8. v3.8: 输出 (--format + --output, 向后兼容 --output-csv)
    out_path = args.output or args.output_csv
    fmt = args.format
    if not fmt:
        # 从后缀猜
        if out_path:
            suf = Path(out_path).suffix.lower()
            fmt = {".csv": "csv", ".md": "markdown", ".json": "json"}.get(suf, "table")
        else:
            fmt = "table"
    # fmt 已在 # 1.5 验证过, 此处不需要

    # 生成输出
    name_map = _fetch_st_names_via_tushare()
    out_df = df.copy()
    out_df.insert(1, "name", out_df["ts_code"].map(lambda c: name_map.get(c, "")))

    if out_path:
        # 有 --output → 保存到文件
        try:
            out_path = Path(out_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            if fmt == "csv":
                out_df.to_csv(out_path, index=False, encoding="utf-8-sig")
            elif fmt == "markdown":
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(f"# 多股扫描结果 (sort_by={args.rank_by})\n\n")
                    f.write(f"成功 {len(detail)}/{len(stocks)} 只, 取前 {len(df)} 名\n\n")
                    f.write(out_df.to_markdown(index=False))
            elif fmt == "json":
                out_df.to_json(out_path, orient="records", force_ascii=False, indent=2)
            elif fmt == "table":
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(f"# 多股扫描结果 (sort_by={args.rank_by})\n\n")
                    f.write(f"成功 {len(detail)}/{len(stocks)} 只, 取前 {len(df)} 名\n\n")
                    f.write(out_df.to_markdown(index=False))
            print(f"[scan] {fmt.upper()} 已保存: {out_path} ({len(out_df)} 行)", file=sys.stderr)
        except Exception as e:
            print(f"[ERROR] {fmt.upper()} 保存失败: {type(e).__name__}: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # 无 --output → stdout
        if fmt == "csv":
            import io
            buf = io.StringIO()
            out_df.to_csv(buf, index=False, encoding="utf-8")  # stdout 不需要 BOM
            print(buf.getvalue(), end="")
            return  # csv 格式输出完 return
        elif fmt == "markdown":
            print(out_df.to_markdown(index=False))
            return  # markdown 同上
        elif fmt == "json":
            print(out_df.to_json(orient="records", force_ascii=False, indent=2))
            return  # json 同上
        elif fmt == "table":
            pass  # 走下面 9. 原表格输出
    # fmt == "table" 无 --output → 走下面 9. 原表格输出

    # 9. 输出表格 (同 v3.5)
    print(f"\n=== 多股扫描排名 (rank_by={args.rank_by}) ===\n")
    print(f"成功 {len(detail)}/{len(stocks)} 只, 取前 {len(df)} 名:\n")

    # 表头
    sig_cols = [c for c in df.columns if c.endswith("_n") and not c.startswith("composite")]
    has_mv = "total_mv" in df.columns
    has_tr = "turnover_rate" in df.columns
    header = f"{'rank':>4}  {'代码':<12}  {'收盘':>7}  {'最近日期':<10}  {'composite':>9}"
    if has_mv:
        header += f"  {'市值亿':>7}"
    if has_tr:
        header += f"  {'换手%':>6}"
    for c in sig_cols:
        alias = c[:-2]  # 去掉 _n
        header += f"  {alias:>4}"
    print(header)
    print("-" * len(header))

    # 表体
    for _, row in df.iterrows():
        line = f"{row['rank']:>4}  {row['ts_code']:<12}  {row['last_close']:>7.2f}  {row['last_dt']:<10}  {row['composite']:>9.1f}"
        if has_mv:
            line += f"  {row['total_mv']:>7.0f}"
        if has_tr:
            line += f"  {row['turnover_rate']:>6.2f}"
        for c in sig_cols:
            line += f"  {int(row[c]):>4}"
        print(line)

    # 10. 详细输出 (每个信号最近触发日期)
    print(f"\n=== 详细: 各信号最近触发日期 ===\n")
    sig_last_cols = [c for c in df.columns if c.endswith("_last")]
    header2 = f"{'rank':>4}  {'代码':<12}"
    for c in sig_last_cols:
        alias = c[:-5]
        header2 += f"  {alias:>10}"
    print(header2)
    print("-" * len(header2))
    for _, row in df.iterrows():
        line = f"{int(row['rank']):>4}  {row['ts_code']:<12}"
        for c in sig_last_cols:
            line += f"  {row[c]:>10}"
        print(line)

    # 10.5 v3.7: --show-stats 输出分布 (百分位 + min/median/max)
    if args.show_stats and detail:
        import statistics
        composites = [r["composite"] for r in detail.values()]
        mvs = [r.get("total_mv", 0) for r in detail.values() if r.get("total_mv", 0) > 0]
        turnovers = [r.get("turnover_rate", 0) for r in detail.values() if r.get("turnover_rate", 0) > 0]
        closes = [r["last_close"] for r in detail.values() if r["last_close"] > 0]

        def pctile(vals, p):
            if not vals: return 0
            s = sorted(vals)
            k = (len(s) - 1) * p / 100
            f, c = int(k), min(int(k) + 1, len(s) - 1)
            return s[f] + (s[c] - s[f]) * (k - f)

        print(f"\n=== 分布统计 (样本: {len(detail)} 只) ===")
        for label, vals, fmt in [
            ("composite",  composites, "{:>7.1f}"),
            ("市值(亿)",  mvs,        "{:>7.0f}"),
            ("换手率(%)", turnovers,   "{:>7.2f}"),
            ("收盘价(元)", closes,     "{:>7.2f}"),
        ]:
            if not vals:
                continue
            print(f"  {label:<10}  min={fmt.format(min(vals))}  p25={fmt.format(pctile(vals, 25))}  "
                  f"p50={fmt.format(pctile(vals, 50))}  p75={fmt.format(pctile(vals, 75))}  "
                  f"max={fmt.format(max(vals))}  mean={fmt.format(statistics.mean(vals))}")

    # 11. 打分公式说明
    print(f"\n=== 打分公式 ===")
    if weights != SIGNAL_WEIGHTS:
        print(f"  ⚠️ 使用自定义权重 (来自: {args.weights_file}):")
        for k in sorted(set(SIGNAL_WEIGHTS) | set(weights)):
            if SIGNAL_WEIGHTS.get(k) != weights.get(k):
                print(f"    {k}: {SIGNAL_WEIGHTS.get(k, '默认0.5')} → {weights[k]} (覆盖)")
    print(f"  composite = Σ (信号触发次数 × 信号权重) + 时效加分")
    print(f"  权重: 一买/一卖=5, 三买=4, 二买卖=3, MACD=1, 其他辅助=0.5")
    print(f"  时效加分: 最新触发距今 <5天 +3, <20天 +1")
    print(f"  排名: 按 composite 降序 (或 --rank-by 指定单信号)")

    # 12. v4.0: --save-preset 保存当前所有 flag 为 preset
    if args.save_preset:
        # args.stocks/watchlist 可能含路径名, 不保存. 只保存参数化的 flag.
        out = _save_user_preset(args.save_preset, args)
        print(f"\n✓ preset 已保存: {out}", file=sys.stderr)
        print(f"  下次调用: python3 czsc_signals.py scan --preset-file {args.save_preset} [其他动态参数]", file=sys.stderr)


