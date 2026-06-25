#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""czsc_cli.preset v5.2.3.2 — 策略层 (9 preset subcommands + 4 helpers).

v5.2.3.2 真拆: 替代 v5.1 __getattr__ lazy 转发, 直接实现在这里.
czsc_signals.py 里这些函数改为 `from czsc_cli.preset import ...`, 保持向后兼容 + `is` 关系.

包含:
  - PRESET_DIR module-level Path (从 czsc_signals.L68 搬到 preset, 8 cmd 全用)
  - PRESET_SAVE_FLAGS tuple (从 czsc_signals.L499 搬到 preset, 3 helpers + 1 validate 用)
  - 3 user preset helpers (save/load/apply)
  - 1 override helper (override_preset_dir, 副作用改 PRESET_DIR)
  - 9 cmd_preset_* subcommands (save/list/show/delete/export/import/diff/merge/validate)

v5.2.3.2 invariant:
  - 不再需要 _EXPORTS / _imported / __getattr__ (v5.1 lazy load 已废)
  - BUILTIN_PRESETS 留在 czsc_signals (被 v3.5.0 BUILTIN_PRESETS 引用, 不循环)
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path


# ---------------------------------------------------------------------------
# module-level state (从 czsc_signals 搬来)
# ---------------------------------------------------------------------------

# v4.1: 自定义 preset 存储路径 (优先环境变量 CZSC_PRESET_DIR, 用于团队共享)
PRESET_DIR = Path(os.environ.get("CZSC_PRESET_DIR", str(Path.home() / ".czsc-presets"))).expanduser()

# v4.0: 可保存的 flag 白名单 (这些 flag 才会被序列化到 JSON)
PRESET_SAVE_FLAGS = (
    "industry", "exclude_keyword",
    "pe_max", "pe_min", "pb_max", "pb_min",
    "market_cap_min", "turnover_min",
    "sort_by", "reverse", "show_stats",
    "signal", "days", "top", "exclude_st",
    "format", "output",
)


# ---------------------------------------------------------------------------
# 3 user preset helpers (private, 用 _ 前缀)
# ---------------------------------------------------------------------------

def _save_user_preset(name: str, args) -> Path:
    """保存当前 args 里的可序列化 flag 为 JSON 文件.
    只保存"非默认"的 flag (null/空/False/0 跳过), JSON 更紧凑.
    name: preset 名 (会验证合法)
    返回保存的路径.
    """
    if not name.replace("_", "").isalnum():
        print(f"[ERROR] preset 名只能含字母/数字/下划线: {name!r}", file=sys.stderr)
        sys.exit(1)
    PRESET_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PRESET_DIR / f"{name}.json"
    cfg = {}
    for attr in PRESET_SAVE_FLAGS:
        val = getattr(args, attr, None)
        # 只保存"用户显式设置"的 (跳过默认占位: null, "", [], 0, False, {})
        if val is None or val == "" or val == [] or val == {} or val == 0 or val == 0.0 or val is False:
            continue
        cfg[attr] = val
    cfg["_meta"] = {
        "name": name,
        "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "skill_version": "v4.6",
        "source_cmd": "scan",
    }
    # v4.3: --preset-tag 标签 (逗号分隔, 存入 _meta.tags)
    preset_tag = getattr(args, "preset_tag", "") or ""
    if preset_tag:
        cfg["_meta"]["tags"] = [t.strip() for t in preset_tag.split(",") if t.strip()]
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2, default=str)
    return out_path


def _load_user_preset(path: str) -> dict:
    """加载 JSON preset 文件, 返回 cfg dict. 验证文件存在与格式. """
    p = Path(path).expanduser()
    if not p.is_absolute():
        # 默认路径: ~/.czsc-presets/<name>.json
        p = PRESET_DIR / path
    if p.suffix == "":
        p = p.with_suffix(".json")
    if not p.exists():
        print(f"[ERROR] preset 文件不存在: {p}", file=sys.stderr)
        print(f"  提示: 用 'czsc_signals.py preset save <name>' 保存, 或检查路径", file=sys.stderr)
        sys.exit(1)
    try:
        with open(p, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        if not isinstance(cfg, dict):
            raise ValueError("JSON 顶层不是 dict")
        return cfg
    except json.JSONDecodeError as e:
        print(f"[ERROR] preset 文件 JSON 解析失败: {p}: {e}", file=sys.stderr)
        sys.exit(1)


def _apply_user_preset(args, cfg: dict) -> None:
    """v4.0: 把自定义 preset 的参数应用到 args (不覆盖用户显式传的值).
    逻辑同 _apply_preset: 只填充"默认"位置.
    跳过 null/空/False/0 这些"默认占位值" (保存时 序列化造成的, 不是用户实际设置).
    """
    applied = []
    for attr, val in cfg.items():
        if attr.startswith("_"):
            continue  # 跳过 _meta
        if attr not in PRESET_SAVE_FLAGS:
            continue
        # JSON 反序列后的 "默认占位": null, "", [], 0, 0.0, False, {} 都跳过 (保留默认)
        if val is None or val == "" or val == [] or val == {} or val == 0 or val == 0.0 or val is False:
            continue
        cur = getattr(args, attr, None)
        is_default = cur is None or cur == "" or cur is False or cur == 0 or cur == 0.0
        if is_default:
            setattr(args, attr, val)
            if isinstance(val, bool):
                applied.append(f"--{attr.replace('_', '-')}")
            elif isinstance(val, list):
                applied.append(f"--{attr.replace('_', '-')}={','.join(map(str, val))}")
            else:
                applied.append(f"--{attr.replace('_', '-')}={val}")
    meta = cfg.get("_meta", {})
    name = meta.get("name", "?")
    print(f"[preset-file] '{name}' 应用 ({len(applied)} 项):", file=sys.stderr)
    if applied:
        print(f"  → {', '.join(applied)}", file=sys.stderr)
    else:
        print(f"  →  (全部参数都是用户显式值, 未覆盖)", file=sys.stderr)


def _override_preset_dir(args) -> None:
    """v4.1: 如果传了 --preset-dir, 临时覆盖全局 PRESET_DIR.
    v5.2.3.2: 用 `global PRESET_DIR` 修改本模块的全局变量 (被 re-export 给 czsc_signals).
    """
    global PRESET_DIR
    if getattr(args, "preset_dir", ""):
        PRESET_DIR = Path(args.preset_dir).expanduser()


# ---------------------------------------------------------------------------
# 9 cmd_preset_* subcommands (public, 不用 _ 前缀)
# ---------------------------------------------------------------------------

def cmd_preset_save(args) -> None:
    """v4.0: 'preset save <name>' 上下文从 scan 调过来, args 是 scan 的 args.
    为了避免重复调用 scan 的所有逻辑, 这个实现依赖 scan 先跑过一次.
    但为了在 preset save 子命令独立可用, 我们需要 args 有所有 scan 参数.
    简便起见: 这个子命令只接受 name, 需要用户提供完整 flag.
    """
    # 实际调用是: scan --save-preset <name> [其他 flags]
    # scan 跑完后 (使用 _save_user_preset) 保存
    # 这里如果用户单独调 preset save, 提示用 scan 子命令
    print(f"[ERROR] 'preset save' 必须从 scan 子命令调用:", file=sys.stderr)
    print(f"  用法: python3 czsc_signals.py scan [flags] --save-preset {args.name}", file=sys.stderr)
    sys.exit(1)


def cmd_preset_list(args) -> None:
    """列出所有自定义 preset."""
    _override_preset_dir(args)
    PRESET_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(PRESET_DIR.glob("*.json"))
    if not files:
        print(f"(空) — 预设目录: {PRESET_DIR}")
        print(f"\n创建第一个 preset:")
        print(f"  python3 czsc_signals.py scan --watchlist xxx --industry 银行 --save-preset my_bank")
        return
    # v4.3: --tag 过滤 (OR 逻辑, 含任一 tag 即匹配)
    tag_filter = getattr(args, "tag", "") or ""
    if tag_filter:
        wanted_tags = {t.strip() for t in tag_filter.split(",") if t.strip()}
    else:
        wanted_tags = set()
    # 读取所有 preset
    rows = []
    for f in files:
        try:
            with open(f, "r", encoding="utf-8") as fp:
                cfg = json.load(fp)
            meta = cfg.get("_meta", {})
            tags = set(meta.get("tags", []))
            rows.append((f.stem, meta.get("saved_at", "?"), tags))
        except Exception as e:
            rows.append((f.stem, f"读取失败: {e}", set()))
    # tag 过滤
    if wanted_tags:
        rows = [(n, t, tags) for n, t, tags in rows if tags & wanted_tags]
    if not rows:
        print(f"(无匹配 — tag: {tag_filter})")
        return
    header = f"=== 自定义 preset ({len(rows)}/{len(files)} 个"
    if wanted_tags:
        header += f", tag={tag_filter}"
    header += f") — {PRESET_DIR} ===\n"
    print(header)
    for name, saved_at, tags in rows:
        line = f"  📦 {name}  (保存于 {saved_at})"
        if tags:
            line += f"  [tags: {', '.join(sorted(tags))}]"
        print(line)


def cmd_preset_show(args) -> None:
    """显示 preset 内容 (pretty-print JSON)."""
    _override_preset_dir(args)
    path = PRESET_DIR / f"{args.name}.json"
    if not path.exists():
        print(f"[ERROR] preset 不存在: {args.name} (路径: {path})", file=sys.stderr)
        sys.exit(1)
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        print(json.dumps(cfg, ensure_ascii=False, indent=2))
    except json.JSONDecodeError as e:
        print(f"[ERROR] JSON 解析失败: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_preset_delete(args) -> None:
    """删除 preset."""
    _override_preset_dir(args)
    path = PRESET_DIR / f"{args.name}.json"
    if not path.exists():
        print(f"[ERROR] preset 不存在: {args.name} (路径: {path})", file=sys.stderr)
        sys.exit(1)
    try:
        path.unlink()
        print(f"✓ 已删除: {path}")
    except Exception as e:
        print(f"[ERROR] 删除失败: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_preset_export(args) -> None:
    """v4.1: 导出 preset 到指定路径 (默认 stdout).
    可以发邮件/微信/上传 git repo 给同事/在其他机器加载.
    """
    _override_preset_dir(args)
    src = PRESET_DIR / f"{args.name}.json"
    if not src.exists():
        print(f"[ERROR] preset 不存在: {args.name} (路径: {src})", file=sys.stderr)
        sys.exit(1)
    try:
        with open(src, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"[ERROR] 读取失败: {e}", file=sys.stderr)
        sys.exit(1)
    if args.output:
        # 保存到指定路径
        out_path = Path(args.output).expanduser()
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"✓ 已导出: {args.name} → {out_path}", file=sys.stderr)
        except Exception as e:
            print(f"[ERROR] 写入失败: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # stdout 输出 (适合管道 / 重定向)
        print(content, end="")


def cmd_preset_import(args) -> None:
    """v4.1: 从 JSON 文件导入 preset 到 PRESET_DIR.
    源文件可能来自另一个机器 / 团队 git repo / 邮件附件.
    """
    _override_preset_dir(args)
    src = Path(args.source).expanduser()
    if not src.exists():
        print(f"[ERROR] 源文件不存在: {src}", file=sys.stderr)
        sys.exit(1)
    if not src.is_file():
        print(f"[ERROR] 源路径不是文件: {src}", file=sys.stderr)
        sys.exit(1)
    # 验证 JSON 合法
    try:
        with open(src, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        if not isinstance(cfg, dict):
            raise ValueError("JSON 顶层不是 dict")
    except json.JSONDecodeError as e:
        print(f"[ERROR] 源文件 JSON 解析失败: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] 读取失败: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
    # 写入 PRESET_DIR
    PRESET_DIR.mkdir(parents=True, exist_ok=True)
    dest = PRESET_DIR / f"{args.name}.json"
    if dest.exists():
        print(f"⚠️  覆盖已有 preset: {args.name}", file=sys.stderr)
    try:
        # 加上 _meta.imported 记录来源
        cfg.setdefault("_meta", {})
        cfg["_meta"].update({
            "imported_from": str(src),
            "imported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2, default=str)
        print(f"✓ 已导入: {args.name} ← {src} → {dest}", file=sys.stderr)
    except Exception as e:
        print(f"[ERROR] 写入失败: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_preset_diff(args) -> None:
    """v4.4: 对比两个 preset 的差异 (git diff 风格).
    跳过 _meta (保存时间/源路径等) — 只对比业务参数.
    """
    _override_preset_dir(args)
    # 加载两个 preset
    def _load(name):
        p = PRESET_DIR / f"{name}.json"
        if not p.exists():
            print(f"[ERROR] preset 不存在: {name} (路径: {p})", file=sys.stderr)
            sys.exit(1)
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[ERROR] 读取 {name} 失败: {e}", file=sys.stderr)
            sys.exit(1)
    cfg_a = _load(args.name_a)
    cfg_b = _load(args.name_b)
    # 去掉 _meta (不对比保存时间/源路径)
    params_a = {k: v for k, v in cfg_a.items() if not k.startswith("_")}
    params_b = {k: v for k, v in cfg_b.items() if not k.startswith("_")}
    # 对比
    keys_a = set(params_a.keys())
    keys_b = set(params_b.keys())
    common = keys_a & keys_b
    only_a = keys_a - keys_b
    only_b = keys_b - keys_a
    differ = {k: (params_a[k], params_b[k]) for k in common if params_a[k] != params_b[k]}
    same = sorted(k for k in common if params_a[k] == params_b[k])
    if args.format == "json":
        out = {
            "common_same": {k: params_a[k] for k in same},
            "only_in_a": {k: params_a[k] for k in sorted(only_a)},
            "only_in_b": {k: params_b[k] for k in sorted(only_b)},
            "differ": {k: {"a": a, "b": b} for k, (a, b) in sorted(differ.items())},
            "_meta": {
                "name_a": args.name_a,
                "name_b": args.name_b,
                "compared_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
        }
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    else:  # text
        print(f"=== preset diff: {args.name_a} ↔ {args.name_b} ===\n")
        if not differ and not only_a and not only_b:
            print("✓ 完全相同 (除 _meta 元数据)")
            return
        if same:
            print(f"=== 相同 ({len(same)}) ===")
            for k in same:
                print(f"  {k}: {params_a[k]}")
        if differ:
            print(f"\n=== 差异 ({len(differ)}) ===")
            for k in sorted(differ.keys()):
                a_val, b_val = differ[k]
                print(f"  {k}:")
                print(f"    - {args.name_a}: {a_val}")
                print(f"    + {args.name_b}: {b_val}")
        if only_a:
            print(f"\n=== 仅 {args.name_a} 有 ({len(only_a)}) ===")
            for k in sorted(only_a):
                print(f"  - {k}: {params_a[k]}")
        if only_b:
            print(f"\n=== 仅 {args.name_b} 有 ({len(only_b)}) ===")
            for k in sorted(only_b):
                print(f"  + {k}: {params_b[k]}")


def cmd_preset_merge(args) -> None:
    """v4.5: 合并多个 preset, 后者覆盖前者 (类似 git merge).
    跳过 _meta 字段 — 只合并业务参数.

    例: preset merge base custom_a custom_b --name final
        → final = base + (custom_a 覆盖 base) + (custom_b 覆盖 custom_a)
    """
    _override_preset_dir(args)
    sources = args.sources
    if len(sources) < 2:
        print(f"[ERROR] preset merge 至少需要 2 个源 preset, 当前 {len(sources)}", file=sys.stderr)
        sys.exit(1)
    # 逐个加载并合并
    merged = {}
    source_stats = []  # [(name, contributed_keys)]
    for src_name in sources:
        p = PRESET_DIR / f"{src_name}.json"
        if not p.exists():
            print(f"[ERROR] preset 不存在: {src_name} (路径: {p})", file=sys.stderr)
            sys.exit(1)
        try:
            with open(p, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception as e:
            print(f"[ERROR] 读取 {src_name} 失败: {e}", file=sys.stderr)
            sys.exit(1)
        params = {k: v for k, v in cfg.items() if not k.startswith("_")}
        contributed = set()
        for k, v in params.items():
            if k not in merged:
                contributed.add(k)
            merged[k] = v  # 覆盖
        source_stats.append((src_name, contributed))
    # 保存
    if not args.name.replace("_", "").isalnum():
        print(f"[ERROR] preset 名只能含字母/数字/下划线: {args.name!r}", file=sys.stderr)
        sys.exit(1)
    PRESET_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PRESET_DIR / f"{args.name}.json"
    merged["_meta"] = {
        "name": args.name,
        "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "skill_version": "v4.6",
        "source_cmd": "preset merge",
        "merged_from": sources,  # 记录合并来源 (调试/审计用)
    }
    # v4.5: --preset-tag 打标签
    if args.preset_tag:
        merged["_meta"]["tags"] = [t.strip() for t in args.preset_tag.split(",") if t.strip()]
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2, default=str)
    # 输出 merge 报告
    print(f"✓ 已合并: {args.name} ← {' + '.join(sources)}", file=sys.stderr)
    print(f"  保存: {out_path}", file=sys.stderr)
    print(f"  参数总数: {len([k for k in merged.keys() if not k.startswith('_')])}", file=sys.stderr)
    for src, contributed in source_stats:
        print(f"    {src}: 贡献 {len(contributed)} 个新 key", file=sys.stderr)


def cmd_preset_validate(args) -> None:
    """v4.6: 验证 preset 字段合法性, 检出未知字段.
    适用场景: 手编辑 JSON 后 / 跨版本迁移 / import 外部文件.

    白名单: PRESET_SAVE_FLAGS (17 个已知 scan flag).
    """
    _override_preset_dir(args)
    PRESET_DIR.mkdir(parents=True, exist_ok=True)
    known = set(PRESET_SAVE_FLAGS)
    if args.name:
        targets = [args.name]
    else:
        # 验证所有
        files = sorted(PRESET_DIR.glob("*.json"))
        targets = [f.stem for f in files]
    if not targets:
        print(f"(无 preset 可验证 — 目录: {PRESET_DIR})")
        return
    n_ok = 0
    n_bad = 0
    for name in targets:
        p = PRESET_DIR / f"{name}.json"
        if not p.exists():
            print(f"⚠️  {name}: 不存在")
            n_bad += 1
            continue
        try:
            with open(p, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception as e:
            print(f"✗ {name}: JSON 解析失败 ({e})")
            n_bad += 1
            continue
        # 检查未知字段
        unknown = []
        type_errors = []
        for k, v in cfg.items():
            if k.startswith("_"):
                continue  # _meta 跳过
            if k not in known:
                unknown.append(k)
                continue
            # 粗类型检查
            if k in ("signal", "exclude_keyword") and not isinstance(v, (str, list)):
                type_errors.append(f"{k} (类型: {type(v).__name__}, 期望: str/list)")
            elif k in ("pe_max", "pe_min", "pb_max", "pb_min", "market_cap_min", "turnover_min", "days", "top") and not isinstance(v, (int, float)):
                type_errors.append(f"{k} (类型: {type(v).__name__}, 期望: number)")
            elif k in ("reverse", "show_stats", "exclude_st") and not isinstance(v, bool):
                type_errors.append(f"{k} (类型: {type(v).__name__}, 期望: bool)")
        if not unknown and not type_errors:
            n_params = sum(1 for k in cfg if not k.startswith("_"))
            print(f"✓ {name}: 合法 ({n_params} 个参数)")
            n_ok += 1
        else:
            print(f"✗ {name}: 无效")
            if unknown:
                print(f"  未知字段 ({len(unknown)}): {', '.join(unknown)}")
                print(f"    合法字段: {', '.join(sorted(known))}")
            if type_errors:
                print(f"  类型错误 ({len(type_errors)}):")
                for e in type_errors:
                    print(f"    - {e}")
            n_bad += 1
            if args.fix and unknown:
                # 删未知字段并保存
                for k in unknown:
                    del cfg[k]
                with open(p, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2, default=str)
                print(f"  ✓ 已修复: 删除 {len(unknown)} 个未知字段 → {p}")
    print(f"\n汇总: {n_ok} 合法 / {n_bad} 有问题 / {len(targets)} 总数")
    if n_bad > 0 and not args.fix:
        sys.exit(1)
