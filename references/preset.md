# preset 模块详细参考

> v5.2.2: 本文档是从 SKILL.md "## 模块参考"章节拆出的独立 chapter. 用户查阅 preset 模块 API 时按需读 references/preset.md..
> 原始行号: SKILL.md L2221-L2269, v5.2.3 真拆完成 commit 505ca07 后.

---

### preset 模块

**路径**: `skills/czsc-trading/czsc_cli/preset.py` (53 行)

**exports** (14 项):

| 名字 | 用途 |
|---|---|
| `_save_user_preset(name, args)` | 保存自定义 preset 到 `~/.czsc-presets/<name>.json` |
| `_load_user_preset(path)` | 从 JSON 文件加载 (返回 dict) |
| `_apply_user_preset(args)` | 合并用户预设到 args (用户显式 flag 不覆盖) |
| `_override_preset_dir(args)` | 改全局 PRESET_DIR (--preset-dir flag) |
| `PRESET_DIR` | 全局预设存储路径 |
| `cmd_preset_save` | `preset save` 子命令 |
| `cmd_preset_list` | `preset list` 子命令 |
| `cmd_preset_show` | `preset show` 子命令 |
| `cmd_preset_delete` | `preset delete` 子命令 |
| `cmd_preset_export` | `preset export` 子命令 |
| `cmd_preset_import` | `preset import` 子命令 |
| `cmd_preset_diff` | `preset diff` 子命令 |
| `cmd_preset_merge` | `preset merge` 子命令 |
| `cmd_preset_validate` | `preset validate` 子命令 |

**典型用法**:
```bash
# CLI
python3 -m czsc_cli preset list                     # 列出所有预设
python3 -m czsc_cli preset show my_bank             # 查看预设详情
python3 -m czsc_cli preset delete my_bank           # 删除
python3 -m czsc_cli preset validate my_bank         # 验证
python3 -m czsc_cli preset export my_bank ./out.json # 导出
python3 -m czsc_cli preset import friend_preset.json # 导入
```

**存储位置**: `~/.czsc-presets/<name>.json` (可被环境变量 `CZSC_PRESET_DIR` 覆盖)

**测试覆盖** (v5.2.1, `tests/test_preset.py`, 11 tests):
- ✅ 模块结构: 14 exports, 全部 8 子命令
- ✅ lazy 转发: cmd_preset_save/list/validate is 原函数
- ✅ PRESET_DIR 类型 + 跨模块共享
- ✅ `_override_preset_dir` 函数存在

**已知坑**:
- `PRESET_DIR` 在模块 load 时 fix — 改环境变量后需重启进程
- 预设文件是普通 JSON, 手动编辑可能破坏格式 → 用 `validate` 子命令
- v3.9 设计的 `--preset value` 让非显式 flag 被覆盖, 但**用户显式传的 flag (非 None) 不覆盖**

---

**章节目录**:
- 上一节: [data.md](data.md)
- 回到索引: [SKILL.md 模块参考](../SKILL.md#模块参考-module-reference)
- 下一节: [batch.md](batch.md)
