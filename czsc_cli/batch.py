#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# czsc_cli.batch v5.2.3.5 - 批量层 (batch runner + dry-run + slack push + retry)
#
# v5.2.3.5 真拆: 替代 v5.1 __getattr__ lazy 转发, 直接实现在这里.
# czsc_signals.py 里这些函数改为 from czsc_cli.batch import ..., 保持向后兼容 + is 关系.
#
# 包含 (10 函数):
#   - 1 slack push: _push_to_slack
#   - 1 batch config: _load_batch_config
#   - 2 dry-run: _batch_dry_run / _merge_scan_args_for_dry_run
#   - 4 dry-run helpers: _filter_bak_basic_dict / _print_filter_summary / _fetch_basic_cached / _load_watchlist_safe
#   - 2 batch runner: _run_batch / _execute_one_run
#
# 跨域依赖:
#   - czsc_cli.scanner (cmd_scan via _execute_one_run)
#   - czsc_cli.preset (_save_user_preset, PRESET_DIR)
#   - czsc_cli.data (_fetch_bak_basic_via_tushare)
#   - czsc_cli.signals (run_signals via cmd_scan)
#   - czsc_signals (BUILTIN_PRESETS - 函数内 import 避免循环)

import copy
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

# v5.2.3.5: 跨域 import (单向, 无循环)
from czsc_cli.scanner import cmd_scan
from czsc_cli.preset import _save_user_preset, PRESET_DIR
from czsc_cli.data import _fetch_bak_basic_via_tushare


# ---------------------------------------------------------------------------
# v5.2.3.5: slack push + batch config 加载 (从 czsc_signals 真拆)
# ---------------------------------------------------------------------------

def _push_to_slack(webhook_url: str, report_text: str, fmt: str) -> bool:
    """推报告到 Slack incoming webhook.
    Slack 不渲染 HTML, 所以 HTML 格式转成纯文本摘要.
    返回 True/False (成功/失败).
    """
    try:
        import urllib.request
        import urllib.error
        # Slack webhook 只接受 JSON {"text": "..."}, 5KB 限制
        if fmt == "markdown":
            payload_text = f"```\n{report_text[:3500]}\n```"  # Slack code block
        elif fmt == "json":
            try:
                d = json.loads(report_text)
                s = d.get("summary", {})
                results = d.get("results", [])
                lines = [
                    f"*czsc batch scan 报告*",
                    f"总计: {s.get('total', '?')}  成功: {s.get('success', '?')}  失败: {s.get('failed', '?')}",
                    "",
                ]
                for r in results:
                    status = "✓" if r.get("ok") else "✗"
                    lines.append(f"{status} {r.get('name')} ({r.get('duration_sec', 0)}s) — {r.get('message', '')}")
                payload_text = "\n".join(lines)
            except Exception:
                payload_text = report_text[:3500]
        else:  # html
            payload_text = report_text.replace("<", "&lt;").replace(">", "&gt;")[:3500]
        body = json.dumps({"text": payload_text}).encode("utf-8")
        req = urllib.request.Request(webhook_url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            ok = resp.status == 200
            if ok:
                print(f"[slack] ✓ 推送成功 ({len(payload_text)} chars, fmt={fmt})", file=sys.stderr)
            return ok
    except urllib.error.URLError as e:
        print(f"[ERROR] slack 推送失败 (网络): {e}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"[ERROR] slack 推送失败: {type(e).__name__}: {e}", file=sys.stderr)
        return False


# ---------------------------------------------------------------------------
# v4.3: 批量扫描 (batch-scan) — YAML/JSON/TOML 配置文件 + preset + watchlist
# ---------------------------------------------------------------------------

def _load_batch_config(path: str) -> list:
    """加载批量配置 (按扩展名自动检测格式), 返回 runs list.

    支持格式:
      - .yaml / .yml → PyYAML
      - .json → json
      - .toml → tomllib (Py 3.11+)
    结构:
      { "runs": [
          { "name": "xxx", "preset": "my_bank", "watchlist": "xxx",
            "format": "markdown", "output": "xxx", "top": 10, ...可选 scan flag... }
        ] }
    """
    p = Path(path).expanduser()
    if not p.exists():
        print(f"[ERROR] batch 配置文件不存在: {p}", file=sys.stderr)
        sys.exit(1)
    suffix = p.suffix.lower()
    try:
        if suffix in (".yaml", ".yml"):
            import yaml
            with open(p, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
        elif suffix == ".json":
            with open(p, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        elif suffix == ".toml":
            import tomllib
            with open(p, "rb") as f:
                cfg = tomllib.load(f)
        else:
            print(f"[ERROR] batch 配置文件格式不支持: {suffix} (.yaml/.yml/.json/.toml)", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"[ERROR] batch 配置解析失败: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
    runs = cfg.get("runs") if isinstance(cfg, dict) else None
    if not isinstance(runs, list) or not runs:
        print(f"[ERROR] batch 配置需要 'runs' 列表字段 (至少 1 项)", file=sys.stderr)
        sys.exit(1)
    for i, r in enumerate(runs):
        if not isinstance(r, dict):
            print(f"[ERROR] runs[{i}] 必须是 dict: {r!r}", file=sys.stderr)
            sys.exit(1)
    return runs


# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# v5.2.3.5: dry-run + filter helpers + batch runner + execute (从 czsc_signals 真拆)
# ---------------------------------------------------------------------------

def _batch_dry_run(runs: list, parent_args) -> None:
    """v4.7: 模拟跑 batch, 只看 filter 后股票数, 不调 K 线 API.
    拉 1 次 bak_basic (5500+ 股) 本地 filter, 报每个 run 剩多少股 + 预计耗时.
    """
    if not runs:
        print("[dry-run] batch config 为空, 无 run 可模拟", file=sys.stderr)
        return
    print(f"[dry-run] 模拟 {len(runs)} 个 run (不调 K 线 API, 不烧 Tushare 配额)\n", file=sys.stderr)
    # 复用 v3.6 已有的 bak_basic 缓存 (1 调拿 5500+ 股, session 内只拉 1 次)
    basic_cache = _fetch_bak_basic_via_tushare()
    if not basic_cache:
        print("[dry-run] [ERROR] bak_basic 拉取失败/为空, 跳过", file=sys.stderr)
        sys.exit(1)
    total_n_stocks = 0
    for i, run_cfg in enumerate(runs, 1):
        name = run_cfg.get("name", f"run_{i}")
        merged = _merge_scan_args_for_dry_run(parent_args, run_cfg)
        # v4.7 bug fix: 展开 preset (同 cmd_scan 逻辑, 不展 set_signal / save 等副作用)
        if getattr(merged, "preset", ""):
            _BUILTIN = {"value", "bank", "momentum", "bargain"}
            if merged.preset in _BUILTIN:
                _apply_preset(merged)
            else:
                print(f"[dry-run] ⚠️ run {name}: 未知 builtin preset {merged.preset!r}", file=sys.stderr)
        if getattr(merged, "preset_file", ""):
            try:
                cfg = _load_user_preset(merged.preset_file)
                _apply_user_preset(merged, cfg)
            except SystemExit as e:
                print(f"[dry-run] ⚠️ run {name}: preset_file={merged.preset_file!r} 加载失败 (exit {e.code})", file=sys.stderr)
        # 应用本地 filter (industry / pe / pb / market_cap / exclude_st)
        filtered = _filter_bak_basic_dict(basic_cache, merged)
        # 进一步用 watchlist 限定
        watchlist = getattr(merged, "watchlist", "") or ""
        if watchlist:
            ws = _load_watchlist_safe(watchlist)
            if ws is not None and not ws.empty:
                wl_codes = set(ws["ts_code"].tolist())
                filtered = {k: v for k, v in filtered.items() if k in wl_codes}
        n_stocks = len(filtered)
        est_sec = n_stocks * _STOCK_SEC_PER
        preset_info = ""
        if getattr(merged, "preset", ""):
            preset_info = f" [preset={merged.preset}]"
        elif getattr(merged, "preset_file", ""):
            preset_info = f" [preset-file={merged.preset_file}]"
        elif getattr(merged, "industry", ""):
            preset_info = f" [industry={merged.industry}]"
        print(f"  [{i}/{len(runs)}] {name}{preset_info}", file=sys.stderr)
        print(f"    filter 后股票数: {n_stocks}", file=sys.stderr)
        print(f"    预计耗时: ~{est_sec:.1f}s ({n_stocks} 股 × {_STOCK_SEC_PER}s)", file=sys.stderr)
        _print_filter_summary(merged, file=sys.stderr)
        print("", file=sys.stderr)
        total_n_stocks += n_stocks
    total_est = total_n_stocks * _STOCK_SEC_PER
    print(f"[dry-run] 汇总: {len(runs)} 个 run, 总预计耗时 ~{total_est:.1f}s ({total_n_stocks} 只股)", file=sys.stderr)
    n_parallel = max(1, getattr(parent_args, "batch_parallel", 1) or 1)
    if n_parallel > 1:
        actual = total_est / n_parallel + n_parallel * 0.5
        print(f"[dry-run] 并行 {n_parallel} 估计: ~{actual:.1f}s (含调度开销)", file=sys.stderr)
    print("[dry-run] ✓ 模拟完成, 未调 K 线 API, 未烧 Tushare 配额", file=sys.stderr)


def _merge_scan_args_for_dry_run(parent_args, run_cfg: dict):
    """v4.7: 复制 parent_args, 用 run_cfg 字段覆盖 (排除 batch/slack/dry-run)."""
    import copy
    new_args = copy.copy(parent_args)
    new_args.batch_scan = ""
    new_args.batch_output = ""
    new_args.batch_output_format = getattr(parent_args, "batch_output_format", "markdown")
    new_args.slack_webhook = ""
    new_args.batch_dry_run = False
    for k, v in run_cfg.items():
        if k in ("name", "batch_dry_run"):
            continue
        if k == "preset":
            # v4.3/4.7: 自动判别 builtin vs custom (复用同白名单)
            _BUILTIN = {"value", "bank", "momentum", "bargain"}
            if v in _BUILTIN:
                new_args.preset = v
                new_args.preset_file = ""
            else:
                new_args.preset_file = v
                new_args.preset = ""
        elif hasattr(new_args, k):
            setattr(new_args, k, v)
    return new_args


def _filter_bak_basic_dict(basic_cache: dict, args) -> dict:
    """v4.7: 复用 v3.6 _BAK_BASIC_CACHE dict, 本地 filter.
    turnover_min 在 dry-run 跳过 (需 vol 数据, 拉 K 线才有).
    """
    result = {}
    industry = getattr(args, "industry", "") or ""
    pe_max = getattr(args, "pe_max", None)
    pe_min = getattr(args, "pe_min", None)
    pb_max = getattr(args, "pb_max", None)
    mcap_min = getattr(args, "market_cap_min", None)
    exclude_st = getattr(args, "exclude_st", False)
    exclude_kw = getattr(args, "exclude_keyword", "") or ""
    kw_list = [k.strip() for k in exclude_kw.split(",") if k.strip()] if exclude_kw else []
    for ts_code, info in basic_cache.items():
        name = info.get("name", "") or ""
        ind = info.get("industry", "") or ""
        pe = info.get("pe", 0) or 0
        pb = info.get("pb", 0) or 0
        # industry
        if industry and industry not in ind:
            continue
        # pe
        if pe_max and (pe <= 0 or pe > pe_max):
            continue
        if pe_min and pe < pe_min:
            continue
        # pb
        if pb_max and (pb <= 0 or pb > pb_max):
            continue
        # market_cap (用近似 股价 10 元 估, dry-run 不准)
        # 实际 dry-run 拿不到股价, 跳过市值 filter 或警告
        # mcap_min 跳过 (拿不到股价)
        # exclude_st
        if exclude_st and "ST" in name.upper():
            continue
        # exclude_keyword
        if kw_list and any(kw in name for kw in kw_list):
            continue
        result[ts_code] = info
    return result


def _print_filter_summary(args, file=None) -> None:
    """v4.7: 打印 filter 条件摘要."""
    if file is None:
        file = sys.stderr
    parts = []
    if getattr(args, "industry", ""):
        parts.append(f"industry={args.industry}")
    if getattr(args, "pe_max", None):
        parts.append(f"pe_max={args.pe_max}")
    if getattr(args, "pe_min", None):
        parts.append(f"pe_min={args.pe_min}")
    if getattr(args, "pb_max", None):
        parts.append(f"pb_max={args.pb_max}")
    if getattr(args, "market_cap_min", None):
        parts.append(f"market_cap_min={args.market_cap_min}亿")
    if getattr(args, "turnover_min", None):
        parts.append(f"turnover_min={args.turnover_min}%(dry-run跳过)")
    if getattr(args, "exclude_st", False):
        parts.append("exclude_st=True")
    if getattr(args, "exclude_keyword", ""):
        parts.append(f"exclude_keyword={args.exclude_keyword}")
    if parts:
        print(f"    filter: {', '.join(parts)}", file=file)
    else:
        print(f"    filter: (无, 全市场 scan)", file=file)


def _fetch_basic_cached():
    """v4.7: dry-run 实际不调, 函数保留占位 (复用 _fetch_bak_basic_via_tushare)."""
    return _fetch_bak_basic_via_tushare()


def _load_watchlist_safe(path: str):
    """v4.7: 加载 watchlist (如果存在), 失败返回 None (dry-run 跳过)."""
    import pandas as pd
    try:
        if not Path(path).exists():
            return None
        codes = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # 只取第一个 token (跳过名字, e.g. "000001.SZ 平安银行" → "000001.SZ")
                codes.append(line.split()[0])
        return pd.DataFrame({"ts_code": codes})
    except Exception as e:
        print(f"[dry-run] watchlist 加载失败: {e}", file=sys.stderr)
        return None


def _run_batch(args) -> None:
    """v4.3: 批量跑多个 scan 预设, 汇总结果.
    v4.5: 支持 --batch-parallel N 并行跑 (ThreadPoolExecutor, 提速 ~Nx).

    每个 run 可以独立指定 preset / watchlist / format / output 等.
    args (父) 上的 --preset-dir / --save-preset / --preset-tag 等会透传到所有 run.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    runs = _load_batch_config(args.batch_scan)
    n_parallel = max(1, getattr(args, "batch_parallel", 1) or 1)
    n_retry = max(0, min(5, getattr(args, "batch_retry", 0) or 0))
    if getattr(args, "batch_dry_run", False):
        _batch_dry_run(runs, args)
        return
    if n_parallel > 1:
        print(f"[batch] 加载配置: {args.batch_scan} ({len(runs)} 个 run, 并行={n_parallel})", file=sys.stderr)
    else:
        print(f"[batch] 加载配置: {args.batch_scan} ({len(runs)} 个 run)", file=sys.stderr)
    if n_retry > 0:
        print(f"[batch] 失败重试: {n_retry} 次 (指数退避 1/2/4/8/16s)", file=sys.stderr)
    def _run_one(idx_run):
        i, run_cfg = idx_run
        name = run_cfg.get("name", f"run_{i}")
        start = time.time()
        try:
            msg = _execute_one_run(run_cfg, args)
            ok = True
        except SystemExit as e:
            ok = False
            msg = f"exit({e.code})"
        except Exception as e:
            ok = False
            msg = f"{type(e).__name__}: {e}"
        dur = time.time() - start
        return (i, name, ok, msg, dur)
    # 并行 / 串行 分支
    indexed = list(enumerate(runs, 1))
    if n_parallel == 1:
        results_raw = [_run_one(idx) for idx in indexed]
    else:
        with ThreadPoolExecutor(max_workers=n_parallel) as ex:
            futures = [ex.submit(_run_one, idx) for idx in indexed]
            results_raw = [f.result() for f in as_completed(futures)]
    # 按原序排序 (as_completed 不保证顺序)
    results_raw.sort(key=lambda x: x[0])
    # v4.8: 重试失败的 run (指数退避 1/2/4/8/16s, 只重试失败的)
    if n_retry > 0:
        for attempt in range(1, n_retry + 1):
            failed_indices = [r for r in results_raw if not r[2]]  # r = (i, name, ok, msg, dur)
            if not failed_indices:
                break
            backoff = 2 ** (attempt - 1)  # 1, 2, 4, 8, 16
            print(f"[batch] 重试第 {attempt}/{n_retry} 轮: {len(failed_indices)} 个失败 run, 等待 {backoff}s...", file=sys.stderr)
            time.sleep(backoff)
            for r in failed_indices:
                i, name = r[0], r[1]
                print(f"[batch] [retry {attempt}] 重跑 {name}...", file=sys.stderr)
                new_result = _run_one((i, runs[i - 1]))
                if new_result[2]:  # ok
                    print(f"[batch] [retry {attempt}] {name} ✓ (重试成功)", file=sys.stderr)
                results_raw[results_raw.index(r)] = new_result
    results = [(n, ok, m, d) for _, n, ok, m, d in results_raw]
    # 输出逐个状态 (都输出, 不管串行并行)
    for i, name, ok, msg, dur in results_raw:
        status = "✓" if ok else "✗"
        print(f"[batch] [{i}/{len(runs)}] {name} {status} ({dur:.1f}s) — {msg}", file=sys.stderr)
    # 汇总
    n_ok = sum(1 for _, ok, _, _ in results if ok)
    print(f"\n[batch] 全部完成: {n_ok}/{len(results)} 成功", file=sys.stderr)
    for name, ok, msg, dur in results:
        status = "✓" if ok else "✗"
        print(f"  {status} {name}  ({dur:.1f}s)  {msg}", file=sys.stderr)
    if args.batch_output or getattr(args, "slack_webhook", ""):
        out = Path(args.batch_output).expanduser() if args.batch_output else None
        if out:
            out.parent.mkdir(parents=True, exist_ok=True)
        fmt = getattr(args, "batch_output_format", "markdown") or "markdown"
        report_text = ""
        if fmt == "json":
            payload = {
                "_meta": {
                    "config": args.batch_scan,
                    "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "skill_version": "v4.6",
                },
                "summary": {
                    "total": len(results),
                    "success": n_ok,
                    "failed": len(results) - n_ok,
                },
                "results": [
                    {"rank": i + 1, "name": n, "ok": ok, "duration_sec": round(d, 2), "message": m}
                    for i, (n, ok, m, d) in enumerate(results)
                ],
            }
            report_text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
            if out:
                with open(out, "w", encoding="utf-8") as f:
                    f.write(report_text)
        elif fmt == "html":
            rows_html = "\n".join(
                f"<tr><td>{i+1}</td><td>{n}</td><td>{'✓' if ok else '✗'}</td><td>{d:.1f}s</td><td>{m}</td></tr>"
                for i, (n, ok, m, d) in enumerate(results)
            )
            color = "#10b981" if n_ok == len(results) else "#f59e0b"
            html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>czsc batch scan 报告</title>
<style>
  body {{ font-family: -apple-system, "Segoe UI", sans-serif; max-width: 900px; margin: 40px auto; padding: 0 20px; color: #1f2937; }}
  h1 {{ color: #111827; border-bottom: 2px solid #e5e7eb; padding-bottom: 8px; }}
  .meta {{ background: #f9fafb; padding: 12px 16px; border-radius: 6px; margin: 16px 0; }}
  .badge {{ display: inline-block; padding: 4px 10px; border-radius: 4px; background: {color}; color: white; font-weight: bold; }}
  table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
  th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #e5e7eb; }}
  th {{ background: #f3f4f6; font-weight: 600; }}
  tr:hover {{ background: #f9fafb; }}
  .ok {{ color: #10b981; font-weight: bold; }}
  .fail {{ color: #ef4444; font-weight: bold; }}
</style>
</head>
<body>
<h1>🦐 czsc batch scan 报告</h1>
<div class="meta">
  <strong>生成时间:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}<br>
  <strong>配置:</strong> <code>{args.batch_scan}</code><br>
  <strong>结果:</strong> <span class="badge">{n_ok}/{len(results)} 成功</span>
</div>
<table>
  <thead><tr><th>#</th><th>名称</th><th>状态</th><th>耗时</th><th>说明</th></tr></thead>
  <tbody>
    {rows_html}
  </tbody>
</table>
</body>
</html>"""
            report_text = html
            if out:
                with open(out, "w", encoding="utf-8") as f:
                    f.write(html)
        else:  # markdown (默认)
            md_lines = [
                f"# czsc batch scan 报告 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "",
                f"**配置**: `{args.batch_scan}`",
                "",
                f"**结果**: {n_ok}/{len(results)} 成功",
                "",
                "| # | 名称 | 状态 | 耗时 | 说明 |",
                "|---|---|---|---|---|",
            ]
            for i, (name, ok, msg, dur) in enumerate(results, 1):
                md_lines.append(f"| {i} | {name} | {'✓' if ok else '✗'} | {dur:.1f}s | {msg} |")
            report_text = "\n".join(md_lines) + "\n"
            if out:
                with open(out, "w", encoding="utf-8") as f:
                    f.write(report_text)
        if out:
            print(f"[batch] 汇总报告 ({fmt}): {out}", file=sys.stderr)
        # v4.6: slack 推送 (不依赖 batch_output, 可独立使用)
        slack_url = getattr(args, "slack_webhook", "") or os.environ.get("SLACK_WEBHOOK_URL", "")
        if slack_url:
            # v4.9: --batch-notify-on-success 只全成功才推
            notify_only_success = getattr(args, "batch_notify_on_success", False)
            if notify_only_success and n_ok < len(results):
                print(f"[batch] 静默 Slack 推送: {n_ok}/{len(results)} 成功 (--batch-notify-on-success)", file=sys.stderr)
            else:
                _push_to_slack(slack_url, report_text, fmt)
    if n_ok < len(results):
        sys.exit(1)


def _execute_one_run(run_cfg: dict, parent_args) -> str:
    """v4.3: 跑单个 run (从 batch config).

    策略: 复制 parent_args, 用 run_cfg 里的字段覆盖, 调 cmd_scan(新 args).
    返回结果消息.
    """
    import copy
    new_args = copy.copy(parent_args)
    # 父 --batch-scan 必须清掉, 不然递归
    new_args.batch_scan = ""
    new_args.batch_output = ""
    new_args.batch_output_format = parent_args.batch_output_format
    new_args.slack_webhook = ""  # 子 run 不重复推, 只父级推 1 次
    # run_cfg 里的字段覆盖 parent_args (除了 batch-scan/output 自身)
    SCAN_OVERRIDE_KEYS = {
        "name", "preset", "preset_file", "watchlist", "stocks",
        "format", "output", "top", "days", "signal",
        "exclude_st", "exclude_keyword", "industry",
        "pe_min", "pe_max", "pb_min", "pb_max",
        "market_cap_min", "turnover_min",
        "sort_by", "reverse", "show_stats",
        "save_preset", "preset_tag",
    }
    for k, v in run_cfg.items():
        if k == "name":
            continue
        if k == "preset":
            # v4.3: 自动判别 builtin vs custom (与 _apply_preset 里的 4 个内置名比较)
            BUILTIN_PRESETS = {"value", "bank", "momentum", "bargain"}
            if v in BUILTIN_PRESETS:
                new_args.preset = v
                new_args.preset_file = ""
            else:
                # 当 preset_file 处理
                new_args.preset_file = v
                new_args.preset = ""
        elif k == "preset_file":
            new_args.preset_file = v
            new_args.preset = ""
        elif k == "preset_tag":
            # 父 --preset-tag 覆盖, 子明确传才覆盖
            if v:
                new_args.preset_tag = v
        else:
            # 动态 setattr, 只允许 SCAN_OVERRIDE_KEYS 里
            attr = k.replace("-", "_")
            if attr in SCAN_OVERRIDE_KEYS:
                setattr(new_args, attr, v)
    # 透传父级 --preset-dir (子没设才用)
    if "preset_dir" not in run_cfg:
        new_args.preset_dir = parent_args.preset_dir
    # 跑
    cmd_scan(new_args)
    # output 路径, 如果有
    out = run_cfg.get("output", "")
    if out:
        return f"输出到 {out}"
    return "stdout"

# CLI 入口
# ---------------------------------------------------------------------------
