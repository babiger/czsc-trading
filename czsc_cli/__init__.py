#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""czsc_cli v5.0 — 缠论信号检测包.

这是 v5.0 重构的入口. v5.0 阶段保持向后兼容:
  - 旧: python3 scripts/czsc_signals.py scan [flags]
  - 新: python3 -m czsc_cli scan [flags]

名字说明: 命名为 czsc_cli 而非 czsc 是为了避免与第三方 czsc 包的命名空间冲突
(原 czsc._native.generate_czsc_signals 是第三方缠论库).

逻辑仍在 scripts/czsc_signals.py, 这里只做 subcommand 分发 + 兼容 wrapper.
真正拆分到 czsc_cli/scanner.py / preset.py / batch.py / slack.py 是 v5.1+ 计划.

用法:
  python3 -m czsc_cli scan --watchlist wl.txt --top 5
  python3 -m czsc_cli preset list
  python3 -m czsc_cli preset save my_bank --industry 银行 --pe-max 15
  python3 -m czsc_cli --help
"""
from .cli import main

__version__ = "5.2.1"
__all__ = ["main"]
