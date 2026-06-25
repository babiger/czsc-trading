"""czsc_cli.data — 数据获取 + 过滤 + K 线 cache (v5.2.3 真拆实现).

包含:
  - tushare fetchers (ST/industry/bak_basic, 走 mcporter CLI)
  - filter helpers (industry+pe, market_cap+turnover, ST 过滤)
  - weights helper (_load_weights, 用 czsc_signals.SIGNAL_WEIGHTS 跨域共享)
  - K 线 (fetch + cache, parquet 本地存储)

v5.2.3 真拆: 替代 v5.1 的 __getattr__ lazy 转发, 直接实现在这里.
czsc_signals.py 里这些函数改为 `from czsc_cli.data import ...`, 保持向后兼容 + `is` 关系.

不再导出:
  - PRESET_DIR (v5.2.3 起搬到 czsc_cli.preset, 不再归属 data 域)
"""
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

# v5.2.3.1: SIGNAL_WEIGHTS 移到 data 模块级 (打破与 czsc_signals 的循环 import).
#            czsc_signals.py re-export 这里, 保持 is 关系. scanner 仍用 czsc_signals.SIGNAL_WEIGHTS.
SIGNAL_WEIGHTS = {
    # 核心缠论买卖点 — 4 个
    "一买":   5.0,   # 下跌趋势底背驰转折
    "一卖":   5.0,   # 上涨趋势顶背驰转折
    "三买":   4.0,   # 突破后回踩
    "二买卖": 3.0,   # 双向, 权重中性
    # 辅助验证 — 7 个
    "MACD一买":  1.0,
    "MACD二买":  1.0,
    "MACD背驰":  1.0,
    "TD9":       0.5,
    "双均线":    0.5,
    "支撑压力":  0.5,
    "笔翼二买":  0.5,
}

# 时效加分 (距今越近加权越高)
RECENCY_BONUS = {
    5:   3.0,   # < 5 个交易日
    20:  1.0,   # < 20 个交易日
}


# ---------------------------------------------------------------------------
# 模块级 caches (替代 czsc_signals 里的同名 global)
# ---------------------------------------------------------------------------

_ST_CACHE = {}  # {ts_code: name}
_INDUSTRY_CACHE = {}  # {ts_code: industry_str}
_BAK_BASIC_CACHE = {}  # {ts_code: {pe, pe_ttm, pb, industry, name, ...}}
_BAK_BASIC_DATE = None

CACHE_DIR = Path.home() / ".cache" / "czsc"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# tushare fetchers (走 mcporter CLI, streamable-http)
# ---------------------------------------------------------------------------

def _fetch_st_names_via_tushare() -> dict:
    """通过 mcporter MCP 调用 tushare stock_basic 获取股票名表 (带缓存)
    返回 {ts_code: name}, 如 {"000001.SZ": "平安银行"}
    """
    if _ST_CACHE:
        return _ST_CACHE
    try:
        # mcporter CLI 走 streamable-http 调 tushare stock_basic
        import subprocess
        result = subprocess.run(
            ["mcporter", "call", "tushareMcp.stock_basic",
             "--args", '{"list_status": "L", "fields": ["ts_code", "name", "industry"]}'],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            print(f"[warn] tushare stock_basic 调用失败, ST 过滤跳过: {result.stderr[:100]}",
                  file=sys.stderr)
            return {}
        data = json.loads(result.stdout)
        # mcporter 返回格式可能是 {"data": [...]} 或直接是 [...]
        rows = data.get("data", data) if isinstance(data, dict) else data
        for row in rows:
            if isinstance(row, dict) and "ts_code" in row and "name" in row:
                _ST_CACHE[row["ts_code"]] = row["name"]
        # 顺便缓存 industry 到 _INDUSTRY_CACHE
        for row in rows:
            if isinstance(row, dict) and "ts_code" in row and "industry" in row:
                _INDUSTRY_CACHE[row["ts_code"]] = row["industry"]
    except FileNotFoundError:
        print("[warn] mcporter CLI 未安装, ST 过滤跳过", file=sys.stderr)
    except Exception as e:
        print(f"[warn] tushare stock_basic 异常, ST 过滤跳过: {type(e).__name__}: {str(e)[:80]}",
              file=sys.stderr)
    return _ST_CACHE


def _fetch_industry_via_tushare() -> dict:
    """复用 stock_basic 缓存, 返回 {ts_code: industry}.
    如果 _ST_CACHE 为空会触发一次拉取 (带 industry 字段).
    """
    if not _INDUSTRY_CACHE:
        _fetch_st_names_via_tushare()  # 触发拉取 (同时填 _INDUSTRY_CACHE)
    return _INDUSTRY_CACHE


def _fetch_bak_basic_via_tushare(trade_date: str = None) -> dict:
    """通过 bak_basic 拉全市场每日基础估值, 返回 {ts_code: {pe, pe_ttm, pb, industry, name, total_share, turnover_rate}}.
    trade_date 默认取最近一个交易日 (不传则试当日, 不存在则不拉).
    带全局缓存 + 日期检查: 同一天只拉一次.
    """
    global _BAK_BASIC_DATE
    if _BAK_BASIC_CACHE:
        return _BAK_BASIC_CACHE
    try:
        import subprocess
        if not trade_date:
            trade_date = pd.Timestamp.today().strftime("%Y%m%d")
        result = subprocess.run(
            ["mcporter", "call", "tushareMcp.bak_basic",
             "--args", json.dumps({"trade_date": trade_date,
                                    "fields": ["ts_code", "name", "industry", "pe", "pe_ttm", "pb",
                                                "total_share", "turnover_rate", "turnover_rate_f"]})],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            print(f"[warn] tushare bak_basic 调用失败, PE 过滤跳过: {result.stderr[:100]}",
                  file=sys.stderr)
            return {}
        data = json.loads(result.stdout)
        rows = data.get("data", data) if isinstance(data, dict) else data
        for row in rows:
            if isinstance(row, dict) and "ts_code" in row:
                _BAK_BASIC_CACHE[row["ts_code"]] = {
                    "name": row.get("name", ""),
                    "industry": row.get("industry", ""),
                    "pe": float(row.get("pe") or 0),
                    "pe_ttm": float(row.get("pe_ttm") or 0),
                    "pb": float(row.get("pb") or 0),
                    "total_share": float(row.get("total_share") or 0),  # 亿股
                    "turnover_rate": float(row.get("turnover_rate") or 0),  # %
                }
        _BAK_BASIC_DATE = trade_date
        print(f"[bak_basic] 拉取 {len(_BAK_BASIC_CACHE)} 只股 ({trade_date})", file=sys.stderr)
    except FileNotFoundError:
        print("[warn] mcporter CLI 未安装, PE 过滤跳过", file=sys.stderr)
    except Exception as e:
        print(f"[warn] tushare bak_basic 异常, PE 过滤跳过: {type(e).__name__}: {str(e)[:80]}",
              file=sys.stderr)
    return _BAK_BASIC_CACHE


# ---------------------------------------------------------------------------
# filter helpers (拉 K 线前的过滤)
# ---------------------------------------------------------------------------

def _filter_by_industry_pe(stocks: list, industries: list, pe_max: float = None,
                            pe_min: float = None, pb_max: float = None,
                            exclude_keywords: list = None) -> tuple:
    """按 industry 关键字 (包含匹配) + PE/PB 范围 + v3.8 名字关键字排除 过滤股池 (拉 K 线前).
    返回 (kept, filtered_out_with_reason).
    industries: list of keyword, e.g. ['银行', '消费'], 匹配 industry 含任一关键字 (or 逻辑)
    pe_max/pe_min: 静态 PE 阈值, PE=0 (亏损) 永远过滤
    pb_max: PB 上限
    exclude_keywords: list of name keyword, e.g. ['北交所', '创业板'], 名字含任一关键字的股过滤掉
    """
    if not industries and pe_max is None and pe_min is None and pb_max is None and not exclude_keywords:
        return list(stocks), []
    bak = _fetch_bak_basic_via_tushare()
    if not bak and (industries or pe_max is not None or pe_min is not None or pb_max is not None):
        return list(stocks), []
    kept, dropped = [], []
    for s in stocks:
        info = bak.get(s)
        if not info:
            kept.append(s)  # 查不到的股保留 (可能是北交所/退市)
            continue
        # industry 过滤
        if industries:
            industry = info.get("industry", "") or ""
            if not any(kw in industry for kw in industries):
                dropped.append((s, info.get("name", ""), f"industry={industry}"))
                continue
        # v3.8: 名字关键字排除 (去掉名字中间空格, 避免 "五 粮 液" vs "五粮液")
        if exclude_keywords:
            name = info.get("name", "") or ""
            name_norm = name.replace(" ", "")
            hit = [kw for kw in exclude_keywords if kw in name_norm]
            if hit:
                dropped.append((s, name, f"含关键字={hit}"))
                continue
        # PE 过滤 (0 = 亏损, 永远过滤)
        pe = info.get("pe", 0)
        if pe_max is not None:
            if pe == 0:
                dropped.append((s, info.get("name", ""), "PE=0亏损"))
                continue
            if pe > pe_max:
                dropped.append((s, info.get("name", ""), f"PE={pe:.1f}>{pe_max}"))
                continue
        if pe_min is not None:
            if pe != 0 and pe < pe_min:
                dropped.append((s, info.get("name", ""), f"PE={pe:.1f}<{pe_min}"))
                continue
        # PB 过滤
        if pb_max is not None:
            pb = info.get("pb", 0)
            if pb > pb_max:
                dropped.append((s, info.get("name", ""), f"PB={pb:.2f}>{pb_max}"))
                continue
        kept.append(s)
    return kept, dropped


def _filter_by_market_cap_turnover(detail: dict, market_cap_min: float = None,
                                     turnover_min: float = None) -> tuple:
    """按市值 + 换手率过滤 (需要 _score_one_stock 后的 detail, 含 last_close + total_mv + turnover_rate).
    返回 (filtered_detail, dropped_with_reason).
    filtered_detail: 保留的 detail 子集
    dropped: [(ts_code, name, reason), ...]
    """
    if market_cap_min is None and turnover_min is None:
        return detail, []
    bak = _fetch_bak_basic_via_tushare()
    if not bak:
        return detail, []
    kept, dropped = {}, []
    for ts_code, r in detail.items():
        info = bak.get(ts_code, {})
        name = info.get("name", "")
        # 市值过滤 (用 detail.total_mv 避免重复计算)
        if market_cap_min is not None:
            mv = r.get("total_mv", 0)
            if mv == 0:
                dropped.append((ts_code, name, "市值数据不足"))
                continue
            if mv < market_cap_min:
                dropped.append((ts_code, name, f"市值={mv:.0f}亿<{market_cap_min}亿"))
                continue
        # 换手率过滤 (从 detail.turnover_rate, 本地计算不用 API)
        if turnover_min is not None:
            tr = r.get("turnover_rate", 0)
            if tr < turnover_min:
                dropped.append((ts_code, name, f"换手={tr:.2f}%<{turnover_min}%"))
                continue
        kept[ts_code] = r
    return kept, dropped


def _is_st_or_delisted(name: str) -> bool:
    """检查股票名是否为 ST/*ST/退市/退 (打上风险警示或已退)"""
    if not name:
        return False
    upper = name.upper()
    return ("ST" in upper or "退" in name or "*ST" in upper)


def _filter_stocks(stocks: list, exclude_st: bool) -> tuple:
    """根据 exclude_st 过滤股池, 返回 (保留, 被过滤)"""
    if not exclude_st:
        return list(stocks), []
    name_map = _fetch_st_names_via_tushare()
    if not name_map:
        return list(stocks), []
    kept, filtered = [], []
    for s in stocks:
        name = name_map.get(s, "")
        if _is_st_or_delisted(name):
            filtered.append((s, name))
        else:
            kept.append(s)
    return kept, filtered


# ---------------------------------------------------------------------------
# weights helper (跨域: scanner._score_one_stock 也用 SIGNAL_WEIGHTS)
# ---------------------------------------------------------------------------

def _load_weights(weights_file: str) -> dict:
    """从 JSON 文件加载权重覆盖, 格式: {"一买": 6, "三买": 4}
    返回合并后的权重 dict (未覆盖的保留默认)
    """
    if not weights_file:
        return dict(SIGNAL_WEIGHTS)
    path = Path(weights_file)
    if not path.exists():
        raise FileNotFoundError(f"权重文件不存在: {weights_file}")
    try:
        user_w = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"权重文件 JSON 格式错: {e}")
    # 合并 (用户覆盖默认)
    merged = dict(SIGNAL_WEIGHTS)
    unknown = []
    for k, v in user_w.items():
        if k not in SIGNAL_WEIGHTS:
            unknown.append(k)
        merged[k] = float(v)
    if unknown:
        print(f"[warn] 权重文件含未知信号别名 (忽略): {unknown}", file=sys.stderr)
    return merged


# ---------------------------------------------------------------------------
# K 线: tushare primary → 腾讯 fallback, parquet 本地缓存
# ---------------------------------------------------------------------------

def fetch_klines_for_signals(ts_code: str, days: int = 500, use_cache: bool = True):
    """拉日 K 线, 返回 czsc 标准 bars 列表 (不是 DataFrame)

    优先级 (v5.4+):
    1. 本地 SQLite DB (~/.openclaw/data/czsc_market.db) — 最快, 无网络
    2. 本地 parquet 缓存 (use_cache=True) — 快, 无网络
    3. tushare (有成交额) — 慢, 限流
    4. 腾讯 ifzq (无成交额) — 慢, 免费
    """
    from datetime import datetime, timedelta
    from . import db_reader

    # === 0. 优先本地 DB (v5.4+) ===
    if db_reader.is_db_available():
        try:
            end_str = datetime.now().strftime("%Y%m%d")
            start_dt = datetime.now() - timedelta(days=int(days * 1.5))
            start_str = start_dt.strftime("%Y%m%d")
            rows = db_reader.get_daily_bars(ts_code, start_str, end_str, adj="qfq")
            if rows and len(rows) >= days * 0.8:  # 80% 数据量才信
                import pandas as pd
                from czsc import format_standard_kline
                symbol = ts_code.split(".")[0]
                df_rows = []
                for r in rows:
                    df_rows.append({
                        "dt": r["trade_date"],
                        "symbol": symbol,
                        "open": float(r["open"] or 0),
                        "close": float(r["close"] or 0),
                        "high": float(r["high"] or 0),
                        "low": float(r["low"] or 0),
                        "vol": float(r["vol"] or 0) * 100,  # 手 → 股
                        "amount": float(r.get("amount", 0) or 0) * 1000,  # 千 → 元
                    })
                df = pd.DataFrame(df_rows)
                df["dt"] = pd.to_datetime(df["dt"])
                df = df.tail(days).reset_index(drop=True)
                bars = format_standard_kline(df, freq="日线")
                return bars, df
        except Exception as e:
            print(f"[fetch] DB 失败, fallback 缓存/网络: {e}", file=sys.stderr)

    # === 1. 本地缓存 ===
    if use_cache:
        return fetch_klines_with_cache(ts_code, days=days, use_cache=True)

    # === 2. 走网络 ===
    return _fetch_klines_uncached(ts_code, days=days)


def _fetch_klines_uncached(ts_code: str, days: int = 500):
    import subprocess
    import json
    import pandas as pd
    from czsc import format_standard_kline

    symbol, market = ts_code.split(".")
    ts_code_full = ts_code

    # === 1. 优先 tushare (前复权) ===
    try:
        from datetime import datetime, timedelta
        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=int(days * 1.5))
        start_str = start_dt.strftime("%Y%m%d")
        end_str = end_dt.strftime("%Y%m%d")

        # 拿日 K (不复权)
        proc = subprocess.run(
            ["mcporter", "call", "tushareMcp.daily",
             "--ts_code", ts_code_full,
             "--start_date", start_str, "--end_date", end_str],
            capture_output=True, text=True, timeout=30)
        if proc.returncode == 0 and proc.stdout.strip():
            data = json.loads(proc.stdout)
            if data and len(data) > 0:
                # 拿复权因子, 算前复权
                af_proc = subprocess.run(
                    ["mcporter", "call", "tushareMcp.adj_factor",
                     "--ts_code", ts_code_full,
                     "--start_date", start_str, "--end_date", end_str],
                    capture_output=True, text=True, timeout=30)
                af_map = {}
                if af_proc.returncode == 0 and af_proc.stdout.strip():
                    af_data = json.loads(af_proc.stdout)
                    for a in af_data:
                        af_map[a["trade_date"]] = float(a["adj_factor"])

                # 升序
                data = sorted(data, key=lambda x: x["trade_date"])

                # 计算前复权 (用最近复权因子作为基准)
                latest_af = max(af_map.values()) if af_map else 1.0
                rows = []
                for k in data:
                    af = af_map.get(k["trade_date"], latest_af)
                    factor = af / latest_af if latest_af else 1.0
                    rows.append({
                        "dt": k["trade_date"],
                        "symbol": symbol,
                        "open": float(k["open"]) * factor,
                        "close": float(k["close"]) * factor,
                        "high": float(k["high"]) * factor,
                        "low": float(k["low"]) * factor,
                        # tushare vol 单位手 → 股 (×100); amount 千元 → 元 (×1000)
                        "vol": float(k["vol"]) * 100,
                        "amount": float(k.get("amount", 0)) * 1000,
                    })
                df = pd.DataFrame(rows)
                df["dt"] = pd.to_datetime(df["dt"])
                df = df.tail(days).reset_index(drop=True)
                bars = format_standard_kline(df, freq="日线")
                return bars, df
    except Exception as e:
        print(f"[fetch] tushare 失败, fallback 腾讯: {e}", file=sys.stderr)

    # === 2. Fallback 腾讯 ifzq ===
    import requests
    secid = f"{market.lower()}{symbol}"
    req_days = min(int(days * 1.5), 1000)
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={secid},day,,,{req_days},qfq"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://gu.qq.com/",
    }
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    klines = data["data"].get(secid, {}).get("qfqday") or data["data"].get(secid, {}).get("day")
    if not klines:
        raise ValueError(f"empty klines: {ts_code}")

    rows = []
    for k in klines:
        rows.append({
            "dt": k[0], "symbol": symbol,
            "open": float(k[1]), "close": float(k[2]),
            "high": float(k[3]), "low": float(k[4]),
            "vol": float(k[5]) * 100, "amount": 0.0,
        })
    df = pd.DataFrame(rows)
    df["dt"] = pd.to_datetime(df["dt"])
    df = df.tail(days).reset_index(drop=True)
    bars = format_standard_kline(df, freq="日线")
    return bars, df


# ---------------------------------------------------------------------------
# Cache helpers (parquet 本地缓存)
# ---------------------------------------------------------------------------

def _cache_path(ts_code: str) -> Path:
    """缓存文件路径"""
    return CACHE_DIR / f"{ts_code.replace('.', '_')}.parquet"


def _load_cache(ts_code: str):
    """读缓存, 不存在返回空 DataFrame"""
    import pandas as pd
    path = _cache_path(ts_code)
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(path)
    except Exception as e:
        print(f"[cache] 读失败 {path}: {e}", file=sys.stderr)
        return pd.DataFrame()


def _save_cache(ts_code: str, df):
    """写缓存"""
    path = _cache_path(ts_code)
    try:
        df.to_parquet(path, index=False)
    except Exception as e:
        print(f"[cache] 写失败 {path}: {e}", file=sys.stderr)


def fetch_klines_with_cache(ts_code: str, days: int = 500, use_cache: bool = True):
    """拉日 K 线 (带本地缓存)

    流程:
        1. 读缓存 → 命中 → 找最早日期
        2. 缺多少天就增量拉多少 (1.5x 余量)
        3. tushare primary → 腾讯 fallback
        4. 合并去重 → 写回缓存 → 返回
    """
    import pandas as pd
    from czsc import format_standard_kline

    cached = _load_cache(ts_code) if use_cache else pd.DataFrame()

    if not cached.empty and len(cached) >= days:
        # 缓存够用
        df = cached.tail(days).copy()
        df["dt"] = pd.to_datetime(df["dt"])
        df = df.reset_index(drop=True)
        bars = format_standard_kline(df, freq="日线")
        return bars, df

    # 需要增量拉
    if cached.empty:
        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=int(days * 1.5))
    else:
        # 缓存最早日期前再拉 1.2x 余量
        cached["dt"] = pd.to_datetime(cached["dt"])
        earliest = cached["dt"].min()
        start_dt = earliest - timedelta(days=int((days - len(cached)) * 1.5) + 30)
        end_dt = datetime.now()
    start_str = start_dt.strftime("%Y%m%d")
    end_str = end_dt.strftime("%Y%m%d")

    # 调原 fetch (不递归)
    print(f"[cache] 增量拉 {ts_code} {start_str} → {end_str} (cache {len(cached)}/{days})", file=sys.stderr)
    _, new_df = _fetch_klines_uncached(ts_code, days=int((end_dt - start_dt).days))

    if new_df.empty:
        return None, new_df

    # 合并
    if cached.empty:
        merged = new_df
    else:
        merged = pd.concat([cached, new_df], ignore_index=True)
        merged["dt"] = pd.to_datetime(merged["dt"])
        merged = merged.drop_duplicates(subset=["dt"], keep="last").sort_values("dt").reset_index(drop=True)

    # 写回缓存
    if use_cache:
        _save_cache(ts_code, merged)

    # 截取
    df = merged.tail(days).copy()
    df["dt"] = pd.to_datetime(df["dt"])
    df = df.reset_index(drop=True)
    bars = format_standard_kline(df, freq="日线")
    return bars, df
