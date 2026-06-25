"""pytest 配置 — 让 tests/ 能 import czsc_cli 和 czsc_signals.

v5.2.1: 单测基础设施. 不依赖外部 API (tushare/腾讯), 只测纯函数 + 模块结构.
"""
import sys
from pathlib import Path

# 把 scripts/ 加进 sys.path 让 czsc_signals 能被 import (跟 czsc_cli 包的做法一致)
SKILL_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# 把 skill 根目录加进 sys.path 让 `import czsc_cli` 找到包
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))