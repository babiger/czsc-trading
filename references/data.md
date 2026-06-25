# data 模块详细参考

> v5.2.2: 本文档是从 SKILL.md "## 模块参考"章节拆出的独立 chapter. 用户查阅 data 模块 API 时按需读 references/data.md..
> 原始行号: SKILL.md L2165-L2220, v5.2.3 真拆完成 commit 505ca07 后.

---

### data 模块

**路径**: `skills/czsc-trading/czsc_cli/data.py` (65 行)

**exports** (15 项):

| 名字 | 类型 | 用途 | 依赖外部 API |
|---|---|---|---|
| `_fetch_st_names_via_tushare` | 函数 | 拉取全市场股票名 (用于 ST 过滤) | ✅ tushare |
| `_fetch_industry_via_tushare` | 函数 | 拉取行业分类 (用于行业筛选) | ✅ tushare |
| `_fetch_bak_basic_via_tushare` | 函数 | 拉取备用基础数据 (PE/PB/市值) | ✅ tushare |
| `_filter_by_industry_pe` | 函数 | 按行业 + PE 过滤股池 | ❌ (可选) |
| `_filter_by_market_cap_turnover` | 函数 | 按市值 + 换手率过滤 | ❌ (可选) |
| `_is_st_or_delisted` | 函数 | 检查股票名是否 ST/退市 | ❌ **纯函数** |
| `_filter_stocks` | 函数 | 综合过滤 (tushare + ST 检查) | ✅ tushare |
| `_load_weights` | 函数 | 从 YAML 加载权重配置 | ⚠️ 文件 IO |
| `fetch_klines_for_signals` | 函数 | 拉取 K 线数据 (自动 clamp 1000 天) | ✅ 腾讯 ifzq API |
| `_fetch_klines_uncached` | 函数 | 无缓存拉取 K 线 | ✅ 腾讯 ifzq API |
| `fetch_klines_with_cache` | 函数 | 带 parquet 缓存的 K 线拉取 | ✅ 腾讯 ifzq API + 磁盘 |
| `_cache_path` | 函数 | parquet 缓存路径生成 | ❌ **纯函数** |
| `_load_cache` | 函数 | 从磁盘加载 parquet 缓存 | ⚠️ 磁盘读取 |
| `_save_cache` | 函数 | 保存 K 线数据到 parquet | ⚠️ 磁盘写入 |
| `PRESET_DIR` | `Path` | 全局预设存储路径 (环境变量 `CZSC_PRESET_DIR`) | — |

**纯函数** (适合单测, 不依赖外部 API):
- `_is_st_or_delisted(name: str) → bool` — 大小写敏感, 识别 `ST`/`*ST`/`退`
- `_cache_path(ts_code: str) → Path` — 格式 `~/.czsc-cache/<ts_code>.parquet`

**典型用法**:
```python
from czsc_cli.data import _is_st_or_delisted, fetch_klines_with_cache

# ST check
name = tushare_name_map.get("000001.SZ", "")
if _is_st_or_delisted(name):
    print(f"⚠️ ST 或退市: {name}")

# 带缓存的 K 线拉取 (高效)
df = fetch_klines_with_cache("600519.SH", days=365, freq="日线")
```

**测试覆盖** (v5.2.1, `tests/test_data.py`, 15 tests):
- ✅ 模块结构: 15 exports, 核心 API 都在
- ✅ lazy `__getattr__` 转发 → 函数是原函数 (`is`)
- ✅ `_is_st_or_delisted` 全覆盖 (正常/ST/*ST/退市/空/None)
- ✅ `_cache_path` 格式验证 (parquet 后缀, 不同 code 不同路径)
- ✅ `PRESET_DIR` 跨模块共享
- ✅ 未知属性 raise `AttributeError`

**已知坑**:
- `fetch_klines_for_signals` 自动 clamp 到 1000 天 (腾讯 API 限制), 超过返回空
- tushare 调用建议缓存在 `~/.czsc-cache/` 避免高频请求
- K 线 parquet 缓存不自动过期 — 需手动 `rm -rf ~/.czsc-cache/` 清

---

**章节目录**:
- 回到索引: [SKILL.md 模块参考](../SKILL.md#模块参考-module-reference)
- 下一节: [preset.md](preset.md)
