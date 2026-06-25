#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""czsc v5.0 CLI 入口 — 把 subcommand 分发给 scripts.czsc_signals.main.

v5.0 阶段不重写主逻辑, 只暴露 subcommand 入口.
真正拆分 scanner/preset/batch 是 v5.1+ 计划.
"""
import sys
from pathlib import Path

# 把 scripts/ 加进 sys.path 让 scripts.czsc_signals 可 import
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))


def main() -> int:
    """v5.0: 转发到 scripts.czsc_signals.main()."""
    try:
        from czsc_signals import main as _main
    except ImportError as e:
        print(f"[czsc v5.0] ✗ 无法 import scripts.czsc_signals: {e}", file=sys.stderr)
        print(f"[czsc v5.0] 提示: 确认 {Path(__file__).parent.parent}/scripts/czsc_signals.py 存在", file=sys.stderr)
        return 1
    _main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
